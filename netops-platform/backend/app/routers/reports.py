"""
报表中心 API：生成、列表、下载日报/周报/月报。
当前为最小可用版本，仅支持手动生成日报。
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db import async_session
from app.models import ReportInstance, ReportTemplate
from app.routers.auth import get_current_user, User
from app.services.report_engine import collect_daily_report_data, generate_daily_pdf, generate_daily_excel

router = APIRouter(tags=["报表中心"])

REPORTS_DIR = Path(__file__).resolve().parent.parent.parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


class GenerateReportRequest(BaseModel):
    template_id: Optional[str] = Field(default=None, description="模板 ID，为空时使用默认日报模板")
    report_type: str = Field(default="daily", pattern=r"^(daily|weekly|monthly)$")
    hours: int = Field(default=24, ge=1, le=720)


class ReportInstanceResponse(BaseModel):
    id: str
    report_type: str
    created_at: datetime
    pdf_path: Optional[str]
    excel_path: Optional[str]
    status: str
    error_message: Optional[str]


@router.post("/generate")
async def generate_report(
    req: GenerateReportRequest,
    current_user: User = Depends(get_current_user),
):
    """手动触发生成报表"""
    try:
        data = await collect_daily_report_data(hours=req.hours)
        pdf_path = await generate_daily_pdf(data)
        excel_path = await generate_daily_excel(data)

        async with async_session() as session:
            instance = ReportInstance(
                report_type=req.report_type,
                created_by=current_user.username,
                pdf_path=str(pdf_path.relative_to(REPORTS_DIR)),
                excel_path=str(excel_path.relative_to(REPORTS_DIR)),
                status="completed",
            )
            session.add(instance)
            await session.commit()
            await session.refresh(instance)

        return {
            "id": instance.id,
            "report_type": instance.report_type,
            "created_at": instance.created_at,
            "pdf_path": instance.pdf_path,
            "excel_path": instance.excel_path,
            "status": instance.status,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"生成报表失败: {e}",
        )


@router.get("/instances", response_model=list[ReportInstanceResponse])
async def list_report_instances(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """分页列出已生成的报表"""
    async with async_session() as session:
        result = await session.execute(
            select(ReportInstance)
            .order_by(ReportInstance.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        instances = result.scalars().all()
    return instances


@router.get("/download/{instance_id}")
async def download_report(
    instance_id: str,
    format: str = Query("pdf", pattern=r"^(pdf|excel)$"),
    current_user: User = Depends(get_current_user),
):
    """下载指定格式的报表文件"""
    async with async_session() as session:
        result = await session.execute(select(ReportInstance).where(ReportInstance.id == instance_id))
        instance = result.scalar_one_or_none()
        if not instance:
            raise HTTPException(status_code=404, detail="报表不存在")

    file_path = instance.pdf_path if format == "pdf" else instance.excel_path
    if not file_path:
        raise HTTPException(status_code=404, detail=f"该报表没有 {format} 文件")

    full_path = REPORTS_DIR / file_path
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="报表文件已丢失")

    media_type = "application/pdf" if format == "pdf" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return FileResponse(
        str(full_path),
        media_type=media_type,
        filename=full_path.name,
    )


@router.delete("/{instance_id}")
async def delete_report(
    instance_id: str,
    current_user: User = Depends(get_current_user),
):
    """删除报表记录及文件"""
    async with async_session() as session:
        result = await session.execute(select(ReportInstance).where(ReportInstance.id == instance_id))
        instance = result.scalar_one_or_none()
        if not instance:
            raise HTTPException(status_code=404, detail="报表不存在")

        for path_attr in ("pdf_path", "excel_path"):
            p = getattr(instance, path_attr)
            if p:
                full = REPORTS_DIR / p
                if full.exists():
                    full.unlink()
        await session.delete(instance)
        await session.commit()
    return {"message": "已删除"}
