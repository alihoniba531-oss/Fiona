"""The service and admin command resolve paths from the same selected dotenv."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


BACKEND = Path(__file__).resolve().parents[1]


def _child_environment(env_file: str) -> dict[str, str]:
    child_env = os.environ.copy()
    for name in ("FIONA_DB_PATH", "FIONA_UPLOADS_DIR", "PYTHON_DOTENV_DISABLED"):
        child_env.pop(name, None)
    child_env["FIONA_ENV_FILE"] = env_file
    child_env["JWT_SECRET"] = "fiona-isolated-test-secret-0123456789"
    child_env["DASHSCOPE_API_KEY"] = "sk-isolated-test-not-real"
    return child_env


def test_selected_dotenv_is_loaded_before_database_and_uploads_import(tmp_path):
    db_path = tmp_path / "from-dotenv.db"
    uploads_path = tmp_path / "from-dotenv-uploads"
    env_file = tmp_path / "isolated.env"
    env_file.write_text(
        f"FIONA_DB_PATH={db_path}\nFIONA_UPLOADS_DIR={uploads_path}\n",
        encoding="utf-8",
    )
    child_env = _child_environment(str(env_file))
    script = (
        "import json, main, database, admin_env; from utils import media; "
        "print(json.dumps({'db': database.DB_PATH, 'uploads': media.UPLOADS_DIR, "
        "'admin_db': str(admin_env.configure_database(None, init_db=True))}))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=BACKEND,
        env=child_env, text=True, capture_output=True, timeout=15, check=True,
    )
    paths = json.loads(result.stdout.strip().splitlines()[-1])
    assert paths == {"db": str(db_path), "uploads": str(uploads_path), "admin_db": str(db_path)}
    assert uploads_path.is_dir()
    assert not db_path.exists()


@pytest.mark.parametrize("entrypoint", ["service", "admin"])
def test_tilde_dotenv_path_is_expanded_in_subprocess(tmp_path, entrypoint):
    isolated_home = tmp_path / "isolated-home"
    isolated_home.mkdir()
    db_path = tmp_path / "from-tilde.db"
    uploads_path = tmp_path / "from-tilde-uploads"
    (isolated_home / "selected.env").write_text(
        f"FIONA_DB_PATH={db_path}\nFIONA_UPLOADS_DIR={uploads_path}\n",
        encoding="utf-8",
    )
    child_env = _child_environment("~/selected.env")
    # HOME changes only in this subprocess; the parent shell and process are untouched.
    child_env["HOME"] = str(isolated_home)
    script = (
        "import main, database; print(database.DB_PATH)"
        if entrypoint == "service" else
        "import admin_env; print(admin_env.configure_database(None, init_db=True))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=BACKEND,
        env=child_env, text=True, capture_output=True, timeout=15, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == str(db_path)
    assert not db_path.exists()
    if entrypoint == "service":
        assert uploads_path.is_dir()


@pytest.mark.parametrize("entrypoint", ["service", "admin"])
def test_explicit_missing_dotenv_fails_before_database_import(tmp_path, entrypoint):
    missing = tmp_path / "missing.env"
    child_env = _child_environment(str(missing))
    child_env["FIONA_DB_PATH"] = str(tmp_path / "must-not-create.db")
    child_env["FIONA_UPLOADS_DIR"] = str(tmp_path / "must-not-create-uploads")
    script = (
        "import main"
        if entrypoint == "service" else
        "import admin_env; admin_env.configure_database(None, init_db=True)"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=BACKEND,
        env=child_env, text=True, capture_output=True, timeout=15, check=False,
    )
    assert result.returncode != 0
    assert f"配置文件不存在或不可读：{missing}" in result.stderr
    assert not (tmp_path / "must-not-create.db").exists()
    assert not (tmp_path / "must-not-create-uploads").exists()


def test_explicit_unreadable_dotenv_fails_service_startup(tmp_path):
    unreadable = tmp_path / "unreadable.env"
    unreadable.write_text("FIONA_DB_PATH=should-not-load\n", encoding="utf-8")
    unreadable.chmod(0o000)
    try:
        result = subprocess.run(
            [sys.executable, "-c", "import main"], cwd=BACKEND,
            env=_child_environment(str(unreadable)), text=True, capture_output=True,
            timeout=15, check=False,
        )
        assert result.returncode != 0
        assert f"配置文件不存在或不可读：{unreadable}" in result.stderr
    finally:
        unreadable.chmod(0o600)


def test_absent_default_dotenv_is_optional(tmp_path, monkeypatch):
    from utils.dotenv_config import select_dotenv_path

    monkeypatch.delenv("FIONA_ENV_FILE", raising=False)
    monkeypatch.delenv("PYTHON_DOTENV_DISABLED", raising=False)
    assert select_dotenv_path(backend_dir=tmp_path) is None
