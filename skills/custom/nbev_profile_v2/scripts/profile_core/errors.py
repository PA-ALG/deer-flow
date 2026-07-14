# @vendored-from skill_lib/errors.py @sha256:bc76983da5dc
# DO NOT EDIT —— 本文件是 vendor 副本;请修改 skill_lib/errors.py 后运行
#               python tools/sync_skill_lib.py 重新同步(--check 供 CI 校验)。
"""
errors.py — 结构化错误体系(支柱2)

harness engineering 原则:每个错误都"可机读 + 可复述 + 可恢复判定"。
统一一个 SkillError,所有失败路径都抛它,由入口统一转成 envelope。
"""

from __future__ import annotations


class SkillError(Exception):
    """所有业务/校验/运行时错误的统一基类。"""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        hint: str = "",
        fields: list[str] | None = None,
        retryable: bool = False,
    ):
        self.code = code
        self.message = message
        self.hint = hint
        self.fields = fields or []
        self.retryable = retryable
        super().__init__(message)

    def to_error(self) -> dict:
        return {
            "error_code": self.code,
            "message": self.message,
            "hint": self.hint,
            "fields": self.fields,
            "retryable": self.retryable,
        }


# 语义化子类(便于 except 精确捕获,也让代码自解释)
class ValidationError(SkillError):
    """入参非法(格式/范围/必填)。不可重试。"""


class ApiError(SkillError):
    """调用后端接口失败。是否可重试取决于具体场景。"""


class TargetUnreachable(SkillError):
    """目标 NBEV 在历史合理范围内不可达。属业务合法结果,非系统错误。"""

    def __init__(self, dimension: str, target_nbev: float, detail: str = ""):
        super().__init__(
            code="TARGET_UNREACHABLE",
            message=f"{dimension}维度在历史合理波动范围内无法达成 {target_nbev} 万元目标。{detail}".strip(),
            hint="可适当下调目标 NBEV,或更换/组合其他测算维度",
            fields=["target_nbev"],
            retryable=False,
        )


class NeedClarify(SkillError):
    """必填信息缺失,需向用户澄清而非报错或猜测。"""

    def __init__(self, message: str, *, hint: str, fields: list[str]):
        super().__init__(
            code="NEED_CLARIFY",
            message=message,
            hint=hint,
            fields=fields,
            retryable=False,
        )


class IdentityMissing(SkillError):
    """带外身份缺失。这是部署/平台配置故障,不是用户问题——绝不向用户澄清身份。"""

    def __init__(self):
        super().__init__(
            code="IDENTITY_MISSING",
            message="无法确定当前用户身份(平台未注入 DEER_FLOW_USER_ID)",
            hint=(
                "这是部署配置问题,请检查平台身份注入是否生效;"
                "本地开发可设置环境变量 NBEV_USER_ID 或使用 --user-id 参数"
            ),
            fields=[],
            retryable=False,
        )


class PlanNotFound(SkillError):
    """指定的 plan_id 不存在(可能拼写错误或方案在其他会话)。"""

    def __init__(self, plan_id: str, available: list[str] | None = None):
        tail = f" 本会话现有方案:{', '.join(available[-5:])}" if available else " 本会话尚无已保存方案。"
        super().__init__(
            code="PLAN_NOT_FOUND",
            message=f"未找到方案 {plan_id}。{tail}",
            hint="请确认 plan_id 是否正确;若无方案,请先用规划能力生成一份",
            fields=["plan_id"],
            retryable=False,
        )
