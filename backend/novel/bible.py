"""Code-owned identifiers and immutable story state transitions."""

from __future__ import annotations

from copy import deepcopy

from .schemas import validate_archive, validate_setup


def _next_number(items: list[dict], prefix: str) -> int:
    numbers = [int(item["id"][len(prefix):]) for item in items
               if isinstance(item.get("id"), str) and item["id"].startswith(prefix)
               and item["id"][len(prefix):].isdigit()]
    return max(numbers, default=0) + 1


def build_setup(data: dict, config: dict) -> tuple[dict, dict]:
    """Validate setup and split its output into compass and bible version 1."""
    setup = validate_setup(data, config)
    compass = {field: deepcopy(setup[field]) for field in
               ("title", "logline", "theme", "core_conflict", "protagonist", "candidate_endings")}
    compass["main_threads"] = [dict(deepcopy(item), id=f"T{i}")
                               for i, item in enumerate(setup["main_threads"], 1)]
    compass["target"] = deepcopy(config["target"])
    compass["seed_idea"] = deepcopy(config.get("seed_idea", ""))
    if config.get("structure") == "v2":
        compass["genre_contract"] = deepcopy(setup["genre_contract"])
    characters, states = [], {}
    for i, source in enumerate(setup["characters"], 1):
        character_id = f"C{i}"
        character = {key: deepcopy(value) for key, value in source.items()
                     if key not in ("id", "initial_state")}
        character["id"] = character_id
        characters.append(character)
        states[character_id] = deepcopy(source["initial_state"])
        states[character_id]["relationships"] = {}
    bible = {
        "locked": {
            "world_rules": deepcopy(setup["world_rules"]),
            "characters": characters,
            "style_guide": deepcopy(setup["style_guide"]),
            "adaptation": deepcopy(config["adaptation"]),
        },
        "dynamic": {
            "character_states": states,
            "timeline": [],
            "foreshadowing": [dict(deepcopy(item), id=f"F{i:03d}",
                                   planted_chapter=0, status="open")
                              for i, item in enumerate(setup["initial_foreshadowing"], 1)],
            "used_beats": [],
            "chapter_summaries": [],
        },
        "version": 1,
    }
    return compass, bible


def apply_volume_plan(bible: dict, plan: dict) -> dict:
    """Install a validated plan as a new immutable bible version.

    Replacing an unapproved draft resets its milestones; models and authors
    cannot claim completion through volume planning. Archiving owns statuses.
    """
    result = deepcopy(bible)
    volumes = result["dynamic"].setdefault("volumes", [])
    installed = deepcopy(plan)
    for milestone in installed["milestones"]:
        milestone["status"] = "open"
    index = next((i for i, item in enumerate(volumes)
                  if item["volume"] == installed["volume"]), None)
    if index is None:
        volumes.append(installed)
    else:
        volumes[index] = installed
    result["version"] += 1
    return result


def apply_archive(bible: dict, archive: dict, chapter: int, title: str, *,
                  config=None, decision=None) -> dict:
    """Apply an archivist delta to a fresh copy, preserving all earlier versions."""
    delta = validate_archive(archive, bible, config=config, decision=decision)
    result = deepcopy(bible)
    dynamic = result["dynamic"]
    for change in delta["character_state_changes"]:
        state = dynamic["character_states"][change["id"]]
        field, value = change["field"], deepcopy(change["value"])
        if field == "knows":
            state["knows"].extend(value if isinstance(value, list) else [value])
        elif field == "relationships":
            state["relationships"].update(value)
        else:
            state[field] = value
    dynamic["timeline"].extend(deepcopy(delta["timeline_add"]))
    dynamic["used_beats"].extend(deepcopy(delta["used_beats_add"]))
    next_foreshadowing = _next_number(dynamic["foreshadowing"], "F")
    for i, item in enumerate(delta["foreshadowing_planted"], next_foreshadowing):
        dynamic["foreshadowing"].append(dict(deepcopy(item), id=f"F{i:03d}",
                                              planted_chapter=chapter, status="open"))
    by_foreshadowing_id = {item["id"]: item for item in dynamic["foreshadowing"]}
    for resolved in delta["foreshadowing_resolved"]:
        by_foreshadowing_id[resolved["id"]].update(
            status="resolved", resolved_chapter=chapter, note=resolved["note"])
    next_character = _next_number(result["locked"]["characters"], "C")
    for i, source in enumerate(delta["new_characters"], next_character):
        character_id = f"C{i}"
        # Even an unsolicited model id cannot select or overwrite a record.
        character = {key: deepcopy(value) for key, value in source.items() if key != "id"}
        character["id"] = character_id
        result["locked"]["characters"].append(character)
        dynamic["character_states"][character_id] = {
            "location": "", "condition": "", "knows": [], "relationships": {}}
    dynamic["chapter_summaries"].append({"chapter": chapter, "title": title,
                                         "summary": delta["summary"]})
    if (config or {}).get("structure") == "v2" and "genre_payoff" in (decision or {}):
        decision = decision or {}
        record = {
            "chapter": chapter, "genre_payoff": deepcopy(decision.get("genre_payoff")),
            "advances_threads": deepcopy(decision.get("beat_sheet", {}).get("advances_threads", [])),
        }
        if "payoff_delivered" in delta:
            record["payoff_delivered"] = delta["payoff_delivered"]
        dynamic.setdefault("structure_history", []).append(record)
        for volume in dynamic.get("volumes", []):
            if volume["chapters"][0] <= chapter <= volume["chapters"][1]:
                done = set(delta.get("milestones_done", []))
                for milestone in volume["milestones"]:
                    if milestone["id"] in done:
                        milestone["status"] = "done"
                    elif chapter == volume["chapters"][1] and milestone.get("status", "open") == "open":
                        milestone["status"] = "missed"
    result["version"] += 1
    return result
