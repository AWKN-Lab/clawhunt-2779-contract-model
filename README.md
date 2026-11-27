# 会员空间平台 · 合同表模型与迁移（#2779 最小样品）

任务 S2-CRM-007 的最小可验证样品：合同表 `crm_contract`（合同编号、
甲乙方快照与电子签状态）+ `crm_membership.contract_id` 外键、
Alembic 迁移 upgrade/downgrade、pytest 覆盖 4 条验收标准。

> 状态：最小样品已完成并通过全部验收（见 `ACCEPTANCE-EVIDENCE.md`）。
> 完整交付以中标和后续授权为前提。本样品只在临时 SQLite 上验证，
> 不连接真实数据库，不做任何真实库操作。

## 验收标准与证据

| # | 验收标准（平台原文） | 证据 |
|---|---|---|
| 1 | upgrade / downgrade 往返成功，alembic check 零漂移 | `tests/test_ac1_roundtrip.py` 3 个测试；`scripts/verify_alembic.py`；`evidence/alembic-20261127.log`（两次 `No new upgrade operations detected.`） |
| 2 | 同一 org 两条未删除合同使用相同 contract_no 被拒绝，软删除后可复用（pytest 通过） | `tests/test_ac2_unique.py` 4 个测试；部分唯一索引 `uq_contract_org_no_alive (org_id, contract_no) WHERE deleted_at IS NULL` |
| 3 | status=active 而 esign_status 不为 signed 的记录被 CHECK 拒绝（pytest 通过） | `tests/test_ac3_check.py` 5 个测试；CHECK `ck_contract_active_requires_signed` |
| 4 | crm_membership.contract_id 外键在 upgrade 后存在、downgrade 后移除（pytest 通过） | `tests/test_ac4_fk.py` 4 个测试；外键 `fk_crm_membership_contract_id_crm_contract`，`ondelete="SET NULL"` |

测试总计 **16 passed**（`python -m pytest -q`，原始输出见
`evidence/pytest-20261127.log`）。

## 快速开始

```bash
pip install -r requirements.txt
bash setup.sh               # 一键自测：Alembic 验证 + pytest + MANIFEST 核验
python -m pytest -q         # 16 passed（也可单独跑）
python scripts/verify_alembic.py   # Alembic 验证：upgrade / check / downgrade / upgrade
python scripts/mutation_check.py   # 变异自证：删 CHECK -> AC3 断言变红，恢复 -> 全绿
```

`setup.sh` 的解释器选择分两条线：`PY` 按版本选（第一个 Python >= 3.11），
`TEST_PY` 按 pytest 选（遍历候选解释器，逐个试 `python -c "import pytest"`，
第一个能过的就是测试解释器）；找不到时先建本地 venv 装依赖再重找，
仍找不到就报错退出，绝不跳过自测。

## 文件结构

```text
README.md                     本文件
ACCEPTANCE-EVIDENCE.md        逐条验收证据（文件路径、测试名、真实输出）
MANIFEST                      SHA256 清单（sha256sum -c 全过）
setup.sh                      一键自测（解释器分两条线选）
requirements.txt              钉死版本：sqlalchemy 2.1.9、alembic 1.20.1、pytest 9.2.0
src/models.py                 SQLAlchemy 模型：crm_contract、crm_membership
migrations/                   Alembic 迁移（0001 建合同表 + 会员表加外键）
scripts/verify_alembic.py     Alembic 验证脚本（只写临时目录）
scripts/mutation_check.py     变异自证脚本（只改临时复制仓）
tests/                        pytest 用例（AC1/AC2/AC3/AC4，共 16 个）
evidence/                     原始日志（pytest、Alembic、变异自证、自测）
```

## 模型要点

- `crm_contract`：contract_no、名称、对方、甲乙方快照（JSON 文本）、
  金额（分，整数）、状态、电子签状态、签署日、生效/到期日；通用字段
  id（UUID）、org_id、site_id、created_at、created_by、updated_at、
  deleted_at（软删除）。
- `status` 只能是 draft / active / terminated（CHECK）。
- `status = 'active'` 时 `esign_status` 必须为 `'signed'`（CHECK）。
- 部分唯一索引 `(org_id, contract_no) WHERE deleted_at IS NULL`：
  同一 org 下未删除合同的编号唯一，软删除后可复用。
- `crm_membership.contract_id` 外键指向 `crm_contract.id`，
  `ondelete="SET NULL"`；可为空。
- DDL 与 `src/models.py` 逐字一致，`alembic check` 用模型 metadata
  做真比对（不是空比对）。

## 已知限制（诚实说明）

- 只在临时 SQLite 上验证（`ALEMBIC_SQL_URL` 指向临时文件）；
  未对任何真实数据库执行过操作；落库到现有 PostgreSQL 须中标后
  另行授权与对接。部分唯一索引的 `postgresql_where` 已与
  `sqlite_where` 写成同一条件，同一份迁移可直接用。
- 样品里的 `crm_membership` 是最小表（只有本单需要的字段），
  由本次迁移创建；downgrade 按精确逆操作一并删表。真实库里
  会员表早已存在，生产迁移只需加列与外键、删列与外键。
- 测试数据全部虚构（虚构公司名、虚构会员名、合同编号 HT-2026-xxxx），
  不出现任何真实客户名称与真实个人信息。
- 金额一律以分存整数；配置与密钥只从环境变量读取
  （`ALEMBIC_SQL_URL`）；不引入向境外发送数据的第三方 SDK。
