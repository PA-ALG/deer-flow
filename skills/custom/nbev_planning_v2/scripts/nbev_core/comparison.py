"""
comparison.py — 同比对比（言行一致的关键）

智能体口径是"按去年同期同比、同比例缩放"。为了让这句话名副其实，
这里在测算本月之后，用同一个接口、传【参考月（去年同期）】再查一次，
拿到去年同期的实际基准（NBEV / 在职人力），算出本月目标相对去年同期的同比增长，
让结果里能真正展示"去年同期基准 → 本月目标（+X%）"。

设计为 best-effort：基准查询失败不影响主测算结果，comparison 标记为不可用即可。
各维度从返回里取"实际NBEV"的字段位置不同，这里按接口结构分别提取。
"""

from __future__ import annotations

from .api_client import call_calculation
from .errors import ApiError
from .obs import log


def _f(x, default=None):
    if x is None or x == "":
        return default
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _extract_actual_nbev(dimension: str, raw: dict) -> float | None:
    """从某维度的接口返回里提取'该月实际/预测 NBEV'（作为基准用）。"""
    if not raw:
        return None
    s = raw.get("calculationSummary", {}) or {}
    # 三维度 summary 里都有 predictedNbev；参考月是历史月，predictedNbev 即其实际达成基准
    return _f(s.get("predictedNbev"))


def _extract_onjob_hr(raw: dict) -> float | None:
    s = raw.get("calculationSummary", {}) or {}
    return _f(s.get("onJobHr"))


def build_comparison(dimension: str, *, request_id: str, payload: dict,
                     reference_month: str, current_target: float) -> dict:
    """
    用参考月再查一次同一接口，得到去年同期基准，算同比。
    返回 comparison dict（始终返回，失败时 available=False）。
    """
    base = {
        "available": False,
        "reference_month": reference_month,
        "reference_nbev": None,
        "current_target": current_target,
        "yoy_growth": None,        # 本月目标相对去年同期的增长率
        "reference_onjob_hr": None,
        "note": "",
    }
    # 用参考月构造基准查询 payload（只改 month，其余沿用）
    ref_payload = dict(payload)
    ref_payload["month"] = reference_month
    ref_payload["is_baseline_query"] = True   # 给后端的标记（若后端识别）
    try:
        raw = call_calculation(dimension, ref_payload)
    except ApiError as e:
        log("baseline_query_failed", level="WARNING", request_id=request_id,
            dimension=dimension, reference_month=reference_month, err=e.code)
        base["note"] = "去年同期基准暂时取不到，已跳过同比对比"
        return base
    except Exception as e:  # best-effort，绝不影响主流程
        log("baseline_query_exception", level="WARNING", request_id=request_id,
            dimension=dimension, err=str(e))
        base["note"] = "去年同期基准查询异常，已跳过同比对比"
        return base

    ref_nbev = _extract_actual_nbev(dimension, raw)
    if ref_nbev is None or ref_nbev <= 0:
        base["note"] = "去年同期无有效NBEV数据，无法计算同比"
        return base

    base["available"] = True
    base["reference_nbev"] = round(ref_nbev, 2)
    base["reference_onjob_hr"] = _extract_onjob_hr(raw)
    base["yoy_growth"] = round((current_target - ref_nbev) / ref_nbev, 4)
    return base
