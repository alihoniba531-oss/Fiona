"""节奏统计（WO3e §7）：按 owner + scene_type 累计集数、镜头数、均长与分布。

WO7 在一次终检通过后调用一次 :func:`accumulate`，把本集分镜按场景类型分组传入。
每次调用代表一集，因此本次出现的每个场景类型 ``episodes`` 加 1；读取时用
各行的最大 ``episodes`` 作为累计集数（每次调用至少命中一个场景类型）。
"""

from __future__ import annotations

from collections.abc import Mapping
import json

from . import schema
from .. import store


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _distribution(shots: list, key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for shot in shots:
        value = shot.get(key)
        label = value if isinstance(value, str) and value.strip() else "未标注"
        counts[label] = counts.get(label, 0) + 1
    return counts


def _duration(shot: Mapping) -> float | None:
    value = shot.get("duration_s")
    if type(value) is bool:
        return None
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return None
    if not isinstance(value, (int, float)):
        return None
    value = float(value)
    if value <= 0:
        return None
    return value


def _validate(owner: str, shots_by_scene_type) -> list[tuple[str, list]]:
    if not isinstance(owner, str) or not owner.strip():
        raise ValueError("owner 必须是非空字符串")
    if not isinstance(shots_by_scene_type, Mapping):
        raise ValueError("shots_by_scene_type 必须是 {scene_type: [shot, …]}")
    groups = []
    for scene_type in sorted(shots_by_scene_type):
        shots = shots_by_scene_type[scene_type]
        if scene_type not in schema.CONTENT_SCENE_TYPES:
            raise ValueError(f"未知内容场景类型：{scene_type}")
        if not isinstance(shots, (list, tuple)):
            raise ValueError(f"{scene_type} 的分镜必须是列表")
        if not shots:
            continue
        for shot in shots:
            if not isinstance(shot, Mapping):
                raise ValueError("每个镜头必须是对象")
        groups.append((scene_type, list(shots)))
    return groups


async def accumulate(owner: str, shots_by_scene_type: Mapping[str, list]) -> None:
    """把一集的分镜累计进 studio_stats；同输入重复调用会重复计集。"""
    groups = _validate(owner, shots_by_scene_type)
    if not groups:
        return
    now = store.utcnow()
    async with store.connection(transaction=True) as db:
        for scene_type, shots in groups:
            row = await store._one(
                db, "SELECT * FROM studio_stats WHERE owner=? AND scene_type=?",
                (owner, scene_type),
            )
            durations = [value for value in (_duration(shot) for shot in shots) if value is not None]
            old_episodes = int(row["episodes"] or 0) if row else 0
            old_shots = int(row["shots"] or 0) if row else 0
            new_shots = old_shots + len(shots)
            if row and row.get("avg_shot_s") is not None:
                weighted = float(row["avg_shot_s"]) * old_shots
            else:
                weighted = 0.0
            if durations:
                average = (weighted + sum(durations)) / new_shots
            elif row and row.get("avg_shot_s") is not None:
                average = float(row["avg_shot_s"])
            else:
                average = 0.0
            shot_sizes = json.loads(row["shot_size_json"]) if row and row["shot_size_json"] else {}
            cameras = json.loads(row["camera_json"]) if row and row["camera_json"] else {}
            for label, count in _distribution(shots, "shot_size").items():
                shot_sizes[label] = shot_sizes.get(label, 0) + count
            for label, count in _distribution(shots, "camera").items():
                cameras[label] = cameras.get(label, 0) + count
            await db.execute(
                """INSERT INTO studio_stats(owner,scene_type,episodes,shots,avg_shot_s,
                   shot_size_json,camera_json,updated_at) VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(owner,scene_type) DO UPDATE SET
                   episodes=excluded.episodes, shots=excluded.shots, avg_shot_s=excluded.avg_shot_s,
                   shot_size_json=excluded.shot_size_json, camera_json=excluded.camera_json,
                   updated_at=excluded.updated_at""",
                (owner, scene_type, old_episodes + 1, new_shots, average,
                 _json(shot_sizes), _json(cameras), now),
            )


async def read_stats(owner: str) -> dict:
    """GET /kb/stats 的返回：不足 5 集只给 ready/episodes，满 5 集给分类型明细。"""
    if not isinstance(owner, str) or not owner.strip():
        raise ValueError("owner 必须是非空字符串")
    rows = await store.list_stats(owner)
    episodes = max((int(row["episodes"] or 0) for row in rows), default=0)
    if episodes < 5:
        return {"ready": False, "episodes": episodes}
    return {"ready": True, "episodes": episodes, "scene_types": rows}


# 读接口别名，便于 WO7/B 按语义调用。
get_stats = read_stats
