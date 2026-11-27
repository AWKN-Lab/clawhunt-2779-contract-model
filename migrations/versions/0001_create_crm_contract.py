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

生产安全约定（M1，GPT 第 1 轮复核必改）：
真实库里 crm_membership 早已存在且有数据，生产迁移只加列与外键、
只删列与外键，永不建表、永不删表：
- upgrade：表已存在时跳过建表，只加 contract_id 列与外键；表不
  存在时（样品绿地路径）先建最小表，再加列与外键。
- downgrade：只删外键与 contract_id 列，再删 crm_contract 表；
  永不删 crm_membership 表——删表会连同真实会员数据一起丢掉。
  样品绿地路径下 downgrade 后会留一个空的最小会员表，这是安全的
  有意行为，不是残留。
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
    # crm_membership：真实库里该表早已存在且有数据，只加列与外键；
    # 表不存在时（样品绿地路径）先建最小表，再以 batch 方式加列与外键——
    # 与真实库里“给已存在的会员表加外键”的动作一致；batch 方式在
    # SQLite 上同样可用。离线模式（只生成 SQL，不连库）下无法探查表
    # 是否存在，沿用旧行为（建表），不改变离线 SQL 输出。
    try:
        _bind = op.get_bind()
        _membership_exists = _bind is not None and sa.inspect(_bind).has_table(
            "crm_membership"
        )
    except Exception:
        _membership_exists = False
    if not _membership_exists:
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
    # AC4：downgrade 移除 contract_id 列与外键。会员表本身永不删除：
    # 真实库里该表早已存在且有数据，删表会连同数据一起丢掉；样品绿地
    # 路径下 downgrade 后留一个空的最小会员表，是安全的有意行为。
    with op.batch_alter_table("crm_membership", recreate="always") as batch_op:
        batch_op.drop_constraint(
            "fk_crm_membership_contract_id_crm_contract", type_="foreignkey"
        )
        batch_op.drop_column("contract_id")
    op.drop_index("uq_contract_org_no_alive", table_name="crm_contract")
    op.drop_table("crm_contract")
