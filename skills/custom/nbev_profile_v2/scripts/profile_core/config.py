"""
config.py — 画像查询配置（配置文件驱动 + 环境变量覆盖，对齐 DeerFlow 范式）

环境切换（默认 dev）：
- APP_ENV=dev|stg|prd 决定加载 config/config.<env>.yaml；
- DEER_FLOW_CONFIG_PATH 可直接指定配置文件绝对路径（对齐 DeerFlow 官方变量）；
- 单项环境变量（如 PROFILE_QUERY_API_BASE）仍可临时覆盖单个值，优先级最高。

画像接口是"通用查询"：POST /api/{tableName}/query，body 含 {requestId, sqlid, queryValues}。
三个维度各对应一组固定的 (tableName, sqlid)，属结构性常量，不随环境变。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_VALID_ENVS = ("dev", "stg", "prd")
_DEFAULT_ENV = "dev"

_FALLBACK = {
    "env": _DEFAULT_ENV,
    "api": {"base": "http://8.148.158.241:8000/api", "timeout": 30.0, "max_retry": 2},
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
    except Exception as e:
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
    env = _resolve_env()
    explicit = (os.getenv("DEER_FLOW_CONFIG_PATH") or "").strip()
    if explicit:
        cfg = _load_yaml(Path(explicit))
        if cfg is not None:
            return _deep_merge(_FALLBACK, cfg), str(cfg.get("env", env))
        _warn("DEER_FLOW_CONFIG_PATH 指定的文件不可用，回退按 APP_ENV 加载")
    cfg = _load_yaml(_CONFIG_DIR / f"config.{env}.yaml")
    if cfg is not None:
        return _deep_merge(_FALLBACK, cfg), str(cfg.get("env", env))
    _warn(f"环境 {env} 的配置文件不可用，使用内置兜底默认")
    return dict(_FALLBACK), env


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

# 画像查询服务基址：单项环境变量 > 配置文件 > 兜底
API_BASE = _env_str("PROFILE_QUERY_API_BASE", _api.get("base")).rstrip("/")

# 三维度 -> (tableName 路径段, sqlid)（结构性常量，来源：画像查询接口文档）
DIMENSION_QUERY = {
    "team": {
        "table_name": "omniMktAgentDomainIndex",
        "sqlid": "omni_mkt_agent_doain_index_phasl_03",
        "extra_values": [],
    },
    "customer": {
        "table_name": "omniMktAgentPlanStatistic",
        "sqlid": "omni_mkt_agent_plan_statistic_data_05",
        "extra_values": [],
    },
    "product": {
        "table_name": "omniMktAgentPlanProductActivity",
        "sqlid": "omni_mkt_agent_plan_product_activity_02",
        "extra_values": [],
    },
}

API_TIMEOUT = _env_float("PROFILE_QUERY_TIMEOUT", float(_api.get("timeout", 30)))
MAX_RETRY = _env_int("PROFILE_QUERY_MAX_RETRY", int(_api.get("max_retry", 2)))

DIMENSION_CN = {"team": "队伍", "customer": "客户", "product": "产品"}
DIMENSION_ORDER = ("team", "customer", "product")

RETRYABLE_API_CODES = {50001, 50002, 50099}
