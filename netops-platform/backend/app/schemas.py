"""
Pydantic 模型 - API 请求/响应的数据校验与序列化
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ============================================================
# 认证相关
# ============================================================
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_info: dict


class UserInfo(BaseModel):
    id: str
    username: str
    role: str


# ============================================================
# 设备相关
# ============================================================
class DeviceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    sys_name: Optional[str] = Field(None, max_length=128, description="LLDP/CDP 系统名，用于拓扑匹配")
    device_type: str = Field(default="single", pattern=r'^(single|stack|mlag|cluster)$')
    ip: str = Field(..., pattern=r'^[\w\.\:-]+$')
    snmp_version: int = Field(default=3, ge=2, le=3)
    snmp_port: int = Field(default=161, ge=1, le=65535)
    snmp_user: Optional[str] = Field(None, max_length=64)
    vendor: Optional[str] = Field(None, max_length=64)
    model: Optional[str] = Field(None, max_length=64)
    role: Optional[str] = Field(None, max_length=64)
    region_id: Optional[str] = Field(None)  # 区域 ID
    sub_region_id: Optional[str] = Field(None)  # 子区域 ID
    poll_interval: int = Field(default=60, ge=10, le=3600)
    adapter: str = Field(default="snmp")
    ssh_port: int = Field(default=22, ge=1, le=65535)
    enabled: bool = True

    # SNMP 凭据（明文传入，后端加密存储）
    snmp_community: Optional[str] = Field(None, description="SNMPv2c 团体字")
    snmp_auth_pass: Optional[str] = Field(None, description="SNMPv3 认证密码")
    snmp_priv_pass: Optional[str] = Field(None, description="SNMPv3 加密密码")
    snmp_auth_protocol: Optional[str] = Field(default="SHA", description="SNMPv3 认证协议: MD5/SHA")
    snmp_priv_protocol: Optional[str] = Field(default="AES", description="SNMPv3 加密协议: DES/AES")

    # SSH 凭据（用于配置备份）
    ssh_username: Optional[str] = Field(None, description="SSH 用户名")
    ssh_password: Optional[str] = Field(None, description="SSH 密码")


class DeviceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    sys_name: Optional[str] = Field(None, max_length=128)
    device_type: Optional[str] = Field(None, pattern=r'^(single|stack|mlag|cluster)$')
    ip: Optional[str] = Field(None, pattern=r'^[\w\.\:-]+$')
    snmp_version: Optional[int] = Field(None, ge=2, le=3)
    snmp_port: Optional[int] = Field(None, ge=1, le=65535)
    snmp_user: Optional[str] = Field(None, max_length=64)
    vendor: Optional[str] = Field(None, max_length=64)
    model: Optional[str] = Field(None, max_length=64)
    role: Optional[str] = Field(None, max_length=64)
    region_id: Optional[str] = Field(None)
    sub_region_id: Optional[str] = Field(None)
    poll_interval: Optional[int] = Field(None, ge=10, le=3600)
    adapter: Optional[str] = None
    ssh_port: Optional[int] = Field(None, ge=1, le=65535)
    enabled: Optional[bool] = None
    snmp_community: Optional[str] = Field(None)
    snmp_auth_pass: Optional[str] = Field(None)
    snmp_priv_pass: Optional[str] = Field(None)
    snmp_auth_protocol: Optional[str] = Field(None)
    snmp_priv_protocol: Optional[str] = Field(None)
    ssh_username: Optional[str] = Field(None)
    ssh_password: Optional[str] = Field(None)


class DeviceResponse(BaseModel):
    id: str
    name: str
    sys_name: Optional[str]
    device_type: str
    ip: str
    snmp_version: int
    snmp_port: int
    snmp_user: Optional[str]
    vendor: Optional[str]
    model: Optional[str]
    role: Optional[str]
    region_id: Optional[str] = None
    sub_region_id: Optional[str] = None
    region_name: Optional[str] = None  # 冗余字段，方便前端展示
    sub_region_name: Optional[str] = None
    poll_interval: int
    adapter: str
    ssh_port: int
    enabled: bool
    status: str
    last_seen_at: Optional[datetime]
    created_at: Optional[datetime]

    model_config = {"from_attributes": True}


class DeviceListResponse(BaseModel):
    total: int
    items: list[DeviceResponse]


# ============================================================
# 指标查询相关
# ============================================================
class MetricsQuery(BaseModel):
    device_id: str
    metric_names: list[str] = ["snmp_cpu_usage_percent", "snmp_memory_usage_percent"]
    range_hours: int = Field(default=1, ge=1, le=168)  # 最大 7 天
    step_seconds: int = Field(default=60, ge=10, le=3600)


class MetricDataPoint(BaseModel):
    timestamp: float
    value: Optional[float]


class MetricSeries(BaseModel):
    metric: dict  # labels 如 {device="xxx", ifName="GE0"}
    values: list[MetricDataPoint]


class MetricsResponse(BaseModel):
    metric_name: str
    data: list[MetricSeries]


# ============================================================
# 告警相关
# ============================================================
class AlertRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    device_id: Optional[str] = Field(None)  # NULL = 全部设备
    metric_name: str
    threshold: float = Field(..., gt=0)
    duration_seconds: int = Field(default=0, ge=0)
    severity: int = Field(default=2, ge=0, le=3)
    critical_threshold: Optional[float] = Field(None, gt=0)  # 超过该值升级为 P0(红)
    enabled: bool = True


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    device_id: Optional[str] = None
    metric_name: Optional[str] = None
    threshold: Optional[float] = Field(None, gt=0)
    duration_seconds: Optional[int] = Field(None, ge=0)
    severity: Optional[int] = Field(None, ge=0, le=3)
    critical_threshold: Optional[float] = Field(None, gt=0)
    enabled: Optional[bool] = None


class AlertRuleResponse(BaseModel):
    id: str
    name: str
    device_id: Optional[str]
    metric_name: str
    operator: str
    threshold: float
    duration_seconds: int
    severity: int
    critical_threshold: Optional[float]
    enabled: bool
    created_at: Optional[datetime]

    model_config = {"from_attributes": True}


class AlertResponse(BaseModel):
    id: str
    rule_id: str
    device_id: str
    status: str
    severity: Optional[int]  # 离线/异常告警为 NULL（不进 P 级别体系）
    category: str
    message: str
    value: Optional[float]
    fired_at: Optional[datetime]
    acknowledged_at: Optional[datetime]
    resolved_at: Optional[datetime]

    model_config = {"from_attributes": True}


class AlertAcknowledge(BaseModel):
    acknowledged_by: str = Field(..., min_length=1)


# ============================================================
# 通用响应
# ============================================================
class MessageResponse(BaseModel):
    message: str
    detail: Optional[dict] = None


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    db_connected: bool = False
    vm_connected: bool = False
