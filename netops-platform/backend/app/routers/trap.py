"""
SNMP Trap 相关 API：日志查询、规则管理、监听状态。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import desc, func, select

from app.models import SnmpTrapLog, TrapRule
from app.routers.auth import get_current_user, User
from app.db import async_session

router = APIRouter(tags=["SNMP Trap"])


class TrapRuleOut(BaseModel):
    id: str
    name: str
    oid_prefix: str
    severity: int
    message_template: str
    enabled: bool
    created_at: Optional[str]

    class Config:
        from_attributes = True


class TrapRuleCreate(BaseModel):
    name: str
    oid_prefix: str
    severity: int = 2
    message_template: str = "收到 SNMP Trap"
    enabled: bool = True


class TrapLogOut(BaseModel):
    id: str
    source_ip: str
    source_port: int
    version: str
    community: Optional[str]
    pdu_type: str
    variables: Optional[list]
    received_at: str
    mapped_alert_id: Optional[str]


@router.get("/logs", response_model=list[TrapLogOut])
async def list_trap_logs(
    source_ip: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
):
    async with async_session() as session:
        q = select(SnmpTrapLog)
        if source_ip:
            q = q.where(SnmpTrapLog.source_ip == source_ip)
        q = q.order_by(desc(SnmpTrapLog.received_at))
        total = (await session.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
        q = q.offset((page - 1) * page_size).limit(page_size)
        rows = await session.execute(q)
        return [
            TrapLogOut(
                id=r.id,
                source_ip=r.source_ip,
                source_port=r.source_port,
                version=r.version,
                community=r.community,
                pdu_type=r.pdu_type,
                variables=r.variables,
                received_at=r.received_at.isoformat() if r.received_at else "",
                mapped_alert_id=r.mapped_alert_id,
            )
            for r in rows.scalars().all()
        ]


@router.get("/rules", response_model=list[TrapRuleOut])
async def list_trap_rules(
    current_user: User = Depends(get_current_user),
):
    async with async_session() as session:
        rows = await session.execute(select(TrapRule).order_by(desc(TrapRule.created_at)))
        return [
            TrapRuleOut(
                id=r.id,
                name=r.name,
                oid_prefix=r.oid_prefix,
                severity=r.severity,
                message_template=r.message_template,
                enabled=r.enabled,
                created_at=r.created_at.isoformat() if r.created_at else "",
            )
            for r in rows.scalars().all()
        ]


@router.post("/rules", response_model=TrapRuleOut)
async def create_trap_rule(
    data: TrapRuleCreate,
    current_user: User = Depends(get_current_user),
):
    async with async_session() as session:
        rule = TrapRule(**data.model_dump())
        session.add(rule)
        await session.commit()
        await session.refresh(rule)
        return TrapRuleOut(
            id=rule.id,
            name=rule.name,
            oid_prefix=rule.oid_prefix,
            severity=rule.severity,
            message_template=rule.message_template,
            enabled=rule.enabled,
            created_at=rule.created_at.isoformat() if rule.created_at else "",
        )


@router.delete("/rules/{rule_id}")
async def delete_trap_rule(
    rule_id: str,
    current_user: User = Depends(get_current_user),
):
    async with async_session() as session:
        rule = await session.get(TrapRule, rule_id)
        if not rule:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="规则不存在")
        await session.delete(rule)
        await session.commit()
    return {"ok": True}


@router.get("/status")
async def trap_status(
    current_user: User = Depends(get_current_user),
):
    """返回当前 Trap 监听配置（不暴露真实状态机，只返回配置值）。"""
    from app.config import settings
    from app.trap_listener import _snmp_engine
    return {
        "listening": _snmp_engine is not None,
        "port": getattr(settings, "TRAP_LISTEN_PORT", 1620),
        "community": getattr(settings, "TRAP_COMMUNITY", "public"),
    }
