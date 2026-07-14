# @vendored-from skill_lib/envelope.py @sha256:f8a8d7aeafd3
# DO NOT EDIT —— 本文件是 vendor 副本;请修改 skill_lib/envelope.py 后运行
#               python tools/sync_skill_lib.py 重新同步(--check 供 CI 校验)。
"""
envelope.py — 统一返回信封(支柱5)

上游失败表达不一(兜底卡片/空 dict/异常),统一包成同一信封,
让 LLM 只读 status + summary + validation,不必从原始大 JSON 自由发挥。

status 枚举:
  success | needs_clarification | needs_reference_confirm |
  target_unreachable | validation_error | runtime_error | no_data
"""

from __future__ import annotations

from .errors import SkillError


def ok(*, request_id, dimension, data, summary, validation=None,
       table=None, plan_id=None, cached=False) -> dict:
    env = {
        "status": "success",
        "request_id": request_id,
        "dimension": dimension,
        "data": data,
        "validation": validation or {"passed": True, "checks": []},
        "error": None,
        "summary": summary,
    }
    if table is not None:
        env["table_md"] = table  # 预渲染的 Markdown 表格(供直接展示,支柱6)
    if plan_id:
        env["plan_id"] = plan_id
    if cached:
        env["cached"] = True
    return env


# 错误码 → status 的确定性映射(LLM 按 status 分支动作,不猜语义)
_STATUS_BY_CODE = {
    "TARGET_UNREACHABLE": "target_unreachable",
    "NEED_CLARIFY": "needs_clarification",
    "NEED_REFERENCE_CONFIRM": "needs_reference_confirm",
    "NO_DATA": "no_data",
    "PROFILE_EMPTY": "no_data",          # 画像:整体无数据
    "DIMENSION_DATA_EMPTY": "no_data",   # 画像:单维度无数据
}


def from_error(*, request_id, dimension, err: SkillError, summary: str | None = None) -> dict:
    status = _STATUS_BY_CODE.get(err.code)
    if status is None:
        status = "runtime_error" if err.retryable else "validation_error"
    return {
        "status": status,
        "request_id": request_id,
        "dimension": dimension,
        "data": None,
        "validation": {"passed": False, "checks": []},
        "error": err.to_error(),
        "summary": summary or err.message,
    }
