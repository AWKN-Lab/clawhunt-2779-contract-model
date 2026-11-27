"""AC4：crm_membership.contract_id 外键在 upgrade 后存在、downgrade 后移除。

平台验收标准逐字：
4. crm_membership.contract_id 外键在 upgrade 后存在、downgrade 后移除
   （pytest 通过）
"""

import uuid

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError

from tests.conftest import make_contract, make_membership, run_alembic
from src.models import CrmMembership


def test_contract_id_column_and_fk_exist_after_upgrade(session, upgraded_db):
    engine = create_engine(f"sqlite:///{upgraded_db}")
    insp = inspect(engine)
    columns = {c["name"] for c in insp.get_columns("crm_membership")}
    assert "contract_id" in columns
    fks = insp.get_foreign_keys("crm_membership")
    assert len(fks) == 1
    fk = fks[0]
    assert fk["referred_table"] == "crm_contract"
    assert fk["constrained_columns"] == ["contract_id"]
    assert fk["referred_columns"] == ["id"]
    engine.dispose()


def test_membership_with_valid_contract_ok(session):
    contract = make_contract(status="active", esign_status="signed")
    session.add(contract)
    session.commit()
    session.add(make_membership(contract_id=contract.id))
    session.commit()
    assert session.query(CrmMembership).filter_by(contract_id=contract.id).count() == 1


def test_membership_with_missing_contract_rejected(session):
    session.add(make_membership(contract_id=uuid.uuid4()))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_downgrade_removes_fk_column_keeps_membership_table(db_path):
    run_alembic("upgrade", "head", db_path=db_path)
    proc = run_alembic("downgrade", "base", db_path=db_path)
    assert proc.returncode == 0, f"downgrade base 失败：\n{proc.stdout}\n{proc.stderr}"
    engine = create_engine(f"sqlite:///{db_path}")
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    # M1（GPT 第 1 轮复核必改）：downgrade 只删外键与 contract_id 列，
    # 会员表本身保留；合同表消失。
    assert "crm_contract" not in tables
    assert "crm_membership" in tables
    columns = {c["name"] for c in insp.get_columns("crm_membership")}
    assert "contract_id" not in columns
    assert insp.get_foreign_keys("crm_membership") == []
    engine.dispose()
