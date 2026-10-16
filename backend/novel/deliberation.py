"""Fixed merge and editor-plan → advisor-critique → finalize protocols."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import json

from .agent_pool import AGENTS, get_agent
from .context import build_brief, context_messages
from .schemas import (validate_critique, validate_critique_plan, validate_decision,
                      validate_proposals)


DIMENSIONS = ("logic", "character", "appeal", "compass_fit", "filmability")


def required_response_ids(objection_ids=(), note_ids=()):
    """List O then N IDs in assignment order; alternatives have their own list."""
    identifiers = [*objection_ids, *note_ids]
    return [identifier for prefix in ("O", "N") for identifier in identifiers
            if identifier.startswith(prefix)]


def split_response_ids(identifiers):
    """Separate code-assigned objection and alternative IDs without reordering."""
    identifiers = list(identifiers)
    return tuple([identifier for identifier in identifiers if identifier.startswith(prefix)]
                 for prefix in ("O", "A"))


async def _gather_phase(coroutines):
    """Cancel and drain sibling calls before a failed phase leaves the meeting."""
    tasks = [asyncio.create_task(coroutine) for coroutine in coroutines]
    try:
        return await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


def messages_for(role, payload, *, chapter_words=2000, task=None, split_context=False):
    card = get_agent(role, chapter_words, task=task)
    users = context_messages(payload) if split_context else [
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)}]
    return card, [{"role": "system", "content": card["system_prompt"]}, *users]


async def deliberate(router, config, compass, bible, *, chapter, arm,
                     participants, history=(), written_words=0, user_notes=()):
    """Run one configured merge or editor-plan / advisor-critique meeting.

    Assignment of IDs and the ordering of results depend only on configuration,
    never on the order in which concurrent model requests finish.
    """
    if config.get("critique_rounds", 1) != 1:
        raise ValueError("P0 的 critique_rounds 必须为 1")
    if config.get("panel_mode", "merge") not in ("merge", "critique", "solo"):
        raise ValueError("panel_mode 必须为 merge、critique 或 solo")
    if len(set(participants)) != len(participants):
        raise ValueError("推演会智能体不能重复")
    roles = []
    for role in participants:
        if role not in config["agents"] or role not in AGENTS:
            raise ValueError(f"推演智能体未配置：{role}")
        if AGENTS[role]["category"] != "deliberation":
            raise ValueError(f"非推演智能体不能参与会议：{role}")
        if role != "editor":
            roles.append(role)
    brief = build_brief(compass, bible, chapter, history=history,
                        written_words=written_words, user_notes=user_notes,
                        timeline_limit=10 if config.get("enable_context_compression") else 5)
    mode = brief.get("mode", brief.get("progress", {}).get("mode", "normal"))
    base = {"chapter": chapter, "brief": brief, "mode": mode}
    prefix = f"arm-{arm}/ch{chapter:03d}"
    semaphore = asyncio.Semaphore(3)

    async def call(role, task, path, payload, validator, *, failure_status="step_failed"):
        card, messages = messages_for(role, {**base, "task": task, **payload},
                                      chapter_words=config["target"]["chapter_words"], task=task,
                                      split_context=config.get("enable_context_compression", False))
        async with semaphore:
            return await router.call(
                step_key=f"{prefix}/{path}", role=role, model=config["agents"][role],
                messages=messages, max_tokens=card["max_tokens"], validator=validator,
                output=card["output"], experiment=config["experiment"], arm=arm,
                chapter=chapter, failure_status=failure_status)

    if (config.get("panel_mode", "merge") == "critique" and roles and arm != "solo"
            and (config["experiment"] in ("B", "P1")
                 or (config["experiment"] == "A" and arm == "panel"))):
        notes = brief.get("user_notes", list(user_notes))
        note_ids = [note["id"] for note in notes]

        def validate_editor(data, objection_ids, alternative_ids=()):
            return validate_decision(data, compass=compass, bible=bible,
                                     chapter=chapter, mode=mode, proposal_ids=[],
                                     objection_ids=objection_ids, note_ids=note_ids,
                                     solo=True, alternative_ids=alternative_ids)

        plan = await call(
            "editor", "plan", "01-plan-editor.json",
            {"solo": True, "proposal_ids": [], "objections": [], "objection_ids": [],
             "user_notes": notes, "note_ids": note_ids,
             "required_response_ids": required_response_ids(note_ids=note_ids)},
            lambda data: validate_editor(data, []), failure_status="decision_invalid")
        if config.get("enable_context_compression"):
            # The initial plan may reintroduce a supporting character absent
            # from the recent window. Advisors and finalize need that card too.
            brief = build_brief(compass, bible, chapter, history=history,
                                written_words=written_words, user_notes=user_notes,
                                timeline_limit=10,
                                named_characters=plan["beat_sheet"]["characters"])
            base["brief"] = brief
        # Advisors see the same brief and the initial plan, without any voting.
        plan_input = {key: deepcopy(plan[key])
                      for key in ("beat_sheet", "rationale", "ending_status")}
        critique_results = await _gather_phase([
            call(role, "critique_plan", f"02-critique-plan-{role}.json",
                 {"plan": plan_input},
                 lambda data, role=role: validate_critique_plan(data, role))
            for role in roles
        ])
        critiques = [{**deepcopy(result), "author": role,
                      "author_name": AGENTS[role]["name"]}
                     for role, result in zip(roles, critique_results)]
        objections, alternatives = [], []
        # Gather preserves configuration order; all O IDs precede all A IDs.
        for critique in critiques:
            author = {"author": critique["author"], "author_name": critique["author_name"]}
            for item in critique["objections"]:
                objections.append({**deepcopy(item), **author,
                                   "id": f"O{len(objections) + 1}"})
            if critique.get("alternative", "").strip():
                alternatives.append({**author, "id": f"A{len(alternatives) + 1}",
                                     "alternative": critique["alternative"]})
        objections.extend(alternatives)
        objection_ids, alternative_ids = split_response_ids(item["id"] for item in objections)
        decision = await call(
            "editor", "finalize", "03-finalize-editor.json",
            {"solo": True, "proposal_ids": [], "plan": plan, "critiques": critiques,
             "objections": objections, "objection_ids": objection_ids,
             "alternative_ids": alternative_ids,
             "user_notes": notes, "note_ids": note_ids,
             "required_response_ids": required_response_ids(objection_ids, note_ids)},
            lambda data: validate_editor(data, objection_ids, alternative_ids),
            failure_status="decision_invalid")
        return {"mode": "critique", "brief": brief, "plan": plan,
                "critiques": critiques, "objections": objections, "decision": decision}

    # gather preserves roles' configuration order, independently of completion.
    proposal_results = await _gather_phase([
        call(role, "proposal", f"01-proposal-{role}.json", {},
             lambda data: validate_proposals(data, compass, bible))
        for role in roles
    ])
    proposals = []
    for role, result in zip(roles, proposal_results):
        for item in result["proposals"]:
            proposals.append({**deepcopy(item), "id": f"P{len(proposals) + 1}",
                              "author": role, "author_name": AGENTS[role]["name"]})

    async def critique(role):
        others = [deepcopy(item) for item in proposals if item["author"] != role]
        if not others:
            # One proposer has no peers; an empty review cannot satisfy the
            # strongest_objection schema and must not invoke the model.
            return None
        ids = [item["id"] for item in others]
        return await call(role, "critique", f"02-critique-{role}.json",
                          {"proposals": others, "proposal_ids": ids},
                          lambda data: validate_critique(data, ids))

    critique_results = await _gather_phase(critique(role) for role in roles)
    objections, reviews = [], []
    scores_by_proposal = {item["id"]: [] for item in proposals}
    for role, result in zip(roles, critique_results):
        if result is None:
            continue
        reviews.append({"author": role, "author_name": AGENTS[role]["name"], **deepcopy(result)})
        for score in result["scores"]:
            scores_by_proposal[score["proposal_id"]].append(score)
        objections.append({"id": f"O{len(objections) + 1}", "author": role,
                           "author_name": AGENTS[role]["name"],
                           **deepcopy(result["strongest_objection"])})
    scores = {}
    for proposal_id, items in scores_by_proposal.items():
        means = {dim: (sum(item[dim] for item in items) / len(items) if items else None)
                 for dim in DIMENSIONS}
        means["total_mean"] = (sum(means[dim] for dim in DIMENSIONS) / len(DIMENSIONS)
                               if items else None)
        means["review_count"] = len(items)
        scores[proposal_id] = means
    notes = brief.get("user_notes", list(user_notes))
    note_ids = [note["id"] for note in notes]
    proposal_ids = [item["id"] for item in proposals]
    objection_ids = [item["id"] for item in objections]
    decision = await call(
        "editor", "decision", "03-decision-editor.json",
        {"proposals": proposals, "scores": scores, "objections": objections,
         "proposal_ids": proposal_ids, "objection_ids": objection_ids,
         "user_notes": notes, "note_ids": note_ids, "solo": not roles,
         "required_response_ids": required_response_ids(objection_ids, note_ids)},
        lambda data: validate_decision(data, compass=compass, bible=bible,
                                       chapter=chapter, mode=mode, proposal_ids=proposal_ids,
                                       objection_ids=objection_ids, note_ids=note_ids,
                                       solo=not roles), failure_status="decision_invalid")
    return {"brief": brief, "proposals": proposals, "reviews": reviews,
            "scores": scores, "objections": objections, "decision": decision}
