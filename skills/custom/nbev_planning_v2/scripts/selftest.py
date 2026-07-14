#!/usr/bin/env python3
"""
selftest.py — nbev_planning_v2 自检脚本（随包交付，可重复回归）

不依赖真实后端：mock api_client，覆盖校验/澄清/护栏/不可达/渲染等关键路径。
用法：python scripts/selftest.py   （全部通过打印 ALL PASS）
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbev_core import planner          # noqa: E402
from nbev_core.render import render_results  # noqa: E402

_fails = []


import os as _os
import tempfile as _tempfile


def _fresh_store():
    """plan_store 用例隔离:每个需要独立缓存空间的用例调用一次。"""
    _os.environ["NBEV_OUTPUTS_DIR"] = _tempfile.mkdtemp(prefix="nbev-selftest-")


_fresh_store()  # 兜底:整个 selftest 绝不污染真实 outputs


def check(name, cond):
    print(("  ✅ " if cond else "  ❌ ") + name)
    if not cond:
        _fails.append(name)


def main():
    print("== 校验 / 澄清路径 ==")
    r = planner.plan(user_id="U1", dimensions=None, target_nbev=None)["results"][0]
    check("无维度无目标→needs_clarification", r["status"] == "needs_clarification")
    check("hint含两问", "维度" in r["error"]["hint"] and "NBEV" in r["error"]["hint"])

    r = planner.plan(user_id="U1", dimensions=["产品"], target_nbev=-5)["results"][0]
    check("负目标→TARGET_NBEV_NONPOSITIVE", r["error"]["error_code"] == "TARGET_NBEV_NONPOSITIVE")

    r = planner.plan(user_id="U1", dimensions=["收入"], target_nbev=6000)["results"][0]
    check("非法维度→DIMENSION_INVALID", r["error"]["error_code"] == "DIMENSION_INVALID")

    r = planner.plan(user_id="U1", dimensions=["产品"], target_nbev=6000, month="2026-7")["results"][0]
    check("非法月份→MONTH_FORMAT_INVALID", r["error"]["error_code"] == "MONTH_FORMAT_INVALID")

    r = planner.plan(user_id="U1", dimensions=["产品"], target_nbev=6000, month="2026-13-01")["results"][0]
    check("13月→MONTH_VALUE_INVALID", r["error"]["error_code"] == "MONTH_VALUE_INVALID")
    r = planner.plan(user_id="U1", dimensions=["产品"], target_nbev=6000, month="2026-07-01", reference_month="2025-13-01")["results"][0]
    check("非法参考月→拒绝", r["error"]["error_code"] == "MONTH_VALUE_INVALID")

    out = planner.plan(user_id="U1", dimensions=["产品"], target_nbev=6000)
    check("月份缺省=下月1号", out["org"]["month"] == "2026-07-01" or out["org"]["month"].endswith("-01"))
    check("机构写死05/深圳", out["org"]["org_id"] == "05" and out["org"]["org_name"] == "深圳")

    print("== 成功 / 护栏 / 不可达（mock 接口）==")

    def fake(dim, payload):
        assert payload["org_id"] == "05"
        if dim == "team":
            return {"calculationSummary": {"onJobHr": 22630, "predictedNbev": 6000.25,
                    "achievementRate": 1.0, "workforceBreakdown": [
                        {"diamondGroup": "双金钻", "hr": 184, "hrRatio": 0.008, "nbev": 2553, "nbevRatio": 0.425},
                        {"diamondGroup": "钻石及以上占比", "hrRatio": 0.043, "nbevRatio": 0.743}]}}
        if dim == "product":
            return {"calculationSummary": {"predictedNbev": 6012.5, "achievementRate": 1.0021},
                    "productPathEstimation": {"productDetails": [{"productName": "御享金越", "items": [
                        {"paymentPeriod": "10年缴", "activityHr": 15468, "activityRate": 0.68, "polNum": 24915,
                         "avgPolNumFyp": 341543, "nbevContribution": 2557.8, "contributionRatio": 0.42,
                         "activityRateStatus": 1, "avgPolNumFypStatus": 0, "isDistributed": True}]}]}}
        return {}  # customer empty -> unreachable

    planner.call_calculation = fake
    out = planner.plan(user_id="U1", dimensions=["产品", "队伍", "客户"], target_nbev=6000)
    st = {r["dimension"]: r["status"] for r in out["results"]}
    check("产品 success", st.get("product") == "success")
    check("队伍 success", st.get("team") == "success")
    check("客户空→target_unreachable", st.get("customer") == "target_unreachable")
    team = next(r for r in out["results"] if r["dimension"] == "team")
    check("C2 护栏识别偏离(74.3%)", team["validation"]["passed"] is False)
    prod = next(r for r in out["results"] if r["dimension"] == "product")
    check("C4 护栏识别触边", prod["validation"]["passed"] is False)

    md = render_results(out)
    check("MD 含表格分隔", "|---" in md or "|--:" in md)
    check("MD 含护栏提示", "护栏提示" in md)

    # 准确性：预测未达目标必须被识别并标红
    planner.call_calculation = lambda d, p: {
        "calculationSummary": {"predictedNbev": 4500, "achievementRate": 0.75, "onJobHr": 22000,
                               "workforceBreakdown": []},
        "productPathEstimation": {"productDetails": [{"productName": "X", "items": [
            {"paymentPeriod": "10年缴", "activityRateStatus": 0, "avgPolNumFypStatus": 0}]}]},
    } if d == "product" else {}
    out2 = planner.plan(user_id="U1", dimensions=["产品"], target_nbev=6000)
    prod2 = out2["results"][0]
    check("未达目标→ACH护栏不通过", any(
        c["code"] == "ACH_target_met" and not c["passed"] for c in prod2["validation"]["checks"]))
    check("未达目标→summary标红", "未达目标" in prod2["summary"])

    # 脏数据鲁棒性：脏字段不应使维度崩溃
    planner.call_calculation = lambda d, p: {"calculationSummary": {"predictedNbev": "脏", "achievementRate": None},
                                             "productPathEstimation": {"productDetails": []}} if d == "product" else {}
    out = planner.plan(user_id="U1", dimensions=["产品"], target_nbev=6000)
    check("脏数据不崩溃", out["results"][0]["status"] in ("success", "validation_error", "runtime_error"))

    print("== 业务月份节点 / 参考月 / 引导 ==")
    from nbev_core.month_context import derive_month_context
    check("1月→开门红", derive_month_context("2026-01-01").month_type == "开门红")
    check("4月→换挡", derive_month_context("2026-04-01").month_type == "换挡")
    check("5月→司庆", derive_month_context("2026-05-01").month_type == "司庆")
    check("7月→常规", derive_month_context("2026-07-01").month_type == "常规")
    check("参考月=去年同期", derive_month_context("2026-07-01").reference_month == "2025-07-01")
    check("换挡月=活动月", derive_month_context("2026-04-01").is_activity_month is True)
    check("司庆月=活动月", derive_month_context("2026-05-01").is_activity_month is True)
    check("开门红=活动月", derive_month_context("2026-01-01").is_activity_month is True)
    check("常规月≠活动月", derive_month_context("2026-07-01").is_activity_month is False)
    check("活动月需先确认参考月", derive_month_context("2026-04-01").needs_ref_confirm is True)
    check("自定义参考月后无需确认", derive_month_context("2026-04-01", "2024-07-01").needs_ref_confirm is False)
    check("节点带解释", "换挡" in derive_month_context("2026-04-01").type_desc)

    planner.call_calculation = fake
    # C方案：活动月首次发起 → 拦截，先确认参考月
    out = planner.plan(user_id="U1", dimensions=["产品"], target_nbev=6000, month="2026-04-01")
    check("活动月首次→needs_reference_confirm",
          out["results"][0]["status"] == "needs_reference_confirm")
    check("拦截态含 month_context", out["month_context"]["month_type"] == "换挡")
    # 已确认默认同比 → 直接测算
    out2 = planner.plan(user_id="U1", dimensions=["产品"], target_nbev=6000,
                        month="2026-04-01", confirm_reference=True)
    check("确认后→正常测算", out2["results"][0]["status"] in ("success", "target_unreachable", "runtime_error"))
    # 自定义参考月 → 直接测算，标记自定义
    out3 = planner.plan(user_id="U1", dimensions=["产品"], target_nbev=6000,
                        month="2026-04-01", reference_month="2024-09-01")
    check("自定义参考月→直接测算且标记", out3["month_context"]["custom_ref_used"] is True
          and out3["results"][0]["status"] != "needs_reference_confirm")
    # 常规月 → 不拦截
    out4 = planner.plan(user_id="U1", dimensions=["产品"], target_nbev=6000, month="2026-07-01")
    check("常规月→不拦截直接测算",
          out4["results"][0]["status"] != "needs_reference_confirm")

    print("== 开场播报指引 ==")
    from nbev_core.month_context import build_playbook
    pb = build_playbook("2026-04-01")
    g = pb["guidance"]
    check("指引含四块", all(k in g for k in
          ("what_node", "how_measure", "how_compare", "what_data_first")))
    check("换挡指引提同类活动月对比", "同类活动" in g["how_compare"])
    check("常规月指引说明同比口径",
          "同比" in build_playbook("2026-07-01")["guidance"]["how_measure"]
          and "常规" in build_playbook("2026-07-01")["guidance"]["how_measure"])
    check("指引建议先查画像", "画像" in g["what_data_first"])

    print("== 同比对比（言行一致）==")
    from nbev_core import comparison as _cmp

    def fake_yoy(dim, payload):
        if dim != "team":
            return {}
        if payload.get("is_baseline_query") or payload["month"] == "2025-07-01":
            return {"calculationSummary": {"predictedNbev": 5200, "achievementRate": 1.0,
                    "onJobHr": 21000, "workforceBreakdown": []}}
        return {"calculationSummary": {"predictedNbev": 6000, "achievementRate": 1.0,
                "onJobHr": 22000, "workforceBreakdown": [
                    {"diamondGroup": "钻石及以上占比", "nbevRatio": 0.85}]}}
    planner.call_calculation = fake_yoy
    _cmp.call_calculation = fake_yoy
    out = planner.plan(user_id="U1", dimensions=["队伍"], target_nbev=6000, month="2026-07-01")
    cmp = out["results"][0].get("comparison", {})
    check("结果含同比对比", cmp.get("available") is True)
    check("同比基准=去年同期实际", cmp.get("reference_nbev") == 5200)
    check("同比增长率正确", abs(cmp.get("yoy_growth") - (6000 - 5200) / 5200) < 1e-3)
    md = render_results(out)
    check("MD含同比基准表", "同比基准" in md and "去年同期实际" in md)

    # 基准查询失败 → best-effort，不影响主结果
    def fake_fail(dim, payload):
        if payload.get("is_baseline_query"):
            raise Exception("baseline boom")
        return {"calculationSummary": {"predictedNbev": 6000, "achievementRate": 1.0,
                "onJobHr": 22000, "workforceBreakdown": []}}
    planner.call_calculation = fake_fail
    _cmp.call_calculation = fake_fail
    _fresh_store()  # 隔离:防止命中上一用例同参数的缓存方案
    out2 = planner.plan(user_id="U1", dimensions=["队伍"], target_nbev=6000, month="2026-07-01")
    check("基准失败不影响主测算", out2["results"][0]["status"] == "success")
    check("基准失败标记不可用", out2["results"][0]["comparison"]["available"] is False)

    print("== 多环境配置 ==")
    import importlib
    from nbev_core import config as _cfg
    # 当前进程已加载的环境（取决于启动时 APP_ENV，缺省 dev）
    check("配置含 APP_ENV", _cfg.APP_ENV in ("dev", "stg", "prd"))
    check("配置含 API_BASE", isinstance(_cfg.API_BASE, str) and _cfg.API_BASE.startswith("http"))
    check("有效环境表", _cfg._VALID_ENVS == ("dev", "stg", "prd"))
    check("默认环境为dev", _cfg._DEFAULT_ENV == "dev")
    # 非法 APP_ENV 解析回退 dev
    import os
    _old = os.environ.get("APP_ENV")
    os.environ["APP_ENV"] = "prod1"
    check("非法APP_ENV回退dev", _cfg._resolve_env() == "dev")
    os.environ["APP_ENV"] = "prd"
    check("APP_ENV=prd正确解析", _cfg._resolve_env() == "prd")
    if _old is None:
        os.environ.pop("APP_ENV", None)
    else:
        os.environ["APP_ENV"] = _old

    # == 身份链(带外传递) ==
    print("== 身份链 / plan_store ==")
    from nbev_core.context import resolve_identity
    from nbev_core.errors import SkillError as _SE
    _saved = {k: os.environ.pop(k, None) for k in ("DEER_FLOW_USER_ID", "NBEV_USER_ID")}
    try:
        os.environ["DEER_FLOW_USER_ID"] = "u_platform"
        os.environ["NBEV_USER_ID"] = "u_dev"
        ident = resolve_identity("u_cli")
        check("平台注入优先", ident.user_id == "u_platform" and ident.source == "platform")
        os.environ.pop("DEER_FLOW_USER_ID")
        check("env 覆盖次之", resolve_identity("u_cli").source == "env")
        os.environ.pop("NBEV_USER_ID")
        check("CLI 兜底", resolve_identity("u_cli").source == "cli")
        try:
            resolve_identity(None)
            check("身份全缺→IDENTITY_MISSING", False)
        except _SE as e:
            check("身份全缺→IDENTITY_MISSING", e.code == "IDENTITY_MISSING")
        # 身份缺失经 plan() 应返回结构化信封,绝不向用户澄清身份
        out_noid = planner.plan(user_id=None, dimensions=["队伍"], target_nbev=1)
        check("plan 身份缺失→runtime/validation信封",
              out_noid["results"][0]["error"]["error_code"] == "IDENTITY_MISSING")
    finally:
        for k, v in _saved.items():
            if v is not None:
                os.environ[k] = v

    # == plan_store:落盘 / 读回 / 缓存 / latest ==
    from nbev_core import plan_store as _ps
    _fresh_store()
    def fake_ok(dim, payload):
        if payload.get("is_baseline_query"):
            raise Exception("no baseline")
        return {"calculationSummary": {"predictedNbev": 6000, "achievementRate": 1.0,
                "onJobHr": 22000, "workforceBreakdown": []}}
    planner.call_calculation = fake_ok
    _cmp.call_calculation = fake_ok
    out_a = planner.plan(user_id="U1", dimensions=["队伍"], target_nbev=6000, month="2026-07-01")
    check("成功测算产生 plan_id", bool(out_a.get("plan_id")))
    rec = _ps.load(out_a["plan_id"])
    check("plan 可读回", rec["plan_id"] == out_a["plan_id"])
    check("latest 指向最新", _ps.latest()["plan_id"] == out_a["plan_id"])
    out_b = planner.plan(user_id="U1", dimensions=["队伍"], target_nbev=6000, month="2026-07-01")
    check("同参数命中缓存", out_b.get("cached") is True and out_b.get("plan_id") == out_a["plan_id"])
    out_c = planner.plan(user_id="U1", dimensions=["队伍"], target_nbev=7000, month="2026-07-01")
    check("变参数不命中缓存", not out_c.get("cached") and out_c.get("plan_id") != out_a["plan_id"])
    md_pid = render_results(out_a)
    check("MD 展示方案编号", out_a["plan_id"] in md_pid)
    try:
        _ps.load("plan_不存在")
        check("载入不存在→PLAN_NOT_FOUND", False)
    except _SE as e:
        check("载入不存在→PLAN_NOT_FOUND", e.code == "PLAN_NOT_FOUND")

    print()
    if _fails:
        print(f"FAILED: {len(_fails)} 项 -> {_fails}")
        sys.exit(1)
    print("ALL PASS ✅")


if __name__ == "__main__":
    main()
