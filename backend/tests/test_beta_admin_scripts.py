"""内测管理脚本始终连接指定库，且发码与草莓操作安全。"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

import pytest


BACKEND = Path(__file__).resolve().parents[1]


def _environment(**updates: str) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("FIONA_DB_PATH", None)
    env.pop("FIONA_ENV_FILE", None)
    env.pop("STRAWBERRY_DAILY_REFILL", None)
    env.update(updates)
    return env


def _run(script: str, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BACKEND / script), *map(str, args)],
        cwd=BACKEND,
        env=env or _environment(),
        capture_output=True,
        text=True,
        check=False,
    )


def _config(tmp_path: Path, *, name: str = "admin.env") -> tuple[Path, Path]:
    db_path = tmp_path / "beta.db"
    env_file = tmp_path / name
    env_file.write_text(f"FIONA_DB_PATH={db_path}\n", encoding="utf-8")
    return db_path, env_file


@pytest.mark.parametrize(
    ("script", "args"),
    [
        ("seed_invites.py", ()),
        ("manage_invites.py", ()),
        ("manage_invites.py", ("list",)),
        ("manage_strawberries.py", ()),
        ("manage_strawberries.py", ("list",)),
    ],
)
def test_admin_scripts_help_shows_shared_options(script, args):
    result = _run(script, *args, "--help")

    assert result.returncode == 0, result.stderr
    assert "--env-file" in result.stdout
    assert "--init-db" in result.stdout


def test_admin_script_subprocess_environment_ignores_parent_refill(monkeypatch):
    monkeypatch.setenv("STRAWBERRY_DAILY_REFILL", "999")

    assert "STRAWBERRY_DAILY_REFILL" not in _environment()
    assert _environment(STRAWBERRY_DAILY_REFILL="30")["STRAWBERRY_DAILY_REFILL"] == "30"


@pytest.mark.parametrize(
    ("script", "args"),
    [
        ("seed_invites.py", ("2",)),
        ("manage_invites.py", ("list",)),
        ("manage_strawberries.py", ("list",)),
    ],
)
def test_admin_scripts_refuse_missing_database_without_init(tmp_path, script, args):
    db_path, env_file = _config(tmp_path)
    result = _run(script, *args, "--env-file", str(env_file))

    assert result.returncode == 2
    assert not db_path.exists()
    assert f"配置：{env_file}" in result.stderr
    assert f"数据库：{db_path}" in result.stderr
    assert f"数据库文件不存在：{db_path}" in result.stderr


def test_seed_invites_uses_deletion_safe_names_and_lists_only_new_codes(tmp_path, monkeypatch):
    db_path, env_file = _config(tmp_path)
    first = _run("seed_invites.py", "2", "--env-file", str(env_file), "--init-db")
    assert first.returncode == 0, first.stderr
    assert db_path.is_file()
    assert f"数据库：{db_path}" in first.stderr
    first_codes = re.findall(r"(?m)^([A-Z2-9]{8})  (tester\d+)$", first.stdout)
    assert len(first_codes) == 2
    assert [username for _, username in first_codes] == ["tester01", "tester02"]

    import database

    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    asyncio.run(database.get_or_create_user("tester01"))
    assert asyncio.run(database.delete_account_data("tester01"))["deleted"]

    second = _run("seed_invites.py", "1", "--env-file", str(env_file))
    assert second.returncode == 0, second.stderr
    assert re.search(r"(?m)^[A-Z2-9]{8}  tester03$", second.stdout)
    assert all(code not in second.stdout for code, _ in first_codes)
    assert "统计：总数 2 / 未用 2 / 已用 0 / 已撤销 0" in second.stdout


def test_seed_invites_parallel_runs_allocate_unique_usernames(tmp_path):
    _, env_file = _config(tmp_path)
    initialized = _run("seed_invites.py", "1", "--env-file", str(env_file), "--init-db")
    assert initialized.returncode == 0, initialized.stderr

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: _run("seed_invites.py", "5", "--env-file", str(env_file)), range(2)))
    assert all(result.returncode == 0 for result in results), [result.stderr for result in results]
    names = [name for result in results for name in re.findall(r"(?m)^[A-Z2-9]{8}  (tester\d+)$", result.stdout)]
    assert len(names) == len(set(names)) == 10
    assert set(names) == {f"tester{i:02d}" for i in range(2, 12)}


def test_admin_env_precedence_and_process_override(tmp_path):
    db_path, env_file = _config(tmp_path)
    other_db = tmp_path / "other.db"
    other_file = tmp_path / "other.env"
    other_file.write_text(f"FIONA_DB_PATH={other_db}\n", encoding="utf-8")

    explicit = _run(
        "seed_invites.py", "1", "--env-file", str(env_file), "--init-db",
        env=_environment(FIONA_ENV_FILE=str(other_file)),
    )
    assert explicit.returncode == 0, explicit.stderr
    assert db_path.exists() and not other_db.exists()

    fallback = _run(
        "manage_invites.py", "list", "--init-db",
        env=_environment(FIONA_ENV_FILE=str(other_file)),
    )
    assert fallback.returncode == 0, fallback.stderr
    assert other_db.exists()
    assert f"配置：{other_file}" in fallback.stderr

    process_path = tmp_path / "process.db"
    override = _run(
        "manage_invites.py", "list", "--env-file", str(env_file), "--init-db",
        env=_environment(FIONA_DB_PATH=str(process_path)),
    )
    assert override.returncode == 0, override.stderr
    assert process_path.exists()
    assert f"数据库：{process_path}" in override.stderr


def test_manage_invites_preserves_rotate_and_revoke(tmp_path):
    _, env_file = _config(tmp_path)
    seeded = _run("seed_invites.py", "1", "--env-file", str(env_file), "--init-db")
    assert seeded.returncode == 0, seeded.stderr
    old_code = re.search(r"(?m)^([A-Z2-9]{8})  tester01$", seeded.stdout).group(1)

    rotated = _run(
        "manage_invites.py", "rotate", old_code, "--new-code", "ABCD2345",
        "--env-file", str(env_file),
    )
    assert rotated.returncode == 0, rotated.stderr
    listed = _run("manage_invites.py", "list", "--env-file", str(env_file))
    assert f"{old_code}  tester01  [已撤销]" in listed.stdout
    assert "ABCD2345  tester01  [有效 / 未使用]" in listed.stdout

    revoked = _run("manage_invites.py", "revoke", "ABCD2345", "--env-file", str(env_file))
    assert revoked.returncode == 0, revoked.stderr
    repeated = _run("manage_invites.py", "revoke", "ABCD2345", "--env-file", str(env_file))
    assert repeated.returncode == 1


def test_manage_strawberries_grant_set_list_and_missing_user(tmp_path, monkeypatch):
    db_path, env_file = _config(tmp_path)
    initialized = _run("manage_strawberries.py", "list", "--env-file", str(env_file), "--init-db")
    assert initialized.returncode == 0, initialized.stderr

    import database

    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    asyncio.run(database.get_or_create_user("tester02"))
    granted = _run("manage_strawberries.py", "grant", "tester02", "50", "--env-file", str(env_file))
    assert granted.returncode == 0, granted.stderr
    assert granted.stdout.strip() == "tester02  250"

    listed = _run("manage_strawberries.py", "list", "--env-file", str(env_file))
    assert listed.returncode == 0, listed.stderr
    assert "tester02  250  -" in listed.stdout

    set_to_zero = _run("manage_strawberries.py", "set", "tester02", "0", "--env-file", str(env_file))
    assert set_to_zero.returncode == 0, set_to_zero.stderr
    assert set_to_zero.stdout.strip() == "tester02  0"

    missing = _run("manage_strawberries.py", "grant", "nobody", "1", "--env-file", str(env_file))
    assert missing.returncode == 1
    assert not missing.stdout


def test_manage_strawberries_list_preserves_raw_balance_and_refill_date(tmp_path, monkeypatch):
    db_path, env_file = _config(tmp_path)
    initialized = _run("manage_strawberries.py", "list", "--env-file", str(env_file), "--init-db")
    assert initialized.returncode == 0, initialized.stderr

    import database

    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    asyncio.run(database.get_or_create_user("tester02"))
    with sqlite3.connect(db_path) as db:
        db.execute(
            "UPDATE users SET strawberry_balance = 5, strawberry_refill_date = '2000-01-01' "
            "WHERE username = 'tester02'"
        )

    env = _environment(STRAWBERRY_DAILY_REFILL="30")
    first = _run("manage_strawberries.py", "list", "--env-file", str(env_file), env=env)
    assert first.returncode == 0, first.stderr
    assert "tester02  5  2000-01-01" in first.stdout
    with sqlite3.connect(db_path) as db:
        assert db.execute(
            "SELECT strawberry_balance, strawberry_refill_date FROM users "
            "WHERE username = 'tester02'"
        ).fetchone() == (5, "2000-01-01")

    with sqlite3.connect(db_path) as db:
        db.execute(
            "UPDATE users SET strawberry_balance = 40, strawberry_refill_date = '2000-01-01' "
            "WHERE username = 'tester02'"
        )
    second = _run("manage_strawberries.py", "list", "--env-file", str(env_file), env=env)
    assert second.returncode == 0, second.stderr
    assert "tester02  40  2000-01-01" in second.stdout
    with sqlite3.connect(db_path) as db:
        assert db.execute(
            "SELECT strawberry_balance, strawberry_refill_date FROM users "
            "WHERE username = 'tester02'"
        ).fetchone() == (40, "2000-01-01")


def test_manage_strawberries_default_list_does_not_backfill_legacy_posts(tmp_path, monkeypatch):
    db_path, env_file = _config(tmp_path)
    initialized = _run("manage_strawberries.py", "list", "--env-file", str(env_file), "--init-db")
    assert initialized.returncode == 0, initialized.stderr

    import database

    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    asyncio.run(database.get_or_create_user("tester02"))
    legacy_anon_id = hashlib.md5(b"fiona_plaza_tester02").hexdigest()[:8]
    with sqlite3.connect(db_path) as db:
        db.execute(
            "INSERT INTO posts (anon_id, media_path, owner_username) VALUES (?, ?, NULL)",
            (legacy_anon_id, "legacy.png"),
        )

    listed = _run("manage_strawberries.py", "list", "--env-file", str(env_file))
    assert listed.returncode == 0, listed.stderr
    assert "tester02  200  -" in listed.stdout
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT owner_username FROM posts").fetchone() == (None,)


def test_manage_strawberries_default_list_reads_old_schema_without_migration(tmp_path):
    db_path, env_file = _config(tmp_path)
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE users (username TEXT, strawberry_balance INTEGER)")
        db.execute("INSERT INTO users VALUES ('tester02', 5)")

    listed = _run("manage_strawberries.py", "list", "--env-file", str(env_file))
    assert listed.returncode == 0, listed.stderr
    assert listed.stdout.strip() == "tester02  5  -"
    with sqlite3.connect(db_path) as db:
        assert [row[1] for row in db.execute("PRAGMA table_info(users)")] == [
            "username", "strawberry_balance"
        ]
        assert db.execute("SELECT * FROM users").fetchone() == ("tester02", 5)


def test_manage_strawberries_default_list_reports_missing_balance_without_migration(tmp_path):
    db_path, env_file = _config(tmp_path)
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE users (username TEXT)")
        db.execute("INSERT INTO users VALUES ('tester02')")

    listed = _run("manage_strawberries.py", "list", "--env-file", str(env_file))
    assert listed.returncode == 2
    assert not listed.stdout
    assert "strawberry_balance" in listed.stderr
    with sqlite3.connect(db_path) as db:
        assert [row[1] for row in db.execute("PRAGMA table_info(users)")] == ["username"]


def test_manage_strawberries_grant_and_set_apply_refill_before_change(tmp_path, monkeypatch):
    db_path, env_file = _config(tmp_path)
    initialized = _run("manage_strawberries.py", "list", "--env-file", str(env_file), "--init-db")
    assert initialized.returncode == 0, initialized.stderr

    import database

    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    asyncio.run(database.get_or_create_user("tester02"))
    with sqlite3.connect(db_path) as db:
        db.execute(
            "UPDATE users SET strawberry_balance = 5, strawberry_refill_date = '2000-01-01' "
            "WHERE username = 'tester02'"
        )

    env = _environment(STRAWBERRY_DAILY_REFILL="30")
    granted = _run(
        "manage_strawberries.py", "grant", "tester02", "10", "--env-file", str(env_file), env=env
    )
    assert granted.returncode == 0, granted.stderr
    assert granted.stdout.strip() == "tester02  40"

    set_to_zero = _run(
        "manage_strawberries.py", "set", "tester02", "0", "--env-file", str(env_file), env=env
    )
    assert set_to_zero.returncode == 0, set_to_zero.stderr
    assert set_to_zero.stdout.strip() == "tester02  0"
    listed = _run("manage_strawberries.py", "list", "--env-file", str(env_file), env=env)
    assert listed.returncode == 0, listed.stderr
    assert re.search(r"(?m)^tester02  0  \d{4}-\d{2}-\d{2}$", listed.stdout)


@pytest.mark.parametrize(
    ("command", "amount"),
    [("grant", "0"), ("grant", "100001"), ("grant", "abc"), ("set", "-1"), ("set", "100001")],
)
def test_manage_strawberries_rejects_invalid_amounts(tmp_path, command, amount):
    db_path, env_file = _config(tmp_path)
    result = _run("manage_strawberries.py", command, "tester02", amount, "--env-file", str(env_file))
    assert result.returncode == 2
    assert not db_path.exists()


@pytest.mark.parametrize("count", ["0", "201"])
def test_seed_invites_rejects_count_outside_one_to_two_hundred(tmp_path, count):
    db_path, env_file = _config(tmp_path)
    result = _run("seed_invites.py", count, "--env-file", str(env_file), "--init-db")
    assert result.returncode == 2
    assert not db_path.exists()
