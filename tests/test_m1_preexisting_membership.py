"""M1（GPT 第 1 轮复核必改）：针对预存会员表的迁移集成测试。

背景：样品里的 crm_membership 是本次迁移新建的最小表；真实库里会员表
早已存在且有数据，生产迁移只加列与外键，downgrade 绝不能删表删数据。
本文件模拟真实既有表：先建一个已有数据的 crm_membership 表（不含
contract_id，另含两个真实表才有的额外列 phone、level），再跑 upgrade /
downgrade，验证增列、外键创建、原有数据完好、downgrade 不删表不删数据。
只在 SQLite 上跑，是模拟，不是真实 PostgreSQL 验证。
本文件不对模拟表跑 alembic check：模拟的真实表 legitimately 比模型多
phone、level 两列，check 会报漂移，那是模拟表比模型丰富，不是迁移的错。

平台验收标准逐字（相关部分）：
4. crm_membership.contract_id 外键在 upgrade 后存在、downgrade 后移除
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import (
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    Uuid,
    create_engine,
    event,
    inspect,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.conftest import ORG_A, SITE_A, make_contract, run_alembic
from src.models import CrmMembership

# 虚构会员：固定 UUID 与电话，不含任何真实个人信息。
MEMBER_1 = uuid.UUID("44444444-4444-4444-8444-444444444444")
MEMBER_2 = uuid.UUID("55555555-5555-4555-8555-555555555555")
_CREATED = datetime(2026, 1, 1, tzinfo=timezone.utc)

# 模拟的真实既有会员表：与样品最小表相比，多 phone、level 两列，
# 且不含 contract_id（contract_id 由本次迁移来加）。
_PREEXISTING = MetaData()
pre_membership = Table(
    "crm_membership",
    _PREEXISTING,
    Column("id", Uuid, primary_key=True),
    Column("org_id", Uuid, nullable=False),
    Column("site_id", Uuid, nullable=False),
    Column("member_name", String(128), nullable=False),
    Column("phone", String(32), nullable=True),
    Column("level", String(16), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("created_by", String(64), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
)

_EXPECTED_ROWS = [
    ("虚构会员甲", "13800000001", "gold"),
    ("虚构会员乙", "13800000002", "silver"),
]


def _engine(db_path):
    """带外键强制的引擎（SQLite 默认不强制外键，不开测不到 FK 拒绝）。"""
    engine = create_engine(f"sqlite:///{db_path}")

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def _read_core_rows(engine):
    """用 Core 只读原有列（downgrade 后表无 contract_id 列，ORM 查会报错）。"""
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                pre_membership.c.member_name,
                pre_membership.c.phone,
                pre_membership.c.level,
            ).order_by(pre_membership.c.id)  # 按 id 排：按姓名排会受汉字码点序影响（乙 U+4E59 < 甲 U+7532）
        ).all()
    return [(r[0], r[1], r[2]) for r in rows]


@pytest.fixture()
def preexisting_db(db_path):
    """先建一个已有数据的 crm_membership 表（模拟真实既有表），再交测试跑迁移。"""
    engine = _engine(db_path)
    _PREEXISTING.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            pre_membership.insert(),
            [
                {
                    "id": MEMBER_1,
                    "org_id": ORG_A,
                    "site_id": SITE_A,
                    "member_name": "虚构会员甲",
                    "phone": "13800000001",
                    "level": "gold",
                    "created_at": _CREATED,
                    "created_by": "system",
                    "updated_at": _CREATED,
                    "deleted_at": None,
                },
                {
                    "id": MEMBER_2,
                    "org_id": ORG_A,
                    "site_id": SITE_A,
                    "member_name": "虚构会员乙",
                    "phone": "13800000002",
                    "level": "silver",
                    "created_at": _CREATED,
                    "created_by": "system",
                    "updated_at": _CREATED,
                    "deleted_at": None,
                },
            ],
        )
    engine.dispose()
    yield db_path


def test_upgrade_adds_column_and_fk_preserves_data(preexisting_db):
    proc = run_alembic("upgrade", "head", db_path=preexisting_db)
    assert proc.returncode == 0, f"upgrade head 失败：\n{proc.stdout}\n{proc.stderr}"
    engine = _engine(preexisting_db)
    insp = inspect(engine)
    # 增列与外键创建成功。
    columns = {c["name"] for c in insp.get_columns("crm_membership")}
    assert "contract_id" in columns
    fks = insp.get_foreign_keys("crm_membership")
    assert len(fks) == 1
    assert fks[0]["referred_table"] == "crm_contract"
    assert fks[0]["constrained_columns"] == ["contract_id"]
    assert fks[0]["referred_columns"] == ["id"]
    # 原有数据完好：两行都在，字段与额外列原样，contract_id 为空。
    assert _read_core_rows(engine) == _EXPECTED_ROWS
    session = Session(engine)
    members = session.query(CrmMembership).order_by(CrmMembership.id).all()
    assert len(members) == 2
    assert members[0].contract_id is None
    assert members[1].contract_id is None
    # 新列可用：建一份合同并挂上去；指向不存在合同的挂接被外键拒绝。
    contract = make_contract(status="active", esign_status="signed")
    session.add(contract)
    session.commit()
    members[0].contract_id = contract.id
    session.commit()
    assert (
        session.query(CrmMembership).filter_by(contract_id=contract.id).count()
        == 1
    )
    session.add(
        CrmMembership(
            org_id=ORG_A,
            site_id=SITE_A,
            member_name="虚构会员丙",
            contract_id=uuid.uuid4(),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.close()
    engine.dispose()


def test_downgrade_keeps_table_and_data(preexisting_db):
    proc = run_alembic("upgrade", "head", db_path=preexisting_db)
    assert proc.returncode == 0, f"upgrade head 失败：\n{proc.stdout}\n{proc.stderr}"
    proc = run_alembic("downgrade", "base", db_path=preexisting_db)
    assert proc.returncode == 0, f"downgrade base 失败：\n{proc.stdout}\n{proc.stderr}"
    engine = _engine(preexisting_db)
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    # 原表没有被删除，合同表已删；外键与 contract_id 列已移除。
    assert "crm_membership" in tables
    assert "crm_contract" not in tables
    columns = {c["name"] for c in insp.get_columns("crm_membership")}
    assert "contract_id" not in columns
    assert insp.get_foreign_keys("crm_membership") == []
    # 原有数据完好：两行都在，字段与额外列原样。
    assert _read_core_rows(engine) == _EXPECTED_ROWS
    engine.dispose()


def test_extra_columns_survive_upgrade_downgrade_upgrade(preexisting_db):
    # 额外列 phone、level 在 upgrade / downgrade / 再 upgrade 后都在、
    # 值不变：SQLite batch 重建表不得丢列。
    for step in ("head", "base", "head"):
        verb = "upgrade" if step == "head" else "downgrade"
        proc = run_alembic(verb, step, db_path=preexisting_db)
        assert proc.returncode == 0, f"alembic {verb} {step} 失败：\n{proc.stdout}\n{proc.stderr}"
    engine = _engine(preexisting_db)
    insp = inspect(engine)
    columns = {c["name"] for c in insp.get_columns("crm_membership")}
    assert "phone" in columns
    assert "level" in columns
    assert "contract_id" in columns
    assert _read_core_rows(engine) == _EXPECTED_ROWS
    engine.dispose()
