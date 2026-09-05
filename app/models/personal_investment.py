"""
个人投资助手数据模型

包含投资画像、策略定义、策略任务和结果等 MongoDB 文档模型。
用于支持面向新手的个人投资助手功能。
"""

from datetime import datetime
from typing import Optional, Dict, Any, List, Annotated
from enum import Enum

from pydantic import BaseModel, Field, BeforeValidator, PlainSerializer, field_validator
from bson import ObjectId

from app.utils.timezone import now_tz


# ==================== ObjectId 处理 ====================

def validate_object_id(v: Any) -> ObjectId:
    """验证ObjectId"""
    if isinstance(v, ObjectId):
        return v
    if isinstance(v, str):
        if ObjectId.is_valid(v):
            return ObjectId(v)
    raise ValueError("Invalid ObjectId")


def serialize_object_id(v: ObjectId) -> str:
    """序列化ObjectId为字符串"""
    return str(v)


PyObjectId = Annotated[
    ObjectId,
    BeforeValidator(validate_object_id),
    PlainSerializer(serialize_object_id, return_type=str),
]


# ==================== 枚举类型 ====================

class RiskPreference(str, Enum):
    """风险偏好"""
    CONSERVATIVE = "conservative"  # 保守型
    BALANCED = "balanced"          # 平衡型
    AGGRESSIVE = "aggressive"      # 进取型


class TradingStyle(str, Enum):
    """交易风格"""
    VALUE = "value"           # 价值投资
    GROWTH = "growth"         # 成长投资
    MOMENTUM = "momentum"     # 趋势跟踪
    DIVIDEND = "dividend"     # 红利投资
    CONTRARIAN = "contrarian" # 逆向投资


class StrategyStatus(str, Enum):
    """策略状态"""
    ACTIVE = "active"       # 启用
    DISABLED = "disabled"   # 停用
    ARCHIVED = "archived"   # 归档


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"       # 等待中
    RUNNING = "running"       # 运行中
    COMPLETED = "completed"   # 已完成
    FAILED = "failed"         # 失败
    DATA_INSUFFICIENT = "data_insufficient"  # 数据不足


class TaskType(str, Enum):
    """任务类型"""
    STRATEGY_SCREENING = "strategy_screening"  # 策略选股
    STRATEGY_CHECKUP = "strategy_checkup"      # 策略体检


class TemplateStatus(str, Enum):
    """策略模板状态"""
    DRAFT = "draft"             # 草稿
    PENDING_REVIEW = "pending_review"  # 待审核
    PUBLISHED = "published"     # 已上架
    REJECTED = "rejected"       # 审核未通过
    DISABLED = "disabled"       # 已下架


class TemplateSource(str, Enum):
    """策略模板来源"""
    BUILTIN = "builtin"         # 系统内置
    OPERATIONS = "operations"   # 运营沉淀
    AGENT_DRAFT = "agent_draft" # Agent 生成草案


# ==================== 投资画像模型 ====================

class InvestmentProfile(BaseModel):
    """个人投资画像"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    user_id: str = Field(..., description="用户 ID")

    # 基本信息
    risk_preference: RiskPreference = Field(default=RiskPreference.BALANCED, description="风险偏好")
    trading_style: TradingStyle = Field(default=TradingStyle.VALUE, description="交易风格")

    # 资金区间（单位：元）
    capital_range_min: float = Field(default=0, ge=0, description="最小资金量")
    capital_range_max: float = Field(default=1000000, gt=0, description="最大资金量")

    # 目标市场
    target_markets: List[str] = Field(default_factory=lambda: ["A股"], description="目标市场列表")

    # 禁投规则
    excluded_sectors: List[str] = Field(default_factory=list, description="禁投行业")
    excluded_stocks: List[str] = Field(default_factory=list, description="禁投标的代码")
    exclude_st: bool = Field(default=True, description="排除 ST 股票")
    exclude_new_stock_days: int = Field(default=60, ge=0, description="排除上市天数少于 N 的新股")

    # 持仓信息
    current_holdings: List[Dict[str, Any]] = Field(default_factory=list, description="当前持仓")
    max_position_per_stock: float = Field(default=0.2, ge=0, le=1, description="单只股票最大仓位比例")

    # 默认研究上下文
    default_context: str = Field(default="", max_length=500, description="默认研究上下文备注")

    # 是否启用上下文注入
    context_injection_enabled: bool = Field(default=True, description="是否在研究中注入画像上下文")

    # 元数据
    created_at: datetime = Field(default_factory=now_tz)
    updated_at: datetime = Field(default_factory=now_tz)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}

    @field_validator("capital_range_max")
    @classmethod
    def validate_capital_range(cls, v: float, info) -> float:
        """验证资金区间合理性"""
        data = info.data
        if "capital_range_min" in data and v <= data["capital_range_min"]:
            raise ValueError("最大资金量必须大于最小资金量")
        return v


# ==================== 策略定义模型 ====================

class StrategyDefinition(BaseModel):
    """策略定义"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    strategy_id: str = Field(..., description="策略唯一标识")
    user_id: str = Field(default="", description="所属用户 ID")

    # 基本信息
    name: str = Field(..., min_length=1, max_length=100, description="策略名称")
    description: str = Field(default="", max_length=1000, description="策略描述")
    status: StrategyStatus = Field(default=StrategyStatus.ACTIVE)

    # 适用市场
    applicable_markets: List[str] = Field(default_factory=lambda: ["A股"], description="适用市场")

    # 筛选条件
    screening_criteria: Dict[str, Any] = Field(default_factory=dict, description="筛选条件")
    # 示例: {"pe_max": 20, "roe_min": 10, "dividend_yield_min": 2, "market_cap_min": 1000000000}

    # 参数配置
    parameters: Dict[str, Any] = Field(default_factory=dict, description="策略参数")

    # 标签
    tags: List[str] = Field(default_factory=list, description="策略标签")

    # 元数据
    created_at: datetime = Field(default_factory=now_tz)
    updated_at: datetime = Field(default_factory=now_tz)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


# ==================== 策略模板模型（策略广场） ====================

class StrategyTemplate(BaseModel):
    """策略广场模板——平台公共资产，与用户策略实例分离"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    template_id: str = Field(..., description="模板唯一标识")

    # 基本信息
    name: str = Field(..., min_length=1, max_length=100, description="策略名称")
    one_liner: str = Field(default="", max_length=200, description="一句话说明（面向新手）")
    description: str = Field(default="", max_length=2000, description="详细描述")

    # 状态与来源
    status: TemplateStatus = Field(default=TemplateStatus.DRAFT)
    source: TemplateSource = Field(default=TemplateSource.BUILTIN)
    version: str = Field(default="1.0.0", description="模板版本")
    author: str = Field(default="system", description="作者/维护者")

    # 新手解释字段
    audience: str = Field(default="", max_length=500, description="适合人群")
    not_for: str = Field(default="", max_length=500, description="不适合人群")
    risk_boundary: str = Field(default="", max_length=1000, description="风险边界说明")
    data_requirements: str = Field(default="", max_length=500, description="数据要求")
    rule_explanation: Dict[str, Any] = Field(default_factory=dict, description="规则拆解和指标解释")

    # 策略核心配置（复制到用户策略时使用）
    applicable_markets: List[str] = Field(default_factory=lambda: ["A股"])
    screening_criteria: Dict[str, Any] = Field(default_factory=dict)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)

    # 模拟指标（由定时任务或按需触发更新）
    simulation_cumulative_return: Optional[float] = Field(default=None, description="最新模拟累计收益")
    simulation_max_drawdown: Optional[float] = Field(default=None, description="最新模拟最大回撤")
    simulation_period: Optional[str] = Field(default=None, description="模拟区间，如 '2024-01-01 ~ 2024-12-31'")
    simulation_data_as_of: Optional[datetime] = Field(default=None, description="模拟数据截至时间")
    simulation_data_sufficient: bool = Field(default=False, description="模拟数据是否充分")
    data_preparation_status: Optional[str] = Field(default=None, description="数据准备状态: ready/preparing/insufficient")

    # 元数据
    created_at: datetime = Field(default_factory=now_tz)
    updated_at: datetime = Field(default_factory=now_tz)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


# ==================== 策略任务模型 ====================

class StrategyTask(BaseModel):
    """策略任务（选股或体检）"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    task_id: str = Field(..., description="任务唯一标识")
    user_id: str = Field(..., description="用户 ID")

    # 任务信息
    task_type: TaskType = Field(..., description="任务类型")
    strategy_id: str = Field(..., description="关联策略 ID")
    profile_id: Optional[str] = Field(default=None, description="关联画像 ID")

    # 任务状态
    status: TaskStatus = Field(default=TaskStatus.PENDING)

    # 输入参数
    input_params: Dict[str, Any] = Field(default_factory=dict, description="任务输入参数")

    # 执行信息
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    error_message: Optional[str] = Field(default=None)

    # 数据来源和时间
    data_sources: List[str] = Field(default_factory=list, description="使用的数据源")
    data_as_of: Optional[datetime] = Field(default=None, description="数据截止时间")

    # 元数据
    created_at: datetime = Field(default_factory=now_tz)
    updated_at: datetime = Field(default_factory=now_tz)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


# ==================== 策略选股结果模型 ====================

class ScreeningCandidate(BaseModel):
    """选股候选标的"""
    stock_code: str = Field(..., description="股票代码")
    stock_name: str = Field(default="", description="股票名称")
    match_reasons: List[str] = Field(default_factory=list, description="命中原因")
    risk_warnings: List[str] = Field(default_factory=list, description="风险提示")
    conflict_with_profile: bool = Field(default=False, description="是否与用户画像冲突")
    conflict_reason: Optional[str] = Field(default=None, description="冲突原因")
    score: float = Field(default=0.0, ge=0, le=1, description="综合评分")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="关键指标")


class ScreeningResult(BaseModel):
    """策略选股结果"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    result_id: str = Field(..., description="结果唯一标识")
    task_id: str = Field(..., description="关联任务 ID")
    user_id: str = Field(default="", description="所属用户 ID")

    # 候选池
    candidates: List[ScreeningCandidate] = Field(default_factory=list, description="候选标的列表")
    total_candidates: int = Field(default=0, description="候选总数")

    # 统计信息
    market_coverage: str = Field(default="", description="覆盖市场")
    screening_date: datetime = Field(default_factory=now_tz, description="筛选日期")

    # 风险提示
    overall_risks: List[str] = Field(default_factory=list, description="整体风险提示")

    # 数据质量
    data_sufficient: bool = Field(default=True, description="数据是否充分")
    coverage_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="数据覆盖率")
    data_as_of: Optional[datetime] = Field(default=None, description="实际数据截至日期")

    # 术语合规检查
    terminology_compliant: bool = Field(default=True, description="术语是否合规")

    created_at: datetime = Field(default_factory=now_tz)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


# ==================== 策略体检结果模型 ====================

class CheckupMetric(BaseModel):
    """体检指标"""
    name: str = Field(..., description="指标名称")
    value: Any = Field(..., description="指标值")
    unit: str = Field(default="", description="单位")
    interpretation: str = Field(default="", description="解读说明")


class CheckupResult(BaseModel):
    """策略体检结果"""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    result_id: str = Field(..., description="结果唯一标识")
    task_id: str = Field(..., description="关联任务 ID")
    user_id: str = Field(default="", description="所属用户 ID")

    # 适配度结论
    fitness_level: str = Field(default="unknown", description="适配度等级: high/medium/low/unknown")
    fitness_summary: str = Field(default="", max_length=500, description="适配度摘要")

    # 关键依据
    key_metrics: List[CheckupMetric] = Field(default_factory=list, description="关键指标")

    # 近期表现摘要
    recent_performance: Dict[str, Any] = Field(default_factory=dict, description="近期表现")

    # 风险提示
    risk_warnings: List[str] = Field(default_factory=list, description="风险提示")

    # 数据质量
    data_sufficient: bool = Field(default=True, description="数据是否充分")
    data_quality_note: Optional[str] = Field(default=None, description="数据质量说明")

    # 数据质量
    coverage_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="数据覆盖率")
    data_as_of: Optional[datetime] = Field(default=None, description="实际行情数据日期")

    # 免责声明
    disclaimer: str = Field(
        default="本体检结果仅供参考，不构成投资建议。历史表现不代表未来收益。",
        description="免责声明"
    )

    checkup_date: datetime = Field(default_factory=now_tz, description="体检日期")
    created_at: datetime = Field(default_factory=now_tz)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}
