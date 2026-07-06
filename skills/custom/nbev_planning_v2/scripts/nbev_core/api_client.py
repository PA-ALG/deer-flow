"""
api_client.py — 三个达成测算接口的业务客户端(薄)

三接口同构(共享 AchievementCalculationRequest + 同前缀路径),故用一个入口收敛。
基础设施语义(超时/重试/降级/身份头/日志)在 vendor 的 http.py 引擎里;
这里只保留业务语义:端点表 + 维度合法性。
"""

from __future__ import annotations

from . import config
from .errors import ApiError
from .http import post_with_retry


def call_calculation(dimension: str, payload: dict) -> dict:
    """调用某维度达成测算接口,返回原始 JSON。失败抛 ApiError。"""
    if dimension not in config.ENDPOINTS:
        raise ApiError("UNKNOWN_DIMENSION", f"未知测算维度:{dimension}")
    url = config.API_BASE + config.ENDPOINTS[dimension]
    try:
        return post_with_retry(
            url, payload,
            timeout=config.API_TIMEOUT,
            max_retry=config.MAX_RETRY,
            request_id=payload.get("request_id"),
            tag=dimension,
        )
    except ApiError as e:
        # 补充测算场景的用户话术(引擎给的是通用 hint)
        if e.code in ("UPSTREAM_5XX", "API_TIMEOUT", "API_CONN_ERROR"):
            e.hint = e.hint or "测算服务暂时不可用,请稍后重试"
        raise
