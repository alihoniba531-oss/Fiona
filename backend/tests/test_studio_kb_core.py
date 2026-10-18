"""WO3e A 块：卡片契约、取材料、知识库检查、案例与统计。

卡片是仓库内的真实 YAML；测试不读仓库外文件、不联网。案例库与统计用隔离
临时库，夹具由测试自写。
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import HTTPException

import database
from studio import store
from studio.director_kb import lint, loader, retrieval, schema, stats


def run(coro):
    return asyncio.run(coro)


def tags(**overrides):
    value = {
        "scene_type": "dialogue",
        "position": "body",
        "pace": "mid",
        "emotion": "克制",
        "cast_count": 2,
        "realism": "photoreal",
        "setting": "interior",
        "sensitive": [],
    }
    value.update(overrides)
    return value


@pytest.fixture
def kb_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "kb.db"))
    run(database.init_db())
    return database.DB_PATH


@pytest.fixture
def owner(kb_db):
    run(database.get_or_create_user("kb-author"))
    return "kb-author"


# ── 卡片：全部过 schema、id 唯一、引用存在、清单齐全 ──────────────────────────


def test_all_cards_validate_and_cover_contract():
    library = loader.load_library()
    assert len(library.cards) == len(set(library.cards))
    counts = {key: len(value) for key, value in library.by_type.items()}
    assert counts["grammar"] == 13
    assert counts["scene"] == 19
    assert counts["model"] == 5
    assert counts["negative"] >= 21
    assert len(library.cards) >= 58
    assert schema.missing_required_ids(library.all()) == []
    assert set(library.by_scene_type) == set(schema.SCENE_TYPES)
    position_cards = [card for card in library.of_type("scene") if "position" in card]
    assert len(position_cards) == 2
    assert {card["scene_type"]: card["position"] for card in position_cards} == {
        "opening-hook": "opening", "cliffhanger": "ending",
    }
    for card in library.all():
        schema.validate_card(card, path=card["id"])
        assert card["id"].startswith(schema.CARD_ID_PREFIX[card["type"]])
    # 加载器已跑过全库引用；这里再确认每条 scene 引用都能解析到正确类型。
    for card in library.of_type("scene"):
        for card_id in card["related_grammar"]:
            assert library.cards[card_id]["type"] == "grammar"
        for card_id in card["related_negative"]:
            assert library.cards[card_id]["type"] == "negative"
    # 文件名与 id 一致由 loader 负责；抽两张样卡确认关键字段没有被破坏。
    assert library.get("scene-dialogue")["scene_type"] == "dialogue"
    assert library.get("scene-fight")["beats"]
    # 列表接口：类型过滤与关键词搜索都按 id 排序。
    scenes = loader.list_cards("scene", "打斗")
    assert [card["id"] for card in scenes] == ["scene-fight"]


# ── select_materials：确定性、预算、位置卡、模型匹配 ─────────────────────────


def test_select_materials_is_deterministic_and_within_budget():
    input_tags = tags(scene_type="fight", pace="fast", sensitive=["structure", "material"])
    first = retrieval.select_materials(input_tags, "seedance")
    second = retrieval.select_materials(input_tags, "seedance")
    assert first == second
    assert first["text"] == second["text"]
    assert first["chars"] == len(first["text"]) <= 8000
    assert first["template"]["id"] == "scene-fight"
    assert first["position"] is None
    assert first["model"]["id"] == "model-seedance-2-5-photoreal"
    assert len(first["grammar"]) <= 5
    assert [card["id"] for card in first["grammar"]] == sorted(
        card["id"] for card in first["grammar"])
    assert len(first["negatives"]) <= 3
    assert len(first["card_ids"]) == len(set(first["card_ids"]))
    for card_id in ("scene-fight", "model-seedance-2-5-photoreal"):
        assert card_id in first["card_ids"]
        assert f"【{card_id}】" in first["text"]


@pytest.mark.parametrize("scene_type", schema.CONTENT_SCENE_TYPES)
def test_default_budget_stays_within_8000(scene_type):
    result = retrieval.select_materials(tags(scene_type=scene_type), "wan")
    assert result["template"]["id"] == f"scene-{scene_type}"
    assert result["model"] is not None
    assert result["chars"] == len(result["text"]) <= 8000
    assert "【scene-" in result["text"]


def test_position_and_model_selection():
    opening = retrieval.select_materials(tags(position="opening"), "wan")
    assert opening["position"]["id"] == "scene-opening-hook"
    ending = retrieval.select_materials(tags(position="ending"), "wan")
    assert ending["position"]["id"] == "scene-cliffhanger"
    body = retrieval.select_materials(tags(position="body"), "wan")
    assert body["position"] is None

    anime = retrieval.select_materials(tags(realism="anime"), "wan")
    assert anime["model"]["id"] == "model-wan-3-anime"
    seedance = retrieval.select_materials(tags(realism="anime"), "seedance")
    assert seedance["model"]["id"] == "model-seedance-2-5-anime"
    # 没有同风格视频模型时返回 None；seedream 是出图模型，不能冒充视频模型。
    assert retrieval.select_materials(tags(realism="3d"), "wan")["model"] is None


def test_tight_budget_keeps_template_position_and_model():
    input_tags = tags(scene_type="fight", position="ending")
    result = retrieval.select_materials(input_tags, "seedance", budget_chars=5000)
    assert result["template"]["id"] == "scene-fight"
    assert result["position"]["id"] == "scene-cliffhanger"
    assert result["model"]["id"] == "model-seedance-2-5-photoreal"
    assert result["chars"] == len(result["text"]) <= 5000
    for card in (result["template"], result["position"], result["model"]):
        assert f"【{card['id']}】" in result["text"]
    # 裁剪先删案例，再删反例，最后删语法尾部。
    assert result["exemplars"] == []
    # 预算小到基础卡全文放不下时，仍保留三张卡的 id/标题/摘要。
    tiny = retrieval.select_materials(input_tags, "seedance", budget_chars=600)
    assert tiny["chars"] == len(tiny["text"]) <= 600
    for card in (tiny["template"], tiny["position"], tiny["model"]):
        assert card["id"] in tiny["card_ids"]
        assert f"【{card['id']}】" in tiny["text"]


def test_position_scene_type_is_422():
    with pytest.raises(HTTPException) as caught:
        retrieval.select_materials(tags(scene_type="opening-hook"), "wan")
    assert caught.value.status_code == 422
    assert "位置卡" in caught.value.detail


def test_unknown_scene_type_and_video_model_are_422():
    with pytest.raises(HTTPException) as caught:
        retrieval.select_materials(tags(scene_type="not-a-scene"), "wan")
    assert caught.value.status_code == 422
    with pytest.raises(HTTPException) as caught:
        retrieval.select_materials(tags(), "seedream")
    assert caught.value.status_code == 422


def test_exemplars_only_queried_with_owner_and_limited_to_three(owner):
    for index in range(4):
        run(store.create_exemplar(
            owner, scene_type="dialogue", shot={"shot_size": f"中景{index}"},
            reason=f"好例 {index}", source="studio",
            created_at=f"2026-10-18T00:0{index}:00+00:00",
        ))
    run(store.create_exemplar(
        owner, scene_type="dialogue", shot={"shot_size": "反例"}, kind="bad",
        reason="反例", source="studio", created_at="2026-10-18T00:09:00+00:00",
    ))
    result = retrieval.select_materials(tags(), "wan", owner=owner, budget_chars=12000)
    assert [item["reason"] for item in result["exemplars"]] == ["好例 3", "好例 2", "好例 1"]
    unowned = retrieval.select_materials(tags(), "wan", budget_chars=12000)
    assert unowned["exemplars"] == []


# ── lint：6 条内置规则 + model / negative 数据驱动规则 ──────────────────────


@pytest.fixture
def no_data_rules(monkeypatch):
    monkeypatch.setattr(lint, "_model_cards", lambda: ())
    monkeypatch.setattr(lint, "_negative_cards", lambda: ())


def _ids(findings):
    return [finding["rule_id"] for finding in findings]


def test_builtin_bare_camera_term(no_data_rules):
    shot = {"no": 1, "shot_size": "远景", "camera": "固定机位",
            "video_prompt": "Dolly 缓慢靠近", "duration_s": 5}
    assert "bare-camera-term" in _ids(lint.lint_shots([shot], video_model="wan", tags=tags()))
    # 同一句里给了中文白话就不算裸写。
    shot["video_prompt"] = "Dolly（推轨，镜头沿地面平稳靠近）"
    assert "bare-camera-term" not in _ids(lint.lint_shots([shot], video_model="wan", tags=tags()))


def test_builtin_looking_at_camera(no_data_rules):
    shot = {"no": 1, "shot_size": "中景", "camera": "固定机位",
            "first_frame_prompt": "她看向镜头", "duration_s": 5}
    findings = lint.lint_shots([shot], video_model="wan", tags=tags())
    assert findings[0]["rule_id"] == "looking-at-camera"
    assert findings[0]["level"] == "warn"


def test_builtin_too_many_actions(no_data_rules):
    shot = {"no": 1, "shot_size": "中景", "camera": "固定机位",
            "action": "推门，然后转身，接着开口、并停顿；离开", "duration_s": 5}
    assert "too-many-actions" in _ids(lint.lint_shots([shot], video_model="wan", tags=tags()))
    shot["action"] = "推门，然后转身"
    assert "too-many-actions" not in _ids(lint.lint_shots([shot], video_model="wan", tags=tags()))


def test_builtin_sensitive_requires_fixed_camera(no_data_rules):
    shot = {"no": 1, "shot_size": "特写", "camera": "跟拍（镜头随人移动）",
            "video_prompt": "手指按住滚柱", "duration_s": 5}
    keyed = tags(scene_type="process-closeup", sensitive=["structure"])
    assert "sensitive-nonfixed-camera" in _ids(
        lint.lint_shots([shot], video_model="wan", tags=keyed))
    shot["camera"] = "固定机位"
    assert "sensitive-nonfixed-camera" not in _ids(
        lint.lint_shots([shot], video_model="wan", tags=keyed))


def test_builtin_seedance_portrait_gate(no_data_rules):
    shot = {"no": 1, "shot_size": "近景", "camera": "固定机位",
            "video_prompt": "林晚正脸看对手", "duration_s": 5}
    seedance = lint.lint_shots([shot], video_model="seedance", tags=tags())
    assert "seedance-portrait-gate" in _ids(seedance)
    wan = lint.lint_shots([shot], video_model="wan", tags=tags())
    assert "seedance-portrait-gate" not in _ids(wan)
    shot["video_prompt"] = "逆光剪影，林晚背对镜头"
    assert "seedance-portrait-gate" not in _ids(
        lint.lint_shots([shot], video_model="seedance", tags=tags()))


def test_builtin_short_generation_is_info(no_data_rules):
    shot = {"no": 1, "shot_size": "全景", "camera": "固定机位",
            "video_prompt": "空镜", "duration_s": 3.2}
    findings = lint.lint_shots([shot], video_model="wan", tags=tags())
    assert findings[0]["rule_id"] == "short-generation"
    assert findings[0]["level"] == "info"


def test_model_card_data_driven_rule():
    shot = {"no": 1, "shot_size": "远景", "camera": "固定机位",
            "video_prompt": "camera_fixed: true", "duration_s": 5}
    findings = lint.lint_shots([shot], video_model="seedance", tags=tags())
    assert "seedance-camera-fixed" in _ids(findings)


def test_negative_card_data_driven_rule():
    shot = {"no": 1, "shot_size": "中景", "camera": "固定机位",
            "video_prompt": "她满脸污垢站在门口", "duration_s": 5}
    findings = lint.lint_shots([shot], video_model="wan", tags=tags())
    assert "negative-grimy-realism" in _ids(findings)
    # applies_to.scene_type 不匹配时不应命中。
    other = lint.lint_shots([shot], video_model="wan", tags=tags(scene_type="fight"))
    assert "negative-grimy-realism" not in _ids(other)


def test_lint_result_shape_and_levels():
    shots = [
        {"no": 1, "shot_size": "近景", "camera": "固定机位",
         "video_prompt": "Dolly 推近，她看向镜头", "action": "走，然后停，接着转身、并回头；离开",
         "duration_s": 2.5, "sensitive": ["face_closeup"]},
        {"no": 2, "shot_size": "全景", "camera": "固定机位", "video_prompt": "空镜", "duration_s": 5},
    ]
    findings = lint.lint_shots(shots, video_model="seedance", tags=tags())
    assert findings
    for finding in findings:
        assert set(finding) == {"shot_no", "rule_id", "level", "message"}
        assert finding["level"] in ("warn", "info")
        assert isinstance(finding["shot_no"], int)


# ── R1（L 块）：lint 规则 1/2、一次加载、语法优先级与 tags 归一 ──────────────


def test_builtin_ascii_boundary_and_negated_looking_phrases(no_data_rules):
    # 英文术语前后紧挨汉字时也要命中。
    shot = {"no": 1, "shot_size": "远景", "camera": "固定机位",
            "video_prompt": "镜头做Dolly缓慢靠近", "duration_s": 5}
    assert "bare-camera-term" in _ids(
        lint.lint_shots([shot], video_model="wan", tags=tags()))
    shot["video_prompt"] = "Crane上升"
    assert "bare-camera-term" in _ids(
        lint.lint_shots([shot], video_model="wan", tags=tags()))

    # 英文看镜头短语同样使用 ASCII 边界。
    shot["video_prompt"] = "她looks at camera"
    assert "looking-at-camera" in _ids(
        lint.lint_shots([shot], video_model="wan", tags=tags()))

    # 中文否定写法不误报；未否定的同句仍要报警。
    shot["video_prompt"] = "固定机位"
    shot["first_frame_prompt"] = "不直视镜头"
    assert "looking-at-camera" not in _ids(
        lint.lint_shots([shot], video_model="wan", tags=tags()))
    shot["first_frame_prompt"] = "避免看向镜头，视线落在钥匙上"
    assert "looking-at-camera" not in _ids(
        lint.lint_shots([shot], video_model="wan", tags=tags()))
    shot["first_frame_prompt"] = "她看向镜头"
    assert "looking-at-camera" in _ids(
        lint.lint_shots([shot], video_model="wan", tags=tags()))
    shot["first_frame_prompt"] = "不直视镜头，但她随后看向镜头"
    assert "looking-at-camera" in _ids(
        lint.lint_shots([shot], video_model="wan", tags=tags()))


def test_builtin_nonfixed_camera_is_not_fixed(no_data_rules):
    shot = {"no": 1, "shot_size": "特写", "camera": "非固定机位（跟拍）",
            "video_prompt": "手指按住滚柱", "duration_s": 5}
    keyed = tags(scene_type="process-closeup", sensitive=["structure"])
    assert "sensitive-nonfixed-camera" in _ids(
        lint.lint_shots([shot], video_model="wan", tags=keyed))
    shot["camera"] = "固定机位"
    assert "sensitive-nonfixed-camera" not in _ids(
        lint.lint_shots([shot], video_model="wan", tags=keyed))


def test_prompt_length_rules_only_measure_their_own_field():
    seedance = {"no": 1, "shot_size": "远景", "camera": "固定机位",
                "video_prompt": "动" * 2001, "duration_s": 5}
    assert "seedance-prompt-too-long" in _ids(
        lint.lint_shots([seedance], video_model="seedance", tags=tags()))
    # video_prompt 刚好 2000 字：其他字段再长也不能触发。
    seedance["video_prompt"] = "动" * 2000
    seedance["first_frame_prompt"] = "静" * 2500
    assert "seedance-prompt-too-long" not in _ids(
        lint.lint_shots([seedance], video_model="seedance", tags=tags()))

    seedream = {"no": 1, "shot_size": "远景", "camera": "固定机位",
                "first_frame_prompt": "景" * 1501, "duration_s": 5}
    assert "seedream-prompt-too-long" in _ids(
        lint.lint_shots([seedream], video_model="seedream", tags=tags()))
    seedream["first_frame_prompt"] = "景" * 1500
    seedream["video_prompt"] = "视" * 2500
    assert "seedream-prompt-too-long" not in _ids(
        lint.lint_shots([seedream], video_model="seedream", tags=tags()))


def test_lint_loads_model_and_negative_cards_once_per_call(monkeypatch):
    calls = {"model": 0, "negative": 0}
    model_card = {
        "id": "model-unit-test", "model": "wan-3.0", "style": "photoreal",
        "lint_rules": [{"id": "unit-model-rule", "pattern": "magic",
                        "level": "warn", "message": "模型规则命中"}],
    }
    negative_card = {
        "id": "negative-unit-test", "title": "单元反例", "why": "原因",
        "lint_pattern": "bad",
    }

    def model_cards():
        calls["model"] += 1
        return (model_card,)

    def negative_cards():
        calls["negative"] += 1
        return (negative_card,)

    monkeypatch.setattr(lint, "_model_cards", model_cards)
    monkeypatch.setattr(lint, "_negative_cards", negative_cards)
    shots = [{"no": index, "shot_size": "远景", "camera": "固定机位",
              "video_prompt": "magic bad", "duration_s": 5}
             for index in (1, 2, 3)]
    findings = lint.lint_shots(shots, video_model="wan", tags=tags())
    assert calls == {"model": 1, "negative": 1}
    assert [finding["rule_id"] for finding in findings].count("unit-model-rule") == 3
    assert [finding["rule_id"] for finding in findings].count("negative-unit-test") == 3


def test_when_model_rules_for_seedance_and_wan():
    # 用真实模型卡，不 monkeypatch 掉数据驱动规则。
    shot = {"no": 1, "shot_size": "近景", "camera": "固定机位",
            "video_prompt": "林晚正脸看向对手，视线落在对方肩上", "duration_s": 5}
    findings = lint.lint_shots([shot], video_model="seedance", tags=tags())
    portrait = [item for item in findings if item["rule_id"] == "seedance-portrait-photoreal"]
    assert len(portrait) == 1
    assert portrait[0]["level"] == "warn"

    # 动漫通道没有写实肖像闸规则。
    anime = lint.lint_shots([shot], video_model="seedance", tags=tags(realism="anime"))
    assert "seedance-portrait-photoreal" not in _ids(anime)

    # 逆光剪影或背影不露脸，不命中。
    for prompt in ("逆光剪影，林晚背对镜头", "林晚背影，约 65° 俯拍加头发遮脸"):
        shot["video_prompt"] = prompt
        assert "seedance-portrait-photoreal" not in _ids(
            lint.lint_shots([shot], video_model="seedance", tags=tags()))

    # 万相写实特写露脸：info 级提醒。
    shot["shot_size"] = "特写"
    shot["video_prompt"] = "林晚正脸看向对手，视线落在对方肩上"
    closeup = [item for item in lint.lint_shots(
        [shot], video_model="wan", tags=tags()) if item["rule_id"] == "wan-face-closeup"]
    assert len(closeup) == 1
    assert closeup[0]["level"] == "info"


def test_select_materials_renders_every_card_header():
    result = retrieval.select_materials(tags(), "wan")
    blocks = result["text"].split("\n\n")
    assert result["grammar"]
    assert result["negatives"]
    for key in ("grammar", "negatives"):
        for card in result[key]:
            header = f"【{card['id']}】{card['title']}：{card['summary']}"
            assert any(block.startswith(header) for block in blocks), header
    for card_id in result["card_ids"]:
        assert f"【{card_id}】" in result["text"]


def test_grammar_priority_keeps_template_related_cards():
    result = retrieval.select_materials(
        tags(scene_type="dialogue", position="body", sensitive=["face_closeup"]), "wan")
    grammar_ids = [card["id"] for card in result["grammar"]]
    for required in ("grammar-over-shoulder", "grammar-shot-reverse-shot",
                     "grammar-shot-size"):
        assert required in grammar_ids
    # 先按优先级取前 5 张，再按 id 排序输出。
    assert grammar_ids == sorted(grammar_ids)


def _valid_grammar_card(**overrides):
    card = {
        "id": "grammar-tag-test",
        "type": "grammar",
        "title": "标签测试",
        "summary": "测试标签正则与匹配归一。",
        "tags": ["face-closeup"],
        "sources": [{"name": "测试", "license": "own"}],
        "version": 1,
        "definition": "定义。",
        "narrative_use": "作用。",
        "safe_prompt": "安全写法。",
        "avoid": [],
        "related": [],
    }
    card.update(overrides)
    return card


def test_tag_schema_rejects_underscores():
    card = _valid_grammar_card()
    schema.validate_card(card)
    with pytest.raises(schema.CardValidationError) as caught:
        schema.validate_card(_valid_grammar_card(tags=["face_closeup"]))
    assert "kebab-case" in str(caught.value)


def test_grammar_tag_matching_normalizes_sensitive_underscores():
    grammar = _valid_grammar_card(
        id="grammar-insert-closeup",
        tags=["insert", "closeup", "face-closeup"],
    )
    template = {
        "id": "scene-dialogue", "type": "scene",
        "related_grammar": [], "related_negative": [],
    }
    library = loader.CardLibrary(
        cards={"grammar-insert-closeup": grammar, "scene-dialogue": template},
        by_type={"grammar": ("grammar-insert-closeup",),
                 "scene": ("scene-dialogue",)},
        by_scene_type={"dialogue": "scene-dialogue"},
    )
    selected = retrieval._select_grammar(
        library, template, None, tags(sensitive=["face_closeup"]))
    assert [card["id"] for card in selected] == ["grammar-insert-closeup"]


def test_tag_tokens_normalize_all_underscores():
    tokens = retrieval._tag_tokens(tags(
        scene_type="process_closeup",
        sensitive=["face_closeup", "giant_offscreen"],
    ))
    assert "process-closeup" in tokens
    assert "face-closeup" in tokens
    assert "giant-offscreen" in tokens
    assert "face_closeup" not in tokens
    assert "giant_offscreen" not in tokens


# ── stats：累计与读接口 ─────────────────────────────────────────────────────


def test_stats_accumulate_and_ready_threshold(kb_db):
    assert run(stats.read_stats("stats-author")) == {"ready": False, "episodes": 0}
    episode = {
        "dialogue": [{"shot_size": "中景", "camera": "固定机位", "duration_s": 3.0},
                     {"shot_size": "近景", "camera": "固定机位", "duration_s": 5.0}],
        "fight": [{"shot_size": "全景", "camera": "跟拍", "duration_s": 1.5}],
    }
    for _ in range(4):
        run(stats.accumulate("stats-author", episode))
    assert run(stats.read_stats("stats-author")) == {"ready": False, "episodes": 4}
    run(stats.accumulate("stats-author", episode))
    result = run(stats.read_stats("stats-author"))
    assert result["ready"] is True
    assert result["episodes"] == 5
    rows = {row["scene_type"]: row for row in result["scene_types"]}
    assert rows["dialogue"]["episodes"] == 5
    assert rows["dialogue"]["shots"] == 10
    assert rows["dialogue"]["avg_shot_s"] == 4.0
    assert rows["dialogue"]["shot_size"] == {"中景": 5, "近景": 5}
    assert rows["dialogue"]["camera"] == {"固定机位": 10}
    assert rows["fight"]["shots"] == 5
    assert rows["fight"]["shot_size"] == {"全景": 5}
    with pytest.raises(ValueError):
        run(stats.accumulate("stats-author", {"not-a-scene": episode["fight"]}))


# ── 导入脚本：合成夹具 ─────────────────────────────────────────────────────


def test_import_exemplars_with_synthetic_manifest(kb_db, tmp_path, owner):
    from scripts import studio_import_exemplars

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([
        {"scene_type": "dialogue", "shot": {"shot_size": "中景", "camera": "固定机位"},
         "reason": "合成好例 1", "tags": ["对话"], "model": "wan"},
        {"scene_type": "fight", "shots": [
            {"shot_size": "全景", "camera": "固定机位"},
            {"shot_size": "近景", "camera": "固定机位"},
        ]},
    ], ensure_ascii=False), encoding="utf-8")
    imported = studio_import_exemplars.import_manifest(owner, manifest, "P01")
    assert len(imported) == 3
    rows = run(store.list_exemplars(owner))
    assert len(rows) == 3
    assert {row["kind"] for row in rows} == {"good"}
    assert {row["source"] for row in rows} == {"import:P01"}
    assert {row["scene_type"] for row in rows} == {"dialogue", "fight"}
    assert any(row["reason"] == "合成好例 1" for row in rows)
    assert any(row["tags"] == ["对话"] for row in rows)

    # --scene-type 作为清单缺省值；缺 scene_type 且无缺省时必须报错。
    fallback = tmp_path / "fallback.json"
    fallback.write_text(json.dumps([{"shot": {"shot_size": "中景"}}]), encoding="utf-8")
    with pytest.raises(ValueError):
        studio_import_exemplars.import_manifest(owner, fallback, "P01")
    assert len(studio_import_exemplars.import_manifest(
        owner, fallback, "P01", "process-closeup")) == 1


# ── G1 门禁返修：预算兜底必须把 template / position / model 都拼进文本 ──────


@pytest.mark.parametrize("budget_chars", [600, 5000])
def test_tiny_budget_text_keeps_all_three_base_cards(budget_chars):
    result = retrieval.select_materials(
        tags(position="opening"), "wan", budget_chars=budget_chars)
    assert result["position"]["id"] == "scene-opening-hook"
    assert result["chars"] == len(result["text"]) <= budget_chars
    for key in ("template", "position", "model"):
        assert result[key] is not None
        assert f"【{result[key]['id']}】" in result["text"]


def test_tiny_budget_fallback_compose_keeps_three_base_card_groups(monkeypatch):
    calls = []
    original_compose = retrieval._compose

    def recording_compose(blocks):
        calls.append([list(group) for group in blocks])
        return original_compose(blocks)

    monkeypatch.setattr(retrieval, "_compose", recording_compose)
    result = retrieval.select_materials(
        tags(position="opening"), "wan", budget_chars=600)
    assert result["position"]["id"] == "scene-opening-hook"
    assert result["chars"] == len(result["text"]) <= 600

    assert len(calls) >= 2, [len(groups) for groups in calls]
    # 兜底分支 break 之后只剩一次最终重拼，所以倒数第二次调用就是兜底调用。
    # 实测兜底只传 3 组（走到兜底时 grammar/negative/exemplar 已裁空）；
    # 若实现改成传 6 组、后三组为空也接受。M2 只传 model 一组，会在这里变红。
    fallback = calls[-2]
    assert len(fallback) in (3, 6), [len(groups) for groups in calls]
    non_empty = [group for group in fallback if group]
    assert len(non_empty) == 3, [len(group) for group in fallback]
    fallback_text = original_compose(fallback)
    for key in ("template", "position", "model"):
        assert f"【{result[key]['id']}】" in fallback_text
    # 裁剪循环与最终重拼固定传 6 组。
    for groups in calls[:-2] + calls[-1:]:
        assert len(groups) == 6, [len(group) for group in groups]
    # 到兜底时 grammar/negative/exemplar 已全部裁空。
    assert result["grammar"] == []
    assert result["negatives"] == []
    assert result["exemplars"] == []
