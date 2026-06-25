"""
planner.py — 规划编排核心（与 CLI 解耦，便于被 DeerFlow 直接 import 调用）

流程：校验入参 → 解析机构 → 构造共享 payload → 按固定顺序逐维度调用 → 统一信封汇总。
任何一步失败都返回结构化信封，绝不抛裸异常给上层。
"""

from __future__ import annotations

import uuid

from . import config, envelope
from .api_client import call_calculation
from .errors import SkillError, ApiError, NeedClarify
from .interpreters import INTERPRETERS
from .org_context import resolve_org_context
from .month_context import derive_month_context
from .comparison import build_comparison
from .next_actions import build_next_actions
from .obs import log
from .validators import (
    normalize_month, validate_target_nbev, validate_dimensions, validate_ratio,
)


def _build_payload(org, target_nbev, month, request_id, session_id, opts, month_ctx) -> dict:
    payload = {
        "request_id": request_id,
        "session_id": session_id,
        "org_id": org.org_id,       # 来自 resolve_org_context（当前写死05/深圳）
        "org_name": org.org_name,
        "target_nbev": target_nbev,
        "month": month,
        "month_type": month_ctx.month_type,          # 业务节点：开门红/换挡/司庆/常规
        "reference_month": month_ctx.reference_month,  # 参考月（默认同比；接口若自算则作解释信息）
        "combination": opts.get("combination") or [],
    }
    for k in ("max_product_activity_rate", "max_avg_fyp_range", "max_double_gold_diamond_ratio"):
        if opts.get(k) is not None:
            payload[k] = opts[k]
    return payload


def _month_ctx_dict(mc) -> dict:
    """把 MonthContext 转成对外 dict（供 render / agent 读取）。"""
    return {
        "month_type": mc.month_type,
        "type_desc": mc.type_desc,
        "reference_month": mc.reference_month,
        "is_activity_month": mc.is_activity_month,
        "custom_ref_used": mc.custom_ref_used,
        "needs_ref_confirm": mc.needs_ref_confirm,
    }


def plan(
    *,
    user_id: str,
    dimensions,
    target_nbev,
    month=None,
    request_id=None,
    session_id=None,
    **opts,
) -> dict:
    """
    主入口。返回 {request_id, org, results:[信封,...]}。
    opts 可含 combination / max_product_activity_rate / max_avg_fyp_range /
    max_double_gold_diamond_ratio。
    """
    request_id = request_id or f"req-{uuid.uuid4().hex[:12]}"
    session_id = session_id or f"sess-{uuid.uuid4().hex[:12]}"
    log("plan_start", request_id=request_id, dimensions=dimensions, target_nbev=target_nbev)

    # 0) 必填澄清：维度与目标NBEV缺失时，返回 needs_clarification（不报错、不猜测）
    missing = []
    if not dimensions:
        missing.append("dimensions")
    if target_nbev in (None, ""):
        missing.append("target_nbev")
    if missing:
        q = []
        if "dimensions" in missing:
            q.append("想从哪个维度看达成（产品/客户/队伍，可多选）")
        if "target_nbev" in missing:
            q.append("目标 NBEV 是多少万元")
        return {
            "request_id": request_id,
            "results": [envelope.from_error(
                request_id=request_id, dimension="-",
                err=NeedClarify(
                    "缺少必要信息，无法开始测算：" + "、".join(missing),
                    hint="请向用户澄清：" + "；".join(q),
                    fields=missing,
                ),
            )],
            "next_actions": [],
        }

    # 1) 入参校验（失败→单条结构化错误信封）
    try:
        dims = validate_dimensions(dimensions)
        tgt = validate_target_nbev(target_nbev)
        mon = normalize_month(month)
        ref = opts.get("reference_month")
        if ref:  # 自定义参考月也要校验格式与合法月份
            ref = normalize_month(ref)
        validate_ratio("max_product_activity_rate", opts.get("max_product_activity_rate"))
        validate_ratio("max_avg_fyp_range", opts.get("max_avg_fyp_range"))
        validate_ratio("max_double_gold_diamond_ratio", opts.get("max_double_gold_diamond_ratio"))
    except SkillError as e:
        return {
            "request_id": request_id,
            "results": [envelope.from_error(request_id=request_id, dimension="-", err=e)],
            "next_actions": [],
        }

    # 2) 机构解析（当前恒为 05/深圳；未来换接口不动此处调用）
    org = resolve_org_context(user_id)

    # 2.5) 业务月份上下文：判定节点类型 + 推导参考月（默认同比，可被 reference_month 覆盖）
    month_ctx = derive_month_context(mon, ref)

    # 2.6) C方案核心：活动月且未自定义/未确认参考月 → 先确认参考月口径，再测算
    # confirm_reference=True 表示用户已确认"就按默认同比"，此时跳过拦截直接测算。
    confirmed = bool(opts.get("confirm_reference"))
    if month_ctx.needs_ref_confirm and not confirmed:
        log("plan_need_ref_confirm", request_id=request_id, month=mon,
            month_type=month_ctx.month_type)
        return {
            "request_id": request_id,
            "org": {"org_id": org.org_id, "org_name": org.org_name, "month": mon},
            "month_context": _month_ctx_dict(month_ctx),
            "results": [{
                "status": "needs_reference_confirm",
                "request_id": request_id,
                "dimension": "-",
                "data": None,
                "error": {
                    "error_code": "NEED_REFERENCE_CONFIRM",
                    "message": (
                        f"当前 {mon} 属于【{month_ctx.month_type}】活动节点"
                        f"（{month_ctx.type_desc}）。默认参考月按同比取 {month_ctx.reference_month}，"
                        f"但活动月去年同期未必是同类活动。"
                    ),
                    "hint": (
                        f"请先与内勤确认参考月口径："
                        f"①按默认同比（{month_ctx.reference_month}）继续测算；"
                        f"②自定义参考月（如筛过去24个月、参考上季度均值后的某月）。"
                        f"确认①则带 confirm_reference 再次调用；确认②则用 --reference-month 传入。"
                    ),
                    "fields": ["reference_month"],
                    "retryable": False,
                },
                "summary": (
                    f"⏸ {mon} 是【{month_ctx.month_type}】活动月。测算前请先确认参考月："
                    f"默认同比为 {month_ctx.reference_month}，"
                    f"活动月去年同期未必同类活动，是否需要自定义参考月？"
                ),
            }],
            "next_actions": [{
                "code": "confirm_reference_month",
                "prompt": f"{mon} 是{month_ctx.month_type}活动月，默认参考去年同期"
                          f"（{month_ctx.reference_month}）。要按默认同比测算，还是自定义参考月？",
            }],
        }

    payload = _build_payload(org, tgt, mon, request_id, session_id, opts, month_ctx)

    # 3) 按固定顺序逐维度调用（产品→队伍→客户）
    order = [d for d in config.DIMENSION_ORDER if d in dims]
    results = []
    for dim in order:
        try:
            raw = call_calculation(dim, payload)
            res = INTERPRETERS[dim](request_id, tgt, raw)
        except ApiError as e:
            results.append(envelope.from_error(request_id=request_id, dimension=dim, err=e))
            continue
        except Exception as e:  # 兜底：绝不让裸异常冒泡
            results.append(envelope.from_error(
                request_id=request_id, dimension=dim,
                err=ApiError("CALCULATION_EXCEPTION", f"{dim}维度测算异常：{e}",
                             hint="请稍后重试，若持续失败请反馈", retryable=True),
            ))
            continue
        # 3.5) 同比对比：测算成功后，用参考月再查一次拿去年同期基准（best-effort）
        if res.get("status") == "success" and config.ENABLE_YOY_COMPARE:
            res["comparison"] = build_comparison(
                dim, request_id=request_id, payload=payload,
                reference_month=month_ctx.reference_month, current_target=tgt,
            )
        results.append(res)

    statuses = {r["dimension"]: r["status"] for r in results}
    next_actions = build_next_actions(results, order, month_ctx)
    log("plan_done", request_id=request_id, org_id=org.org_id, month=mon,
        month_type=month_ctx.month_type, statuses=statuses)
    return {
        "request_id": request_id,
        "org": {"org_id": org.org_id, "org_name": org.org_name, "month": mon},
        "month_context": _month_ctx_dict(month_ctx),
        "results": results,
        "next_actions": next_actions,
    }
