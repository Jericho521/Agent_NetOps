"""
设备配置管理 API：备份、版本列表、diff。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.models import ConfigBackup
from app.routers.auth import get_current_user, User
from app.config_manager import (
    backup_device_config,
    compute_config_diff,
    fetch_device_config,
    get_config_backup,
    get_latest_config,
    list_config_backups,
)

router = APIRouter(prefix="/devices/{device_id}/config", tags=["Config Management"])


class ConfigBackupOut(BaseModel):
    id: str
    device_id: str
    revision: int
    content_hash: str
    captured_at: str
    captured_by: str
    change_summary: Optional[str]

    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, obj: ConfigBackup) -> "ConfigBackupOut":
        return cls(
            id=obj.id,
            device_id=obj.device_id,
            revision=obj.revision,
            content_hash=obj.content_hash,
            captured_at=obj.captured_at.isoformat() if obj.captured_at else "",
            captured_by=obj.captured_by,
            change_summary=obj.change_summary,
        )


class ConfigContentOut(BaseModel):
    id: str
    revision: int
    content: str
    captured_at: str
    captured_by: str


@router.get("/backups", response_model=list[ConfigBackupOut])
async def list_backups(
    device_id: str,
    current_user: User = Depends(get_current_user),
):
    return [ConfigBackupOut.from_orm(b) for b in await list_config_backups(device_id)]


@router.post("/backups", response_model=ConfigBackupOut)
async def create_backup(
    device_id: str,
    current_user: User = Depends(get_current_user),
):
    try:
        backup = await backup_device_config(device_id, captured_by=current_user.username)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"抓取配置失败: {e}")
    return ConfigBackupOut.from_orm(backup)


@router.get("/backups/{backup_id}", response_model=ConfigContentOut)
async def get_backup(
    device_id: str,
    backup_id: str,
    current_user: User = Depends(get_current_user),
):
    backup = await get_config_backup(backup_id)
    if not backup or backup.device_id != device_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="备份不存在")
    return ConfigContentOut(
        id=backup.id,
        revision=backup.revision,
        content=backup.content,
        captured_at=backup.captured_at.isoformat() if backup.captured_at else "",
        captured_by=backup.captured_by,
    )


@router.get("/backups/{backup_id}/diff")
async def diff_backup(
    device_id: str,
    backup_id: str,
    compare_with: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """与指定旧版本 diff；默认与上一版本 diff。"""
    new_backup = await get_config_backup(backup_id)
    if not new_backup or new_backup.device_id != device_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="备份不存在")

    if compare_with:
        old_backup = await get_config_backup(compare_with)
    else:
        backups = await list_config_backups(device_id)
        old_backup = next((b for b in backups if b.revision < new_backup.revision), None)

    if not old_backup:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="没有可对比的旧版本")

    diff_text = compute_config_diff(
        old_backup.content,
        new_backup.content,
        old_label=f"rev{old_backup.revision}",
        new_label=f"rev{new_backup.revision}",
    )
    return {"old_revision": old_backup.revision, "new_revision": new_backup.revision, "diff": diff_text}


@router.post("/preview")
async def preview_current_config(
    device_id: str,
    current_user: User = Depends(get_current_user),
):
    """直接 SSH 抓取当前配置并返回，但不保存。"""
    from app.db import async_session
    from app.models import Device

    async with async_session() as session:
        device = await session.get(Device, device_id)
        if not device:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="设备不存在")

    try:
        content = await fetch_device_config(device)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"抓取配置失败: {e}")

    return {"content": content}
