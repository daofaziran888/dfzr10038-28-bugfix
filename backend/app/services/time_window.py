"""时间窗口领域服务：字段、状态和动作来自业务配置，数据处理骨架由基类复用。

窗口计算明细（计算清单）记录模板实际接受的就绪输入和已交付的计算结果范围，
是窗口启动计算与回溯人员领取可回溯区间的共同依据。
"""
from __future__ import annotations

import re
from typing import Any

from app.services.base import BaseModuleService
from app.store import store

# 特征清单允许用 ; , 、 或空白分隔；只登记单个输出的历史模板不含分隔符，同样能解析。
_FEATURE_SPLIT = re.compile(r"[;,，、\s]+")


def parse_feature_list(raw: Any) -> list[str]:
    """把特征清单字段解析为特征名列表，按完整特征名精确匹配，避免子串误关联。"""
    text = str(raw or "").strip()
    if not text:
        return []
    return [token for token in _FEATURE_SPLIT.split(text) if token]


class TimeWindowService(BaseModuleService):
    MODULE = "time_window"
    ENTITY = "窗口模板"
    OPERATION_TERM = "计算"
    LIST_FIELDS = ["模板编号", "窗口类型", "窗口宽度", "滑动步长", "对齐基准", "缺值填充", "特征列表", "最近计算"]
    REQUIRED_FIELDS = ["模板编号", "窗口类型", "窗口宽度"]
    STATUS_ORDER = ["草稿", "计算中", "窗口关闭", "已废弃"]
    ACTION_RULES = {"启动计算": "计算中", "关闭窗口": "窗口关闭", "废弃模板": "已废弃"}
    NEGATIVE_ACTIONS = []

    def backfill_ranges(self, entry_id: int) -> dict[str, Any] | None:
        """读取窗口的可回溯区间。

        已交付范围逐项保留来源（衍生规则与真实输入特征），部分覆盖时标明尚缺输入，
        防止回溯人员把部分覆盖当成全量而漏补数据。
        """
        row = store.find(self.MODULE, entry_id)
        if row is None:
            return None
        detail = row.get("计算明细") or {}
        required = parse_feature_list(row.get("特征列表"))
        accepted = list(detail.get("已接受特征", []))
        accepted_names = {str(item.get("特征", "")) for item in accepted}
        missing = [feat for feat in required if feat not in accepted_names]
        delivered = list(detail.get("已交付区间", []))
        if not required:
            coverage = "未登记特征清单"
            waiting = "窗口模板未登记特征清单，无法核对输入依赖"
        elif not missing and delivered:
            coverage = "全量覆盖"
            waiting = None
        elif delivered:
            coverage = "部分覆盖"
            waiting = f"尚缺输入：{'、'.join(missing)}"
        else:
            coverage = "未开始"
            waiting = (
                f"尚缺输入：{'、'.join(missing)}" if missing else "尚无已交付的计算结果范围"
            )
        return {
            "模板编号": row.get("模板编号", ""),
            "status": row.get("status", ""),
            "需求特征": required,
            "已接受特征": accepted,
            "尚缺输入": missing,
            "可用范围": delivered,
            "覆盖状态": coverage,
            "等待原因": waiting,
        }
