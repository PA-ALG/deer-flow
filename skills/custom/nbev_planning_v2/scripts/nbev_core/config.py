"""
config.py — 集中配置（配置文件驱动 + 环境变量覆盖，对齐 DeerFlow 范式）

环境切换（默认 dev）：
- APP_ENV=dev|stg|prd 决定加载 config/config.<env>.yaml；
- DEER_FLOW_CONFIG_PATH 可直接指定配置文件绝对路径（对齐 DeerFlow 官方变量，优先级最高的"选文件"方式）；
- 单项环境变量（如 MARKETING_PLANNING_API_BASE）仍可临时覆盖单个值，优先级最高，便于调试。

解析优先级（高→低）：
  单项环境变量  >  DEER_FLOW_CONFIG_PATH 指定的文件  >  APP_ENV 选中的文件  >  内置兜底默认

harness 要点：
- 地址等"会变的东西"全部进配置文件，代码零业务字面量；
- 非法 APP_ENV / 配置文件缺失 / yaml 解析失败 → fail-fast 显性告警并安全回退，绝不静默连错环境；
- 当前生效环境会被记录，供日志标记（见 obs.py 的 env 字段），避免"测试数据混进生产"。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_VALID_ENVS = ("dev", "stg", "prd")
_DEFAULT_ENV = "dev"  # 默认开发环境

# 内置兜底默认（配置文件全部不可用时才用，保证 skill 永不因缺配置而崩）
_FALLBACK = {
    "env": _DEFAULT_ENV,
    "api": {
        "base": "http://8.148.158.241:8001/api/v1/marketing-planning",
        "timeout": 60.0,
        "max_retry": 2,
    },
    "features": {"yoy_compare": True},
    "guards": {"shouzuan_low": 0.80, "shouzuan_high": 0.90},
}

_CONFIG_DIR = Path(__file__).resolve().parent / "config"


def _warn(msg: str) -> None:
    print(f"[config] {msg}", file=sys.stderr)


def _resolve_env() -> str:
    raw = (os.getenv("APP_ENV") or "").strip().lower()
    if not raw:
        return _DEFAULT_ENV
    if raw not in _VALID_ENVS:
        _warn(f"APP_ENV='{raw}' 非法（可选 {'/'.join(_VALID_ENVS)}），回退默认 {_DEFAULT_ENV}")
        return _DEFAULT_ENV
    return raw


def _load_yaml(path: Path) -> dict | None:
    try:
        import yaml
    except ImportError:
        _warn("缺少 pyyaml，无法读配置文件，使用内置兜底默认")
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            _warn(f"配置文件 {path} 内容非法（非映射），忽略")
            return None
        return data
    except FileNotFoundError:
        _warn(f"配置文件不存在：{path}")
        return None
    except Exception as e:  # yaml 解析错误等
        _warn(f"配置文件 {path} 解析失败：{e}")
        return None


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _load_config() -> tuple[dict, str]:
    """加载生效配置，返回 (配置字典, 当前环境名)。"""
    env = _resolve_env()

    # DEER_FLOW_CONFIG_PATH：官方范式，直接指定配置文件（优先于 APP_ENV 选文件）
    explicit = (os.getenv("DEER_FLOW_CONFIG_PATH") or "").strip()
    if explicit:
        cfg = _load_yaml(Path(explicit))
        if cfg is not None:
            merged = _deep_merge(_FALLBACK, cfg)
            return merged, str(cfg.get("env", env))
        _warn("DEER_FLOW_CONFIG_PATH 指定的文件不可用，回退按 APP_ENV 加载")

    # 按 APP_ENV 选 config/config.<env>.yaml
    cfg = _load_yaml(_CONFIG_DIR / f"config.{env}.yaml")
    if cfg is not None:
        return _deep_merge(_FALLBACK, cfg), str(cfg.get("env", env))

    _warn(f"环境 {env} 的配置文件不可用，使用内置兜底默认")
    return dict(_FALLBACK), env


# ── 单项环境变量覆盖（最高优先级，便于临时调试）──
def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        _warn(f"环境变量 {key}='{raw}' 非法，回退 {default}")
        return default


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        _warn(f"环境变量 {key}='{raw}' 非法，回退 {default}")
        return default


def _env_str(key: str, default: str) -> str:
    raw = os.getenv(key)
    return raw if raw not in (None, "") else default


# ===== 实际生效配置 =====
_CFG, APP_ENV = _load_config()
_api = _CFG.get("api", {})
_feat = _CFG.get("features", {})
_guard = _CFG.get("guards", {})

# 后端达成测算接口基址：单项环境变量 > 配置文件 > 兜底
API_BASE = _env_str("MARKETING_PLANNING_API_BASE", _api.get("base")).rstrip("/")

# 三个维度的接口末段（结构性常量，不随环境变）
ENDPOINTS = {
    "product": "/get-product-card-data",
    "customer": "/get-customer-card-data",
    "team": "/get-team-card-data",
}

API_TIMEOUT = _env_float("MARKETING_PLANNING_TIMEOUT", float(_api.get("timeout", 60)))
MAX_RETRY = _env_int("MARKETING_PLANNING_MAX_RETRY", int(_api.get("max_retry", 2)))

DIMENSION_ORDER = ("product", "team", "customer")

ENABLE_YOY_COMPARE = _env_int(
    "NBEV_YOY_COMPARE", 1 if _feat.get("yoy_compare", True) else 0
) == 1

DIMENSION_CN = {"product": "产品", "team": "队伍", "customer": "客户"}

SHOUZUAN_NBEV_RATIO_RANGE = (
    _env_float("GUARD_SHOUZUAN_LOW", float(_guard.get("shouzuan_low", 0.80))),
    _env_float("GUARD_SHOUZUAN_HIGH", float(_guard.get("shouzuan_high", 0.90))),
)
