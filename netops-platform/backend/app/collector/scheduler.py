"""
APScheduler 调度器 - 定时触发 SNMP 采集任务
每 60 秒对所有 enabled 设备执行一次采集
"""
import asyncio
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.db import async_session
from app.models import Device, DeviceCredential, AlertRule, Alert
from app.collector.snmp import collect_device_metrics
from app.collector.victoriametrics import write_metrics_to_vm
from app.collector.topology_snmp import collect_device_sysname
from app.security.credentials import decrypt_credential

logger = logging.getLogger(__name__)

# 全局调度器实例
_scheduler: AsyncIOScheduler | None = None


def start_scheduler():
    """启动 APScheduler 调度器"""
    global _scheduler
    if _scheduler and _scheduler.running:
        return

    _scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
    _scheduler.add_job(
        collect_all_devices,
        trigger=IntervalTrigger(seconds=settings.collect_interval_seconds),
        id="collect_all_devices",
        name="全量设备采集",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(f"调度器已启动，采集间隔: {settings.collect_interval_seconds}s")


def stop_scheduler():
    """停止调度器"""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("调度器已停止")


async def collect_all_devices():
    """
    采集所有已启用设备的指标。
    由调度器定时调用，也可手动触发。
    """
    from sqlalchemy import select

    logger.debug("开始全量设备采集...")

    async with async_session() as session:
        # 确保默认告警规则（CPU/内存阈值）存在
        await _ensure_default_rules(session)

        # 获取所有启用的设备
        result = await session.execute(
            select(Device).where(Device.enabled == True).order_by(Device.ip)
        )
        devices = result.scalars().all()

        if not devices:
            logger.debug("没有启用的设备需要采集")
            return

        success_count = 0
        fail_count = 0

        for device in devices:
            try:
                # 获取凭据并解密
                creds_result = await session.execute(
                    select(DeviceCredential).where(DeviceCredential.device_id == device.id)
                )
                creds = {}
                for c in creds_result.scalars().all():
                    creds[c.cred_type] = decrypt_credential(c.secret_enc)

                # 构建设备信息字典
                device_info = {
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

                # 执行采集
                metrics = await collect_device_metrics(device_info)

                old_status = device.status

                if metrics:
                    # 写入 VictoriaMetrics
                    write_ok = await write_metrics_to_vm(metrics)
                    if write_ok:
                        device.status = "online"
                        device.last_seen_at = datetime.now(timezone.utc)
                        success_count += 1
                        # 顺手更新设备自身 sysName，用于拓扑节点合并/匹配
                        try:
                            sys_name = await collect_device_sysname(device_info)
                            if sys_name:
                                device.sys_name = sys_name
                        except Exception:
                            pass
                    else:
                        device.status = "error"
                        fail_count += 1
                else:
                    device.status = "offline"
                    fail_count += 1

                # 设备状态变更 → 自动处理离线/恢复告警
                if device.status != old_status:
                    await _handle_device_alert(session, device, old_status)

                # 更新设备状态到数据库
                session.add(device)

            except Exception as e:
                logger.error(f"采集设备 {device.name}({device.ip}) 异常: {e}", exc_info=True)
                device.status = "error"
                session.add(device)
                fail_count += 1

        await session.commit()

        # 采集完成后执行拓扑发现（LLDP/CDP 邻居 → link 表）
        try:
            from app.collector.topology import discover_topology_safe
            await discover_topology_safe()
        except Exception as e:
            logger.error(f"拓扑发现触发失败: {e}", exc_info=True)

    logger.info(f"本轮采集完成: 成功 {success_count}/{len(devices)}, 失败 {fail_count}")


# ============================================================
# 设备离线/恢复自动告警
# ============================================================
async def _ensure_offline_rule(session) -> AlertRule:
    """确保存在一条「设备离线」系统告警规则（不存在则自动创建）"""
    from sqlalchemy import select
    result = await session.execute(
        select(AlertRule).where(AlertRule.name == "设备离线")
    )
    rule = result.scalar_one_or_none()
    if not rule:
        rule = AlertRule(
            name="设备离线",
            metric_name="device_status",
            operator="eq",
            threshold=0,
            duration_seconds=0,
            severity=1,  # P1 严重
            enabled=True,
        )
        session.add(rule)
        await session.flush()
    return rule


async def _ensure_default_rules(session):
    """确保存在 CPU/内存利用率默认阈值规则（>85% P1 重要/橙，>95% P0 严重/红）。"""
    from sqlalchemy import select
    DEFAULTS = [
        ("CPU利用率过高", "snmp_cpu_usage_percent", 85, 95),
        ("内存利用率过高", "snmp_mem_usage_percent", 85, 95),
    ]
    for name, metric, thr, crit in DEFAULTS:
        exists = await session.execute(select(AlertRule).where(AlertRule.name == name))
        if exists.scalar_one_or_none():
            continue
        rule = AlertRule(
            name=name, metric_name=metric, operator="gt", threshold=thr,
            critical_threshold=crit, severity=1, enabled=True,
        )
        session.add(rule)
        logger.info(f"已自动创建默认告警规则：{name}（阈值 {thr}=P1，严重阈值 {crit}=P0）")
    await session.commit()


async def _handle_device_alert(session, device: Device, old_status: str):
    """
    根据设备状态变更自动创建或恢复告警：
      - 变为 offline/error → 创建「设备离线」告警（若尚无 active 告警）
      - 恢复为 online   → resolve 该设备的 active 离线告警
    """
    from sqlalchemy import select

    new_status = device.status

    # 恢复在线 → resolve 离线告警
    if new_status == "online" and old_status in ("offline", "error"):
        result = await session.execute(
            select(Alert).where(
                Alert.device_id == device.id,
                Alert.status == "active",
            )
        )
        for alert in result.scalars().all():
            alert.status = "resolved"
            alert.resolved_at = datetime.now(timezone.utc)
            logger.info(f"设备 {device.name}({device.ip}) 已恢复，告警 {alert.id} 已自动恢复")
        return

    # 变为离线/异常 → 创建离线告警（级别按设备重要性升级）
    if new_status in ("offline", "error") and old_status in (None, "online"):
        # 检查是否已有未解决的离线告警
        existing = await session.execute(
            select(Alert).where(
                Alert.device_id == device.id,
                Alert.status.in_(["active", "acknowledged"]),
            )
        )
        if existing.scalar_one_or_none():
            return  # 已有活跃告警，不重复创建

        rule = await _ensure_offline_rule(session)
        status_text = "离线" if new_status == "offline" else "采集异常"
        cat = "offline" if new_status == "offline" else "error"
        # 设备离线/异常不进入 P 级别体系（severity=NULL），仅作状态标记。
        # P0/P1 级别仅保留给：堆叠分裂、M-LAG 脑裂、用户标记的重要链路中断等故障类告警。

        alert = Alert(
            rule_id=rule.id,
            device_id=device.id,
            status="active",
            severity=None,
            category=cat,
            message=f"[{status_text}] 设备 {device.name}({device.ip}) {status_text}",
        )
        session.add(alert)
        logger.info(f"设备 {device.name}({device.ip}) {status_text}，已生成离线状态告警（不分级）")
