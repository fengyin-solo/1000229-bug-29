"""化妆造型业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "makeup"
REQUIRED_FIELDS = ["方案编号", "角色名称", "造型风格"]
OPTIONAL_FIELDS = ["特效需求", "化妆师", "试妆日期", "定妆照片"]
STATUS_ORDER = ["待设计", "待试妆", "已定妆", "已作废"]
ACTION_RULES = {"提交方案": "待试妆", "安排试妆": "已定妆", "作废方案": "已作废"}
NEGATIVE_ACTIONS = ["作废方案"]
TERMINAL_STATUSES = ["已定妆", "已作废"]
# 生命周期：每个阶段只允许列出的动作，逐级推进、不允许越级；终态不再接受任何动作
LIFECYCLE_RULES = {
    "待设计": ["提交方案", "作废方案"],
    "待试妆": ["安排试妆", "作废方案"],
    "已定妆": [],
    "已作废": [],
}
STATUS_FIELD = "方案状态"
TRIAL_DATE_FIELD = "试妆日期"


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
        for field in OPTIONAL_FIELDS:
            if values.get(field) not in (None, ""):
                entry[field] = values.get(field)
        entry["status"] = STATUS_ORDER[0]
        entry[STATUS_FIELD] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"妆造方案 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于化妆造型可执行范围"
        current = str(entry.get("status") or STATUS_ORDER[0])
        if current in TERMINAL_STATUSES:
            return None, f"妆造方案当前状态为「{current}」，已完成的结果不会被覆盖"
        if action not in LIFECYCLE_RULES.get(current, []):
            return None, f"妆造方案当前为「{current}」，不能越级执行「{action}」"
        target = ACTION_RULES[action]
        updates: dict[str, Any] = {}
        if values and TRIAL_DATE_FIELD in values:
            trial_date = str(values.get(TRIAL_DATE_FIELD) or "").strip()
            try:
                datetime.strptime(trial_date, "%Y-%m-%d")
            except ValueError:
                return None, f"试妆日期「{trial_date}」格式不正确，方案仍保留在「{current}」"
            updates[TRIAL_DATE_FIELD] = trial_date
        snapshot = dict(entry)
        try:
            entry.update(updates)
            entry["status"] = target
            entry[STATUS_FIELD] = target
            entry["pending"] = target not in TERMINAL_STATUSES
            entry["abnormal"] = action in NEGATIVE_ACTIONS
        except Exception:  # 任何一步写库失败都回滚，记录保持在上一阶段
            entry.clear()
            entry.update(snapshot)
            return None, f"妆造方案{action}失败，已恢复到「{current}」"
        return entry, f"妆造方案已{action}"
