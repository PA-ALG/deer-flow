"""
next_actions.py — 引导式"下一步"建议生成（让 agent 的结尾引导有据可依）

产品形态要求像 Claude 一样一步步引导用户完成 NBEV 测算。
引导若全靠 LLM 自由发挥会跑偏，故由代码根据结果状态确定性地生成候选下一步，
LLM 在回答结尾据此给出 1 个最自然的引导。

返回的 next_actions 是有序候选（最相关在前），每项含 code + prompt（给用户看的引导话术）。
"""

from __future__ import annotations

_DIM_CN = {"product": "产品", "team": "队伍", "customer": "客户"}
_ALL = ["product", "team", "customer"]


def build_next_actions(results: list[dict], requested_dims: list[str],
                       month_ctx) -> list[dict]:
    actions: list[dict] = []

    done_dims = [r["dimension"] for r in results if r["dimension"] in _ALL]
    success_dims = [r["dimension"] for r in results if r.get("status") == "success"]
    has_unreachable = any(r.get("status") == "target_unreachable" for r in results)
    # 任一维度未达标（ACH 护栏未过）
    under_target = any(
        any(c.get("code") == "ACH_target_met" and not c.get("passed")
            for c in r.get("validation", {}).get("checks", []))
        for r in results
    )

    # 1) 活动月参考口径提示（最专业、最该先问）
    if month_ctx is not None and getattr(month_ctx, "is_activity_month", False) \
            and not getattr(month_ctx, "custom_ref_used", False):
        actions.append({
            "code": "confirm_reference_month",
            "prompt": f"当前是{month_ctx.month_type}活动月，去年同期未必是同类活动节点。"
                      f"要不要自定义参考月（如筛过去24个月或参考上季度均值），而不是默认同比？",
        })

    # 2) 未达标 → 引导下调或反推
    if under_target or has_unreachable:
        actions.append({
            "code": "adjust_target",
            "prompt": "预测未完全达成目标。要我按当前可达上限，帮您反推一个更现实的建议目标吗？",
        })

    # 3) 补齐其他路径，凑成完整规划
    remaining = [d for d in _ALL if d not in done_dims]
    if remaining and success_dims:
        cn = "、".join(_DIM_CN[d] for d in remaining)
        actions.append({
            "code": "complete_other_paths",
            "prompt": f"要不要再看{cn}路径，凑成产品/客户/队伍三条路径的完整规划？",
        })

    # 4) 三条路径都做完 → 引导对比/沉淀
    if success_dims and not remaining:
        actions.append({
            "code": "compare_paths",
            "prompt": "三条路径都测完了。要不要我把它们汇总对比，看哪条路径达成压力最小？",
        })

    # 5) 兜底：成功但无其他引导 → 引导查现状画像佐证
    if success_dims and len(actions) == 0:
        actions.append({
            "code": "view_profile",
            "prompt": "要不要对照看下该机构当前的现状画像，验证这个规划是否贴合实际？",
        })

    return actions
