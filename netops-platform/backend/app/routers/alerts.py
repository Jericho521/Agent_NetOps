"""
告警 API - 告警规则 CRUD + 告警事件列表 + 确认/解决
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session
from app.models import AlertRule, Alert, Device
from app.schemas import (
    AlertRuleCreate, AlertRuleUpdate, AlertRuleResponse,
    AlertResponse, AlertAcknowledge, MessageResponse,
)
from app.security.jwt_auth import get_current_user, require_admin, User

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================
# 告警规则
# ============================================================

@router.get("/rules", response_model=list[AlertRuleResponse])
async def list_alert_rules(
    enabled_only: bool = Query(False),
    current_user: User = Depends(get_current_user),
):
    """获取告警规则列表"""
    async with async_session() as session:
        query = select(AlertRule)
        if enabled_only:
            query = query.where(AlertRule.enabled == True)
        query = query.order_by(AlertRule.created_at.desc())

        result = await session.execute(query)
        rules = result.scalars().all()
        return [AlertRuleResponse.model_validate(r) for r in rules]


@router.post("/rules", response_model=AlertRuleResponse, status_code=201)
async def create_alert_rule(
    rule_data: AlertRuleCreate,
    current_user: User = Depends(require_admin),
):
    """创建告警规则"""
    async with async_session() as session:
        # 如果指定了设备，验证设备存在
        if rule_data.device_id:
            dev = await session.execute(select(Device).where(Device.id == rule_data.device_id))
            if not dev.scalar_one_or_none():
                raise HTTPException(status_code=404, detail="指定的设备不存在")

        rule = AlertRule(
            name=rule_data.name,
            device_id=rule_data.device_id,
            metric_name=rule_data.metric_name,
            operator="gt",  # MVP 只支持"大于"
            threshold=rule_data.threshold,
            duration_seconds=rule_data.duration_seconds,
            severity=rule_data.severity,
            critical_threshold=rule_data.critical_threshold,
            enabled=rule_data.enabled,
        )
        session.add(rule)
        await session.commit()
        await session.refresh(rule)
        return AlertRuleResponse.model_validate(rule)


@router.put("/rules/{rule_id}", response_model=AlertRuleResponse)
async def update_alert_rule(
    rule_id: str,
    rule_data: AlertRuleUpdate,
    current_user: User = Depends(require_admin),
):
    """更新告警规则"""
    async with async_session() as session:
        result = await session.execute(select(AlertRule).where(AlertRule.id == rule_id))
        rule = result.scalar_one_or_none()
        if not rule:
            raise HTTPException(status_code=404, detail="告警规则不存在")

        update_data = rule_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(rule, field, value)

        await session.commit()
        await session.refresh(rule)
        return AlertRuleResponse.model_validate(rule)


@router.delete("/rules/{rule_id}", response_model=MessageResponse)
async def delete_alert_rule(
    rule_id: str,
    current_user: User = Depends(require_admin),
):
    """删除告警规则"""
    async with async_session() as session:
        result = await session.execute(select(AlertRule).where(AlertRule.id == rule_id))
        rule = result.scalar_one_or_none()
        if not rule:
            raise HTTPException(status_code=404, detail="告警规则不存在")

        name = rule.name
        await session.delete(rule)
        await session.commit()
        return MessageResponse(message=f"告警规则 '{name}' 已删除")


# ============================================================
# 告警事件
# ============================================================

@router.get("", response_model=dict)
async def list_alerts(
    status_filter: Optional[str] = Query(None, alias="status"),
    severity: Optional[int] = Query(None),
    device_id: Optional[str] = Query(None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """获取告警事件列表"""
    async with async_session() as session:
        query = select(Alert)

        if status_filter:
            query = query.where(Alert.status == status_filter)
        if severity:
            query = query.where(Alert.severity == severity)
        if device_id:
            query = query.where(Alert.device_id == device_id)

        # 总数
        count_q = select(func.count()).select_from(query.subquery())
        total = (await session.execute(count_q)).scalar() or 0

        # 分页
        query = query.order_by(Alert.fired_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await session.execute(query)
        alerts = result.scalars().all()

        return {
            "total": total,
            "items": [AlertResponse.model_validate(a) for a in alerts],
        }


@router.put("/{alert_id}/acknowledge", response_model=MessageResponse)
async def acknowledge_alert(
    alert_id: str,
    ack: AlertAcknowledge,
    current_user: User = Depends(get_current_user),
):
    """确认告警（认领）"""
    from datetime import datetime, timezone
    async with async_session() as session:
        result = await session.execute(select(Alert).where(Alert.id == alert_id))
        alert = result.scalar_one_or_none()
        if not alert:
            raise HTTPException(status_code=404, detail="告警不存在")
        if alert.status != "active":
            raise HTTPException(status_code=400, detail="只有 active 状态的告警可以确认")

        alert.status = "acknowledged"
        alert.acknowledged_by = ack.acknowledged_by
        alert.acknowledged_at = datetime.now(timezone.utc)

        await session.commit()
        return MessageResponse(message="告警已确认")


@router.put("/{alert_id}/resolve", response_model=MessageResponse)
async def resolve_alert(
    alert_id: str,
    current_user: User = Depends(get_current_user),
):
    """解决告警（标记为已恢复）"""
    from datetime import datetime, timezone
    async with async_session() as session:
        result = await session.execute(select(Alert).where(Alert.id == alert_id))
        alert = result.scalar_one_or_none()
        if not alert:
            raise HTTPException(status_code=404, detail="告警不存在")
        if alert.status in ("resolved", "closed"):
            raise HTTPException(status_code=400, detail="该告警已经解决或关闭")

        alert.status = "resolved"
        alert.resolved_at = datetime.now(timezone.utc)

        await session.commit()
        return MessageResponse(message="告警已标记为解决")
