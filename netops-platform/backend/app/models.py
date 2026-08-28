"""
SQLAlchemy ORM 模型 - 数据库无关设计（兼容 SQLite / PostgreSQL）
UUID 主键用 String 存储（避免依赖 PG 的 UUID 类型）
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, Boolean, Text, Float, ForeignKey, JSON, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


def generate_uuid() -> str:
    """生成 UUID 字符串"""
    return str(uuid.uuid4())


# ============================================================
# 用户模型（MVP 简化：仅 admin / viewer 两角色）
# ============================================================
class User(Base):
    __tablename__ = "user"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="viewer")  # admin / viewer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ============================================================
# 设备模型
# ============================================================
class Device(Base):
    __tablename__ = "device"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    sys_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)  # LLDP/CDP 系统名别名，用于拓扑匹配
    device_type: Mapped[str] = mapped_column(String(16), default="single")  # single(单机) / stack(堆叠) / mlag / cluster
    ip: Mapped[str] = mapped_column(String(45), nullable=False, index=True)  # 支持 IPv6
    snmp_version: Mapped[int] = mapped_column(Integer, default=3)  # 2 或 3
    snmp_port: Mapped[int] = mapped_column(Integer, default=161)
    snmp_user: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # v3 用户名
    vendor: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # huawei/h3c/generic/...
    model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    role: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # firewall/core/switch/router/...
    region_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("region.id"), nullable=True, index=True)  # 所属区域
    sub_region_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("sub_region.id"), nullable=True, index=True)  # 所属子区域
    region: Mapped[Optional["Region"]] = relationship(foreign_keys=[region_id])
    sub_region: Mapped[Optional["SubRegion"]] = relationship(foreign_keys=[sub_region_id])
    poll_interval: Mapped[int] = mapped_column(Integer, default=60)  # 采集间隔（秒）
    adapter: Mapped[str] = mapped_column(String(32), default="snmp")  # snmp/api/cli/web
    ssh_port: Mapped[int] = mapped_column(Integer, default=22)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(16), default="unknown")  # online/offline/unknown/error
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 关联：凭据（一对多）
    credentials: Mapped[list["DeviceCredential"]] = relationship(back_populates="device", cascade="all, delete-orphan")


# ============================================================
# 区域模型
# ============================================================
class Region(Base):
    __tablename__ = "region"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)  # 排序权重
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # 关联：子区域（一对多）
    sub_regions: Mapped[list["SubRegion"]] = relationship(back_populates="region", cascade="all, delete-orphan")
    # 关联：设备
    devices: Mapped[list["Device"]] = relationship(foreign_keys=[Device.region_id], overlaps="region")


class SubRegion(Base):
    __tablename__ = "sub_region"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    region_id: Mapped[str] = mapped_column(String(36), ForeignKey("region.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # 所属区域
    region: Mapped["Region"] = relationship(back_populates="sub_regions")
    # 设备
    devices: Mapped[list["Device"]] = relationship(foreign_keys=[Device.sub_region_id], overlaps="sub_region")


# ============================================================
# 设备凭据（加密存储）
# ============================================================
class DeviceCredential(Base):
    __tablename__ = "device_credential"

    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("device.id", ondelete="CASCADE"), primary_key=True)
    cred_type: Mapped[str] = mapped_column(String(32), primary_key=True)  # snmp_v2c_community / snmp_v3_auth / snmp_v3_priv
    secret_enc: Mapped[str] = mapped_column(Text, nullable=False)  # AES-256-GCM 加密后的密文（Base64 编码）
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # 关联：设备
    device: Mapped["Device"] = relationship(back_populates="credentials")


# ============================================================
# 告警规则
# ============================================================
class AlertRule(Base):
    __tablename__ = "alert_rule"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    device_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("device.id"), nullable=True)  # NULL = 全部设备
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False)  # 如 snmp_cpu_usage_percent
    operator: Mapped[str] = mapped_column(String(8), default="gt")  # gt (大于)，MVP 只支持这一种
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)  # 持续多久才触发（秒）
    severity: Mapped[int] = mapped_column(Integer, default=2)  # 0=P0严重(红), 1=P1重要(橙), 2=P2次要(黄), 3=P3提示(蓝)
    # 可选的第二级阈值：当采集值超过该值时，严重级别升级为 1(P1/红)。
    # 例：CPU 利用率 threshold=85(橙/警告) 但 critical_threshold=95(红/严重)。
    critical_threshold: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # 关联设备
    device: Mapped[Optional["Device"]] = relationship()


# ============================================================
# SNMP Trap 接收日志
# ============================================================
class SnmpTrapLog(Base):
    __tablename__ = "snmp_trap_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    source_ip: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_port: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[str] = mapped_column(String(8), nullable=False, default="v2c")
    community: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    security_level: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    pdu_type: Mapped[str] = mapped_column(String(16), nullable=False, default="Trap")
    variables: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    raw_hex: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    mapped_alert_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("alert.id"), nullable=True)


# ============================================================
# Trap → Alert 映射规则
# ============================================================
class TrapRule(Base):
    __tablename__ = "trap_rule"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    oid_prefix: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    severity: Mapped[int] = mapped_column(Integer, default=2)
    message_template: Mapped[str] = mapped_column(Text, nullable=False, default="收到 SNMP Trap")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ============================================================
# 告警事件
# ============================================================
class Alert(Base):
    __tablename__ = "alert"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    rule_id: Mapped[str] = mapped_column(String(36), ForeignKey("alert_rule.id"))
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("device.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active/acknowledged/resolved/closed
    # 严重级别 1=P1(红) 2=P2(橙) 3=P3(蓝)。设备离线/采集异常不进入 P 级别体系，severity 为 NULL。
    severity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    category: Mapped[str] = mapped_column(String(16), default="threshold")  # threshold(阈值) / offline(离线) / error(采集异常)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 触发时的值
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # 关联
    rule: Mapped["AlertRule"] = relationship()
    device: Mapped["Device"] = relationship()


# ============================================================
# 设备配置备份
# ============================================================
class ConfigBackup(Base):
    __tablename__ = "config_backup"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    device_id: Mapped[str] = mapped_column(String(36), ForeignKey("device.id", ondelete="CASCADE"), index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)  # 版本号，按设备递增
    content: Mapped[str] = mapped_column(Text, nullable=False)  # 配置内容
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256 哈希
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    captured_by: Mapped[str] = mapped_column(String(64), default="system")  # system / username
    change_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 相对上一版本的摘要

    device: Mapped["Device"] = relationship()


# ============================================================
# 审计日志
# ============================================================
class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    actor: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)  # create_device / login / ...
    target: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 操作对象描述
    detail: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class ReportTemplate(Base):
    __tablename__ = "report_template"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    report_type: Mapped[str] = mapped_column(String(16), default="daily")  # daily/weekly/monthly
    widgets: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON 数组
    schedule: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # cron 表达式
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ReportInstance(Base):
    __tablename__ = "report_instance"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    template_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("report_template.id"), nullable=True)
    report_type: Mapped[str] = mapped_column(String(16), default="daily")
    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    pdf_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    excel_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="completed")  # completed/failed
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ============================================================
# 拓扑连接（链路）
#   通过 LLDP/CDP 自动发现设备间的物理/逻辑连接。
#   local_* 为本端设备侧，remote_* 为对端（可能未录入系统，故 remote_device_id 可空）。
# ============================================================
class Link(Base):
    __tablename__ = "link"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    local_device_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("device.id", ondelete="CASCADE"), index=True
    )
    local_port: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # 本端端口
    remote_device_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("device.id", ondelete="SET NULL"), nullable=True, index=True
    )
    remote_sysname: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)  # 对端系统名
    remote_port: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # 对端端口
    remote_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # 对端管理 IP（如有）
    protocol: Mapped[str] = mapped_column(String(16), default="lldp")  # lldp / cdp
    link_type: Mapped[str] = mapped_column(String(16), default="unknown")  # trunk / access / unknown
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否为用户标记的重要链路
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    local_device: Mapped["Device"] = relationship("Device", foreign_keys=[local_device_id])
    remote_device: Mapped[Optional["Device"]] = relationship("Device", foreign_keys=[remote_device_id])
