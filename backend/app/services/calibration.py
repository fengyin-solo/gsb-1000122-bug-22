"""校准记录业务规则：状态流转、字段校验、外部文件导入与筛选口径都收在这里。

关键约定（列表页与详情页必须共用同一套口径）：
- ``status`` 是工作流状态的唯一事实来源，展示列「记录状态」始终由它派生，
  导入文件里即便带了「记录状态」列也不允许改写工作流，避免两处显示互相打架。
- 外部文件按「记录编号」（去空白、统一大小写后）做唯一匹配：命中则只补齐/
  更新本次明确给出的非空字段，未提供的列保留原值；未命中才新增，杜绝同号两条。
- 导入先逐行校验、再整体提交：任何一行失败都不写入，因此中断后可直接重试，
  已落库的数据不会重复、不会丢失。
"""
from __future__ import annotations

import threading
import time
from typing import Any

from app.store import store

MODULE = "calibration"
# 匹配键与必填列：匹配只用「记录编号」，仪器编号/校准机构是普通数据列
KEY_FIELD = "记录编号"
REQUIRED_FIELDS = ["记录编号", "仪器编号", "校准机构"]
# 允许随文件更新的非必填数据列（「记录状态」不在其中，状态只能走动作流转）
OPTIONAL_DATA_FIELDS = ["校准日期", "校准结果", "偏差值", "校准证书号"]
DATA_FIELDS = REQUIRED_FIELDS + OPTIONAL_DATA_FIELDS
STATUS_ORDER = ["待校准", "校准中", "已合格", "不合格"]
STATUS_PENDING = {"待校准", "校准中"}
ACTION_RULES = {"执行校准": "校准中", "标记合格": "已合格", "标记不合格": "不合格"}
NEGATIVE_ACTIONS = ["标记不合格"]


def normalize_code(value: Any) -> str:
    """记录编号归一化：去首尾空白、压缩内部空白、统一大写。

    这样 'cali-0001 '、'CALI-0001'、'CALI - 0001' 都会指向同一条记录。
    """
    return "".join(str(value or "").split()).upper()


class CalibrationService:
    # 同一时刻只允许一个导入/导出快照任务，冲突时让调用方稍后重试
    _io_lock = threading.Lock()

    # ---- 状态唯一事实来源 -------------------------------------------------
    def _canonicalize(self, entry: dict[str, Any]) -> dict[str, Any]:
        """让一条记录的工作流状态与展示列始终一致，并补齐修订号。

        列表页和详情页拿到的都是经过这里规整的数据，从根上保证两处内容不冲突。
        """
        status = entry.get("status")
        if status not in STATUS_ORDER:
            status = STATUS_ORDER[0]
        entry["status"] = status
        entry["记录状态"] = status
        entry["pending"] = status in STATUS_PENDING
        entry["abnormal"] = status == "不合格"
        if not entry.get("revision"):
            entry["revision"] = int(time.time() * 1000)
        return entry

    def _next_id(self) -> int:
        return max((int(row.get("id", 0)) for row in store.rows(MODULE)), default=0) + 1

    def _find_by_code(self, code: str) -> dict[str, Any] | None:
        if not code:
            return None
        for row in store.rows(MODULE):
            if normalize_code(row.get(KEY_FIELD)) == code:
                return row
        return None

    def _canonicalize_all(self) -> list[dict[str, Any]]:
        return [self._canonicalize(row) for row in store.rows(MODULE)]

    # ---- 查询 -------------------------------------------------------------
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        instrument: str | None = None,
        organization: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._canonicalize_all()
        if keyword:
            rows = [row for row in rows if keyword.strip() in str(row.get(KEY_FIELD, ""))]
        if instrument:
            rows = [row for row in rows if instrument.strip() in str(row.get("仪器编号", ""))]
        if organization:
            rows = [row for row in rows if organization.strip() in str(row.get("校准机构", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self._canonicalize(entry) if entry is not None else None

    def stats(self) -> dict[str, int]:
        """数量指标与列表用同一份数据、同一套状态口径，保证数字对得上。"""
        rows = self._canonicalize_all()
        return {
            "待校准": sum(1 for row in rows if row["status"] == "待校准"),
            "校准中": sum(1 for row in rows if row["status"] == "校准中"),
            "已合格": sum(1 for row in rows if row["status"] == "已合格"),
            "不合格": sum(1 for row in rows if row["status"] == "不合格"),
            "total": len(rows),
        }

    # ---- 登记 / 编辑 ------------------------------------------------------
    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        code = normalize_code(values.get(KEY_FIELD))
        if self._find_by_code(code) is not None:
            return None, [f"记录编号 {str(values.get(KEY_FIELD)).strip()} 已存在，请直接更新该记录"]
        entry: dict[str, Any] = {"id": self._next_id(), "status": STATUS_ORDER[0]}
        for field in DATA_FIELDS:
            text = str(values.get(field) or "").strip()
            if text:
                entry[field] = text
        store.rows(MODULE).append(entry)
        return self._canonicalize(entry), []

    def update_entry(
        self,
        entry_id: int,
        values: dict[str, Any],
        revision: int | None = None,
    ) -> tuple[dict[str, Any] | None, str, int]:
        """详情页保存编辑。

        返回 (记录, 错误说明, 冲突类型)：``conflict=revision`` 表示期间已被别处
        （如再次导入）改过，调用方可刷新后重试，表单里已填的内容由前端保留不丢。
        """
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"校准记录单 {entry_id} 不存在或已归档", "missing"
        entry = self._canonicalize(entry)
        if revision is not None and int(entry.get("revision") or 0) != int(revision):
            return entry, "该记录刚被其他操作更新，请核对下方最新内容后重试", "revision"

        payload: dict[str, str] = {}
        for field in DATA_FIELDS:
            if field in values:
                payload[field] = str(values.get(field) or "").strip()

        missing = [
            field for field in REQUIRED_FIELDS
            if not (payload.get(field) if field in payload else entry.get(field))
        ]
        if missing:
            return None, f"必填字段不能为空：{'、'.join(missing)}", "validation"

        new_code = payload.get(KEY_FIELD, normalize_code(entry.get(KEY_FIELD)))
        if normalize_code(new_code) != normalize_code(entry.get(KEY_FIELD)):
            holder = self._find_by_code(normalize_code(new_code))
            if holder is not None and int(holder.get("id", 0)) != entry_id:
                return entry, f"记录编号 {new_code} 已被其他记录占用，请换一个编号", "duplicate"

        for field, text in payload.items():
            if text:
                entry[field] = text
            elif field in OPTIONAL_DATA_FIELDS:
                # 详情页显式清空可选项是允许的；必填项上面已拦截
                entry[field] = ""
        entry["revision"] = int(time.time() * 1000)
        return self._canonicalize(entry), "", ""

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
        entry["revision"] = int(time.time() * 1000)
        return self._canonicalize(entry), f"校准记录单已{action}"

    # ---- 外部文件导入 -----------------------------------------------------
    def import_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        source: str = "外部文件",
    ) -> tuple[dict[str, Any], bool]:
        """逐行校验、整体提交外部文件数据。

        返回 (报告, busy)；``busy=True`` 表示有另一个导入在执行，调用方应稍后重试。
        报告里给每一行一个明确结论（新增/更新/重复跳过/失败及原因），并保证
        created + updated + skipped + failed 与文件数据行一一对应。
        """
        if not self._io_lock.acquire(blocking=False):
            return {"ok": False, "message": "另一个导入任务正在执行，请稍后重试", "busy": True}, True

        try:
            table = store.rows(MODULE)
            line_results: list[dict[str, Any]] = []
            staged: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
            seen: dict[str, int] = {}
            blank = 0
            next_new_id = self._next_id()

            for index, raw in enumerate(rows, start=1):
                code_raw = str(raw.get(KEY_FIELD) or "").strip()
                data = {
                    field: str(raw.get(field) or "").strip()
                    for field in DATA_FIELDS
                    if str(raw.get(field) or "").strip()
                }
                if not code_raw and not data:
                    blank += 1
                    line_results.append({
                        "line": index, "record": "", "outcome": "skipped",
                        "message": "空行已跳过",
                    })
                    continue

                code = normalize_code(code_raw)
                missing = [
                    field for field in REQUIRED_FIELDS
                    if not str(raw.get(field) or "").strip()
                ]
                if missing:
                    line_results.append({
                        "line": index, "record": code_raw, "outcome": "failed",
                        "message": f"缺少必填列：{'、'.join(missing)}",
                    })
                    continue

                if code in seen:
                    line_results.append({
                        "line": index, "record": code_raw, "outcome": "failed",
                        "message": f"与文件第 {seen[code]} 行记录编号重复，已中止本行",
                    })
                    continue
                seen[code] = index

                existing = self._find_by_code(code)
                if existing is not None:
                    changed = {
                        field: data[field]
                        for field in DATA_FIELDS
                        if field in data
                        and str(existing.get(field) or "").strip() != data[field]
                    }
                    if not changed:
                        line_results.append({
                            "line": index, "record": code_raw, "outcome": "skipped",
                            "message": "与现有记录内容一致，已跳过",
                        })
                    else:
                        staged.append(("updated", existing, changed))
                        line_results.append({
                            "line": index, "record": code_raw, "outcome": "updated",
                            "message": f"更新字段：{'、'.join(changed.keys())}，其余列保留原值",
                        })
                else:
                    new_entry = {"id": next_new_id, "status": STATUS_ORDER[0]}
                    next_new_id += 1
                    new_entry.update(data)
                    staged.append(("created", new_entry, data))
                    line_results.append({
                        "line": index, "record": code_raw, "outcome": "created",
                        "message": "新增校准记录",
                    })

            created = [item for item in staged if item[0] == "created"]
            updated = [item for item in staged if item[0] == "updated"]
            failed = [item for item in line_results if item["outcome"] == "failed"]
            skipped = [item for item in line_results if item["outcome"] == "skipped"]

            if not line_results or (not staged and not failed):
                return {
                    "ok": False, "busy": False, "source": source,
                    "message": "文件没有可导入的数据行（仅表头或全为空行），未做任何改动",
                    "total": len(rows), "blank": blank,
                    "created": 0, "updated": 0, "skipped": len(skipped), "failed": 0,
                    "lines": line_results,
                }, False

            if failed:
                # 关键：任何一行失败都不提交，已存在的数据原样保留，修好后可整体重试
                return {
                    "ok": False, "busy": False, "source": source,
                    "message": (
                        f"{len(failed)} 行未通过校验，本次未写入任何数据；"
                        "请按逐行提示修正后重新上传（已存在的记录可原样重试，不会重复）"
                    ),
                    "total": len(rows), "blank": blank,
                    "created": 0, "updated": 0,
                    "skipped": len(skipped), "failed": len(failed),
                    "lines": line_results,
                }, False

            # 校验全部通过后才整体提交
            now = int(time.time() * 1000)
            for kind, entry, changes in staged:
                if kind == "created":
                    entry["import_source"] = source
                    entry["revision"] = now
                    table.append(entry)
                    self._canonicalize(entry)
                else:
                    entry.update(changes)
                    entry["revision"] = now
                    self._canonicalize(entry)

            return {
                "ok": True, "busy": False, "source": source,
                "message": (
                    f"导入完成：新增 {len(created)} 条，更新 {len(updated)} 条，"
                    f"跳过 {len(skipped)} 行；同一记录编号只保留一条，既有数据未丢失"
                ),
                "total": len(rows), "blank": blank,
                "created": len(created), "updated": len(updated),
                "skipped": len(skipped), "failed": 0,
                "lines": line_results,
            }, False
        finally:
            self._io_lock.release()

    def export_snapshot(self) -> dict[str, Any] | None:
        """导出与导入共用同一把锁，导出期间撞上导入就让调用方重试下载。"""
        if not self._io_lock.acquire(blocking=False):
            return None
        try:
            items = self._canonicalize_all()
            return {"module": MODULE, "total": len(items), "items": items}
        finally:
            self._io_lock.release()
