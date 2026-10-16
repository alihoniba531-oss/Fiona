"""Keep the frozen rereview rule and append the opt-in adaptation exception."""

from novel.agent_pool import get_agent


def test_rereview_preserves_frozen_sentence_and_points_to_the_opt_in_exception():
    frozen = '收到 previous_blocking_issues 表示复审：先逐条判断上一轮的阻断问题是否已经解决；新发现的问题只有属于上述三类中的严重情况，才可以判为阻断，否则 blocking=false。'
    exception = '或符合前述唯一例外（payload 含 adaptation_blocking=true 时的硬约束）'
    prompt = get_agent('reviewer')['system_prompt']
    assert frozen+'\n'+exception in prompt
    assert prompt.count(exception) == 1
