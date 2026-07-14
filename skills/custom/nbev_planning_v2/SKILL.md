---
name: nbev_planning_v2
version: 2.2.0
author: marketing-planning-team
compatibility: deerflow>=2.0
description: 万能营销规划（从零新建达成路径）。当内勤需要根据目标NBEV，从产品、客户、队伍三个维度规划"如何达成"时使用。触发场景：万能营销规划、新建规划、达成路径、NBEV怎么达成、产品/客户/队伍达成测算、这个月怎么做规划、从哪开始。开场可先用 run_playbook.py 播报当前业务节点（开门红/换挡/司庆/常规）及"怎么测算/怎么对比/先查什么数据"的指引。能力边界——本skill只做"从零新建"；若用户在已有规划上调整某个数值（"把X调到Y"），改用 nbev_modify_v2；若用户只想看现状画像，改用 nbev_profile_v2。测算维度（产品/客户/队伍）与目标NBEV为必填，缺失须先向用户澄清；测算月份缺省取下个月1号。机构信息由登录用户自动解析，无需也不应向用户索取 org_id/org_name。
---

# 万能营销规划 Skill（达成测算 · 从零新建）

围绕目标 NBEV，从 **产品 / 客户 / 队伍** 三维度生成达成路径。底层是三个同构的达成测算接口，通过 `scripts/run_planning.py` 统一编排。

## 第〇步：开场播报节点指引（强烈建议先做）

当用户表达"想做这个月的规划/这个月怎么搞/从哪开始"等开场意图，或刚进入规划话题时，**先调用节点指引脚本做一次播报**，告诉内勤：当前是什么节点、该怎么测算、怎么对比、先查什么数据。这是让内勤显式感受到业务引导的关键。

```bash
python scripts/run_playbook.py [-m YYYY-MM-01] --format md
```

输出已是组织好的 Markdown（节点+怎么测算+怎么对比+建议先查数据+下一步），**直接呈现**，再顺着结尾的"下一步"引导用户给出目标NBEV与维度。不必先有目标也能播报（缺省按下月）。

> **常规月也要播报**：无论活动月还是常规月都做这次播报。常规月也是一种节点，要明确告诉内勤"当前是【常规】月，按去年同期同比、同比例缩放即可"，让口径透明。区别仅在于：常规月播报完直接进入测算；活动月正式测算前还有一轮参考月确认。

## 第一步：判断是否该用本 skill

| 用户意图 | 处理 |
|----------|------|
| "怎么达成6000万 / 做产品达成路径 / 看队伍如何达成" | ✅ 用本 skill |
| "把银钻调到45人 / 活动率改到6%"（在已有规划上改某值） | ❌ 转 `nbev_modify_v2` |
| "看当前队伍画像 / 客户结构现状" | ❌ 转 `nbev_profile_v2` |

## 第二步：必填澄清（仅这两项，其余直接用默认）

只有以下**两项硬必填**缺失时才澄清，**一次只补问缺的那一项，已知的绝不重复问**；其余信息一律用默认值直接执行，不要反问：

1. **测算维度**：产品 / 客户 / 队伍（可多选）。完全没提到时才问："您想从哪个维度看达成？产品、客户还是队伍？（可多选）"
2. **目标 NBEV（万元）**：完全没提到金额时才问："目标 NBEV 是多少万元？"

> 用户只要给了维度和目标（哪怕只给一个维度），就**直接测算**，不要追问其他维度、不要追问月份。
> 若脚本返回 `status=needs_clarification`，按其 `error.hint` 提问，不要当报错。

**可选信息（不要为此反问）：**
- **业务月份**：缺省自动取**下个月1号**（如今天 2026-06-16 → 2026-07-01）。用户说"6月""下个月"这类能直接确定的，直接用，**不要确认月份**。
- **机构信息与身份**：登录身份由平台自动注入脚本(带外传递)，org_id/org_name 由脚本据此解析。**不要问用户、不要在命令里写机构、不要传 --user-id**。

## 第二步半：活动月先确认参考月（C方案 · 重要）

规划的核心方法是**选对参考月，再按目标同比例缩放**；参考月默认取**同比**（去年同期）。

- **常规月（6-12月）**：直接测算，无需确认参考月。
- **活动月（开门红1-3月 / 换挡4月 / 司庆5月）**：去年同期未必是同类活动，**首次测算会被脚本拦截**，返回 `status=needs_reference_confirm`。此时你要：
  1. 向用户展示脚本给出的节点说明与默认参考月，按 `error.hint` 提问"按默认同比，还是自定义参考月？"；
  2. 用户选①默认 → 带 `--confirm-reference` 再次调用；
  3. 用户选②自定义（如"参考去年9月"）→ 用 `--reference-month 2025-09-01` 调用。
- 这是让内勤显式感受到"选参考月"专业逻辑的关键，**不要跳过、不要擅自替用户决定**。

## 第三步：调用脚本

> **⚠️ 一轮只调用一次本脚本**：要测多个维度时，把维度一起传给 `--dimensions`（如 `产品 队伍 客户`），脚本内部会顺序跑完所有维度并自动做同比，**只需一次调用**。绝不要每个维度各调一次、也不要在同一轮里再调其他脚本，否则会触发框架的 sandbox 并发冲突。

```bash
python scripts/run_planning.py \
  --dimensions 产品 队伍 客户 \
  --target-nbev 8000 \
  --month 2026-07-01 \
  --format md
```

- 脚本内部固定按 **产品 → 队伍 → 客户** 顺序调用，无需手动排序。
- `--format md` 直接返回美观 Markdown（含表格），推荐用于向用户呈现；`--format json` 返回含完整 `data` 的结构化结果。

### 参数

| 参数 | 短参 | 必填 | 说明 |
|------|------|------|------|
| `--user-id` | `-uid` | 否 | **不要传**。身份由平台带外注入(DEER_FLOW_USER_ID),仅本地调试可用 |
| `--dimensions` | `-d` | 是* | `产品` `客户` `队伍`，可多选（*缺失会触发澄清） |
| `--target-nbev` | `-tv` | 是* | 目标NBEV（万元）（*缺失会触发澄清） |
| `--month` | `-m` | 否 | `YYYY-MM-01`，缺省下月1号 |
| `--reference-month` | `-rm` | 否 | 自定义参考月 `YYYY-MM-01`；缺省按同比（去年同期）。活动月内勤想换口径时用 |
| `--confirm-reference` | `-cr` | 否 | 活动月已与内勤确认"就按默认同比"，跳过参考月确认直接测算 |
| `--format` | `-f` | 否 | `md`（美观表格）/ `json`（默认） |
| `--request-id` / `--session-id` | | 否 | 缺省自动生成 |
| `--max-product-activity-rate` / `--max-avg-fyp-range` / `--max-double-gold-diamond-ratio` | | 否 | 浮动范围/占比上限，缺省走接口默认 |
| `--output` | `-o` | 否 | 结果落盘路径 |

## 第四步：呈现给用户（输出规范）

- 用 `--format md` 时，脚本输出已是组织好的 Markdown，**直接呈现**，再用一两句话点评要点（尤其护栏未过项）。
- **方案编号(硬规则)**：测算成功后输出顶部有 `plan_id`(方案编号)。**务必转达给用户**(如"方案已保存,编号 plan_xxx,后续想调整直接说'把××调到××'")——这是后续 nbev_modify_v2 调整方案的锚点。带 `cached` 标记说明命中同参数缓存,如实告知"参数相同,直接给出已保存的方案"。
- 数据一律以 **Markdown 表格**呈现，不要堆成长段文字。
- 输出顶部会标注**业务节点**（开门红/换挡/司庆/常规）与**参考月（同比）**。若是活动月，主动提示用户"去年同期未必同类活动，可自定义参考月"。
- **同比对比（言行一致）**：测算成功后，脚本已用参考月（去年同期）再查一次同一接口，结果里带 `comparison` 字段，并在 Markdown 里渲染"**同比基准**"小表（去年同期实际 NBEV → 本月目标 → 同比增长率）。**务必把这张同比表一并呈现并点评**（如"本月目标较去年同期 5,200 万增长 15.4%"），这样"按同比测算"才名副其实，不是空话。若 `comparison.available=false`（基准取不到），如实说"去年同期基准暂未取到"，不要编造同比数字。
- 输出含 `next_actions`（已按业务逻辑排好优先级）：**在回答结尾采用第一条**作为向导式下一步建议，用自然语言说出来，一次只给一个。
- 每个维度结果含一个 `status`：

| status | 含义 | 你的动作 |
|--------|------|----------|
| `success` | 测算成功（注意看 `validation`） | 展示表格 + summary；**务必转达是否达标**：若 `ACH_target_met` 未过说明预测未达目标 NBEV，需提示用户调整或下调目标；C2/C4 护栏未过也要转达 |
| `needs_reference_confirm` | 活动月，测算前需先确认参考月口径 | 展示节点说明，按 `error.hint` 让用户选"默认同比/自定义参考月"；选默认带 `--confirm-reference` 重调，选自定义带 `--reference-month` 重调 |
| `needs_clarification` | 缺必填项 | 按 `error.hint` 向用户提问，不要报错 |
| `target_unreachable` | 目标不可达 | 按 `error.hint` 引导下调目标或换维度 |
| `runtime_error`(retryable) | 服务繁忙 | 告知"稍后重试"，不展示堆栈 |
| `validation_error` | 入参非法 | 按 `error.hint` 纠正后重试 |

## 错误码速查

| error_code | 对用户怎么说 |
|------------|--------------|
| `NEED_CLARIFY` | （按 hint 提问，非报错） |
| `TARGET_NBEV_NONPOSITIVE` / `TARGET_NBEV_INVALID` | 目标NBEV需为正数 |
| `MONTH_FORMAT_INVALID` | 月份请用 YYYY-MM-01 |
| `DIMENSION_INVALID` / `DIMENSIONS_EMPTY` | 维度仅支持 产品/客户/队伍 |
| `RATIO_OUT_OF_BOUND` / `RATIO_NOT_NUMBER` | 比率参数需为 0~1 小数 |
| `PRODUCT_FALLBACK_CARD` / `PRODUCT_RESULT_EMPTY` | 该机构当月暂无产品历史/配置，无法完成产品测算 |
| `TARGET_UNREACHABLE` | 历史数据难支撑该目标，建议下调或换维度 |
| `DEPENDENCY_MISSING` | 运行环境缺依赖，请联系管理员 |
| `API_TIMEOUT` / `UPSTREAM_5XX` / `API_CONN_ERROR` | 测算服务繁忙，请稍后重试 |
| `CALCULATION_EXCEPTION` | 测算异常，请稍后重试 |

## 与其他 Skill 的边界

| 场景 | Skill |
|------|-------|
| 从零新建达成路径 | **nbev_planning_v2（本skill）** |
| 调整已有规划 | nbev_modify_v2 |
| 查看现状画像 | nbev_profile_v2 |

## 工程说明（维护者）

- 入口：`scripts/run_planning.py`（薄壳：解析CLI→调 planner→输出 json/md）
- 核心：`scripts/nbev_core/`（**skill 自包含**，不依赖外部目录）
  - `planner.py` 编排 · `validators.py` 校验(月份缺省=下月) · `api_client.py` 调接口(超时/重试)
  - `interpreters.py` 解读+护栏 · `render.py` Markdown渲染 · `envelope.py` 信封 · `errors.py` 错误体系
  - `org_context.py` 机构解析（**当前写死 05/深圳**，未来替换此文件一处即可）
  - `config.py` 环境变量配置
- 多环境配置（对齐 DeerFlow 范式）：接口地址等按环境放在 `scripts/nbev_core/config/config.{dev,stg,prd}.yaml`，**默认 dev**。切换方式：
  - 设 `APP_ENV=dev|stg|prd` 选择环境；
  - 或设 `DEER_FLOW_CONFIG_PATH=/abs/path/config.xxx.yaml` 直接指定配置文件（官方变量）；
  - 单项环境变量（如 `MARKETING_PLANNING_API_BASE`）可临时覆盖单个值，优先级最高，便于调试。
  - 解析优先级：单项环境变量 > DEER_FLOW_CONFIG_PATH > APP_ENV 选中的文件 > 内置兜底。非法 APP_ENV 会告警并回退 dev；日志带 `env` 字段便于排障。
- 其他环境变量：`MARKETING_PLANNING_TIMEOUT`、`MARKETING_PLANNING_MAX_RETRY`、`NBEV_YOY_COMPARE`、`NBEV_LOG_LEVEL`、`GUARD_SHOUZUAN_LOW/HIGH`
