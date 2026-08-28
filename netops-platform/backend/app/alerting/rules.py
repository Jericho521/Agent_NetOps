"""
告警规则引擎 - 周期性评估阈值规则，命中则写入告警表
MVP 阶段只支持"大于阈值"(gt)一种算子
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.db import async_session
from app.models import AlertRule, Alert, Device
from app.collector.victoriametrics import query_vm_instant

logger = logging.getLogger(__name__)


async def evaluate_alert_rules():
    """
    评估所有启用的告警规则。
    由调度器周期调用（建议 60s 一次）。
    """
    async with async_session() as session:
        # 获取所有启用的规则
        result = await session.execute(
            select(AlertRule).where(AlertRule.enabled == True)
        )
        rules = result.scalars().all()

        for rule in rules:
            await _evaluate_rule(session, rule)

        await session.commit()


async def _evaluate_rule(session, rule: AlertRule):
    """评估单条规则"""
    try:
        # 构造 PromQL 查询
        if rule.device_id:
            # 规则绑定到特定设备
            dev_result = await session.execute(
                select(Device).where(Device.id == rule.device_id)
            )
            device = dev_result.scalar_one_or_none()
            if not device:
                return
            promql = f'{rule.metric_name}{{device="{device.name}"}}'
            device_filter = rule.device_id
        else:
            # 全局规则：匹配所有设备
            promql = f'{rule.metric_name}'
            device_filter = None

        # 查询 VM 最新值
        vm_result = await query_vm_instant(promql)

        if not vm_result:
            return

        # 检查每个结果是否超过阈值
        for item in vm_result:
            value_raw = item.get("value", [None, None])[1]
            if value_raw is None:
                continue

            try:
                value = float(value_raw)
            except (ValueError, TypeError):
                continue

            # 判断是否触发（只支持 gt）
            triggered = value > rule.threshold

            if triggered:
                metric_labels = item.get("metric", {})
                device_name = metric_labels.get("device", "unknown")

                # 找到对应的设备 ID
                dev_id = device_filter
                if not dev_id and device_name:
                    dev_lookup = await session.execute(
                        select(Device.id).where(Device.name == device_name)
                    )
                    dev_id = dev_lookup.scalar_one_or_none()

                if not dev_id:
                    continue

                # 检查是否已有 active 状态的同规则+同设备告警（避免重复）
                existing_alert = await session.execute(
                    select(Alert).where(
                        Alert.rule_id == rule.id,
                        Alert.device_id == dev_id,
                        Alert.status == "active",
                    )
                )

                if existing_alert.scalar_one_or_none():
                    continue  # 已有活跃告警，不重复创建

                # 计算最终严重级别：若设置了 critical_threshold 且超过，则升级为 P0(红/严重)
                final_severity = rule.severity
                is_critical = False
                if rule.critical_threshold is not None and value > rule.critical_threshold:
                    final_severity = 0  # P0 严重（红色）
                    is_critical = True

                severity_text = {0: "P0-严重", 1: "P1-重要", 2: "P2-次要", 3: "P3-提示"}.get(final_severity, "未知")
                level_tag = "严重" if is_critical else "警告"

                alert = Alert(
                    rule_id=rule.id,
                    device_id=dev_id,
                    status="active",
                    severity=final_severity,
                    category="threshold",
                    message=f"[{severity_text}] {device_name}: {rule.metric_name} = {value:.2f}, 阈值 > {rule.threshold}"
                            + (f" (严重阈值 > {rule.critical_threshold})" if is_critical else ""),
                    value=value,
                )
                session.add(alert)
                logger.info(f"告警触发: {alert.message}")

    except Exception as e:
        logger.error(f"评估规则 '{rule.name}' 失败: {e}", exc_info=True)
