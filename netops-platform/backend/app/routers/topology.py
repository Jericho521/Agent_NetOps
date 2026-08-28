"""
拓扑管理 API - 返回设备节点 + 链路连线，供前端绘制拓扑图
"""
import logging
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session
from app.models import Device, Link, Region, SubRegion
from app.security.jwt_auth import get_current_user, User

logger = logging.getLogger(__name__)
router = APIRouter()


def _device_type_rank(t: Optional[str]) -> int:
    """设备类型优先级：集群/堆叠/M-LAG 优先于单机。"""
    return {"cluster": 4, "stack": 3, "mlag": 2}.get(t or "single", 1)


def _status_rank(s: Optional[str]) -> int:
    """状态优先级：在线 > 异常 > 离线 > 未知。"""
    return {"online": 4, "error": 3, "offline": 2, "unknown": 1}.get(s or "unknown", 0)


@router.get("")
async def get_topology(
    current_user: User = Depends(get_current_user),
    region_id: Optional[str] = Query(None, description="按区域筛选"),
):
    """返回拓扑图所需的节点(设备)与连线(链路)。

    同一 LLDP/CDP sysName 的多个设备记录（堆叠多 IP、管理口/带内口重复录入）
    会被合并为一个逻辑节点，避免一台物理设备在图上出现多次。
    """
    async with async_session() as session:
        # 1. 拉取启用的设备
        dev_query = select(Device).where(Device.enabled == True)
        if region_id:
            dev_query = dev_query.where(Device.region_id == region_id)
        devices = (await session.execute(dev_query)).scalars().all()

        # 查区域/子区域名字（用于节点显示）
        region_ids = {d.region_id for d in devices if d.region_id}
        sub_region_ids = {d.sub_region_id for d in devices if d.sub_region_id}
        regions_map: dict[str, str] = {}
        sub_regions_map: dict[str, str] = {}
        if region_ids:
            rows = (await session.execute(select(Region.id, Region.name).where(Region.id.in_(region_ids)))).all()
            regions_map = {r[0]: r[1] for r in rows}
        if sub_region_ids:
            rows = (await session.execute(select(SubRegion.id, SubRegion.name).where(SubRegion.id.in_(sub_region_ids)))).all()
            sub_regions_map = {r[0]: r[1] for r in rows}

        # 2. 按 sys_name 分组合并：sys_name 相同 → 同一物理设备
        groups: dict[str, list[Device]] = defaultdict(list)
        for d in devices:
            key = (d.sys_name or "").strip() or f"__single__::{d.id}"
            groups[key].append(d)

        dev_to_merged: dict[str, str] = {}
        nodes = []
        for group in groups.values():
            # 选主设备：类型优先级 > 状态优先级 > 创建时间早
            master = max(
                group,
                key=lambda d: (
                    _device_type_rank(d.device_type),
                    _status_rank(d.status),
                    d.created_at or "",
                ),
            )
            aliases = []
            for d in group:
                dev_to_merged[d.id] = master.id
                if d.id != master.id:
                    aliases.append({"id": d.id, "name": d.name, "ip": d.ip})

            # 状态取组内最优
            merged_status = max((d.status for d in group), key=_status_rank)
            # device_type 取组内最高优先级
            merged_type = max((d.device_type for d in group), key=_device_type_rank)

            nodes.append({
                "id": master.id,
                "name": master.name,
                "sys_name": master.sys_name,
                "device_type": merged_type,
                "ip": master.ip,
                "vendor": master.vendor,
                "role": master.role,
                "model": master.model,
                "status": merged_status,
                "region_id": master.region_id,
                "sub_region_id": master.sub_region_id,
                "region_name": regions_map.get(master.region_id or ""),
                "sub_region_name": sub_regions_map.get(master.sub_region_id or ""),
                "aliases": aliases,
            })

        merged_ids = {n["id"] for n in nodes}

        # 3. 链路：映射到合并后的节点 ID
        links_raw = (await session.execute(select(Link))).scalars().all()
        links = []
        for lk in links_raw:
            source = dev_to_merged.get(lk.local_device_id)
            if not source:
                continue
            # 对端：已录入设备优先用合并后 ID；否则生成虚拟节点
            if lk.remote_device_id:
                target = dev_to_merged.get(lk.remote_device_id)
                if not target:
                    continue
            else:
                target = f"__unknown__::{lk.remote_sysname or lk.remote_ip or 'unknown'}"
                nodes.append({
                    "id": target,
                    "name": lk.remote_sysname or lk.remote_ip or "未知设备",
                    "ip": lk.remote_ip,
                    "vendor": None,
                    "role": None,
                    "model": None,
                    "status": "unknown",
                    "region_id": None,
                    "sub_region_id": None,
                    "virtual": True,
                    "aliases": [],
                })
            links.append({
                "id": lk.id,
                "source": source,
                "target": target,
                "local_port": lk.local_port,
                "remote_port": lk.remote_port,
                "remote_sysname": lk.remote_sysname,
                "protocol": lk.protocol,
                "link_type": lk.link_type,
                "is_critical": lk.is_critical,
            })

        # 4. 去重虚拟节点
        seen = set()
        dedup_nodes = []
        for n in nodes:
            if n["id"] in seen:
                continue
            seen.add(n["id"])
            dedup_nodes.append(n)

        return {
            "nodes": dedup_nodes,
            "links": links,
            "stats": {
                "node_count": len([n for n in dedup_nodes if not n.get("virtual")]),
                "link_count": len(links),
                "virtual_count": len([n for n in dedup_nodes if n.get("virtual")]),
                "critical_count": len([l for l in links if l.get("is_critical")]),
            },
        }


class LinkCriticalUpdate(BaseModel):
    is_critical: bool = Field(..., description="是否标记为重要链路")


@router.put("/links/{link_id}/critical")
async def update_link_critical(
    link_id: str,
    body: LinkCriticalUpdate,
    current_user: User = Depends(get_current_user),
):
    """标记/取消标记某条链路为重要链路。"""
    async with async_session() as session:
        link = (await session.execute(select(Link).where(Link.id == link_id))).scalar_one_or_none()
        if not link:
            raise HTTPException(status_code=404, detail="链路不存在")
        link.is_critical = body.is_critical
        await session.commit()
        return {"id": link.id, "is_critical": link.is_critical}
