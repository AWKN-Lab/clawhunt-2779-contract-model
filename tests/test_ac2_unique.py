"""AC2：同一 org 两条未删除合同使用相同 contract_no 被拒绝，软删除后可复用。

平台验收标准逐字：
2. 同一 org 两条未删除合同使用相同 contract_no 被拒绝，软删除后可复用
   （pytest 通过）
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from tests.conftest import ORG_A, ORG_B, make_contract
from src.models import CrmContract


def test_same_org_same_no_alive_rejected(session):
    session.add(make_contract(org_id=ORG_A, contract_no="HT-2026-0001"))
    session.commit()
    session.add(make_contract(org_id=ORG_A, contract_no="HT-2026-0001"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_reuse_after_soft_delete(session):
    first = make_contract(org_id=ORG_A, contract_no="HT-2026-0002")
    session.add(first)
    session.commit()
    first.deleted_at = datetime.now(timezone.utc)
    session.commit()
    session.add(make_contract(org_id=ORG_A, contract_no="HT-2026-0002"))
    session.commit()
    assert session.query(CrmContract).filter_by(contract_no="HT-2026-0002").count() == 2


def test_same_no_different_org_ok(session):
    session.add(make_contract(org_id=ORG_A, contract_no="HT-2026-0003"))
    session.commit()
    session.add(make_contract(org_id=ORG_B, contract_no="HT-2026-0003"))
    session.commit()
    assert session.query(CrmContract).filter_by(contract_no="HT-2026-0003").count() == 2


def test_two_soft_deleted_same_no_ok(session):
    for _ in range(2):
        row = make_contract(org_id=ORG_A, contract_no="HT-2026-0004")
        row.deleted_at = datetime.now(timezone.utc)
        session.add(row)
        session.commit()
    assert session.query(CrmContract).filter_by(contract_no="HT-2026-0004").count() == 2
