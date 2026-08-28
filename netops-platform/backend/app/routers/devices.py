"""
设备管理 API - CRUD + 批量 CSV 导入 + 按厂商/角色筛选
"""
import csv
import io
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session
from app.models import Device, DeviceCredential, AuditLog, Region, SubRegion
from app.schemas import (
    DeviceCreate, DeviceUpdate, DeviceResponse, DeviceListResponse, MessageResponse
)
from app.security.credentials import encrypt_credential, decrypt_credential
from app.security.jwt_auth import get_current_user, require_admin, User

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/overview")
async def device_overview(
    current_user: User = Depends(get_current_user),
):
    """仪表盘概览统计：设备总数 / 在线 / 离线 / 告警设备数 / 活跃告警数"""
    from app.models import Alert

    async with async_session() as session:
        total = (await session.execute(select(func.count()).select_from(Device))).scalar() or 0
        online = (await session.execute(
            select(func.count()).select_from(Device).where(Device.status == "online")
        )).scalar() or 0
        offline = (await session.execute(
            select(func.count()).select_from(Device).where(Device.status == "offline")
        )).scalar() or 0

        # 处于告警状态的设备数量：排除离线/采集异常类（category=offline/error），只统计阈值告警
        alert_dev_res = await session.execute(
            select(func.count(func.distinct(Alert.device_id))).select_from(Alert).where(
                Alert.status.in_(["active", "acknowledged"]),
                Alert.category == "threshold",
            )
        )
        warning = alert_dev_res.scalar() or 0

        # 活跃告警总数（含离线，用于告警列表展示）
        active_alerts = (await session.execute(
            select(func.count()).select_from(Alert).where(Alert.status == "active")
        )).scalar() or 0

        return {
            "total": total,
            "online": online,
            "offline": offline,
            "warning": warning,
            "total_alerts_active": active_alerts,
        }


@router.get("", response_model=DeviceListResponse)
async def list_devices(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    vendor: Optional[str] = None,
    role: Optional[str] = None,
    enabled: Optional[bool] = None,
    search: Optional[str] = None,
    region_id: Optional[str] = None,
    sub_region_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """获取设备列表（支持分页、筛选、搜索）"""
    async with async_session() as session:
        query = select(Device)

        # 筛选条件
        filters = []
        if vendor:
            filters.append(Device.vendor.ilike(f"%{vendor}%"))
        if role:
            filters.append(Device.role == role)
        if enabled is not None:
            filters.append(Device.enabled == enabled)
        if region_id:
            filters.append(Device.region_id == region_id)
        if sub_region_id:
            filters.append(Device.sub_region_id == sub_region_id)
        if search:
            filters.append(or_(
                Device.name.ilike(f"%{search}%"),
                Device.ip.ilike(f"%{search}%"),
            ))

        for f in filters:
            query = query.where(f)

        # 总数
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0

        # 分页
        query = query.order_by(Device.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await session.execute(query)
        devices = result.scalars().all()

        # 批量获取区域名称
        region_ids = {d.region_id for d in devices if d.region_id}
        sub_region_ids = {d.sub_region_id for d in devices if d.sub_region_id}
        region_map: dict[str, str] = {}
        sub_region_map: dict[str, str] = {}
        if region_ids:
            rr = await session.execute(select(Region.id, Region.name).where(Region.id.in_(region_ids)))
            for rid, rname in rr.all():
                region_map[rid] = rname
        if sub_region_ids:
            sr = await session.execute(select(SubRegion.id, SubRegion.name).where(SubRegion.id.in_(sub_region_ids)))
            for sid, sname in sr.all():
                sub_region_map[sid] = sname

        items = []
        for d in devices:
            item = DeviceResponse.model_validate(d)
            item.region_name = region_map.get(d.region_id) if d.region_id else None
            item.sub_region_name = sub_region_map.get(d.sub_region_id) if d.sub_region_id else None
            items.append(item)

        return DeviceListResponse(total=total, items=items)


@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(
    device_id: str,
    current_user: User = Depends(get_current_user),
):
    """获取单个设备详情"""
    async with async_session() as session:
        result = await session.execute(select(Device).where(Device.id == device_id))
        device = result.scalar_one_or_none()
        if not device:
            raise HTTPException(status_code=404, detail="设备不存在")
        return DeviceResponse.model_validate(device)


@router.post("", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
async def create_device(
    device_data: DeviceCreate,
    current_user: User = Depends(require_admin),
):
    """添加新设备（含凭据加密）"""
    async with async_session() as session:
        # 检查 IP 是否重复
        existing = await session.execute(
            select(Device).where(Device.ip == device_data.ip)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail=f"IP {device_data.ip} 已存在")

        # 创建设备记录
        device = Device(
            name=device_data.name,
            sys_name=device_data.sys_name,
            device_type=device_data.device_type,
            ip=device_data.ip,
            snmp_version=device_data.snmp_version,
            snmp_port=device_data.snmp_port,
            snmp_user=device_data.snmp_user,
            vendor=device_data.vendor,
            model=device_data.model,
            role=device_data.role,
            region_id=device_data.region_id,
            sub_region_id=device_data.sub_region_id,
            poll_interval=device_data.poll_interval,
            adapter=device_data.adapter,
            ssh_port=device_data.ssh_port,
            enabled=device_data.enabled,
        )
        session.add(device)
        await session.flush()  # 获取 device.id

        # 加密并保存凭据
        await _save_credentials(session, device.id, device_data)

        # 审计日志
        _audit_log(session, current_user, "create_device", f"设备: {device.name} ({device.ip})")

        await session.commit()
        await session.refresh(device)
        return DeviceResponse.model_validate(device)


@router.put("/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: str,
    device_data: DeviceUpdate,
    current_user: User = Depends(require_admin),
):
    """更新设备信息"""
    async with async_session() as session:
        result = await session.execute(select(Device).where(Device.id == device_id))
        device = result.scalar_one_or_none()
        if not device:
            raise HTTPException(status_code=404, detail="设备不存在")

        # 更新字段
        update_data = device_data.model_dump(exclude_unset=True)
        cred_fields = {"snmp_community", "snmp_auth_pass", "snmp_priv_pass",
                       "snmp_auth_protocol", "snmp_priv_protocol", "ssh_username", "ssh_password"}

        for field, value in update_data.items():
            if field not in cred_fields and hasattr(device, field):
                setattr(device, field, value)

        # 如果有凭据更新，重新加密保存
        if any(f in update_data for f in cred_fields):
            await _save_credentials(session, device_id, device_data, is_update=True)

        _audit_log(session, current_user, "update_device", f"设备: {device.name}")

        await session.commit()
        await session.refresh(device)
        return DeviceResponse.model_validate(device)


@router.delete("/{device_id}", response_model=MessageResponse)
async def delete_device(
    device_id: str,
    current_user: User = Depends(require_admin),
):
    """删除设备（级联删除凭据）"""
    async with async_session() as session:
        result = await session.execute(select(Device).where(Device.id == device_id))
        device = result.scalar_one_or_none()
        if not device:
            raise HTTPException(status_code=404, detail="设备不存在")

        device_name = device.name
        await session.delete(device)

        _audit_log(session, current_user, "delete_device", f"设备: {device_name}")

        await session.commit()
        return MessageResponse(message=f"设备 '{device_name}' 已删除")


@router.post("/import/csv", response_model=MessageResponse)
async def import_devices_csv(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
):
    """
    批量导入设备（CSV 文件）
    CSV 列名: name, ip, vendor, model, role, snmp_version, snmp_port,
             snmp_user, snmp_community, snmp_auth_pass, snmp_priv_pass, region
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="仅支持 CSV 文件")

    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("gbk")  # 兼容中文 Excel 导出的 CSV

    reader = csv.DictReader(io.StringIO(text))

    created_count = 0
    skipped_count = 0
    errors = []

    async with async_session() as session:
        for row_num, row in enumerate(reader, start=2):  # 从第2行开始（跳过表头）
            try:
                # 必填字段校验
                if not row.get("name") or not row.get("ip"):
                    errors.append(f"第{row_num}行: 缺少 name 或 ip")
                    skipped_count += 1
                    continue

                # 检查 IP 是否已存在
                existing = await session.execute(
                    select(Device).where(Device.ip == row["ip"].strip())
                )
                if existing.scalar_one_or_none():
                    skipped_count += 1
                    continue

                # 构建设备数据
                device = Device(
                    name=row["name"].strip(),
                    ip=row["ip"].strip(),
                    snmp_version=int(row.get("snmp_version", 3)),
                    snmp_port=int(row.get("snmp_port", 161)),
                    snmp_user=(row.get("snmp_user") or "").strip() or None,
                    vendor=(row.get("vendor") or "").strip() or None,
                    model=(row.get("model") or "").strip() or None,
                    role=(row.get("role") or "").strip() or None,
                    region=(row.get("region") or "").strip() or None,
                    enabled=True,
                )
                session.add(device)
                await session.flush()

                # 凭据加密
                community = (row.get("snmp_community") or "").strip()
                auth_pass = (row.get("snmp_auth_pass") or "").strip()
                priv_pass = (row.get("snmp_priv_pass") or "").strip()

                if community:
                    session.add(DeviceCredential(
                        device_id=device.id,
                        cred_type="snmp_v2c_community",
                        secret_enc=encrypt_credential(community),
                    ))
                if auth_pass:
                    session.add(DeviceCredential(
                        device_id=device.id,
                        cred_type="snmp_v3_auth",
                        secret_enc=encrypt_credential(auth_pass),
                    ))
                if priv_pass:
                    session.add(DeviceCredential(
                        device_id=device.id,
                        cred_type="snmp_v3_priv",
                        secret_enc=encrypt_credential(priv_pass),
                    ))

                created_count += 1

            except Exception as e:
                errors.append(f"第{row_num}行: {str(e)}")
                skipped_count += 1

        _audit_log(session, current_user, "import_csv",
                   f"导入 {created_count} 台设备，跳过 {skipped_count} 台")

        await session.commit()

    return MessageResponse(
        message=f"导入完成: 成功 {created_count} 台，跳过 {skipped_count} 台",
        detail={"errors": errors[:10]} if errors else None,  # 最多返回前 10 条错误
    )


@router.post("/{device_id}/test-connectivity", response_model=MessageResponse)
async def test_connectivity(
    device_id: str,
    current_user: User = Depends(get_current_user),
):
    """测试设备 SNMP 连通性（手动触发一次采集）"""
    async with async_session() as session:
        result = await session.execute(select(Device).where(Device.id == device_id))
        device = result.scalar_one_or_none()
        if not device:
            raise HTTPException(status_code=404, detail="设备不存在")

        creds_result = await session.execute(
            select(DeviceCredential).where(DeviceCredential.device_id == device_id)
        )
        creds = {}
        for c in creds_result.scalars().all():
            creds[c.cred_type] = decrypt_credential(c.secret_enc)

        device_info = _device_to_dict(device, creds)

        from app.collector.snmp import collect_device_metrics
        metrics_data = await collect_device_metrics(device_info)

        if metrics_data:
            device.status = "online"
            device.last_seen_at = datetime.utcnow()
            session.add(device)
            await session.commit()
            return MessageResponse(
                message="连接成功",
                detail={"metrics_collected": len(metrics_data)},
            )
        else:
            return MessageResponse(
                message="连接失败",
                detail={"error": "无法通过 SNMP 获取数据，请检查 IP/端口/凭据"},
            )


@router.post("/{device_id}/test-connectivity-stream")
async def test_connectivity_stream(
    device_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    测试设备 SNMP 连通性（流式进度，SSE）。
    实时返回每个采集阶段的状态，避免前端长时间无反馈。
    """
    from app.collector.snmp import test_connectivity_progress

    async with async_session() as session:
        result = await session.execute(select(Device).where(Device.id == device_id))
        device = result.scalar_one_or_none()
        if not device:
            raise HTTPException(status_code=404, detail="设备不存在")

        creds_result = await session.execute(
            select(DeviceCredential).where(DeviceCredential.device_id == device_id)
        )
        creds = {}
        for c in creds_result.scalars().all():
            creds[c.cred_type] = decrypt_credential(c.secret_enc)

        device_info = _device_to_dict(device, creds)

        async def event_gen():
            final_success = False
            discovered = {}
            async for stage in test_connectivity_progress(device_info):
                if stage.get("stage") == "finish":
                    final_success = stage.get("status") == "success"
                    discovered = stage.get("detail", {}).get("discovered", {})
                yield f"data: {json.dumps(stage, ensure_ascii=False)}\n\n"

            # 测试通过 → 立即更新设备状态为在线，并自动补全型号/厂商
            # 测试失败 → 立即更新为 error（离线）
            if final_success:
                device.status = "online"
                device.last_seen_at = datetime.utcnow()
                if discovered.get("model"):
                    device.model = discovered["model"]
                if discovered.get("vendor") and device.vendor in (None, "", "generic"):
                    device.vendor = discovered["vendor"]
            else:
                device.status = "error"
            session.add(device)
            await session.commit()

            yield "data: __DONE__\n\n"

        return StreamingResponse(
            event_gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )


# ============================================================
# 内部辅助函数
# ============================================================
async def _save_credentials(session: AsyncSession, device_id: str, data: DeviceCreate | DeviceUpdate, is_update: bool = False):
    """加密并保存设备凭据到数据库"""
    # v2c community
    if data.snmp_community:
        existing = None
        if is_update:
            r = await session.execute(
                select(DeviceCredential).where(
                    DeviceCredential.device_id == device_id,
                    DeviceCredential.cred_type == "snmp_v2c_community",
                )
            )
            existing = r.scalar_one_or_none()

        enc = encrypt_credential(data.snmp_community)
        if existing:
            existing.secret_enc = enc
        else:
            session.add(DeviceCredential(
                device_id=device_id,
                cred_type="snmp_v2c_community",
                secret_enc=enc,
            ))

    # v3 auth 密码
    if data.snmp_auth_pass:
        existing = None
        if is_update:
            r = await session.execute(
                select(DeviceCredential).where(
                    DeviceCredential.device_id == device_id,
                    DeviceCredential.cred_type == "snmp_v3_auth",
                )
            )
            existing = r.scalar_one_or_none()

        enc = encrypt_credential(data.snmp_auth_pass)
        if existing:
            existing.secret_enc = enc
        else:
            session.add(DeviceCredential(
                device_id=device_id,
                cred_type="snmp_v3_auth",
                secret_enc=enc,
            ))

    # v3 priv 密码
    if data.snmp_priv_pass:
        existing = None
        if is_update:
            r = await session.execute(
                select(DeviceCredential).where(
                    DeviceCredential.device_id == device_id,
                    DeviceCredential.cred_type == "snmp_v3_priv",
                )
            )
            existing = r.scalar_one_or_none()

        enc = encrypt_credential(data.snmp_priv_pass)
        if existing:
            existing.secret_enc = enc
        else:
            session.add(DeviceCredential(
                device_id=device_id,
                cred_type="snmp_v3_priv",
                secret_enc=enc,
            ))

    # SSH 用户名
    if data.ssh_username:
        existing = None
        if is_update:
            r = await session.execute(
                select(DeviceCredential).where(
                    DeviceCredential.device_id == device_id,
                    DeviceCredential.cred_type == "ssh_username",
                )
            )
            existing = r.scalar_one_or_none()

        enc = encrypt_credential(data.ssh_username)
        if existing:
            existing.secret_enc = enc
        else:
            session.add(DeviceCredential(
                device_id=device_id,
                cred_type="ssh_username",
                secret_enc=enc,
            ))

    # SSH 密码
    if data.ssh_password:
        existing = None
        if is_update:
            r = await session.execute(
                select(DeviceCredential).where(
                    DeviceCredential.device_id == device_id,
                    DeviceCredential.cred_type == "ssh_password",
                )
            )
            existing = r.scalar_one_or_none()

        enc = encrypt_credential(data.ssh_password)
        if existing:
            existing.secret_enc = enc
        else:
            session.add(DeviceCredential(
                device_id=device_id,
                cred_type="ssh_password",
                secret_enc=enc,
            ))


def _audit_log(session: AsyncSession, user: User, action: str, target: str, detail: dict = None):
    """写入审计日志"""
    session.add(AuditLog(
        actor=user.username,
        action=action,
        target=target,
        detail=detail,
    ))


def _device_to_dict(device: Device, creds: dict) -> dict:
    """将 ORM 设备对象转为字典（供采集器使用）"""
    return {
        "id": device.id,
        "name": device.name,
        "ip": device.ip,
        "snmp_version": device.snmp_version,
        "snmp_port": device.snmp_port,
        "snmp_user": device.snmp_user,
        "vendor": device.vendor or "generic",
        "model": device.model,
        "community": creds.get("snmp_v2c_community", ""),
        "auth_password": creds.get("snmp_v3_auth", ""),
        "priv_password": creds.get("snmp_v3_priv", ""),
    }
