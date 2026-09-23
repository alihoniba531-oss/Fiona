"""导入期路径与逐用例数据库打桩的隔离回归测试。"""

import asyncio
import os
import sqlite3
from pathlib import Path


def test_import_time_paths_use_session_temporary_directory():
    import database
    from utils import media

    backend_dir = Path(__file__).resolve().parents[1]
    assert database.DB_PATH == os.environ["FIONA_DB_PATH"]
    assert media.UPLOADS_DIR == os.environ["FIONA_UPLOADS_DIR"]
    assert not Path(database.DB_PATH).is_relative_to(backend_dir)
    assert not Path(media.UPLOADS_DIR).is_relative_to(backend_dir)


def test_trace_uses_current_database_path(tmp_path, monkeypatch):
    import database
    import trace

    path = tmp_path / "trace.db"
    monkeypatch.setattr(database, "DB_PATH", str(path))
    asyncio.run(database.init_db())
    asyncio.run(trace.log_event(None, "isolation_probe", payload={"count": 1}))

    with sqlite3.connect(path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type = 'isolation_probe'"
        ).fetchone()[0]
    assert count == 1
