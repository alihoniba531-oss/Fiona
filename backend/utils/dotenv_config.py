"""Select the service and admin dotenv with identical precedence and checks."""

import os
from pathlib import Path


class DotenvSelectionError(ValueError):
    """The selected configuration file cannot safely be read."""


def select_dotenv_path(
    env_file: str | Path | None = None, *, backend_dir: Path | None = None,
) -> Path | None:
    """Return a readable dotenv, or None when the optional default is absent."""
    explicit = env_file is not None or "FIONA_ENV_FILE" in os.environ
    if env_file is not None:
        raw = str(env_file)
    elif "FIONA_ENV_FILE" in os.environ:
        raw = os.environ["FIONA_ENV_FILE"]
    else:
        # Tests deliberately disable dotenv while importing backend modules.
        # Do not even inspect the real default file in that mode.
        if os.environ.get("PYTHON_DOTENV_DISABLED") == "1":
            return None
        raw = str((backend_dir or Path(__file__).resolve().parents[1]) / ".env")

    if not raw.strip():
        raise DotenvSelectionError("配置文件不存在或不可读：FIONA_ENV_FILE 为空")
    try:
        selected = Path(raw).expanduser().resolve()
        exists = selected.exists()
        readable = (
            selected.is_file()
            and bool(selected.stat().st_mode & 0o444)
            and os.access(selected, os.R_OK)
        ) if exists else False
    except (OSError, RuntimeError, ValueError):
        selected = Path(raw)
        exists = False
        readable = False
    if not readable:
        if explicit or exists:
            raise DotenvSelectionError(f"配置文件不存在或不可读：{selected}")
        return None
    return selected
