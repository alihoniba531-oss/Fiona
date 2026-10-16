"""Atomic, resumable storage for the offline novel experiments."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import tempfile
from datetime import datetime, timezone


class ConfigurationError(ValueError):
    exit_code = 2


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def configuration_hash(config: dict, *, dry_run: bool = False) -> str:
    # The spending ceiling is an operational setting, never a story input.
    content = {key: value for key, value in config.items() if key != "max_total_tokens"}
    encoded = json.dumps({"config": content, "dry_run": dry_run}, ensure_ascii=False,
                         sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class RunStore:
    def __init__(self, out, config: dict, *, dry_run=False, max_total_tokens=3_000_000):
        if isinstance(max_total_tokens, bool) or not isinstance(max_total_tokens, int) or max_total_tokens < 0:
            raise ConfigurationError("max-total-tokens 必须为非负整数")
        self.out = Path(out)
        self.max_total_tokens = max_total_tokens
        self.dry_run = bool(dry_run)
        self.budget_lock = asyncio.Lock()
        self.reserved_tokens = 0
        digest = configuration_hash(config, dry_run=self.dry_run)
        manifest_path = self.out / "manifest.json"
        if manifest_path.exists():
            try:
                self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (ValueError, OSError) as exc:
                raise ConfigurationError("运行清单不可读取，请换一个 --out") from exc
            if self.manifest.get("config_hash") != digest:
                raise ConfigurationError("配置已变化，请换一个 --out")
        else:
            self.out.mkdir(parents=True, exist_ok=True)
            self.manifest = {"config": config, "config_hash": digest, "dry_run": self.dry_run,
                             "experiment": config.get("experiment"), "status": "running",
                             "started_at": utc_now(), "finished_at": None, "failed_step": None}
            self.write_json("manifest.json", self.manifest)
        self.usage = self.read_usage()

    def _path(self, relative) -> Path:
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValueError("运行文件必须使用目录内的相对路径")
        target = self.out / path
        # Also reject pre-existing symbolic links escaping the output directory.
        if not target.resolve().is_relative_to(self.out.resolve()):
            raise ValueError("运行文件不得越过输出目录")
        return target

    def write_text(self, relative, text: str):
        target = self._path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                             prefix=f".{target.name}.", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return target

    def write_json(self, relative, data):
        return self.write_text(relative, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    def read_json(self, relative):
        return json.loads(self._path(relative).read_text(encoding="utf-8"))

    def read_usage(self):
        path = self.out / "usage.jsonl"
        if not path.exists():
            return []
        records = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    records.append(json.loads(line))
                except ValueError as exc:
                    raise ConfigurationError("用量记录损坏，请检查 usage.jsonl") from exc
        return records

    @property
    def total_tokens(self):
        return sum(row.get("input_tokens", 0) + row.get("output_tokens", 0) for row in self.usage)

    def append_usage(self, record: dict):
        # Synchronous append cannot interleave within one asyncio event loop.
        with (self.out / "usage.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.usage.append(record)

    def mark_usage(self, record: dict, *, ok: bool):
        """Finalize validation status without adding a second billing record."""
        record["ok"] = bool(ok)
        self.write_text("usage.jsonl", "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                                             for row in self.usage))

    def set_status(self, status: str, **fields):
        self.manifest.update(fields)
        self.manifest["status"] = status
        self.manifest["updated_at"] = utc_now()
        self.manifest["finished_at"] = None if status == "running" else utc_now()
        self.write_json("manifest.json", self.manifest)
