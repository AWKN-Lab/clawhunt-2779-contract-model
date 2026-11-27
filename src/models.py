"""SQLAlchemy 模型：#2779 合同表模型与迁移。

表：
- ``crm_contract``：合同表。合同编号、名称、对方、金额（分）、状态、
  电子签状态、签署日、生效/到期日；业务表通用字段 id（UUID）、org_id、
  site_id、created_at、created_by、updated_at、deleted_at（软删除）。
- ``crm_membership``：会员表（最小占位，只含本单需要的字段）。
  ``contract_id`` 外键指向 ``crm_contract.id``。

约束（与 migrations/versions/0001_create_crm_contract.py 的 DDL 逐字一致，
``alembic check`` 用这份 metadata 做零漂移比对）：
- ``uq_contract_org_no_alive``：部分唯一索引
  ``(org_id, contract_no) WHERE deleted_at IS NULL`` —— 同一 org 下两条
  未删除合同不得用相同 contract_no；软删除后可复用。
- ``ck_contract_status_values``：``status`` 只能是 draft / active / terminated。
- ``ck_contract_active_requires_signed``：``status = 'active'`` 时
  ``esign_status`` 必须为 ``'signed'``。

测试数据全部虚构，不出现任何真实客户名称与真实个人信息。
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CrmContract(Base):
    """合同表。"""

    __tablename__ = "crm_contract"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'active', 'terminated')",
            name="ck_contract_status_values",
        ),
        CheckConstraint(
            "(status <> 'active' OR esign_status = 'signed')",
            name="ck_contract_active_requires_signed",
        ),
        Index(
            "uq_contract_org_no_alive",
            "org_id",
            "contract_no",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    contract_no: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    counterparty: Mapped[str] = mapped_column(String(128), nullable=False)
    counterparty_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    esign_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unsigned"
    )
    signed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CrmMembership(Base):
    """会员表（最小占位）。本单只要求 contract_id 外键存在与否，其余字段从简。"""

    __tablename__ = "crm_membership"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    member_name: Mapped[str] = mapped_column(String(128), nullable=False)
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("crm_contract.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
