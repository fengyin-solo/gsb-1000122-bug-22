"""接口出入参模型：列表分页、动作结果与各模块的明细结构。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class ActionResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None


class EntryPayload(BaseModel):
    """登记或修改一条业务记录时提交的字段集合。"""

    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None


class ImportPayload(BaseModel):
    """外部文件导入：前端解析后按行提交的字段集合。"""

    rows: list[dict[str, Any]] = Field(default_factory=list)
    source: str | None = None
    file_name: str | None = None


class ImportLineResult(BaseModel):
    """逐行反馈：行号、记录编号、结论与可读原因。"""

    line: int
    record: str = ""
    outcome: str  # created / updated / skipped / failed
    message: str = ""


class ImportReport(BaseModel):
    ok: bool
    message: str
    busy: bool = False
    source: str | None = None
    file_name: str | None = None
    total: int = 0
    blank: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    lines: list[ImportLineResult] = Field(default_factory=list)


class UpdatePayload(BaseModel):
    """详情页保存编辑时提交的字段与修订号（用于冲突检测）。"""

    values: dict[str, Any] = Field(default_factory=dict)
    revision: int | None = None



class SampleEntry(BaseModel):
    """检测样品明细结构。"""

    field_0: str | None = None  # 样品编号
    field_1: str | None = None  # 样品名称
    field_2: str | None = None  # 委托单位
    field_3: str | None = None  # 样品类型
    field_4: str | None = None  # 接收日期
    field_5: str | None = None  # 保存条件
    field_6: str | None = None  # 送样人员
    field_7: str | None = None  # 接收状态

class TaskEntry(BaseModel):
    """检测任务单明细结构。"""

    field_0: str | None = None  # 任务编号
    field_1: str | None = None  # 所属样品
    field_2: str | None = None  # 检测项目
    field_3: str | None = None  # 检测标准
    field_4: str | None = None  # 指定检测员
    field_5: str | None = None  # 截止日期
    field_6: str | None = None  # 优先级
    field_7: str | None = None  # 任务状态

class InstrumentEntry(BaseModel):
    """检测仪器明细结构。"""

    field_0: str | None = None  # 仪器编号
    field_1: str | None = None  # 仪器名称
    field_2: str | None = None  # 型号规格
    field_3: str | None = None  # 所属实验室
    field_4: str | None = None  # 校准周期
    field_5: str | None = None  # 上次校准日
    field_6: str | None = None  # 下次校准日
    field_7: str | None = None  # 仪器状态

class CalibrationEntry(BaseModel):
    """校准记录单明细结构。"""

    field_0: str | None = None  # 记录编号
    field_1: str | None = None  # 仪器编号
    field_2: str | None = None  # 校准机构
    field_3: str | None = None  # 校准日期
    field_4: str | None = None  # 校准结果
    field_5: str | None = None  # 偏差值
    field_6: str | None = None  # 校准证书号
    field_7: str | None = None  # 记录状态

class ReagentEntry(BaseModel):
    """试剂耗材明细结构。"""

    field_0: str | None = None  # 试剂编号
    field_1: str | None = None  # 试剂名称
    field_2: str | None = None  # 规格等级
    field_3: str | None = None  # 生产厂家
    field_4: str | None = None  # 有效期至
    field_5: str | None = None  # 存放位置
    field_6: str | None = None  # 领用人员
    field_7: str | None = None  # 使用状态

class ResultEntry(BaseModel):
    """检测结果明细结构。"""

    field_0: str | None = None  # 结果编号
    field_1: str | None = None  # 所属任务
    field_2: str | None = None  # 检测项
    field_3: str | None = None  # 实测值
    field_4: str | None = None  # 标准限值
    field_5: str | None = None  # 判定结论
    field_6: str | None = None  # 检测日期
    field_7: str | None = None  # 结果状态

class ReportEntry(BaseModel):
    """检测报告明细结构。"""

    field_0: str | None = None  # 报告编号
    field_1: str | None = None  # 委托单位
    field_2: str | None = None  # 样品名称
    field_3: str | None = None  # 报告类型
    field_4: str | None = None  # 编制人
    field_5: str | None = None  # 批准人
    field_6: str | None = None  # 签发日期
    field_7: str | None = None  # 报告状态

class QcEntry(BaseModel):
    """质控样品明细结构。"""

    field_0: str | None = None  # 质控编号
    field_1: str | None = None  # 质控类别
    field_2: str | None = None  # 标准值
    field_3: str | None = None  # 允许偏差
    field_4: str | None = None  # 实测值
    field_5: str | None = None  # 判定结果
    field_6: str | None = None  # 检测日期
    field_7: str | None = None  # 质控状态

class DeviationEntry(BaseModel):
    """偏离记录明细结构。"""

    field_0: str | None = None  # 偏离编号
    field_1: str | None = None  # 偏离描述
    field_2: str | None = None  # 涉及样品
    field_3: str | None = None  # 发现人
    field_4: str | None = None  # 发现日期
    field_5: str | None = None  # 处理措施
    field_6: str | None = None  # 验证结果
    field_7: str | None = None  # 偏离状态

class SampleStorageEntry(BaseModel):
    """留存样品明细结构。"""

    field_0: str | None = None  # 留存编号
    field_1: str | None = None  # 样品编号
    field_2: str | None = None  # 留存位置
    field_3: str | None = None  # 留存期限
    field_4: str | None = None  # 到期日期
    field_5: str | None = None  # 保管人员
    field_6: str | None = None  # 处理方式
    field_7: str | None = None  # 留存状态

class ContractEntry(BaseModel):
    """委托检验合同明细结构。"""

    field_0: str | None = None  # 合同编号
    field_1: str | None = None  # 委托单位
    field_2: str | None = None  # 联系人
    field_3: str | None = None  # 样品数量
    field_4: str | None = None  # 检测项目
    field_5: str | None = None  # 合同金额
    field_6: str | None = None  # 签约日期
    field_7: str | None = None  # 合同状态

class StaffEntry(BaseModel):
    """检测员明细结构。"""

    field_0: str | None = None  # 员工编号
    field_1: str | None = None  # 姓名
    field_2: str | None = None  # 技术职称
    field_3: str | None = None  # 资质证书
    field_4: str | None = None  # 授权项目
    field_5: str | None = None  # 在岗状态
    field_6: str | None = None  # 考核日期
    field_7: str | None = None  # 考核结果

class MethodEntry(BaseModel):
    """检测方法明细结构。"""

    field_0: str | None = None  # 方法编号
    field_1: str | None = None  # 方法名称
    field_2: str | None = None  # 适用标准
    field_3: str | None = None  # 检测范围
    field_4: str | None = None  # 检出限
    field_5: str | None = None  # 方法版本
    field_6: str | None = None  # 批准日期
    field_7: str | None = None  # 方法状态

class EnvironmentEntry(BaseModel):
    """环境记录明细结构。"""

    field_0: str | None = None  # 记录编号
    field_1: str | None = None  # 监测区域
    field_2: str | None = None  # 温度值
    field_3: str | None = None  # 湿度值
    field_4: str | None = None  # 压差值
    field_5: str | None = None  # 记录时间
    field_6: str | None = None  # 记录人员
    field_7: str | None = None  # 环境状态

class ComplainEntry(BaseModel):
    """申诉记录明细结构。"""

    field_0: str | None = None  # 申诉编号
    field_1: str | None = None  # 申诉单位
    field_2: str | None = None  # 涉及报告
    field_3: str | None = None  # 申诉内容
    field_4: str | None = None  # 受理日期
    field_5: str | None = None  # 处理结果
    field_6: str | None = None  # 回复日期
    field_7: str | None = None  # 申诉状态

class AuditEntry(BaseModel):
    """内审记录明细结构。"""

    field_0: str | None = None  # 内审编号
    field_1: str | None = None  # 审核范围
    field_2: str | None = None  # 审核组长
    field_3: str | None = None  # 审核日期
    field_4: str | None = None  # 不符合项
    field_5: str | None = None  # 纠正期限
    field_6: str | None = None  # 跟踪验证
    field_7: str | None = None  # 内审状态

class EquipmentRepairEntry(BaseModel):
    """维修记录明细结构。"""

    field_0: str | None = None  # 维修编号
    field_1: str | None = None  # 仪器编号
    field_2: str | None = None  # 故障描述
    field_3: str | None = None  # 报修人
    field_4: str | None = None  # 报修日期
    field_5: str | None = None  # 维修单位
    field_6: str | None = None  # 修复日期
    field_7: str | None = None  # 维修状态

class DocumentEntry(BaseModel):
    """体系文档明细结构。"""

    field_0: str | None = None  # 文档编号
    field_1: str | None = None  # 文档名称
    field_2: str | None = None  # 文档类型
    field_3: str | None = None  # 编制人
    field_4: str | None = None  # 版本号
    field_5: str | None = None  # 生效日期
    field_6: str | None = None  # 分发范围
    field_7: str | None = None  # 文档状态
