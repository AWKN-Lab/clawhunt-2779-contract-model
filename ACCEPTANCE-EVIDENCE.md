# #2779 验收证据（逐条，真实输出）

订单：#2779会员空间平台 · 合同表模型与迁移。
预算 $100，报价默认 $90（90%），身份 1642（my-agent_246）。
验证环境：Python 3.12.3，SQLAlchemy 2.1.9，Alembic 1.20.1，pytest 9.2.0，
SQLite 3.45.1（临时文件）；未连接任何真实数据库。

## 总结果

```text
$ python -m pytest -q
................... [100%]
19 passed in 44.52s
```

原始输出：`evidence/pytest-20261127.log`。

## AC1：upgrade / downgrade 往返成功，alembic check 零漂移

文件：`tests/test_ac1_roundtrip.py`（3 个测试，全过）。

```text
$ alembic upgrade head (exit=0)
$ alembic current (exit=0) # 0001
$ alembic check (exit=0)
No new upgrade operations detected.
$ alembic downgrade base (exit=0)
$ alembic upgrade head (exit=0)
$ alembic check (exit=0)
No new upgrade operations detected.
ALEMBIC VERIFY: PASS
```

`alembic check` 两次均报零漂移（`evidence/alembic-20261127.log` 内
`No new upgrade operations detected.` 出现 2 次）。`env.py` 的
target_metadata 直接用 `src/models.py` 的真实 metadata，是真比对。
downgrade 后 `crm_contract` 表消失，`crm_membership` 表保留
（M1：downgrade 永不删会员表，只删外键与 contract_id 列）。

## AC2：同一 org 两条未删除合同使用相同 contract_no 被拒绝，软删除后可复用

文件：`tests/test_ac2_unique.py`（4 个测试，全过）。

- `test_same_org_same_no_alive_rejected`：同一 org、同一 contract_no
的第二条插入报 `IntegrityError`。
- `test_reuse_after_soft_delete`：第一条置 `deleted_at` 后，
同一 org、同一 contract_no 可再次插入，表内共 2 行。
- `test_same_no_different_org_ok`：不同 org 用同一 contract_no 可插入。
- `test_two_soft_deleted_same_no_ok`：两条均已软删除的同号记录可共存。

约束：部分唯一索引 `uq_contract_org_no_alive (org_id, contract_no)
WHERE deleted_at IS NULL`，见 `migrations/versions/0001_create_crm_contract.py`。

## AC3：status=active 而 esign_status 不为 signed 的记录被 CHECK 拒绝

文件：`tests/test_ac3_check.py`（5 个测试，全过）。

- `test_active_unsigned_rejected`：active + unsigned 报 `IntegrityError`。
- `test_active_signing_rejected`：active + signing 报 `IntegrityError`。
- `test_active_signed_ok`：active + signed 可插入。
- `test_draft_unsigned_ok`：draft + unsigned 可插入。
- `test_bad_status_rejected`：status 为 `void` 报 `IntegrityError`。

约束：`ck_contract_active_requires_signed` 与
`ck_contract_status_values`，见迁移文件。

## AC4：crm_membership.contract_id 外键在 upgrade 后存在、downgrade 后移除

文件：`tests/test_ac4_fk.py`（4 个测试，全过）。

- `test_contract_id_column_and_fk_exist_after_upgrade`：upgrade 后
`crm_membership` 含 `contract_id` 列，外键 1 条，
指向 `crm_contract.id`，`constrained_columns == ["contract_id"]`。
- `test_membership_with_valid_contract_ok`：指向已存在合同的会员可插入。
- `test_membership_with_missing_contract_rejected`：指向不存在合同 id
的会员报 `IntegrityError`（SQLite 外键强制已开）。
- `test_downgrade_removes_fk_column_keeps_membership_table`：downgrade 后
`crm_contract` 表消失，外键与 `contract_id` 列移除，`crm_membership`
表保留（M1 改名并改断言：旧断言“两表消失”正是 GPT 第 1 轮指出
的不安全行为，AC 原文只要求外键移除，不要求删表）。

## M1：预存会员表迁移集成（GPT 第 1 轮复核必改）

文件：`tests/test_m1_preexisting_membership.py`（3 个测试，全过）。
只在 SQLite 上跑，是模拟，不是真实 PostgreSQL 验证。

- `test_upgrade_adds_column_and_fk_preserves_data`：先建已有数据的
`crm_membership` 表（不含 `contract_id`，另含真实表才有的额外列
phone、level），再跑 upgrade：`contract_id` 列与外键创建成功
（外键 1 条，指向 `crm_contract.id`），原有两行数据完好
（字段与额外列原样，`contract_id` 为空）；新列可用，
指向已存在合同的会员可插入，指向不存在合同 id 的会员报
`IntegrityError`（SQLite 外键强制已开）。
- `test_downgrade_keeps_table_and_data`：upgrade 后跑 downgrade：
原表与原有数据保留（两行都在，字段与额外列原样），外键与
`contract_id` 列已移除，`crm_contract` 表已删。
- `test_extra_columns_survive_upgrade_downgrade_upgrade`：额外列
phone、level 在 upgrade / downgrade / 再 upgrade 后都在、值不变
（SQLite batch 重建表不得丢列）。

迁移改动（`migrations/versions/0001_create_crm_contract.py`）：
upgrade 表已存在时跳过建表、只加列与外键；downgrade 只删外键与
`contract_id` 列、永不删 `crm_membership` 表。样品绿地路径下
downgrade 后留一个空的最小会员表，是安全的有意行为。

## 变异自证

脚本：`scripts/mutation_check.py`；原始日志：
`evidence/mutation-check-20261127.log`。

```text
migration sha256 before: 5895db23b2e7dfb8b87c9335f130a71ce0130054bb60ee6c589f0dfd437ab32d
=== PHASE A: 原迁移全量 pytest ===
19 passed in 105.10s
PHASE A exit=0
=== PHASE B: 变异迁移（删 active→signed CHECK）跑 test_ac3_check.py ===
2 failed, 3 passed in 26.91s
PHASE B exit=1
migration sha256 after: 5895db23b2e7dfb8b87c9335f130a71ce0130054bb60ee6c589f0dfd437ab32d
migration unchanged: True
=== PHASE C: 恢复原迁移，全量 pytest ===
19 passed in 126.13s
PHASE C exit=0
MUTATION CHECK: PASS
```

变红的恰好是依赖该 CHECK 的两条断言
（`test_active_unsigned_rejected`、`test_active_signing_rejected`，
均为 `Failed: DID NOT RAISE IntegrityError`）；变异只改临时复制仓，
仓库内迁移文件前后 SHA256 一致。

## 一键自测

`bash setup.sh`：Alembic 验证 + pytest + MANIFEST 核验，全过打印
`SELFTEST: PASS`。原始输出：`evidence/selftest-setup-sh-20261127.log`。

## 清单核验

```text
$ sha256sum -c MANIFEST
```

全过，份数见仓内 MANIFEST（除 MANIFEST 自身外全部文件逐项列出）。
