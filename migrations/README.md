# 迁移说明

`migrations/versions/0001_create_crm_contract.py` 是本样品唯一的迁移：

- 建 `crm_contract` 表（合同编号、名称、对方、金额分、状态、电子签状态、
  签署日、生效/到期日 + 业务表通用字段）。
- 建 `crm_membership` 最小表，再以 batch 方式加 `contract_id` 列与
  指向 `crm_contract.id` 的外键（`ondelete="SET NULL"`）。
- 两条 CHECK 约束与一条部分唯一索引，见迁移文件内注释。

验证只在临时 SQLite 文件上跑（`ALEMBIC_SQL_URL` 指向临时文件），
不连接任何真实数据库：

```bash
export ALEMBIC_SQL_URL="sqlite:////tmp/2779-check.db"
alembic -c migrations/alembic.ini upgrade head
alembic -c migrations/alembic.ini check      # 零漂移
alembic -c migrations/alembic.ini downgrade base
alembic -c migrations/alembic.ini upgrade head
```

一键跑全部验证见 `scripts/verify_alembic.py`，原始输出见
`evidence/alembic-20261127.log`。

落库到现有数据库（PostgreSQL）时：同一份迁移可直接用，
`postgresql_where` 已与 `sqlite_where` 写成同一条件；真实库迁移
须中标后另行授权与对接，本样品不做任何真实库操作。
