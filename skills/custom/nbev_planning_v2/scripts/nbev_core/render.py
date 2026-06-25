"""
render.py — 把规划结果信封渲染成美观的 Markdown（含表格）

为什么放在 skill 里渲染、而不是让 LLM 自由排版：
- 稳定：每次输出结构一致，不会忽长忽短；
- 准确：数字、占比、达成率的格式化集中处理，避免 LLM 口算出错；
- 高效：LLM 只需把这段 Markdown 原样呈现 + 适当口语化点评。

LLM 使用约定（见 SKILL.md）：优先直接展示本函数产出的 Markdown，
再在表格后用一两句话做要点提示（尤其是护栏未通过项）。
"""

from __future__ import annotations


def _pct(x) -> str:
    try:
        return f"{float(x) * 100:.1f}%"
    except (TypeError, ValueError):
        return "—"


def _num(x) -> str:
    try:
        f = float(x)
        return f"{f:,.0f}" if abs(f - round(f)) < 1e-9 else f"{f:,.2f}"
    except (TypeError, ValueError):
        return "—"


def _render_product(data: dict) -> str:
    est = data.get("productPathEstimation", {})
    rows = []
    for p in est.get("productDetails", []):
        pname = p.get("productName", "")
        for it in p.get("items", []):
            flag = ""
            if it.get("activityRateStatus") == 1 or it.get("avgPolNumFypStatus") == 1:
                flag = " ⚠️触顶"
            elif it.get("activityRateStatus") == -1 or it.get("avgPolNumFypStatus") == -1:
                flag = " ⚠️触底"
            rows.append(
                f"| {pname} | {it.get('paymentPeriod','')} | {_num(it.get('activityHr'))} | "
                f"{_pct(it.get('activityRate'))} | {_num(it.get('polNum'))} | "
                f"{_num(it.get('avgPolNumFyp'))} | {_num(it.get('nbevContribution'))} | "
                f"{_pct(it.get('contributionRatio'))}{flag} |"
            )
    head = (
        "| 产品 | 缴期 | 活动人数 | 活动率 | 件数 | 件均FYP | NBEV贡献(万) | 占比 |\n"
        "|---|---|--:|--:|--:|--:|--:|--:|"
    )
    return head + "\n" + "\n".join(rows) if rows else ""


def _render_team(data: dict) -> str:
    s = data.get("calculationSummary", {})
    rows = []
    for r in s.get("workforceBreakdown", []):
        rows.append(
            f"| {r.get('diamondGroup','')} | {_num(r.get('hr'))} | {_pct(r.get('hrRatio'))} | "
            f"{_num(r.get('avgNbev'))} | {_num(r.get('nbev'))} | {_pct(r.get('nbevRatio'))} |"
        )
    head = (
        "| 钻石人群 | 人力 | 人力占比 | 人均NBEV(万) | NBEV(万) | NBEV占比 |\n"
        "|---|--:|--:|--:|--:|--:|"
    )
    return head + "\n" + "\n".join(rows) if rows else ""


def _render_customer(data: dict) -> str:
    m = data.get("customerPathMatrix", {})
    # 九宫格：行=客价(A/BC/DEF/合计) 列=客温(冷却/低温/中高温/合计)
    temps = ["冷却", "低温", "中高温", "合计"]
    values = ["A", "BC", "DEF", "合计"]
    grid = {(it.get("customerValueTier"), it.get("customerTempTier")): it
            for it in m.get("items", [])}
    head = "| 客价＼客温 | " + " | ".join(temps) + " |\n|---" + "|--:" * len(temps) + "|"
    rows = []
    for v in values:
        cells = []
        for t in temps:
            it = grid.get((v, t))
            if it:
                c = it.get("custCount")
                nbev = it.get("nbev")
                cells.append(f"{_num(c)}人/{_num(nbev)}万")
            else:
                cells.append("—")
        rows.append(f"| {v} | " + " | ".join(cells) + " |")
    return head + "\n" + "\n".join(rows)


_RENDERERS = {"product": _render_product, "team": _render_team, "customer": _render_customer}
_DIM_CN = {"product": "产品", "team": "队伍", "customer": "客户"}


def render_results(out: dict) -> str:
    """把 plan() 的整体输出渲染为 Markdown 字符串。"""
    org = out.get("org", {})
    parts = []
    if org:
        parts.append(
            f"**机构：{org.get('org_name','')}（{org.get('org_id','')}）　测算月份：{org.get('month','')}**\n"
        )
    mc = out.get("month_context")

    # C方案：活动月先确认参考月（拦截态），用醒目区块呈现，引导用户选择口径
    results = out.get("results", [])
    if results and results[0].get("status") == "needs_reference_confirm":
        r0 = results[0]
        parts.append(f"### ⏸ 测算前确认：参考月口径")
        if mc:
            parts.append(
                f"检测到 **{org.get('month','')}** 属于 **【{mc.get('month_type','')}】** 活动节点"
                f"（{mc.get('type_desc','')}）。"
            )
            parts.append(
                f"\n规划的核心是**选对参考月再按目标同比例缩放**。默认按**同比**取参考月 "
                f"**{mc.get('reference_month','')}**（去年同期）。"
            )
        parts.append(
            f"\n> ⚠️ 但活动月的去年同期**未必是同类活动**（例如去年某月做了换挡、今年未必）。"
            f"这种情况内勤通常会筛过去24个月、或参考上季度均值，挑一个更合适的参考月。"
        )
        parts.append(
            f"\n**请确认参考月口径：**\n"
            f"1. 就按默认同比（{mc.get('reference_month','') if mc else ''}）继续测算；\n"
            f"2. 自定义参考月（告诉我参考哪个月，如\"参考去年9月\"）。"
        )
        return "\n".join(parts).strip()

    if mc:
        ref_label = "自定义" if mc.get("custom_ref_used") else "同比"
        line = (
            f"**业务节点：{mc.get('month_type','')}（{mc.get('type_desc','')}）　"
            f"参考月（{ref_label}）：{mc.get('reference_month','')}**"
        )
        parts.append(line + "\n")
    for r in out.get("results", []):
        dim = r.get("dimension", "-")
        cn = _DIM_CN.get(dim, dim)
        status = r.get("status")
        # 顶层错误（澄清/校验失败，dimension='-'）不挂维度标题，直接给提示
        if dim == "-":
            if status == "needs_clarification":
                parts.append(f"❓ {r.get('error',{}).get('hint','')}")
            else:
                err = r.get("error", {})
                parts.append(f"⚠️ {r.get('summary','')}" + (f"\n\n（{err.get('hint','')}）" if err.get('hint') else ""))
            parts.append("")
            continue
        parts.append(f"### {cn}达成测算")
        if status == "success":
            parts.append(r.get("summary", ""))
            # 同比对比：先把"去年同期基准 → 本月目标 (+X%)"摆出来，做到言行一致
            cmp = r.get("comparison")
            if cmp and cmp.get("available"):
                ref_m = cmp.get("reference_month", "")
                ref_nbev = cmp.get("reference_nbev")
                growth = cmp.get("yoy_growth")
                gtxt = (f"+{growth*100:.1f}%" if growth is not None and growth >= 0
                        else (f"{growth*100:.1f}%" if growth is not None else "—"))
                parts.append(
                    f"\n**同比基准（参考月 {ref_m}）**\n\n"
                    f"| 口径 | 去年同期实际 | 本月目标 | 同比 |\n"
                    f"|---|--:|--:|--:|\n"
                    f"| NBEV(万) | {ref_nbev:,.0f} | {cmp.get('current_target'):,.0f} | {gtxt} |"
                )
                parts.append(
                    f"\n> 本月以去年同期（{ref_m}）实际 {ref_nbev:,.0f} 万元为基准、"
                    f"同比例缩放到目标 {cmp.get('current_target'):,.0f} 万元（同比 {gtxt}）。"
                )
            elif cmp and cmp.get("note"):
                parts.append(f"\n> ℹ️ {cmp['note']}")
            body = _RENDERERS.get(dim, lambda d: "")(r.get("data") or {})
            if body:
                parts.append("\n" + body)
            # 护栏未过则补一行提示
            for c in r.get("validation", {}).get("checks", []):
                if not c.get("passed"):
                    label = {
                        "ACH_target_met": "预测未达成目标 NBEV",
                        "C2_shouzuan_nbev_ratio": "钻石及以上NBEV占比偏离 80%–90% 合理区间",
                        "C4_boundary_touch": c.get("detail", "部分缴期活动率/件均FYP已触边"),
                    }.get(c.get("code"), c.get("code"))
                    parts.append(f"\n> ⚠️ 护栏提示：{label}，建议复核后再上调。")
                    break
        elif status == "needs_clarification":
            parts.append(f"❓ {r.get('error',{}).get('hint','')}")
        elif status == "target_unreachable":
            parts.append(f"🚫 {r.get('summary','')}\n\n建议：{r.get('error',{}).get('hint','')}")
        else:
            err = r.get("error", {})
            parts.append(f"⚠️ {r.get('summary','')}\n\n（{err.get('hint','')}）")
        parts.append("")
    # 引导式下一步（取最相关的一条），供 agent 在回答结尾自然引导
    nas = out.get("next_actions") or []
    if nas:
        parts.append(f"---\n👉 下一步建议：{nas[0]['prompt']}")
    return "\n".join(parts).strip()
