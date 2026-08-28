"""
AI 助手 API：对接内网大模型，提供聊天与平台智能分析。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.routers.auth import get_current_user, User
from app.services.llm import chat_completion, analyze_with_context

router = APIRouter(tags=["AI 助手"])


class ChatMessage(BaseModel):
    role: str = Field(..., pattern=r"^(system|user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model: Optional[str] = None


class ChatResponse(BaseModel):
    content: str


class AnalyzeRequest(BaseModel):
    question: Optional[str] = None
    model: Optional[str] = None


class AnalyzeResponse(BaseModel):
    content: str


@router.post("/chat", response_model=ChatResponse)
async def ai_chat(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    """通用 AI 对话接口。"""
    try:
        messages = [{"role": m.role, "content": m.content} for m in req.messages]
        content = await chat_completion(messages, model=req.model)
        return ChatResponse(content=content)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI 模型调用失败: {e}",
        )


@router.post("/analyze", response_model=AnalyzeResponse)
async def ai_analyze(
    req: AnalyzeRequest,
    current_user: User = Depends(get_current_user),
):
    """基于平台当前数据生成运维分析建议。"""
    try:
        # 聚合平台概览数据
        from app.db import async_session
        from sqlalchemy import func, select
        from app.models import Device, Alert

        summary_lines: list[str] = []
        async with async_session() as session:
            total = (await session.execute(select(func.count()).select_from(Device))).scalar() or 0
            online = (await session.execute(
                select(func.count()).where(Device.status == "online")
            )).scalar() or 0
            offline = (await session.execute(
                select(func.count()).where(Device.status == "offline")
            )).scalar() or 0
            error = (await session.execute(
                select(func.count()).where(Device.status == "error")
            )).scalar() or 0
            active_alerts = (await session.execute(
                select(func.count()).where(Alert.status == "firing")
            )).scalar() or 0

        summary_lines.append(f"设备总数: {total}")
        summary_lines.append(f"在线: {online}，离线: {offline}，异常: {error}")
        summary_lines.append(f"当前未恢复告警: {active_alerts}")

        content = await analyze_with_context("\n".join(summary_lines), req.question)
        return AnalyzeResponse(content=content)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI 分析失败: {e}",
        )


class ContextStats(BaseModel):
    devices_total: int
    devices_online: int
    devices_offline: int
    devices_error: int
    active_alerts: int
    recent_alerts: int


@router.get("/context", response_model=ContextStats)
async def ai_context(
    current_user: User = Depends(get_current_user),
):
    """返回平台实时统计，供 AI 助手展示与回答数据类问题。"""
    from app.db import async_session
    from sqlalchemy import func, select
    from app.models import Device, Alert

    async with async_session() as session:
        total = (await session.execute(select(func.count()).select_from(Device))).scalar() or 0
        online = (await session.execute(
            select(func.count()).where(Device.status == "online")
        )).scalar() or 0
        offline = (await session.execute(
            select(func.count()).where(Device.status == "offline")
        )).scalar() or 0
        error = (await session.execute(
            select(func.count()).where(Device.status == "error")
        )).scalar() or 0
        active_alerts = (await session.execute(
            select(func.count()).where(Alert.status == "firing")
        )).scalar() or 0
        recent_alerts = (await session.execute(
            select(func.count()).where(Alert.status.in_(["firing", "resolved"]))
        )).scalar() or 0

    return ContextStats(
        devices_total=total,
        devices_online=online,
        devices_offline=offline,
        devices_error=error,
        active_alerts=active_alerts,
        recent_alerts=recent_alerts,
    )
