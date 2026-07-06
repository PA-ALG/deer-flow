# @vendored-from skill_lib/obs.py @sha256:f817c67a70a1
# DO NOT EDIT —— 本文件是 vendor 副本;请修改 skill_lib/obs.py 后运行
#               python tools/sync_skill_lib.py 重新同步(--check 供 CI 校验)。
"""
obs.py — 结构化日志 + trace 贯穿(支柱7)

- JSON 行 → stderr(绝不污染 stdout 的结果,DeerFlow 坑4);
- 自动携带 env(防"测试数据混进生产")与平台注入的 thread trace
  (DEER_FLOW_THREAD_ID,与网关/模型轮次日志一个 ID grep 到底,docs/07 §六);
- 日志永远不能成为故障源(全函数 try/except)。

日志级别由环境变量 NBEV_LOG_LEVEL 控制(默认 INFO)。
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time

_LEVEL = os.getenv("NBEV_LOG_LEVEL", "INFO").upper()
# logger 名取自所在包名(vendor 进 nbev_core → "nbev_core"),多 skill 互不串扰
_logger = logging.getLogger(__package__ or "skill_lib")

if not _logger.handlers:  # 防止重复加 handler(多次 import)
    _h = logging.StreamHandler(sys.stderr)  # stderr,避免污染 stdout 结果
    _h.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(_h)
    _logger.setLevel(getattr(logging, _LEVEL, logging.INFO))
    _logger.propagate = False


def log(event: str, *, level: str = "INFO", **fields) -> None:
    """输出一行结构化 JSON 日志。失败绝不影响主流程。"""
    try:
        try:
            from .config import APP_ENV as _env
        except Exception:
            _env = "?"
        record = {"ts": round(time.time(), 3), "env": _env, "event": event}
        trace = os.getenv("DEER_FLOW_THREAD_ID")
        if trace:
            record["thread"] = trace
        record.update(fields)
        line = json.dumps(record, ensure_ascii=False, default=str)
        _logger.log(getattr(logging, level.upper(), logging.INFO), line)
    except Exception:
        pass  # 日志永远不能成为故障源
