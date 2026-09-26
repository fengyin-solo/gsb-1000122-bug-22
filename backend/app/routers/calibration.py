"""校准记录接口：维护校准记录单，覆盖动作流转、外部文件导入、导出与详情编辑。

路由顺序注意：``/export``、``/stats`` 这类静态路径必须声明在 ``/{entry_id}``
之前，否则 GET /export 会被当成 entry_id 解析而报 422。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import (
    ActionResult,
    EntryPayload,
    ImportPayload,
    ImportReport,
    PageResult,
    UpdatePayload,
)
from app.services.calibration import MODULE, CalibrationService

router = APIRouter(prefix="/api/calibration", tags=["校准记录"])

service = CalibrationService()

LIST_FIELDS = ["记录编号", "仪器编号", "校准机构", "校准日期", "校准结果", "偏差值", "校准证书号", "记录状态"]
STATUSES = ["待校准", "校准中", "已合格", "不合格"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按记录编号检索"),
    instrument: str | None = Query(default=None, description="按仪器编号检索"),
    organization: str | None = Query(default=None, description="按校准机构检索"),
    status: str | None = Query(default=None, description="待校准、校准中、已合格、不合格"),
    page: int = 1,
    size: int = 200,
) -> PageResult[dict]:
    """按记录编号、仪器编号、校准机构与状态过滤列表；空页不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword,
        instrument=instrument,
        organization=organization,
        status=status,
        page=page,
        size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def stats() -> dict[str, int]:
    """数量指标：与列表共用同一份状态口径，卡片数字和列表始终对得上。"""
    return service.stats()


@router.post("/import", response_model=ImportReport)
def import_entries(payload: ImportPayload) -> ImportReport:
    """导入外部文件（校准记录、校准机构等列）。

    同一记录编号做 upsert：已存在则只更新本次给出的非空列，不存在才新增；
    逐行反馈，空文件/缺列/文件内重复行都会明确提示，任一行失败则整批不提交，
    可修正后直接重试。
    """
    source = (payload.source or payload.file_name or "外部文件").strip() or "外部文件"
    report, busy = service.import_rows(payload.rows, source=source)
    if busy:
        raise HTTPException(status_code=409, detail=report.get("message", "导入冲突，请稍后重试"))
    return ImportReport(**report)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出校准记录清单：与导入互斥，撞上导入时返回 409 让前端再次下载。"""
    snapshot = service.export_snapshot()
    if snapshot is None:
        raise HTTPException(status_code=409, detail="校准记录正在导入，请稍后再次下载")
    return snapshot


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条校准记录单明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"校准记录单 {entry_id} 不存在或已归档")
    return entry


@router.patch("/{entry_id}", response_model=ActionResult)
def update_entry(entry_id: int, payload: UpdatePayload) -> ActionResult:
    """详情页保存编辑：只改数据列，工作流状态仍由动作流转，编号撞车会被拦下。"""
    entry, message, conflict = service.update_entry(entry_id, payload.values, revision=payload.revision)
    if conflict == "missing":
        raise HTTPException(status_code=404, detail=message)
    if conflict == "revision":
        raise HTTPException(status_code=409, detail=message)
    if conflict == "duplicate":
        return ActionResult(ok=False, message=message, entry=entry)
    if conflict == "validation":
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="校准记录已保存", entry=entry)


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条校准记录单，缺字段或编号重复时说明原因而不是静默丢弃。"""
    entry, problems = service.create_entry(payload.values)
    if problems:
        return ActionResult(ok=False, message="；".join(problems))
    return ActionResult(ok=True, message="校准记录单已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条校准记录单执行执行校准、标记合格、标记不合格；不允许的动作会被拦下。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
