"""AC1：upgrade / downgrade 往返成功，alembic check 零漂移。

平台验收标准逐字：
1. upgrade / downgrade 往返成功，alembic check 零漂移
"""

from sqlalchemy import inspect

from tests.conftest import ROOT, run_alembic


def test_upgrade_head_then_check_zero_drift(db_path):
    proc = run_alembic("upgrade", "head", db_path=db_path)
    assert proc.returncode == 0, f"upgrade head 失败：\n{proc.stdout}\n{proc.stderr}"

    current = run_alembic("current", db_path=db_path)
    assert current.returncode == 0
    assert "0001" in current.stdout, f"alembic current 未见 0001：\n{current.stdout}"

    check = run_alembic("check", db_path=db_path)
    assert check.returncode == 0, f"alembic check 失败：\n{check.stdout}\n{check.stderr}"
    assert "No new upgrade operations detected." in check.stdout, (
        f"alembic check 未报零漂移：\n{check.stdout}\n{check.stderr}"
    )

    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{db_path}")
    tables = set(inspect(engine).get_table_names())
    engine.dispose()
    assert "crm_contract" in tables
    assert "crm_membership" in tables
    assert "alembic_version" in tables


def test_downgrade_removes_contract_table_and_fk_column(db_path):
    run_alembic("upgrade", "head", db_path=db_path)
    proc = run_alembic("downgrade", "base", db_path=db_path)
    assert proc.returncode == 0, f"downgrade base 失败：\n{proc.stdout}\n{proc.stderr}"

    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{db_path}")
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    # M1（GPT 第 1 轮复核必改）：downgrade 删合同表、删外键与 contract_id 列，
    # 但永不删会员表（真实库里会员表早已存在）；样品绿地路径下留一个空的
    # 最小会员表，是安全的有意行为。
    assert "crm_contract" not in tables
    assert "crm_membership" in tables
    columns = {c["name"] for c in insp.get_columns("crm_membership")}
    assert "contract_id" not in columns
    assert insp.get_foreign_keys("crm_membership") == []
    engine.dispose()


def test_upgrade_downgrade_upgrade_roundtrip(db_path):
    for step in ("head", "base", "head"):
        proc = run_alembic("upgrade" if step == "head" else "downgrade", step, db_path=db_path)
        assert proc.returncode == 0, f"alembic {step} 失败：\n{proc.stdout}\n{proc.stderr}"
    check = run_alembic("check", db_path=db_path)
    assert check.returncode == 0
    assert "No new upgrade operations detected." in check.stdout
