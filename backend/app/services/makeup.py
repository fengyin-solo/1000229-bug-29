"""化妆造型业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "makeup"
REQUIRED_FIELDS = ["方案编号", "角色名称", "造型风格"]
STATUS_ORDER = ["待设计", "待试妆", "已定妆", "已作废"]
ACTION_RULES = {"提交方案": "待试妆", "安排试妆": "已定妆", "作废方案": "已作废"}
NEGATIVE_ACTIONS = ["作废方案"]
TERMINAL_STATUSES = ["已定妆", "已作废"]
DISPLAY_FIELD = "方案状态"


class MakeupService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("方案编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry[DISPLAY_FIELD] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"妆造方案 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于化妆造型可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        current = str(entry.get("status") or STATUS_ORDER[0])
        if current not in STATUS_ORDER:
            return None, f"当前状态「{current}」不在允许的状态序列里，无法继续流转"
        if current in TERMINAL_STATUSES:
            return None, f"妆造方案已处于「{current}」阶段，完成结果不允许被覆盖"
        if action not in NEGATIVE_ACTIONS:
            expected = STATUS_ORDER[STATUS_ORDER.index(current) + 1]
            if target == current:
                return None, f"妆造方案已处于「{current}」阶段，请勿重复{action}"
            if target != expected:
                return None, f"妆造方案需按「{' → '.join(STATUS_ORDER[:3])}」逐级流转，不能从「{current}」越级到「{target}」"
        # 全部校验通过后才落库：任何一步失败，记录都停留在上一阶段，
        # 状态、列表展示字段与概览计数标记一起更新，保证列表、详情、概览一致。
        entry["status"] = target
        entry[DISPLAY_FIELD] = target
        entry["pending"] = target not in TERMINAL_STATUSES
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"妆造方案已{action}，进入「{target}」阶段"
