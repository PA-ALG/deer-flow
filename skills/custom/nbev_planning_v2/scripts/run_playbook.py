#!/usr/bin/env python3
"""
run_playbook.py — 节点作战指引（开场播报用 · 不测算、只给指引）

用途：用户一进来或表达"想做规划/看看这个月怎么做"时，先调本脚本拿到
当前月的【节点指引】——是什么节点、为什么、怎么测算、怎么对比、先查什么数据。
这是"开场播报 + 全程引导"产品形态的入口，不依赖目标/维度，零门槛。

用法：
  python run_playbook.py [--month 2026-07-01] [--format md]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbev_core.month_context import build_playbook  # noqa: E402
from nbev_core.validators import normalize_month     # noqa: E402
from nbev_core.errors import SkillError              # noqa: E402


def render_md(pb: dict) -> str:
    g = pb["guidance"]
    flag = "活动节点" if pb["is_activity_month"] else "常规节点"
    lines = [
        f"## 本月规划指引 · {pb['month']}（{pb['month_type']}）",
        f"",
        f"**当前节点**：{g['what_node']}　【{flag}】",
        f"",
        f"**怎么测算**：{g['how_measure']}",
        f"",
        f"**怎么对比**：{g['how_compare']}",
        f"",
        f"**建议先查的数据**：{g['what_data_first']}",
    ]
    if pb["is_activity_month"]:
        lines += [
            "",
            f"> ⚠️ 这是活动月，正式测算前我会先和你确认参考月口径（默认同比 {pb['reference_month']}，或自定义）。",
        ]
    lines += [
        "",
        "---",
        "👉 下一步：要我先帮你查现状画像（队伍/客户/产品），还是直接做某条路径的达成测算？告诉我目标 NBEV 和想看的维度即可。",
    ]
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description="节点作战指引（开场播报）")
    p.add_argument("--user-id", "-uid", default=None,
                   help="本地调试兜底;生产身份由平台带外注入,无需传参")
    p.add_argument("--month", "-m", default=None, help="YYYY-MM-01，缺省=下月（规划口径）")
    p.add_argument("--format", "-f", choices=["json", "md"], default="json")
    a = p.parse_args()

    try:
        mon = normalize_month(a.month)  # 规划口径：缺省下月
    except SkillError as e:
        out = {"status": "validation_error",
               "error": {"error_code": e.code, "message": e.message, "hint": e.hint}}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    pb = build_playbook(mon)
    if a.format == "md":
        print(render_md(pb))
    else:
        print(json.dumps({"status": "success", "playbook": pb},
                         ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
