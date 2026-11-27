"""AC3：status=active 而 esign_status 不为 signed 的记录被 CHECK 拒绝。

平台验收标准逐字：
3. status=active 而 esign_status 不为 signed 的记录被 CHECK 拒绝
   （pytest 通过）
"""

import pytest
from sqlalchemy.exc import IntegrityError

from tests.conftest import make_contract
from src.models import CrmContract


def test_active_unsigned_rejected(session):
    session.add(make_contract(status="active", esign_status="unsigned"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_active_signing_rejected(session):
    session.add(make_contract(status="active", esign_status="signing"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_active_signed_ok(session):
    session.add(make_contract(status="active", esign_status="signed"))
    session.commit()
    assert session.query(CrmContract).filter_by(status="active").count() == 1


def test_draft_unsigned_ok(session):
    session.add(make_contract(status="draft", esign_status="unsigned"))
    session.commit()
    assert session.query(CrmContract).filter_by(status="draft").count() == 1


def test_bad_status_rejected(session):
    session.add(make_contract(status="void", esign_status="unsigned"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
