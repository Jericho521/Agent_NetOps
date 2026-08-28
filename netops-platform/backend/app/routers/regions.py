"""
区域管理 API：CRUD 区域（Region）和子区域（SubRegion）。
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import async_session
from app.models import Region, SubRegion
from app.routers.auth import get_current_user, User

router = APIRouter(tags=["区域管理"])


# ========== 请求/响应模型 ==========
class RegionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: Optional[str] = None
    sort_order: int = 0


class RegionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    description: Optional[str] = None
    sort_order: Optional[int] = None


class SubRegionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: Optional[str] = None
    sort_order: int = 0


class SubRegionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    description: Optional[str] = None
    sort_order: Optional[int] = None


class RegionResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    sort_order: int
    sub_regions: list[dict] = []

    class Config:
        from_attributes = True


class SubRegionResponse(BaseModel):
    id: str
    region_id: str
    name: str
    description: Optional[str]
    sort_order: int

    class Config:
        from_attributes = True


# ========== 区域 CRUD ==========
@router.get("/regions", response_model=list[RegionResponse])
async def list_regions(
    include_sub_regions: bool = Query(True),
    current_user: User = Depends(get_current_user),
):
    """列出所有区域，可选包含子区域"""
    async with async_session() as session:
        if include_sub_regions:
            result = await session.execute(
                select(Region).options(selectinload(Region.sub_regions)).order_by(Region.sort_order, Region.name)
            )
        else:
            result = await session.execute(
                select(Region).order_by(Region.sort_order, Region.name)
            )
        regions = result.scalars().all()

        return [
            {
                "id": r.id,
                "name": r.name,
                "description": r.description,
                "sort_order": r.sort_order,
                "sub_regions": [
                    {"id": sr.id, "name": sr.name, "description": sr.description, "sort_order": sr.sort_order}
                    for sr in (r.sub_regions or [])
                ],
            }
            for r in regions
        ]


@router.post("/regions", response_model=RegionResponse)
async def create_region(data: RegionCreate, current_user: User = Depends(get_current_user)):
    """创建区域"""
    async with async_session() as session:
        # 检查名称唯一性
        existing = await session.execute(select(Region).where(Region.name == data.name))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail=f"区域 '{data.name}' 已存在")

        region = Region(name=data.name, description=data.description, sort_order=data.sort_order)
        session.add(region)
        await session.commit()
        await session.refresh(region)
        return {"id": region.id, "name": region.name, "description": region.description, "sort_order": region.sort_order, "sub_regions": []}


@router.put("/regions/{region_id}", response_model=RegionResponse)
async def update_region(region_id: str, data: RegionUpdate, current_user: User = Depends(get_current_user)):
    """更新区域"""
    async with async_session() as session:
        result = await session.execute(select(Region).where(Region.id == region_id))
        region = result.scalar_one_or_none()
        if not region:
            raise HTTPException(status_code=404, detail="区域不存在")

        if data.name is not None:
            # 检查唯一性
            existing = await session.execute(select(Region).where(Region.name == data.name, Region.id != region_id))
            if existing.scalar_one_or_none():
                raise HTTPException(status_code=409, detail=f"区域 '{data.name}' 已存在")
            region.name = data.name
        if data.description is not None:
            region.description = data.description
        if data.sort_order is not None:
            region.sort_order = data.sort_order

        await session.commit()
        await session.refresh(region)
        return {"id": region.id, "name": region.name, "description": region.description, "sort_order": region.sort_order, "sub_regions": []}


@router.delete("/regions/{region_id}")
async def delete_region(region_id: str, current_user: User = Depends(get_current_user)):
    """删除区域（级联删除子区域）"""
    async with async_session() as session:
        result = await session.execute(select(Region).where(Region.id == region_id))
        region = result.scalar_one_or_none()
        if not region:
            raise HTTPException(status_code=404, detail="区域不存在")
        await session.delete(region)
        await session.commit()
    return {"message": "已删除"}


# ========== 子区域 CRUD ==========
@router.get("/regions/{region_id}/sub-regions", response_model=list[SubRegionResponse])
async def list_sub_regions(region_id: str, current_user: User = Depends(get_current_user)):
    """列出某区域下的所有子区域"""
    async with async_session() as session:
        # 验证区域存在
        reg_result = await session.execute(select(Region).where(Region.id == region_id))
        if not reg_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="区域不存在")

        result = await session.execute(
            select(SubRegion).where(SubRegion.region_id == region_id).order_by(SubRegion.sort_order, SubRegion.name)
        )
        return result.scalars().all()


@router.post("/regions/{region_id}/sub-regions", response_model=SubRegionResponse)
async def create_sub_region(region_id: str, data: SubRegionCreate, current_user: User = Depends(get_current_user)):
    """在指定区域下创建子区域"""
    async with async_session() as session:
        reg_result = await session.execute(select(Region).where(Region.id == region_id))
        if not reg_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="区域不存在")

        # 同一区域内子区域名称不重复
        existing = await session.execute(
            select(SubRegion).where(SubRegion.region_id == region_id, SubRegion.name == data.name)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail=f"子区域 '{data.name}' 在该区域内已存在")

        sub = SubRegion(region_id=region_id, name=data.name, description=data.description, sort_order=data.sort_order)
        session.add(sub)
        await session.commit()
        await session.refresh(sub)
        return sub


@router.put("/sub-regions/{sub_region_id}", response_model=SubRegionResponse)
async def update_sub_region(sub_region_id: str, data: SubRegionUpdate, current_user: User = Depends(get_current_user)):
    """更新子区域"""
    async with async_session() as session:
        result = await session.execute(select(SubRegion).where(SubRegion.id == sub_region_id))
        sub = result.scalar_one_or_none()
        if not sub:
            raise HTTPException(status_code=404, detail="子区域不存在")

        if data.name is not None:
            existing = await session.execute(
                select(SubRegion).where(SubRegion.region_id == sub.region_id, SubRegion.name == data.name, SubRegion.id != sub_region_id)
            )
            if existing.scalar_one_or_none():
                raise HTTPException(status_code=409, detail=f"子区域 '{data.name}' 在该区域内已存在")
            sub.name = data.name
        if data.description is not None:
            sub.description = data.description
        if data.sort_order is not None:
            sub.sort_order = data.sort_order

        await session.commit()
        await session.refresh(sub)
        return sub


@router.delete("/sub-regions/{sub_region_id}")
async def delete_sub_region(sub_region_id: str, current_user: User = Depends(get_current_user)):
    """删除子区域"""
    async with async_session() as session:
        result = await session.execute(select(SubRegion).where(SubRegion.id == sub_region_id))
        sub = result.scalar_one_or_none()
        if not sub:
            raise HTTPException(status_code=404, detail="子区域不存在")
        await session.delete(sub)
        await session.commit()
    return {"message": "已删除"}
