"""
设备配置管理：通过 SSH(Netmiko) 抓取当前配置、归档版本、diff 比对。
"""
from __future__ import annotations

import difflib
import hashlib
from typing import Optional

from sqlalchemy import select, desc

from app.db import async_session
from app.models import ConfigBackup, Device, DeviceCredential
from app.security.credentials import decrypt_credential


def _map_vendor_to_netmiko(vendor: Optional[str]) -> str:
    v = (vendor or "").lower()
    if v in ("huawei", "huawei_vrp"):
        return "huawei"
    if v in ("h3c", "h3c_comware"):
        return "hp_comware"
    if v in ("cisco",):
        return "cisco_ios"
    return "generic_termserver"


def _config_command(vendor: Optional[str]) -> str:
    v = (vendor or "").lower()
    if v in ("huawei", "huawei_vrp", "h3c", "h3c_comware"):
        return "display current-configuration"
    return "show running-config"


async def _get_ssh_credential(device_id: str) -> tuple[str, str]:
    """从凭据库读取 SSH 用户名/密码，解密后返回。"""
    async with async_session() as session:
        rows = await session.execute(
            select(DeviceCredential).where(DeviceCredential.device_id == device_id)
        )
        cred_map = {c.cred_type: c for c in rows.scalars().all()}

        username = ""
        password = ""
        if "ssh_username" in cred_map:
            username = decrypt_credential(cred_map["ssh_username"].secret_enc)
        if "ssh_password" in cred_map:
            password = decrypt_credential(cred_map["ssh_password"].secret_enc)

        if not username or not password:
            raise ValueError("设备未配置 SSH 用户名/密码凭据（cred_type=ssh_username/ssh_password）")
        return username, password


async def fetch_device_config(device: Device) -> str:
    """通过 Netmiko SSH 抓取设备当前配置文本。"""
    username, password = await _get_ssh_credential(device.id)

    # 延迟导入 netmiko：不是每个环境都安装，且首次加载较重
    from netmiko import ConnectHandler

    device_type = _map_vendor_to_netmiko(device.vendor)
    command = _config_command(device.vendor)

    conn = ConnectHandler(
        device_type=device_type,
        host=device.ip,
        username=username,
        password=password,
        port=getattr(device, "ssh_port", 22) or 22,
        timeout=20,
        banner_timeout=15,
    )
    try:
        output = conn.send_command(command, read_timeout=60)
        return output or ""
    finally:
        conn.disconnect()


async def get_latest_config(device_id: str) -> Optional[ConfigBackup]:
    async with async_session() as session:
        row = await session.execute(
            select(ConfigBackup)
            .where(ConfigBackup.device_id == device_id)
            .order_by(desc(ConfigBackup.revision))
            .limit(1)
        )
        return row.scalar_one_or_none()


async def backup_device_config(device_id: str, captured_by: str = "system") -> ConfigBackup:
    """抓取并保存一份新配置；如无变化则返回最新版本。"""
    async with async_session() as session:
        device = await session.get(Device, device_id)
        if not device:
            raise ValueError("设备不存在")

    content = await fetch_device_config(device)
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    async with async_session() as session:
        latest = (await session.execute(
            select(ConfigBackup)
            .where(ConfigBackup.device_id == device_id)
            .order_by(desc(ConfigBackup.revision))
            .limit(1)
        )).scalar_one_or_none()

        if latest and latest.content_hash == content_hash:
            return latest

        revision = (latest.revision + 1) if latest else 1

        change_summary: Optional[str] = None
        if latest:
            added, removed = _count_changes(latest.content, content)
            change_summary = f"新增 {added} 行，删除 {removed} 行"

        backup = ConfigBackup(
            device_id=device_id,
            revision=revision,
            content=content,
            content_hash=content_hash,
            captured_by=captured_by,
            change_summary=change_summary,
        )
        session.add(backup)
        await session.commit()
        await session.refresh(backup)
        return backup


async def list_config_backups(device_id: str) -> list[ConfigBackup]:
    async with async_session() as session:
        rows = await session.execute(
            select(ConfigBackup)
            .where(ConfigBackup.device_id == device_id)
            .order_by(desc(ConfigBackup.revision))
        )
        return list(rows.scalars().all())


async def get_config_backup(backup_id: str) -> Optional[ConfigBackup]:
    async with async_session() as session:
        return await session.get(ConfigBackup, backup_id)


def compute_config_diff(old_text: str, new_text: str, old_label: str = "旧版本", new_label: str = "新版本") -> str:
    """返回 unified diff 文本。"""
    return "".join(
        difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=old_label,
            tofile=new_label,
        )
    )


def _count_changes(old_text: str, new_text: str) -> tuple[int, int]:
    diff = list(difflib.unified_diff(
        old_text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
    ))
    added = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))
    return added, removed
