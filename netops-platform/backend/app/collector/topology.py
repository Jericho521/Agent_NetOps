"""
拓扑发现 - 周期性采集所有在线设备的 LLDP/CDP 邻居，解析成本端↔对端连接并写入 link 表
同时检测用户标记的重要链路中断/恢复，并生成/关闭 P0 级告警
"""
import logging
from datetime import datetime, timezone
from sqlalchemy import select, delete

from app.db import async_session
from app.models import Device, Link, Alert
from app.collector.topology_snmp import collect_topology_neighbors
from app.security.credentials import decrypt_credential

logger = logging.getLogger(__name__)


def _build_device_info(device: Device, creds: dict) -> dict:
    return {
        "id": device.id,
        "name": device.name,
        "ip": device.ip,
        "snmp_version": device.snmp_version,
        "snmp_port": device.snmp_port,
        "snmp_user": device.snmp_user,
        "vendor": device.vendor or "generic",
        "model": device.model,
        "community": creds.get("snmp_v2c_community", "") or creds.get("snmp_v2_community", ""),
        "auth_password": creds.get("snmp_v3_auth", ""),
        "priv_password": creds.get("snmp_v3_priv", ""),
    }


def _link_key(local_device_id: str, local_port: str | None, remote_sysname: str | None) -> str:
    """用于匹配同一物理链路的稳定 key（对端 sysname 不变即可认为同一条链路）。"""
    return f"{local_device_id}||{(local_port or '').strip().lower()}||{(remote_sysname or '').strip().lower()}"


def _link_fingerprint(local_device_id: str, local_port: str | None, remote_sysname: str | None) -> str:
    """嵌入 Alert.message 用于后续恢复告警时精确匹配。"""
    return f"#[{local_device_id}|{(local_port or '').strip()}|{(remote_sysname or '').strip()}]"


async def discover_topology():
    """
    对每台 online 设备采集邻居，解析连接并写入 link 表。
    每轮先删除该设备的旧链路（全量重算，保证拓扑始终最新）。
    同时保留用户标记的重要链路标记，并检测中断/恢复。
    """
    from app.db import async_session
    from app.models import DeviceCredential

    async with async_session() as session:
        result = await session.execute(
            select(Device).where(Device.enabled == True, Device.status == "online")
        )
        devices = result.scalars().all()
        if not devices:
            logger.debug("没有在线设备，跳过拓扑发现")
            return

        # 建立 name/sys_name/ip → device 的查找表（用于把对端解析成具体设备）
        all_devs = (await session.execute(select(Device))).scalars().all()
        name_map: dict[str, Device] = {}
        sysname_map: dict[str, Device] = {}
        ip_map: dict[str, Device] = {}
        dev_name_by_id: dict[str, str] = {}
        for d in all_devs:
            if d.name:
                name_map[d.name.strip().lower()] = d
                dev_name_by_id[d.id] = d.name
            if d.sys_name:
                sysname_map[d.sys_name.strip().lower()] = d
            if d.ip:
                ip_map[d.ip.strip()] = d

        # 上一轮所有被标记为重要的链路 key
        old_critical_result = await session.execute(select(Link).where(Link.is_critical == True))
        old_critical_links = old_critical_result.scalars().all()
        critical_keys: set[str] = {
            _link_key(lk.local_device_id, lk.local_port, lk.remote_sysname)
            for lk in old_critical_links
        }
        survived_critical_keys: set[str] = set()

        new_links: list[Link] = []
        processed = 0

        for device in devices:
            creds_result = await session.execute(
                select(DeviceCredential).where(DeviceCredential.device_id == device.id)
            )
            creds = {}
            for c in creds_result.scalars().all():
                creds[c.cred_type] = decrypt_credential(c.secret_enc)

            device_info = _build_device_info(device, creds)
            neighbors = await collect_topology_neighbors(device_info)

            # 删除该设备旧链路，准备重算
            await session.execute(delete(Link).where(Link.local_device_id == device.id))

            for nb in neighbors:
                remote_name = (nb.get("remote_sysname") or "").strip().lower()
                remote_ip = (nb.get("remote_ip") or "").strip()

                # 过滤堆叠/集群口自连：对端 sysName 就是本机自己，
                # 这是堆叠成员间内部互联，不能画成"自己连自己"的假链路
                self_name = (device.sys_name or device.name or "").strip().lower()
                if self_name and remote_name == self_name:
                    logger.info(
                        "跳过堆叠自连邻居: %s remote=%s port=%s",
                        device.ip, nb.get("remote_sysname"), nb.get("local_port"),
                    )
                    continue
                remote_device = (
                    name_map.get(remote_name)
                    or sysname_map.get(remote_name)
                    or (ip_map.get(remote_ip) if remote_ip else None)
                )

                local_port = nb.get("local_port") or None
                remote_sysname = nb.get("remote_sysname") or None
                key = _link_key(device.id, local_port, remote_sysname)
                is_critical = key in critical_keys
                if is_critical:
                    survived_critical_keys.add(key)

                link = Link(
                    local_device_id=device.id,
                    local_port=local_port,
                    remote_sysname=remote_sysname,
                    remote_port=nb.get("remote_port") or None,
                    remote_ip=nb.get("remote_ip"),
                    remote_device_id=remote_device.id if remote_device else None,
                    protocol=nb.get("protocol", "lldp"),
                    link_type=nb.get("link_type", "unknown"),
                    is_critical=is_critical,
                    discovered_at=datetime.now(timezone.utc),
                )
                new_links.append(link)

            processed += 1

        # 批量写入新链路
        for link in new_links:
            session.add(link)
        await session.flush()

        # 处理重要链路中断/恢复
        lost_keys = critical_keys - survived_critical_keys
        await _handle_critical_link_alerts(session, lost_keys, survived_critical_keys, old_critical_links, dev_name_by_id)

        await session.commit()
        logger.info(
            f"拓扑发现完成：扫描 {processed} 台在线设备，发现 {len(new_links)} 条连接，"
            f"重要链路 {len(critical_keys)} 条，中断 {len(lost_keys)} 条"
        )


async def _handle_critical_link_alerts(
    session,
    lost_keys: set[str],
    survived_critical_keys: set[str],
    old_critical_links: list[Link],
    dev_name_by_id: dict[str, str],
):
    """
    为丢失的重要链路生成 P0 告警；为恢复的重要链路关闭已有的 active link 告警。
    """
    # key -> Link 旧记录映射
    old_by_key: dict[str, Link] = {
        _link_key(lk.local_device_id, lk.local_port, lk.remote_sysname): lk
        for lk in old_critical_links
    }

    now = datetime.now(timezone.utc)

    # 1) 生成中断告警
    for key in lost_keys:
        lk = old_by_key.get(key)
        if not lk:
            continue
        local_name = dev_name_by_id.get(lk.local_device_id, lk.local_device_id[:8])
        remote_display = lk.remote_sysname or lk.remote_ip or "未知设备"
        fingerprint = _link_fingerprint(lk.local_device_id, lk.local_port, lk.remote_sysname)

        # 避免重复告警：如果已存在同一条链路的 active 中断告警，则不再创建
        exists = (await session.execute(
            select(Alert).where(
                Alert.category == "link",
                Alert.status == "active",
                Alert.message.like(f"%{fingerprint}%"),
            )
        )).scalar_one_or_none()
        if exists:
            continue

        alert = Alert(
            rule_id=None,
            device_id=lk.local_device_id,
            status="active",
            severity=0,  # P0 红
            category="link",
            message=f"[P0] 重要链路中断：{local_name}({lk.local_port or '-'}) -> {remote_display}({lk.remote_port or '-'}) {fingerprint}",
            fired_at=now,
        )
        session.add(alert)
        logger.warning(f"重要链路中断告警: {alert.message}")

    # 2) 恢复已重新出现的重要链路告警
    for key in survived_critical_keys:
        lk = old_by_key.get(key)
        if not lk:
            continue
        fingerprint = _link_fingerprint(lk.local_device_id, lk.local_port, lk.remote_sysname)
        recovered = (await session.execute(
            select(Alert).where(
                Alert.category == "link",
                Alert.status == "active",
                Alert.message.like(f"%{fingerprint}%"),
            )
        )).scalars().all()
        for al in recovered:
            al.status = "resolved"
            al.resolved_at = now
            logger.info(f"重要链路恢复，告警已关闭: {al.message}")


async def discover_topology_safe():
    """带异常保护的拓扑发现入口，供调度器调用。"""
    try:
        await discover_topology()
    except Exception as e:
        logger.error(f"拓扑发现异常: {e}", exc_info=True)
