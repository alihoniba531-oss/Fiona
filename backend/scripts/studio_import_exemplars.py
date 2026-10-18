#!/usr/bin/env python3
"""从 v2.1 好例清单导入到 studio_exemplars（WO3e §7）。

只在本机验收时手动运行：

    python scripts/studio_import_exemplars.py --owner author --manifest ~/P01.json --source P01

测试使用合成夹具；公开仓库不放作者原始清单。清单支持 JSON 或 YAML，顶层可以是
数组，也可以是 ``{"items"|"exemplars"|"shots"|"records"|"data": [...]}``。
每条记录必须有（或经 ``--scene-type`` 提供）场景类型和镜头数据；缺省按好例导入。
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sqlite3
import sys

from fastapi import HTTPException

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

_LIST_KEYS = ("items", "exemplars", "shots", "records", "data", "examples", "entries", "rows")
_SHOT_FIELDS = (
    "no", "beat", "shot_size", "angle", "camera", "action", "first_frame_prompt",
    "video_prompt", "dialogue", "sound_intent", "duration_s", "sensitive", "basis",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="从 v2.1 清单导入导演知识库好例（只写 studio_exemplars）")
    parser.add_argument("--owner", required=True, help="案例归属用户名")
    parser.add_argument("--manifest", required=True, type=Path, help="v2.1 清单（JSON/YAML）")
    parser.add_argument("--source", required=True, help="来源标记，如 P01；写入 import:P01")
    parser.add_argument("--scene-type", help="清单记录没写 scene_type 时使用的默认场景类型")
    return parser


def _load_yaml(text: str):
    import yaml
    return yaml.safe_load(text)


def load_manifest(path: Path) -> list:
    """读清单；解析失败给出带文件名的错误。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"无法读取清单 {path}：{exc.__class__.__name__}") from None
    suffix = path.suffix.lower()
    data = None
    if suffix == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"清单 JSON 解析失败：{exc.msg}") from None
    elif suffix in (".yaml", ".yml"):
        try:
            data = _load_yaml(text)
        except Exception as exc:  # PyYAML 的异常类型较多，统一给出文件名
            raise ValueError(f"清单 YAML 解析失败：{exc.__class__.__name__}") from None
    else:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            try:
                data = _load_yaml(text)
            except Exception as exc:
                raise ValueError(f"清单既不是合法 JSON 也不是合法 YAML：{exc.__class__.__name__}") from None
    if isinstance(data, dict):
        for key in _LIST_KEYS:
            if isinstance(data.get(key), list):
                return data[key]
        raise ValueError("清单顶层对象里没有可识别的案例数组")
    if isinstance(data, list):
        return data
    raise ValueError("清单顶层必须是数组或含案例数组的对象")


def _shot_from(entry: dict) -> dict | None:
    for key in ("shot", "shot_json"):
        value = entry.get(key)
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                raise ValueError(f"案例 {entry.get('id')} 的 shot_json 不是合法 JSON") from None
            if not isinstance(parsed, dict):
                raise ValueError(f"案例 {entry.get('id')} 的 shot_json 必须是对象")
            return parsed
    fields = {key: entry[key] for key in _SHOT_FIELDS if key in entry}
    if any(key in fields for key in ("shot_size", "camera", "action", "video_prompt")):
        return fields
    return None


def _expand(entry: dict) -> list[dict]:
    """一条记录可以是单镜，也可以带 shots 数组（展开为多条好例）。"""
    if not isinstance(entry, dict):
        raise ValueError("清单里的每条记录必须是对象")
    nested = entry.get("shots")
    if isinstance(nested, list) and "shot" not in entry and "shot_json" not in entry:
        # 父记录的 id 不能给多条案例复用；子镜头自带 id 时优先用它。
        base = {key: value for key, value in entry.items()
                if key not in {"shots", "shot", "shot_json", "id"}}
        expanded = []
        for shot in nested:
            if not isinstance(shot, dict):
                raise ValueError("shots 数组里的每一项必须是镜头对象")
            item = {**base, "shot": shot}
            shot_id = shot.get("id")
            if isinstance(shot_id, str) and shot_id.strip():
                item["id"] = shot_id
            expanded.append(item)
        return expanded
    return [entry]


def _payload(entry: dict, *, source: str, default_scene_type: str | None) -> dict:
    from studio.director_kb import schema

    scene_type = entry.get("scene_type")
    if not scene_type:
        nested_scene = entry.get("scene")
        if isinstance(nested_scene, dict):
            scene_type = nested_scene.get("scene_type") or nested_scene.get("type")
        else:
            scene_type = nested_scene
    if not scene_type:
        scene_type = default_scene_type
    if not isinstance(scene_type, str) or not scene_type:
        raise ValueError("案例缺少 scene_type，请写在清单里或用 --scene-type 指定")
    if scene_type not in schema.SCENE_TYPES:
        raise ValueError(f"未知场景类型：{scene_type}")
    shot = _shot_from(entry)
    if shot is None:
        raise ValueError(f"案例 {entry.get('id')} 缺少镜头数据")
    identifier = entry.get("id")
    if not isinstance(identifier, str) or not identifier.strip():
        identifier = None
    value = {
        "id": identifier,
        "project_id": entry.get("project_id") if isinstance(entry.get("project_id"), str) else None,
        "source": source if source.startswith("import:") else f"import:{source}",
        "scene_type": scene_type,
        "kind": "good",
        "reason": entry.get("reason") or entry.get("why") or "",
        "shot": shot,
        "keyframe_asset_id": entry.get("keyframe_asset_id") or entry.get("keyframe"),
        "video_model": entry.get("video_model") or entry.get("model"),
        "qc": entry.get("qc", entry.get("qc_json")),
        "cost_cny": entry.get("cost_cny", entry.get("cost")),
        "tags": entry.get("tags", entry.get("tags_json")),
    }
    return {key: item for key, item in value.items() if item is not None}


def _check_owner(owner: str) -> None:
    import database
    connection = sqlite3.connect(database.DB_PATH, timeout=database.SQLITE_BUSY_TIMEOUT)
    try:
        try:
            row = connection.execute("SELECT 1 FROM users WHERE username=?", (owner,)).fetchone()
        except sqlite3.OperationalError:
            raise ValueError("数据库尚未初始化；请先启动一次服务或运行 init_db") from None
    finally:
        connection.close()
    if row is None:
        raise ValueError(f"用户不存在：{owner}")


async def _import(owner: str, manifest: Path, source: str, scene_type: str | None) -> list[str]:
    from studio import store

    records = load_manifest(manifest)
    if not records:
        raise ValueError("清单里没有案例")
    payloads = []
    for record in records:
        for entry in _expand(record):
            payloads.append(_payload(entry, source=source, default_scene_type=scene_type))
    imported = []
    for payload in payloads:
        exemplar = await store.create_exemplar(owner, **payload)
        imported.append(exemplar["id"])
    return imported


def import_manifest(owner: str, manifest: Path, source: str,
                    scene_type: str | None = None) -> list[str]:
    """同步入口：CLI 与测试共用。"""
    if not isinstance(owner, str) or not owner.strip():
        raise ValueError("--owner 不能为空")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("--source 不能为空")
    if not isinstance(manifest, Path):
        manifest = Path(manifest)
    _check_owner(owner)
    return asyncio.run(_import(owner, manifest, source.strip(), scene_type))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        ids = import_manifest(args.owner, args.manifest, args.source, args.scene_type)
    except HTTPException as exc:
        print(f"导入失败：{exc.detail}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print(f"导入失败：{exc}", file=sys.stderr)
        return 2
    print(json.dumps({"imported": len(ids), "ids": ids, "source": args.source},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
