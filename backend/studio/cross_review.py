"""交叉审核：一次导演调用只做一次付费请求，失败只记录，不影响主结果。"""
from __future__ import annotations

from fastapi import HTTPException

from .brain import BrainProviderError, InvalidBrainOutput, run_brain
from .config import get_settings

ADAPTATION_SCALES = ("忠实", "适度", "自由")
DEFAULT_MODEL = {"qwen": "qwen3.8-max"}


def _default_model(provider: str) -> str | None:
    if provider == "deepseek":
        return get_settings().deepseek_model
    return DEFAULT_MODEL.get(provider)

_FAILED_SUMMARY = {
    "queued": "审核尚未发出。",
    "running": "审核进行中。",
    "failed": "审核没有完成，主结果不受影响。",
    "invalid_output": "审核输出未通过校验，主结果不受影响。",
    "rejected": "审核调用被拒绝（未扣费），主结果不受影响。",
    "uncertain": "审核结果不确定，可能已扣费；主结果不受影响，请核对账单。",
    "cancelled": "审核已取消，主结果不受影响。",
    "released": "审核额度已释放，主结果不受影响。",
}


def build_inputs(source_text: str, shots, *, bible=None, continuity=None,
                 adaptation_scale: str = "适度", script=None) -> dict:
    """组装审核输入；只带确实提供的材料。"""
    if adaptation_scale not in ADAPTATION_SCALES:
        raise ValueError("改编尺度必须为忠实、适度或自由")
    inputs = {"source_text": source_text, "adaptation_scale": adaptation_scale, "shots": shots}
    if bible:
        inputs["bible"] = bible
    if continuity:
        inputs["continuity"] = continuity
    if script:
        inputs["script"] = script
    return inputs


def review_record(job: dict) -> dict | None:
    """把已发送（kind=brain）的审核任务转成对外的 R；占位任务不算已发送。"""
    if not isinstance(job, dict) or job.get("kind") != "brain" or job.get("task") != "cross_review":
        return None
    status = job.get("status") or "queued"
    output = job.get("output") if status == "succeeded" and isinstance(job.get("output"), dict) else None
    model = job.get("model")
    return {
        "provider": job.get("provider"),
        "model": model,
        "status": status,
        "verdict": output.get("verdict") if output else None,
        "summary": output.get("summary") if output else (
            job.get("error_message") or _FAILED_SUMMARY.get(status, "审核没有完成，主结果不受影响。")),
        "issues": list(output.get("issues") or []) if output else [],
    }


async def _expected_model(provider: str, username: str) -> str | None:
    expected = _default_model(provider)
    if expected is not None:
        return expected
    try:
        from .brain import provider_options
        options = await provider_options(username)
        option = next((item for item in options if item.get("id") == provider), None)
        model = option.get("model") if option else None
        return model if isinstance(model, str) and model else None
    except Exception:
        return None


async def review(shots, *, source_text: str, provider: str, username: str,
                 adaptation_scale: str = "适度", bible=None, continuity=None,
                 script=None) -> dict | None:
    """单发审核；provider=off 时返回 None。传输错误不重试。"""
    if provider == "off":
        return None
    inputs = build_inputs(source_text, shots, bible=bible, continuity=continuity,
                          adaptation_scale=adaptation_scale, script=script)
    try:
        result = await run_brain("cross_review", inputs, provider=provider, username=username)
    except BrainProviderError as exc:
        return {"provider": provider, "model": exc.model or await _expected_model(provider, username),
                "status": exc.status, "verdict": None, "summary": exc.message, "issues": []}
    except InvalidBrainOutput as exc:
        return {"provider": provider, "model": exc.reply.model or await _expected_model(provider, username),
                "status": "invalid_output", "verdict": None,
                "summary": "审核输出未通过校验，主结果不受影响。", "issues": []}
    except HTTPException as exc:
        return {"provider": provider, "model": await _expected_model(provider, username),
                "status": "rejected", "verdict": None, "summary": str(exc.detail), "issues": []}
    except Exception:
        # 异常正文可能带上游素材，只记录固定分类。
        return {"provider": provider, "model": await _expected_model(provider, username),
                "status": "uncertain", "verdict": None,
                "summary": _FAILED_SUMMARY["uncertain"], "issues": []}
    output = result.output
    return {"provider": provider, "model": result.model,
            "status": "succeeded", "verdict": output["verdict"], "summary": output["summary"],
            "issues": list(output["issues"])}
