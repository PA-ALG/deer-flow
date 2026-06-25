"""
month_context.py — 业务月份类型判定 + 参考月推导（C方案：活动月先确认参考月）

把内勤"选参考月"的专业判断编码成确定性逻辑（harness：从 LLM 自觉搬到代码）。

业务节点定义（平安）：
- 开门红：1-3月（首爆1/1，覆盖Q1），全年冲规模关键期 —— 活动月
- 换挡：  4月（开门红转常态的过渡期）           —— 活动月
- 司庆：  5月（5/27 集团成立日，司庆版专属产品）  —— 活动月
- 常规：  6-12月，常态化业务推动期             —— 非活动月

参考月口径：统一默认【同比】（去年同期），最有参考价值。
C方案：常规月直接按同比测算；活动月去年同期未必同类活动，先确认参考月口径再测算。
"""

from __future__ import annotations

from dataclasses import dataclass


# 节点 -> 给用户看的解释（让"为什么是这个节点"可见）
_TYPE_DESC = {
    "开门红": "1-3月开门红，全年冲规模关键期",
    "换挡": "4月换挡，开门红转常态的过渡期",
    "司庆": "5月司庆（5/27集团成立日），常推司庆版专属产品",
    "常规": "6-12月常态化业务推动期",
}

# 活动月集合（这些月份去年同期未必是同类活动，需先确认参考月）
_ACTIVITY_TYPES = {"开门红", "换挡", "司庆"}


def classify_month_type(month_num: int) -> str:
    if month_num in (1, 2, 3):
        return "开门红"
    if month_num == 4:
        return "换挡"
    if month_num == 5:
        return "司庆"
    return "常规"  # 6-12


def _yoy(month: str) -> str:
    """去年同期：YYYY-MM-01 -> (YYYY-1)-MM-01。"""
    y, m, _ = month.split("-")
    return f"{int(y) - 1:04d}-{m}-01"


def _prev_month(month: str) -> str:
    """上个月：YYYY-MM-01 -> 上月1号。"""
    y, m, _ = month.split("-")
    y, m = int(y), int(m)
    if m == 1:
        return f"{y - 1:04d}-12-01"
    return f"{y:04d}-{m - 1:02d}-01"


# 每个节点的"作战指引"模板（结构化骨架，供 agent 照着说）
def build_playbook(month: str, reference_month: str | None = None) -> dict:
    """
    生成当前月的【节点作战指引】：是什么节点、为什么、怎么测算、怎么对比、先查什么数据。
    这是给 agent 开场播报 + 全程引导用的结构化骨架（harness：业务逻辑落到代码，不靠 LLM 记忆）。
    """
    mnum = int(month.split("-")[1])
    mtype = classify_month_type(mnum)
    is_activity = mtype in _ACTIVITY_TYPES
    yoy = _yoy(month)
    custom_used = reference_month is not None
    ref = reference_month or yoy

    # 怎么测算：参考月口径建议
    if is_activity:
        how_measure = (
            f"{mtype}属于活动节点，去年同期（{yoy}）未必是同类活动。"
            f"建议先确认参考月口径：①默认同比（{yoy}）；"
            f"②若去年同期非同类活动，可筛过去24个月挑同类活动月，或参考上季度均值。"
        )
        ref_note = f"默认同比 {yoy}，但活动月建议先与内勤确认"
    else:
        how_measure = (
            f"当前是【{mtype}】月（常态化推动期）。这种月份业务相对平稳，"
            f"测算口径为：以去年同期（{yoy}）为基准参考月，按目标与去年同期"
            f"做同比例缩放，得出本月各路径的达成方案。常规月无需特别调整参考月，同比最稳。"
        )
        ref_note = f"默认同比 {yoy}（常规月按此即可）"

    # 怎么对比
    how_compare = (
        f"主对比去年同期（{yoy}）看同比；"
        f"辅助参考上月（{_prev_month(month)}）看环比走势。"
        + ("活动月还应与去年同类活动月对比，而非简单同比。" if is_activity else "")
    )

    # 先查什么数据（画像建议）
    what_data = (
        "建议先查现状画像作为测算基线："
        "①队伍画像（钻石结构/在职人力）→ 支撑队伍路径；"
        "②客户画像（客温×客价九宫格）→ 支撑客户路径；"
        "③产品画像（产品×缴期NBEV排序）→ 支撑产品路径。"
        "可先看与本月主推方向最相关的一条。"
    )

    return {
        "month": month,
        "month_type": mtype,
        "type_desc": _TYPE_DESC.get(mtype, mtype),
        "is_activity_month": is_activity,
        "reference_month": ref,
        "reference_note": ref_note,
        "custom_ref_used": custom_used,
        # 四块作战指引（agent 照此播报/引导）
        "guidance": {
            "what_node": f"当前 {month} 是【{mtype}】（{_TYPE_DESC.get(mtype, mtype)}）",
            "how_measure": how_measure,
            "how_compare": how_compare,
            "what_data_first": what_data,
        },
    }


@dataclass(frozen=True)
class MonthContext:
    month: str            # 当前测算月 YYYY-MM-01
    month_type: str       # 开门红/换挡/司庆/常规
    type_desc: str        # 节点解释（给用户看）
    reference_month: str  # 参考月 YYYY-MM-01（默认同比=去年同期）
    is_activity_month: bool   # 是否活动月
    custom_ref_used: bool     # 是否使用了用户自定义参考月
    needs_ref_confirm: bool   # 是否需要"先确认参考月再测算"（C方案核心信号）


def derive_month_context(month: str, reference_month: str | None = None) -> MonthContext:
    """
    根据测算月推导业务节点类型与参考月。
    reference_month 显式传入时优先用它（内勤自定义口径，如筛过去24个月/上季度均值后的某月）。

    needs_ref_confirm 的判定（C方案）：是活动月 且 用户尚未自定义参考月 → True。
    planner 据此决定"先确认参考月口径，确认后再测算"。
    """
    mnum = int(month.split("-")[1])
    mtype = classify_month_type(mnum)
    is_activity = mtype in _ACTIVITY_TYPES
    custom_used = reference_month is not None
    ref = reference_month or _yoy(month)
    return MonthContext(
        month=month,
        month_type=mtype,
        type_desc=_TYPE_DESC.get(mtype, mtype),
        reference_month=ref,
        is_activity_month=is_activity,
        custom_ref_used=custom_used,
        needs_ref_confirm=is_activity and not custom_used,
    )
