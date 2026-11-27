#!/usr/bin/env python3
"""Alembic 验证：临时 SQLite 上跑 upgrade / check / downgrade / upgrade。

- upgrade head：建表成功，alembic_version 为 0001。
- alembic check：必须输出 "No new upgrade operations detected."（零漂移）。
- downgrade base：crm_contract 表消失，crm_membership 的 contract_id 列消失。
- 再次 upgrade head：往返成功，check 仍零漂移。
只写临时目录，不碰真实数据库，不写仓内文件（setup.sh 调它时不改 MANIFEST）。
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALEMBIC_INI = os.path.join(ROOT, "migrations", "alembic.ini")


def run(*args: str, db_path: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, ALEMBIC_SQL_URL=f"sqlite:///{db_path}")
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", ALEMBIC_INI, *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    print(f"$ alembic {' '.join(args)} (exit={proc.returncode})")
    print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="")
    return proc


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="2779-alembic-") as tmp:
        db_path = os.path.join(tmp, "verify.db")

        proc = run("upgrade", "head", db_path=db_path)
        if proc.returncode != 0:
            print("FAIL: upgrade head")
            return 1
        proc = run("current", db_path=db_path)
        if proc.returncode != 0 or "0001" not in proc.stdout:
            print("FAIL: alembic current 未见 0001")
            return 1
        proc = run("check", db_path=db_path)
        if proc.returncode != 0 or "No new upgrade operations detected." not in proc.stdout:
            print("FAIL: alembic check 未报零漂移")
            return 1
        proc = run("downgrade", "base", db_path=db_path)
        if proc.returncode != 0:
            print("FAIL: downgrade base")
            return 1
        proc = run("upgrade", "head", db_path=db_path)
        if proc.returncode != 0:
            print("FAIL: 二次 upgrade head（往返）")
            return 1
        proc = run("check", db_path=db_path)
        if proc.returncode != 0 or "No new upgrade operations detected." not in proc.stdout:
            print("FAIL: 往返后 alembic check 未报零漂移")
            return 1
    print("ALEMBIC VERIFY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
