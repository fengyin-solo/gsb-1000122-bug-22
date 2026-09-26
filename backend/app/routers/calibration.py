"""校准记录接口：维护校准记录单，覆盖执行校准、标记合格、标记不合格等动作。

注意路由声明顺序：/export、/stats、/import 这类固定路径必须写在 /{entry_id}
之前，否则 /export 会被当成 entry_id 解析，下载和详情互相冲突。
"""
from __future__ import annotations

import csv
import io
import json
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from app.schemas import ActionResult, EntryPayload, ImportResult, ImportRowResult, ImportSummary, PageResult
from app.services.calibration import CalibrationService

router = APIRouter(prefix="/api/calibration", tags=["校准记录"])

service = CalibrationService()

LIST_FIELDS = ["记录编号", "仪器编号", "校准机构", "校准日期", "校准结果", "偏差值", "校准证书号", "记录状态"]
STATUSES = ["待校准", "校准中", "已合格", "不合格"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按记录编号检索"),
    status: str | None = Query(default=None, description="待校准、校准中、已合格、不合格"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按记录编号与状态过滤校准记录列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出校准记录清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "calibration", "total": total, "items": items}


@router.get("/stats")
def stats_entries() -> dict[str, Any]:
    """按状态汇总记录数：列表页指标卡的数据源，与列表、详情读同一份数据。"""
    return {"module": "calibration", "cards": service.stats()}


@router.post("/import", response_model=ImportResult)
def import_entries(file: UploadFile = File(...)) -> ImportResult:
    """导入外部校准记录文件（CSV 或 JSON）：按记录编号匹配，逐行反馈处理结果。

    空文件、缺表头、解析失败都会给出可读说明；数据行的问题逐行反馈，不影响其他行。
    """
    raw = file.file.read()
    if not raw:
        return ImportResult(ok=False, message="文件为空，没有可导入的内容")
    text = _decode_text(raw)
    if text is None:
        return ImportResult(ok=False, message="文件编码无法识别，请使用 UTF-8 或 GBK 编码的文件")

    name = (file.filename or "").lower()
    try:
        raw_rows = _parse_json(text) if name.endswith(".json") else _parse_csv(text)
    except ValueError as exc:
        return ImportResult(ok=False, message=str(exc))
    if not raw_rows:
        return ImportResult(ok=False, message="文件中没有可导入的数据行")

    outcome = service.import_rows(raw_rows)
    summary = ImportSummary(**outcome["summary"])
    message = (
        f"共 {summary.total} 行：新建 {summary.created}、更新 {summary.updated}、"
        f"未变化 {summary.unchanged}、重复 {summary.duplicated}、失败 {summary.failed}"
    )
    if summary.skipped:
        message += f"、空行 {summary.skipped}"
    results = [ImportRowResult(**item) for item in outcome["results"]]
    return ImportResult(ok=True, message=message, summary=summary, results=results)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条校准记录单明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"校准记录单 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条校准记录单，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="校准记录单已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条校准记录单执行执行校准、标记合格、标记不合格；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


def _decode_text(raw: bytes) -> str | None:
    """依次尝试常见编码；都解不开时返回 None，由调用方给出提示。"""
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def _parse_csv(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = [(name or "").strip() for name in (reader.fieldnames or [])]
    if not any(fieldnames):
        raise ValueError("CSV 文件缺少表头，第一行应是列名")
    if "记录编号" not in fieldnames:
        raise ValueError("CSV 缺少必需表头：记录编号")
    return [{(key or "").strip(): value for key, value in row.items()} for row in reader]


def _parse_json(text: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 解析失败：{exc.msg}") from exc
    if isinstance(payload, dict):
        payload = payload.get("items")  # 兼容清单导出的格式，导出文件可以直接再导入
    if not isinstance(payload, list):
        raise ValueError("JSON 文件必须是记录数组，或包含 items 数组的对象")
    rows = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("JSON 里的每条记录必须是对象")
        rows.append(item)
    return rows
