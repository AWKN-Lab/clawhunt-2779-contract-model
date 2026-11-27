#!/usr/bin/env python3
"""变异自证：删掉迁移里的 active→signed CHECK，AC3 断言必须变红。

- A 相：原迁移跑全量 pytest，期望 exit 0。
- B 相：复制整仓到临时目录，只删迁移文件里 ck_contract_active_requires_signed
  那条 CheckConstraint，用复制仓跑 tests/test_ac3_check.py，期望 exit != 0
  （active + unsigned / active + signing 两条拒绝断言应失败，
  因为库里已无 CHECK 约束）。
- C 相：原迁移重跑全量 pytest，期望 exit 0。
- 全程不改仓库内的迁移文件：前后各算一次 SHA256 并打印。
- 本脚本只打印结果；调用方把原始 stdout 存入 evidence/mutation-check-20261127.log。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION = os.path.join(
    ROOT, "migrations", "versions", "0001_create_crm_contract.py"
)

REMOVED_BLOCK = """        sa.CheckConstraint(
            "(status <> 'active' OR esign_status = 'signed')",
            name="ck_contract_active_requires_signed",
        ),
"""


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def run(cmd: list[str], cwd: str) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    before = sha256(MIGRATION)
    print(f"migration sha256 before: {before}")

    print("=== PHASE A: 原迁移全量 pytest ===")
    code_a, out_a = run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT)
    print(out_a, end="")
    print(f"PHASE A exit={code_a}")

    print("=== PHASE B: 变异迁移（删 active→signed CHECK）跑 test_ac3_check.py ===")
    code_b, out_b = -1, ""
    with tempfile.TemporaryDirectory(prefix="2779-mutation-") as tmp:
        copy_root = os.path.join(tmp, "repo")
        shutil.copytree(
            ROOT,
            copy_root,
            ignore=shutil.ignore_patterns(
                ".venv", ".git", "__pycache__", ".pytest_cache", "evidence"
            ),
        )
        mutated = os.path.join(
            copy_root, "migrations", "versions", "0001_create_crm_contract.py"
        )
        with open(mutated, encoding="utf-8") as f:
            text = f.read()
        assert REMOVED_BLOCK in text, "变异目标行在复制仓里找不到，变异未生效"
        with open(mutated, "w", encoding="utf-8") as f:
            f.write(text.replace(REMOVED_BLOCK, ""))
        code_b, out_b = run(
            [sys.executable, "-m", "pytest", "tests/test_ac3_check.py", "-q"],
            cwd=copy_root,
        )
        print(out_b, end="")
        print(f"PHASE B exit={code_b}")

    after = sha256(MIGRATION)
    print(f"migration sha256 after: {after}")
    print(f"migration unchanged: {before == after}")

    print("=== PHASE C: 恢复原迁移，全量 pytest ===")
    code_c, out_c = run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT)
    print(out_c, end="")
    print(f"PHASE C exit={code_c}")

    ok = code_a == 0 and code_b != 0 and code_c == 0 and before == after
    print(f"MUTATION CHECK: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
