"""校准记录业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "calibration"
REQUIRED_FIELDS = ["记录编号", "仪器编号", "校准机构"]
# 导入时接受的数据列（与列表页列一致）；id/status/pending/abnormal 是系统字段，外部文件不允许改。
IMPORT_FIELDS = ["记录编号", "仪器编号", "校准机构", "校准日期", "校准结果", "偏差值", "校准证书号", "记录状态"]
STATUS_ORDER = ["待校准", "校准中", "已合格", "不合格"]
ACTION_RULES = {"执行校准": "校准中", "标记合格": "已合格", "标记不合格": "不合格"}
NEGATIVE_ACTIONS = []


def _next_id(rows: list[dict[str, Any]]) -> int:
    return max((int(row.get("id", 0)) for row in rows), default=0) + 1


def _clean(value: Any) -> str:
    """把导入值归一成去掉首尾空白的字符串；None 视为未提供。"""
    if value is None:
        return ""
    return str(value).strip()


class CalibrationService:
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
            rows = [row for row in rows if keyword in str(row.get("记录编号", ""))]
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
        entry = {"id": _next_id(rows)}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"校准记录单 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于校准记录可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"校准记录单已{action}"

    def stats(self) -> list[dict[str, Any]]:
        """按状态统计记录数，给列表页的指标卡用，保证卡片、列表、状态三者同源。"""
        rows = store.rows(MODULE)

        def count(status: str) -> int:
            return sum(1 for row in rows if row.get("status") == status)

        return [
            {"label": "待校准记录", "value": count("待校准")},
            {"label": "合格记录", "value": count("已合格")},
            {"label": "不合格记录", "value": count("不合格")},
        ]

    def import_rows(self, raw_rows: list[dict[str, Any]]) -> dict[str, Any]:
        """按记录编号匹配导入：已存在则合并非空字段，不存在且必填齐全才新建。

        - 同一文件内编号重复的行只处理第一行，其余标记为重复，不会生成两份记录；
        - 合并时空白字段一律保留原值，已记录的数据不会因为再次上传被覆盖掉；
        - 缺必填列的行直接判失败并说明原因，不会变成页面上看不见的残缺记录；
        - 同一文件重复导入结果一致（中断后重试安全）。
        """
        summary = {"total": 0, "created": 0, "updated": 0, "unchanged": 0, "duplicated": 0, "failed": 0, "skipped": 0}
        results: list[dict[str, Any]] = []
        rows = store.rows(MODULE)
        by_number = {str(row.get("记录编号", "")).strip(): row for row in rows}
        seen_in_file: dict[str, int] = {}

        for index, raw in enumerate(raw_rows, start=1):
            summary["total"] += 1
            values = {field: _clean(raw.get(field)) for field in IMPORT_FIELDS}
            number = values["记录编号"]

            if not any(values.values()):
                summary["skipped"] += 1
                results.append({"row": index, "key": "", "result": "空行", "message": "整行为空，已跳过"})
                continue
            if not number:
                summary["failed"] += 1
                results.append({"row": index, "key": "", "result": "失败", "message": "缺少必填字段：记录编号"})
                continue
            if number in seen_in_file:
                summary["duplicated"] += 1
                results.append({
                    "row": index,
                    "key": number,
                    "result": "重复",
                    "message": f"与第 {seen_in_file[number]} 行的记录编号重复，已跳过",
                })
                continue
            seen_in_file[number] = index

            existing = by_number.get(number)
            if existing is not None:
                changed = []
                for field in IMPORT_FIELDS[1:]:
                    incoming = values[field]
                    if incoming and incoming != _clean(existing.get(field)):
                        existing[field] = incoming
                        changed.append(field)
                if changed:
                    summary["updated"] += 1
                    message = f"已更新字段：{'、'.join(changed)}"
                    result = "更新"
                else:
                    summary["unchanged"] += 1
                    message = "记录已存在且内容一致，未改动"
                    result = "未变化"
                results.append({"row": index, "key": number, "result": result, "message": message})
                continue

            missing = [field for field in REQUIRED_FIELDS if not values[field]]
            if missing:
                summary["failed"] += 1
                results.append({
                    "row": index,
                    "key": number,
                    "result": "失败",
                    "message": f"缺少必填字段：{'、'.join(missing)}",
                })
                continue

            entry = {"id": _next_id(rows)}
            entry.update({field: values[field] for field in IMPORT_FIELDS if values[field]})
            entry["status"] = STATUS_ORDER[0]
            entry["pending"] = True
            entry["abnormal"] = False
            rows.append(entry)
            by_number[number] = entry
            summary["created"] += 1
            results.append({"row": index, "key": number, "result": "新建", "message": "已登记为新校准记录单"})

        return {"summary": summary, "results": results}
