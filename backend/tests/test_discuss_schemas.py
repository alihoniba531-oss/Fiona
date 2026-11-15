"""讨论群各步骤校验与截断的单元测试（规格 4.7）。

每个用例自带输入构造，不依赖其他测试文件或执行顺序。
"""

import copy

import pytest

from discuss import schemas
from novel.schemas import ValidationError


POOL = [
    {"role": "market", "name": "市场与行业", "does": "查市场规模与趋势"},
    {"role": "competitor", "name": "竞品与对标", "does": "查竞品定位与定价"},
    {"role": "user", "name": "用户与需求", "does": "查目标用户与反馈"},
]


def plan(**changes):
    value = {
        "title": "小团队怎么选调研工具",
        "goal": "比较三款调研工具的价格与适用场景，给出建议。",
        "deliverable": {"kind": "report", "outline": ["结论", "对比", "建议"]},
        "criteria": ["列出价格", "给出明确建议", "说明适用前提"],
        "picks": [
            {"role": "market", "focus": "查市场规模"},
            {"role": "competitor", "focus": "查竞品定价"},
        ],
        "questions": [],
    }
    value.update(changes)
    return value


def note(**changes):
    value = {
        "note": "市场规模在增长 [S1]，竞品定价差异明显 [S2]。",
        "key_points": [
            {"text": "市场仍在增长 [S1]", "refs": ["S1"]},
            {"text": "定价差异明显 [S2]", "refs": ["S2"]},
        ],
        "gaps": ["缺少小团队样本"],
    }
    value.update(changes)
    return value


def critique(**changes):
    value = {
        "objections": [{
            "target": "market",
            "type": "missing",
            "problem": "缺少小团队样本",
            "suggestion": "补查小团队的使用反馈",
        }],
        "counter_view": "增长数据可能只覆盖大客户。",
    }
    value.update(changes)
    return value


def decide(**changes):
    value = {
        "responses": [{"id": "O1", "action": "accept", "reason": "补查后再判断"}],
        "note_responses": [],
        "decision": "draft",
        "assignments": [],
        "brief_for_writer": "按结论、对比、建议三节写，明确适用前提。",
        "summary": "一条质疑成立，开始撰稿。",
    }
    value.update(changes)
    return value


def rework(**changes):
    value = {
        "assignments": [{"role": "market", "task": "补查小团队样本"}],
        "note_responses": [],
        "brief_for_writer": "把补查结果并入对比一节。",
        "summary": "安排补查。",
    }
    value.update(changes)
    return value


def accept(**changes):
    value = {
        "verdicts": [
            {"id": "C1", "pass": True, "evidence": "价格表齐全"},
            {"id": "C2", "pass": True, "evidence": "结论明确"},
            {"id": "C3", "pass": True, "evidence": "前提已写"},
        ],
        "citation_issues": [],
        "rework": [],
    }
    value.update(changes)
    return value


def test_refs_in_matches_pilot_syntax():
    """场景 9（4.7）：refs_in 取方括号内的 S 编号。"""
    assert schemas.refs_in("一 [S1] 二 [S12]，三 [S2]") == {"S1", "S2", "S12"}
    assert schemas.refs_in("[S1 S2] 和 [S3]") == {"S1", "S2", "S3"}
    assert schemas.refs_in("没有编号 S1 也不算") == set()
    assert schemas.refs_in("[不是编号]") == set()
    assert schemas.refs_in("[" + "x" * 40 + "S1" + "x" * 50 + "]") == set()
    assert schemas.refs_in(None) == set()


def test_check_plan_accepts_legal_plan_and_normalizes_names():
    """场景 4/21（4.7）：picks 用中文名字时归一成代号。"""
    value = plan()
    value["picks"][0]["role"] = "市场与行业"
    result = schemas.check_plan(value, role_pool=POOL)
    assert [pick["role"] for pick in result["picks"]] == ["market", "competitor"]
    assert result["title"] == value["title"]
    # 纯函数：不修改调用方传入的对象。
    assert value["picks"][0]["role"] == "市场与行业"


@pytest.mark.parametrize("change", [
    {"title": ""},
    {"goal": "   "},
    {"deliverable": {"kind": "article", "outline": ["a", "b", "c"]}},
    {"deliverable": {"kind": "report", "outline": ["a", "b"]}},
    {"criteria": ["只有一条"]},
    {"questions": ["1", "2", "3", "4"]},
    {"picks": [{"role": "market", "focus": "x"}]},
    {"picks": [{"role": "market", "focus": "x"}, {"role": "market", "focus": "y"}]},
    {"picks": [{"role": "unknown", "focus": "x"}, {"role": "competitor", "focus": "y"}]},
    {"picks": [{"role": "overall", "focus": "x"}, {"role": "competitor", "focus": "y"}]},
    {"picks": [{"role": "market", "focus": ""}, {"role": "competitor", "focus": "y"}]},
    {"picks": [{"role": "market"}, {"role": "competitor"}]},
])
def test_check_plan_rejects_bad_shape(change):
    """场景 21（4.7）：主持人点将的结构与取值范围。"""
    with pytest.raises(ValidationError):
        schemas.check_plan(plan(**change), role_pool=POOL)


def test_check_plan_fixed_members_must_match_exactly_and_allow_custom():
    """场景 21/23（4.7）：作者组队时 picks 必须不增不减，自定义代号合法。"""
    fixed = [
        {"role": "market", "name": "行业观察", "does": "作者写的行业职责"},
        {"role": "custom1", "name": "小探", "does": "作者写的自定义职责"},
    ]
    value = plan(picks=[
        {"role": "小探", "focus": "查定价"},
        {"role": "market", "focus": "查趋势"},
    ])
    result = schemas.check_plan(value, role_pool=fixed, fixed_members=fixed)
    # 归一后按作者组队的顺序排好。
    assert [pick["role"] for pick in result["picks"]] == ["market", "custom1"]

    extra = plan(picks=[
        {"role": "market", "focus": "查趋势"},
        {"role": "custom1", "focus": "查定价"},
        {"role": "competitor", "focus": "多出来的"},
    ])
    with pytest.raises(ValidationError):
        schemas.check_plan(extra, role_pool=fixed, fixed_members=fixed)
    missing = plan(picks=[{"role": "market", "focus": "查趋势"}])
    with pytest.raises(ValidationError):
        schemas.check_plan(missing, role_pool=fixed, fixed_members=fixed)


def test_check_plan_truncates_hard_limits():
    """场景 4/21（4.7）：标题 40、目标 400、完成标准 120、分工 300。"""
    value = plan(
        title="标" * 100,
        goal="目" * 500,
        criteria=["甲" * 200, "乙" * 200, "丙" * 200],
        picks=[
            {"role": "market", "focus": "分" * 500},
            {"role": "competitor", "focus": "工" * 500},
        ],
        deliverable={"kind": "report", "outline": ["一" * 400, "二", "三"]},
    )
    result = schemas.check_plan(value, role_pool=POOL)
    assert len(result["title"]) == 40
    assert len(result["goal"]) == 400
    assert [len(item) for item in result["criteria"]] == [120, 120, 120]
    assert [len(item["focus"]) for item in result["picks"]] == [300, 300]
    assert len(result["deliverable"]["outline"][0]) == 300


def test_check_queries_accepts_and_rejects():
    """场景 4（4.7）：queries 必须是 1–5 个非空字符串。"""
    assert schemas.check_queries({"queries": ["一个问题"]})["queries"] == ["一个问题"]
    assert schemas.check_queries({"queries": ["一", "二", "三", "四", "五"]})
    for bad in ({"queries": []}, {"queries": ["一"] * 6}, {"queries": [""]},
                {"queries": [1]}, {"queries": "问题"}, {}):
        with pytest.raises(ValidationError):
            schemas.check_queries(bad)


def test_check_note_accepts_and_rejects_unknown_refs():
    """场景 9（4.7）：笔记与要点只可引用已登记来源。"""
    result = schemas.check_note(note(), known={"S1", "S2"})
    assert result["note"].startswith("市场规模")
    with pytest.raises(ValidationError):
        schemas.check_note(note(note="引用了 [S9] 的发言。"), known={"S1", "S2"})
    bad_point = note()
    bad_point["key_points"][0]["refs"] = ["S9"]
    with pytest.raises(ValidationError):
        schemas.check_note(bad_point, known={"S1", "S2"})
    with pytest.raises(ValidationError):
        schemas.check_note(note(key_points=[]), known={"S1", "S2"})
    with pytest.raises(ValidationError):
        schemas.check_note(note(gaps=["a", "b", "c", "d"]), known={"S1", "S2"})
    with pytest.raises(ValidationError):
        schemas.check_note(note(note=""), known={"S1", "S2"})


def test_check_note_truncates_hard_limits():
    """场景 9（4.7）：笔记正文 2000、要点 300、缺口 150。"""
    value = note(
        note="正" * 2500 + " [S1]",
        key_points=[
            {"text": "要" * 400 + " [S1]", "refs": ["S1"]},
            {"text": "点" * 400 + " [S2]", "refs": ["S2"]},
        ],
        gaps=["缺" * 200],
    )
    result = schemas.check_note(value, known={"S1", "S2"})
    assert len(result["note"]) == 2000
    assert [len(point["text"]) for point in result["key_points"]] == [300, 300]
    assert len(result["gaps"][0]) == 150


def test_check_critique_normalizes_names_and_validates_targets():
    """场景 8/23（4.7）：质疑 target 可用成员名字、「整体」或「全体」。"""
    value = critique()
    value["objections"][0]["target"] = "市场与行业"
    result = schemas.check_critique(
        value, roles=["market", "competitor"],
        names={"市场与行业": "market", "竞品与对标": "competitor"})
    assert result["objections"][0]["target"] == "market"

    overall = critique()
    overall["objections"][0]["target"] = "全体"
    assert schemas.check_critique(
        overall, roles=["market"],
        names={})["objections"][0]["target"] == "overall"
    whole = critique()
    whole["objections"][0]["target"] = "整体"
    assert schemas.check_critique(
        whole, roles=["market"],
        names={})["objections"][0]["target"] == "overall"

    for bad in (
        critique(objections=[]),
        critique(objections=[{"target": "writer", "type": "missing",
                              "problem": "x", "suggestion": "y"}]),
        critique(objections=[{"target": "market", "type": "wrong",
                              "problem": "x", "suggestion": "y"}]),
        critique(objections=[{"target": "market", "type": "missing",
                              "problem": "", "suggestion": "y"}]),
        critique(counter_view=""),
    ):
        with pytest.raises(ValidationError):
            schemas.check_critique(bad, roles=["market"], names={})


def test_check_critique_truncates_hard_limits():
    """场景 8（4.7）：质疑的问题与建议各 300，反方观点 500。"""
    value = critique(counter_view="反" * 600)
    value["objections"][0]["problem"] = "问" * 400
    value["objections"][0]["suggestion"] = "建" * 400
    result = schemas.check_critique(value, roles=["market"], names={})
    assert len(result["objections"][0]["problem"]) == 300
    assert len(result["objections"][0]["suggestion"]) == 300
    assert len(result["counter_view"]) == 500


def test_check_decide_accepts_draft_and_research():
    """场景 7/8（4.7）：裁决两种走向的合法结构；角色名归一。"""
    draft = schemas.check_decide(
        decide(), roles=["market"], names={}, objection_ids=["O1"],
        can_research_more=False, note_ids=[])
    assert draft["decision"] == "draft" and draft["brief_for_writer"]

    research = decide(
        decision="research",
        assignments=[{"role": "市场与行业", "task": "补查小团队样本"}],
        brief_for_writer="",
    )
    result = schemas.check_decide(
        research, roles=["market"], names={"市场与行业": "market"},
        objection_ids=["O1"], can_research_more=True, note_ids=[])
    assert result["assignments"][0]["role"] == "market"


def test_check_decide_rejects_research_when_cannot_research_more():
    """场景 7：can_research_more 为假时 research 必须校验失败。"""
    research = decide(decision="research",
                      assignments=[{"role": "market", "task": "再查"}],
                      brief_for_writer="")
    with pytest.raises(ValidationError) as error:
        schemas.check_decide(
            research, roles=["market"], names={}, objection_ids=["O1"],
            can_research_more=False, note_ids=[])
    assert any("can_research_more" in item for item in error.value.errors)

    with pytest.raises(ValidationError):
        schemas.check_decide(
            decide(responses=[{"id": "O9", "action": "accept", "reason": "x"}]),
            roles=["market"], names={}, objection_ids=["O1"],
            can_research_more=True, note_ids=[])
    with pytest.raises(ValidationError):
        schemas.check_decide(
            decide(decision="research", assignments=[], brief_for_writer=""),
            roles=["market"], names={}, objection_ids=["O1"],
            can_research_more=True, note_ids=[])


def test_check_decide_requires_exact_note_responses():
    """场景 10：note_responses 必须对每条插话恰好回应一次，reply 非空。"""
    legal = decide(note_responses=[{"id": "N1", "reply": "让撰稿人补一句"}])
    schemas.check_decide(legal, roles=["market"], names={}, objection_ids=["O1"],
                         can_research_more=False, note_ids=["N1"])
    for bad in (
        decide(),
        decide(note_responses=[{"id": "N1", "reply": ""}]),
        decide(note_responses=[{"id": "N2", "reply": "对不上"}]),
        decide(note_responses=[{"id": "N1", "reply": "a"},
                               {"id": "N1", "reply": "b"}]),
    ):
        with pytest.raises(ValidationError):
            schemas.check_decide(bad, roles=["market"], names={}, objection_ids=["O1"],
                                 can_research_more=False, note_ids=["N1"])


def test_check_decide_truncates_hard_limits():
    """场景 10/17（4.7）：裁决理由 200、给撰稿人的要求 1200、小结 500、插话回应 300。"""
    value = decide(
        responses=[{"id": "O1", "action": "accept", "reason": "由" * 300}],
        brief_for_writer="要" * 2000,
        summary="结" * 700,
        note_responses=[{"id": "N1", "reply": "回" * 400}],
    )
    result = schemas.check_decide(value, roles=["market"], names={}, objection_ids=["O1"],
                                  can_research_more=False, note_ids=["N1"])
    assert len(result["responses"][0]["reason"]) == 200
    assert len(result["brief_for_writer"]) == 1200
    assert len(result["summary"]) == 500
    assert len(result["note_responses"][0]["reply"]) == 300


def test_check_draft_rules():
    """场景 9（4.7）：成果 <400 字、未知来源、网址都失败。"""
    body = "# 成果\n\n" + "结论有依据 [S1]。" * 40
    assert schemas.check_draft(body, known={"S1"}) == body

    for bad in (
        "太短 [S1]",
        "# 成果\n\n" + "结论 [S9]。" * 40,
        "# 成果\n\n" + "结论 [S1] 见 https://example.com/x。" * 40,
        "# 成果\n\n" + "结论 [S1] 见 http://example.com/x。" * 40,
    ):
        with pytest.raises(ValidationError):
            schemas.check_draft(bad, known={"S1"})


def test_check_draft_truncates_to_12000():
    """场景 9（4.7）：成果全文 12000。"""
    body = "# 成果\n\n" + "字" * 13000
    assert len(schemas.check_draft(body, known=set())) == 12000


def test_check_accept_rules_and_truncation():
    """场景 5（4.7）：verdicts 逐条对应、pass 布尔、citation_issues/rework 数组。"""
    criteria = [{"id": "C1", "text": "a"}, {"id": "C2", "text": "b"}]
    legal = accept(verdicts=[
        {"id": "C1", "pass": True, "evidence": "证" * 400},
        {"id": "C2", "pass": False, "evidence": "缺"},
    ], rework=["改" * 400])
    result = schemas.check_accept(legal, criteria=criteria, draft="draft")
    assert len(result["verdicts"][0]["evidence"]) == 300
    assert len(result["rework"][0]) == 300

    for bad in (
        accept(verdicts=[{"id": "C1", "pass": True, "evidence": "x"}]),
        accept(verdicts=[{"id": "C1", "pass": 1, "evidence": "x"},
                         {"id": "C2", "pass": True, "evidence": "y"}]),
        accept(citation_issues=None),
        accept(rework="不是数组"),
    ):
        with pytest.raises(ValidationError):
            schemas.check_accept(bad, criteria=criteria, draft="draft")


def test_check_rework_accepts_names_and_rejects_bad_tasks():
    """场景 8/23（4.7）：返工安排可用成员名字，任务 0–3 条。"""
    value = rework(assignments=[{"role": "竞品与对标", "task": "再查定价"}])
    result = schemas.check_rework(
        value, roles=["competitor"], names={"竞品与对标": "competitor"},
        note_ids=[])
    assert result["assignments"][0]["role"] == "competitor"
    assert schemas.check_rework(
        rework(assignments=[]), roles=["market"], names={}, note_ids=[])["assignments"] == []

    for bad in (
        rework(assignments=[{"role": "writer", "task": "x"}]),
        rework(assignments=[{"role": "market", "task": ""}]),
        rework(assignments=[{"role": "market", "task": "x"}] * 4),
        rework(brief_for_writer=""),
        rework(note_responses=[{"id": "N1", "reply": ""}]),
    ):
        with pytest.raises(ValidationError):
            schemas.check_rework(bad, roles=["market"], names={}, note_ids=["N1"])


def test_check_rework_truncates_hard_limits():
    """场景 8/17（4.7）：返工要求 300、给撰稿人的要求 1200。"""
    value = rework(
        assignments=[{"role": "market", "task": "任" * 400}],
        brief_for_writer="改" * 2000,
        summary="结" * 700,
        note_responses=[{"id": "N1", "reply": "回" * 400}],
    )
    result = schemas.check_rework(value, roles=["market"], names={}, note_ids=["N1"])
    assert len(result["assignments"][0]["task"]) == 300
    assert len(result["brief_for_writer"]) == 1200
    assert len(result["summary"]) == 500
    assert len(result["note_responses"][0]["reply"]) == 300


def test_check_brief_rules_and_truncation():
    """场景 11（4.7）：brief 的 answers.q 在提问序号内，context 600。"""
    legal = schemas.check_brief(
        {"context": "背" * 700, "answers": [{"q": 1, "answer": "答" * 700}],
         "ask_owner": [2]}, question_count=2)
    assert len(legal["context"]) == 600
    assert len(legal["answers"][0]["answer"]) == 600
    assert schemas.check_brief({"context": "背景", "answers": [], "ask_owner": []},
                               question_count=0)

    for bad in (
        {"context": "", "answers": [], "ask_owner": []},
        {"context": "背景", "answers": [{"q": 3, "answer": "超范围"}], "ask_owner": []},
        {"context": "背景", "answers": [{"q": 0, "answer": "超范围"}], "ask_owner": []},
        {"context": "背景", "answers": [{"q": True, "answer": "布尔"}], "ask_owner": []},
        {"context": "背景", "answers": [{"q": 1, "answer": ""}], "ask_owner": []},
        {"context": "背景", "answers": [], "ask_owner": ["2"]},
        {"context": "背景", "answers": "不是数组", "ask_owner": []},
    ):
        with pytest.raises(ValidationError):
            schemas.check_brief(bad, question_count=2)


def test_check_view_rules_and_truncation():
    """场景 11（4.7）：view 的 comment 非空，must_fix 0–3 条，意见 600。"""
    legal = schemas.check_view(
        {"comment": "意" * 700, "must_fix": ["修" * 700]})
    assert len(legal["comment"]) == 600
    assert len(legal["must_fix"][0]) == 600
    assert schemas.check_view({"comment": "可以", "must_fix": []})
    for bad in (
        {"comment": "", "must_fix": []},
        {"comment": "可以", "must_fix": [""]},
        {"comment": "可以", "must_fix": ["一", "二", "三", "四"]},
        {"comment": "可以", "must_fix": "不是数组"},
    ):
        with pytest.raises(ValidationError):
            schemas.check_view(bad)


def test_validation_errors_do_not_echo_model_text():
    """场景 9/10（4.7）：错误文字点名字段和合法取值，不回显模型输出。"""
    marker = "MODEL_ONLY_TEXT_SHOULD_NOT_ECHO"
    cases = [
        (schemas.check_plan, {"title": marker, "goal": marker,
                              "deliverable": {"kind": marker, "outline": [marker]},
                              "criteria": marker, "picks": marker,
                              "questions": marker}, {"role_pool": POOL}),
        (schemas.check_critique, critique(objections=[{
            "target": marker, "type": marker, "problem": marker,
            "suggestion": marker}], counter_view=marker),
         {"roles": ["market"], "names": {}}),
        (schemas.check_decide, decide(decision=marker, brief_for_writer=marker),
         {"roles": ["market"], "names": {}, "objection_ids": ["O1"],
          "can_research_more": False, "note_ids": []}),
        (schemas.check_accept, accept(verdicts=[
            {"id": "C1", "pass": marker, "evidence": marker}]),
         {"criteria": [{"id": "C1", "text": "a"}], "draft": "d"}),
    ]
    for function, value, kwargs in cases:
        with pytest.raises(ValidationError) as error:
            function(copy.deepcopy(value), **kwargs)
        assert marker not in str(error.value)
