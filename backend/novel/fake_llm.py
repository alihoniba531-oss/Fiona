"""Deterministic local model, including explicit fault injection for offline tests."""

from __future__ import annotations

from collections import defaultdict
import copy
import inspect
import json
import re


def input_characters(messages):
    return sum(len(message.get("content", "")) if isinstance(message.get("content", ""), str)
               else len(json.dumps(message.get("content"), ensure_ascii=False)) for message in messages)


def _find(data, key, default=None):
    if isinstance(data, dict):
        if key in data:
            return data[key]
        for value in data.values():
            if isinstance(value, (dict, list)):
                found = _find(value, key, None)
                if found is not None:
                    return found
    elif isinstance(data, list):
        for value in data:
            found = _find(value, key, None)
            if found is not None:
                return found
    return default


class FakeLLM:
    """Scripts may be a callable(request, one_based_index), or keyed sequences.

    Mapping keys are matched by step_key, task, then role. Returning None falls
    back to the deterministic response; exception objects are raised. A string
    is returned verbatim, allowing malformed JSON and interrupted runs.
    """

    inserted_sentences = (
        "她的头发突然被叙述成金色及腰长发，银色发夹从未存在。",
        "她此刻远在北方雪山医院，右手骨折已经整整三个月。",
        "此前她从未核对或保存过任何记录，过去三章的行动都没有发生。",
    )

    def __init__(self, script=None):
        self.script = script
        self.calls = []
        self._positions = defaultdict(int)

    @property
    def call_count(self):
        return len(self.calls)

    @staticmethod
    def payload(request):
        merged = {}

        def merge(target, source):
            for key, value in source.items():
                if isinstance(value, dict) and isinstance(target.get(key), dict):
                    merge(target[key], value)
                else:
                    target[key] = copy.deepcopy(value)

        for message in request.get("messages", []):
            if message.get("role") == "user":
                try:
                    value = json.loads(message.get("content", ""))
                    if isinstance(value, dict):
                        merge(merged, value)
                        if "task" in value:
                            return merged
                except (ValueError, TypeError):
                    pass
        return request.get("payload", {})

    async def __call__(self, request=None, **kwargs):
        request = dict(request or kwargs)
        payload = self.payload(request)
        request.setdefault("task", payload.get("task", request.get("role", "")))
        self.calls.append(copy.deepcopy(request))
        answer = None
        if callable(self.script):
            answer = self.script(request, self.call_count)
            if inspect.isawaitable(answer):
                answer = await answer
        elif isinstance(self.script, dict):
            for key in (request.get("step_key"), request.get("task"), request.get("role")):
                if key in self.script:
                    responses = self.script[key]
                    position = self._positions[key]
                    self._positions[key] += 1
                    if isinstance(responses, (list, tuple)):
                        answer = responses[position] if position < len(responses) else None
                    else:
                        answer = responses
                    break
        elif isinstance(self.script, (list, tuple)):
            position = self.call_count - 1
            answer = self.script[position] if position < len(self.script) else None
        if isinstance(answer, BaseException):
            raise answer
        if callable(answer):
            answer = answer(request, self.call_count)
            if inspect.isawaitable(answer):
                answer = await answer
        if answer is None:
            answer = self.default_response(request)
        # A test may inject provider-shaped usage as well as response content.
        if isinstance(answer, tuple) or (isinstance(answer, dict) and "usage" in answer and
                                         ("text" in answer or "raw_response" in answer)):
            return answer
        raw = answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False, sort_keys=True)
        return raw, {"input_tokens": input_characters(request.get("messages", [])),
                     "output_tokens": len(raw), "cached_tokens": 0}

    async def complete(self, request):
        return await self(request)

    def default_response(self, request):
        payload = self.payload(request)
        task = request.get("task") or payload.get("task") or request.get("role")
        chapter = request.get("chapter") or payload.get("chapter", 1)
        compass = _find(payload, "compass", {})
        bible = _find(payload, "bible", {})
        if isinstance(payload.get("brief"), dict):
            # Deliberation carries one scoped brief, with no outer bible copy.
            brief = payload["brief"]
            bible = {"locked": brief.get("locked", {}), "dynamic": brief.get("dynamic", {})}
        threads = [item["id"] for item in compass.get("main_threads", [])] or ["T1"]
        characters = [item["id"] for item in bible.get("locked", {}).get("characters", [])] or ["C1"]
        contract = compass.get("genre_contract") or _find(payload, "genre_contract", {})
        if task == "genre_contract":
            return self.genre_contract(threads[0])
        if task in {"volume_plan", "volume_finalize"}:
            start, end = payload["chapters"]
            period = contract["payoff_every_chapters"]
            count = (end - start + period) // period
            return {
                "volume": payload["volume"], "chapters": [start, end],
                "goal": "取得阶段性进展并兑现本卷的类型承诺。",
                "milestones": [
                    {"id": "M1", "thread": contract["core_thread"],
                     "description": "主角完成第一次阶段性成长。", "due_chapter": min(start + 1, end)},
                    {"id": "M2", "thread": contract["core_thread"],
                     "description": "完成本卷目标并确认已有线索。", "due_chapter": end}],
                "payoff_plan": [{"chapter_hint": min(start + (i + 1) * period - 1, end),
                                 "type": contract["core_payoffs"][i % len(contract["core_payoffs"])]}
                                for i in range(count)],
                "threads_focus": [contract["core_thread"]],
                "foreshadowing_to_resolve": [item["id"] for item in bible.get("dynamic", {}).get("foreshadowing", [])
                                              if item["status"] == "open"],
                "new_mystery_budget": 4,
            }
        if task == "setup":
            result = {
                "title": "未发送的自己", "logline": "痕迹清理员从旧案视频中发现自己，追查被删除的真相。",
                "theme": "记忆与选择", "core_conflict": "删除证据的委托与保护真相的责任冲突。",
                "protagonist": {"name": "林澈", "want": "完成委托", "need": "承担保存真相的责任"},
                "candidate_endings": [{"summary": "公开证据，承担暴露自己的代价。"},
                                      {"summary": "保留关键证人，私下交出证据。"}],
                "main_threads": [{"name": "旧案真相", "description": "追查未发送视频与委托人的关系。"}],
                "characters": [{"name": "林澈", "role": "main", "age": "26",
                    "appearance": "身形清瘦，黑色齐耳短发，左眉有浅疤，常穿深灰工装外套并佩戴银色发夹。",
                    "personality": "谨慎而执拗", "motivation": "保护被抹去的人",
                    "initial_state": {"location": "旧数据中心", "condition": "右手完好，没有外伤", "knows": ["三年前发生坠楼旧案"]}}],
                "world_rules": ["故事发生在现代城市，所有线索必须有现实证据。", "三年前发生坠楼旧案，原始录像仍然封存。"],
                "style_guide": {"pov": "第三人称限知", "tense": "过去时", "voice": "克制、对白和动作优先",
                                "banned_phrases": ["命运的齿轮", "不禁", "仿佛", "一抹", "嘴角勾起"]},
                "initial_foreshadowing": [{"description": "未发送视频中出现银色发夹的反光", "importance": "major"}],
            }
            if payload.get("structure") == "v2":
                result["genre_contract"] = self.genre_contract("T1")
            return result
        if task == "proposal":
            return {"proposals": [{"direction": f"第{chapter}章核对一份新证据并与保管者对质。",
                "advances_threads": threads[:1], "conflict": "证据即将被清理", "ending_hook": "新时间戳出现",
                "characters": characters[:1], "risks": "避免重复已用桥段", "suggest_closing": False,
                "closing_reason": ""}]}
        if task == "critique":
            ids = payload.get("proposal_ids") or [item["id"] for item in payload.get("proposals", [])]
            return {"scores": [{"proposal_id": identifier, "logic": 4, "character": 4, "appeal": 4,
                                "compass_fit": 5, "filmability": 4, "comment": "因果明确，动作可拍。"}
                               for identifier in ids],
                    "strongest_objection": {"proposal_id": ids[0] if ids else "P1", "objection": "须交代证据为何留存。"}}
        if task in {"critique_plan", "volume_critique"}:
            result = {"objections": [{"severity": "major", "target": "核对新证据的节拍",
                "problem": "初案尚未交代记录的保管者为何愿意提供原件。",
                "suggestion": "让保管者先要求主角证明副本不会再次流失，再交出原始记录。"}],
                "keep": "保留主角在时间压力下主动保存证据的选择。"}
            if request.get("role") == "twist_designer":
                result["alternative"] = (
                    "让主角发现新签名来自她自己留下的备份，而不是新的嫌疑人。保管者拒绝交出原件，"
                    "因为此前答应过主角保护一名证人。主角必须在公开备份与兑现旧承诺之间选择；"
                    "她先保住原件，再循旧承诺寻找证人，把身份答案留给后续证据确认。")
            return result
        if task in {"decision", "plan", "finalize"}:
            proposals = payload.get("proposals", [])
            ids = [item.get("id", item.get("proposal_id")) for item in proposals]
            ids = [identifier for identifier in ids if identifier]
            objections = payload.get("objections", [])
            objection_ids = payload.get("objection_ids") or [item.get("id", item.get("objection_id")) for item in objections]
            split_alternatives = task == "finalize" and "alternative_ids" in payload
            if split_alternatives:
                # Current finalize inputs separate alternatives. Legacy requests
                # without this field retain the original combined response shape.
                objection_ids = payload.get("objection_ids", [])
            if task == "plan":
                objection_ids = []
            note_ids = payload.get("note_ids") or [item.get("id", item.get("note_id")) for item in payload.get("user_notes", [])]
            experiment = request.get("experiment") or _find(payload, "experiment", "")
            mode = payload.get("mode") or _find(payload, "mode", "normal")
            ending = "end" if mode == "final" or (experiment == "B" and chapter >= 9) else "continue"
            open_major = [item["id"] for item in bible.get("dynamic", {}).get("foreshadowing", [])
                          if item.get("status") == "open" and item.get("importance") == "major"]
            result = {"chosen_proposal_ids": [] if payload.get("solo", False) or task != "decision" else ids[:1],
                "merge_note": "以核对证据为主，保留人物选择。", "objection_responses": [
                    {"objection_id": identifier, "response": (
                        "不采纳：本章保留原来的证据核对方向，替代走向需要更多既有线索铺垫。"
                        if task == "finalize" and identifier.startswith("A") else
                        "安排保管记录解释证据来源。")} for identifier in objection_ids],
                "user_note_responses": [{"note_id": identifier, "adopted": True, "response": "让读者先看到身份线索，主角稍后确认。"}
                                        for identifier in note_ids],
                "rationale": "兼顾因果、人物处境与主线推进。",
                "beat_sheet": {"title": f"第{chapter}次核验", "chapter_goal": "确认新证据的来源", "advances_threads": threads[:1],
                    "characters": characters[:1], "scenes": [{"location": "旧数据中心", "summary": "核对记录并作出保存决定。"}],
                    "beats": ["删除倒计时出现", "核对新证据", "发现签名人的线索"], "opening_hook": "删除倒计时只剩一分钟。",
                    "ending_hook": "屏幕亮起一个新的签名。", "foreshadowing_plant": [],
                    "foreshadowing_resolve": open_major if ending == "end" else []},
                "ending_status": ending, "closing_chapters_left": 0, "unresolved_major_handling": []}
            if split_alternatives:
                result["alternative_responses"] = [
                    {"alternative_id": identifier, "decision": "reject",
                     "response": "本章保留原来的证据核对方向，替代走向需要更多既有线索铺垫。"}
                    for identifier in payload["alternative_ids"]]
            if contract:
                brief = payload.get("brief", {})
                volume = brief.get("current_volume") or next((item for item in bible.get("dynamic", {}).get("volumes", [])
                    if item["chapters"][0] <= chapter <= item["chapters"][1]), None)
                period = contract["payoff_every_chapters"]
                result["genre_payoff"] = ({"type": contract["core_payoffs"][(chapter // period - 1) % len(contract["core_payoffs"])],
                                           "beat_index": 2}
                                          if chapter % period == 0 or brief.get("payoff_required") else None)
                result["milestones_advanced"] = [item["id"] for item in (volume or {}).get("milestones", [])
                                                  if item.get("status", "open") == "open" and item["due_chapter"] <= chapter]
                result["beat_sheet"]["advances_threads"] = [contract["core_thread"]]
                if volume and chapter == volume["chapters"][0] and volume["new_mystery_budget"] > 0:
                    result["beat_sheet"]["foreshadowing_plant"] = [
                        {"description": f"第{chapter}章出现有待确认的新记录。", "importance": "minor"}]
                if volume and chapter == volume["chapters"][1]:
                    result["beat_sheet"]["foreshadowing_resolve"] = [item["id"]
                        for item in bible.get("dynamic", {}).get("foreshadowing", []) if item["status"] == "open"]
            return result
        if task == "write":
            title = payload.get("title") or _find(payload, "title", f"第{chapter}次核验")
            target = payload.get("target_words") or _find(payload, "chapter_words", 1500)
            opening = ("删除倒计时突然跳到六十秒，林澈立即拔掉了外接线。\n"
                       "林澈把黑色短发拨到耳后，银色发夹在灯下闪了一下。\n"
                       "她仍站在旧数据中心的控制台旁，右手没有伤口。\n"
                       "三年前那场坠楼已被档案标注为旧案，原始录像依然封存。\n")
            paragraph = "她核对屏幕上的时间戳，把两份记录并排放好。电话那端的人问她还需要多久。她没有回答，先将证据复制到离线盘，再逐项写下来源。\n"
            body = opening
            while len(re.sub(r"\s", "", body)) < int(target) * 0.9:
                body += paragraph
            payoff = payload.get("context", {}).get("genre_payoff")
            if payoff:
                body += self.payoff_scene(payoff) + "\n"
            return f"# 第{chapter}章 {title}\n\n{body}\n屏幕上的签名忽然改变，她认出了那个名字。\n"
        if task == "review":
            body = payload.get("body", "")
            issues = [{"category": "continuity", "problem": "正文与圣经中的事实冲突。",
                                 "evidence": sentence, "fix": "恢复圣经中的事实。", "blocking": True}
                                for sentence in self.inserted_sentences if sentence in body]
            payoff = payload.get("genre_payoff")
            if payoff and self.payoff_scene(payoff) not in body:
                evidence = next((line for line in body.splitlines() if len(line.strip()) >= 6), "")
                issues.append({"category": "beat_sheet", "problem": "细纲计划的类型爽点整条节拍未兑现。",
                               "evidence": evidence, "fix": "在指定节拍写出可见的兑现场面。", "blocking": True})
            return {"issues": issues}
        if task == "archive":
            beat = payload.get("beat_sheet", {})
            resolved = beat.get("foreshadowing_resolve", [])
            result = {"summary": f"第{chapter}章林澈保存了即将消失的记录，核对来源并发现新签名。",
                    "character_state_changes": [], "timeline_add": [f"第{chapter}章：核对并保存记录。"],
                    "foreshadowing_planted": [], "foreshadowing_resolved": [
                        {"id": identifier, "note": "通过原始记录确认银色发夹反光的来源。"} for identifier in resolved],
                    "used_beats_add": [f"第{chapter}章核对记录"], "new_characters": [],
                    "deviation_from_beat_sheet": {"deviated": False, "note": ""}, "locked_conflicts": []}
            if "milestones_advanced" in payload:
                result["milestones_done"] = copy.deepcopy(payload["milestones_advanced"])
                result["foreshadowing_planted"] = copy.deepcopy(beat.get("foreshadowing_plant", []))
            if payload.get("genre_payoff"):
                result["payoff_delivered"] = self.payoff_scene(payload["genre_payoff"]) in payload.get("body", "")
            return result
        if task == "arc_summary":
            return {"summary": (f"第{payload.get('start_chapter', chapter - 9)}至{chapter}章："
                                "林澈持续核对并保存原始记录，循签名线索追查旧案；"
                                "在删除压力下选择保留证据，逐步确认记录与自身的关联。")}
        if task == "corrupt":
            body = payload.get("body", "")
            preferred = ["林澈把黑色短发拨到耳后，银色发夹在灯下闪了一下。",
                         "她仍站在旧数据中心的控制台旁，右手没有伤口。",
                         "三年前那场坠楼已被档案标注为旧案，原始录像依然封存。"]
            candidates = [sentence for sentence in re.findall(r"[^。！？\n]+[。！？]", body)
                          if body.count(sentence) == 1]
            anchors = [sentence if body.count(sentence) == 1 else candidates[index]
                       for index, sentence in enumerate(preferred)]
            locked = bible.get("locked", {})
            dynamic = bible.get("dynamic", {})
            character = locked.get("characters", [{}])[0]
            states = dynamic.get("character_states", {})
            state = next(iter(states.values()), {})
            timeline = dynamic.get("timeline", [])
            condition = state.get("condition", "")
            state_fact = (condition if len(re.sub(r"\s", "", condition)) >= 8
                          else f"{state.get('location', '旧数据中心')}；{condition}")
            facts = [character.get("appearance", "黑色短发"),
                     state_fact,
                     str(timeline[-1]) if timeline else locked.get("world_rules", ["三年前发生坠楼旧案"])[-1]]
            return {"insertions": [{"after_anchor": anchor, "new_sentence": sentence,
                                     "contradicts": fact} for anchor, sentence, fact in zip(anchors, self.inserted_sentences, facts)]}
        raise ValueError(f"fake 不支持任务：{task}")

    @staticmethod
    def payoff_scene(payoff):
        return {"确认关键证据": "林澈将两份原件逐项比对，找出相同的封存编号；保管人签字确认，这条证据链终于闭合。",
                "主动反击": "林澈当众放出离线备份，对手撤回删除指令，将原始记录交到了她手中。",
                "揭露真相": "林澈展示未删改的原始录像，指出伪造签名的那个人；众人转向他，他低头承认并交出了原件。"}.get(
                    payoff["type"], f"林澈亲手完成了「{payoff['type']}」，让所有人看见成果，并将夺回的原件收进离线柜。")

    @staticmethod
    def genre_contract(core_thread):
        return {"genre": "悬疑探真", "reader_promise": "主角主动成长，逐步查明真相并反击。",
                "core_thread": core_thread,
                "core_payoffs": ["确认关键证据", "主动反击", "揭露真相"],
                "payoff_every_chapters": 3,
                "progression_ladder": ["初次调查", "独立求证", "掌握全局"],
                "drift_warnings": ["连续多章只有谜团，没有主角主动取得的进展"]}
