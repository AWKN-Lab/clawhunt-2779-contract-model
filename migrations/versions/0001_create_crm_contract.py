"""create crm_contract + add crm_membership.contract_id FK

Revision ID: 0001
Revises:
Create Date: 2026-11-27

对应平台验收标准（#2779，逐字）：
1. upgrade / downgrade 往返成功，alembic check 零漂移
2. 同一 org 两条未删除合同使用相同 contract_no 被拒绝，软删除后可复用
3. status=active 而 esign_status 不为 signed 的记录被 CHECK 拒绝
4. crm_membership.contract_id 外键在 upgrade 后存在、downgrade 后移除

DDL 与 src/models.py 的定义逐字一致，alembic check 用模型 metadata
做真比对。部分唯一索引在 SQLite 与 PostgreSQL 用同一 WHERE 条件。
"""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crm_contract",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("contract_no", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("counterparty", sa.String(length=128), nullable=False),
        sa.Column("counterparty_snapshot", sa.Text(), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("esign_status", sa.String(length=32), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'terminated')",
            name="ck_contract_status_values",
        ),
        sa.CheckConstraint(
            "(status <> 'active' OR esign_status = 'signed')",
            name="ck_contract_active_requires_signed",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # AC2：部分唯一索引。同一 org 下未删除合同的 contract_no 唯一；
    # 软删除（deleted_at 非空）后可复用。
    op.create_index(
        "uq_contract_org_no_alive",
        "crm_contract",
        ["org_id", "contract_no"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    # crm_membership 在本样品里是最小表：先建表（不含 contract_id），
    # 再以 batch 方式加列与外键——与真实库里“给已存在的会员表加外键”
    # 的动作一致；batch 方式在 SQLite 上同样可用。
    op.create_table(
        "crm_membership",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=False),
        sa.Column("member_name", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("crm_membership", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("contract_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_crm_membership_contract_id_crm_contract",
            "crm_contract",
            ["contract_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    # AC4：downgrade 移除 contract_id 列与外键。样品的最小 crm_membership 表
    # 是本次迁移创建的（独立样品需要它存在），按“downgrade 是 upgrade 的精确
    # 逆操作”一并删表；真实库里会员表早已存在，生产迁移只需删列与外键。
    with op.batch_alter_table("crm_membership", recreate="always") as batch_op:
        batch_op.drop_constraint(
            "fk_crm_membership_contract_id_crm_contract", type_="foreignkey"
        )
        batch_op.drop_column("contract_id")
    op.drop_index("uq_contract_org_no_alive", table_name="crm_contract")
    op.drop_table("crm_contract")
    op.drop_table("crm_membership")
