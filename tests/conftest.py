"""pytest 配置：仓根进 sys.path；Alembic 与临时 SQLite 夹具。

每个测试用全新的临时 SQLite 文件：先 ``alembic upgrade head`` 建库，
再用 SQLAlchemy 会话操作；结束时关闭连接并删除文件。
外键用 PRAGMA foreign_keys=ON 打开（SQLite 默认不强制外键），
否则 AC4 的外键拒绝测不到。
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.models import CrmContract, CrmMembership  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALEMBIC_INI = os.path.join(ROOT, "migrations", "alembic.ini")

# 虚构数据：固定 UUID 与合同编号，不含任何真实客户信息。
ORG_A = uuid.UUID("11111111-1111-4111-8111-111111111111")
ORG_B = uuid.UUID("22222222-2222-4222-8222-222222222222")
SITE_A = uuid.UUID("33333333-3333-4333-8333-333333333333")


def run_alembic(*args: str, db_path: str) -> subprocess.CompletedProcess:
    """在仓根跑 alembic CLI，数据库指向临时 SQLite 文件。返回 CompletedProcess。"""
    env = dict(os.environ, ALEMBIC_SQL_URL=f"sqlite:///{db_path}")
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", ALEMBIC_INI, *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def make_contract(
    org_id: uuid.UUID = ORG_A,
    contract_no: str = "HT-2026-0001",
    status: str = "draft",
    esign_status: str = "unsigned",
    amount_cents: int = 100000,
) -> CrmContract:
    """一份虚构合同。对方为虚构公司，金额以分为单位。"""
    return CrmContract(
        org_id=org_id,
        site_id=SITE_A,
        contract_no=contract_no,
        name="虚构会员服务合同",
        counterparty="虚构乙方贸易有限公司",
        counterparty_snapshot=(
            '{"party_a": "虚构甲方科技有限公司", '
            '"party_b": "虚构乙方贸易有限公司", "license_no": "虚构证照 000000"}'
        ),
        amount_cents=amount_cents,
        status=status,
        esign_status=esign_status,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
    )


def make_membership(
    org_id: uuid.UUID = ORG_A,
    contract_id: uuid.UUID | None = None,
) -> CrmMembership:
    return CrmMembership(
        org_id=org_id,
        site_id=SITE_A,
        member_name="虚构会员甲",
        contract_id=contract_id,
    )


@pytest.fixture()
def db_path(tmp_path):
    """全新临时 SQLite 文件路径（文件本身由 alembic 创建）。"""
    return str(tmp_path / "test-2779.db")


@pytest.fixture()
def upgraded_db(db_path):
    """upgrade head 后的数据库路径。"""
    proc = run_alembic("upgrade", "head", db_path=db_path)
    assert proc.returncode == 0, f"alembic upgrade head 失败：\n{proc.stdout}\n{proc.stderr}"
    yield db_path
    run_alembic("downgrade", "base", db_path=db_path)


@pytest.fixture()
def session(upgraded_db):
    """带外键强制的 SQLAlchemy 会话。"""
    engine = create_engine(f"sqlite:///{upgraded_db}")

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    sess = Session(engine)
    yield sess
    sess.close()
    engine.dispose()
