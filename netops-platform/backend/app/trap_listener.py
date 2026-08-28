"""
SNMP Trap/Inform 接收器（基于 PySNMP 7.x）。
在 FastAPI 启动时监听 UDP 端口，收到 Trap 后写入 snmp_trap_log 并生成 Alert。
"""
from __future__ import annotations

import asyncio
import binascii
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from pysnmp.entity import engine as snmp_engine_mod
from pysnmp.carrier.asyncio.dgram import udp
from pysnmp.entity.rfc3413 import ntfrcv
from pysnmp.proto.api import v2c

from app.config import settings
from app.db import async_session
from app.models import Alert, Device, SnmpTrapLog, TrapRule

logger = logging.getLogger(__name__)

_snmp_engine: Optional[snmp_engine_mod.SnmpEngine] = None
_main_loop: Optional[asyncio.AbstractEventLoop] = None
_last_transport_address: tuple[Optional[Any], Optional[Any]] = (None, None)


# ============================================================
# 默认 Trap 规则库
# ============================================================
DEFAULT_TRAP_RULES = [
    {
        "name": "标准 linkDown",
        "oid_prefix": "1.3.6.1.6.3.1.1.5.3",
        "severity": 1,
        "message_template": "接口链路 DOWN（SNMP Trap）",
    },
    {
        "name": "标准 linkUp",
        "oid_prefix": "1.3.6.1.6.3.1.1.5.4",
        "severity": 3,
        "message_template": "接口链路 UP（SNMP Trap）",
    },
    {
        "name": "标准 冷启动",
        "oid_prefix": "1.3.6.1.6.3.1.1.5.1",
        "severity": 1,
        "message_template": "设备冷启动（SNMP Trap）",
    },
    {
        "name": "标准 热启动",
        "oid_prefix": "1.3.6.1.6.3.1.1.5.2",
        "severity": 3,
        "message_template": "设备热启动（SNMP Trap）",
    },
    {
        "name": "华为 链路状态变化",
        "oid_prefix": "1.3.6.1.4.1.2011.5.25.129.2.1.1",
        "severity": 1,
        "message_template": "华为设备接口状态变化（SNMP Trap）",
    },
    {
        "name": "华为 温度异常",
        "oid_prefix": "1.3.6.1.4.1.2011.5.25.129.2.2",
        "severity": 1,
        "message_template": "华为设备温度异常（SNMP Trap）",
    },
]


async def ensure_default_trap_rules():
    """如果 trap_rule 表为空，则插入默认规则。"""
    async with async_session() as session:
        from sqlalchemy import func, select
        count = (await session.execute(select(func.count()).select_from(TrapRule))).scalar() or 0
        if count > 0:
            return
        for r in DEFAULT_TRAP_RULES:
            session.add(TrapRule(**r))
        await session.commit()
        logger.info("Inserted %d default SNMP trap rules", len(DEFAULT_TRAP_RULES))


# ============================================================
# 启动 / 停止
# ============================================================
def start_trap_listener(loop: asyncio.AbstractEventLoop):
    """在后台线程启动 SNMP Trap 监听。"""
    global _snmp_engine, _main_loop
    _main_loop = loop

    port = getattr(settings, "TRAP_LISTEN_PORT", 1620)
    community = getattr(settings, "TRAP_COMMUNITY", "public")

    snmpEngine = snmp_engine_mod.SnmpEngine()
    _snmp_engine = snmpEngine

    # 监听 UDP 端口
    try:
        from pysnmp.entity import config as snmp_config
        snmp_config.add_transport(
            snmpEngine,
            udp.DOMAIN_NAME,
            udp.UdpTransport().open_server_mode(("0.0.0.0", port)),
        )
        snmp_config.add_v1_system(snmpEngine, "trap-area", community)
    except Exception as e:
        logger.error("Failed to bind SNMP trap listener to port %s: %s", port, e)
        return

    # 通过 observer 捕获 stateReference → transportAddress 映射
    for execpoint in (
        "rfc2576.prepareDataElements:unconfirmed",
        "rfc3412.prepareDataElements:unconfirmed",
    ):
        try:
            snmpEngine.observer.register_observer(_store_transport_address, execpoint)
        except Exception as e:
            logger.warning("Observer already registered for %s: %s", execpoint, e)

    # 注册 Trap 接收回调
    ntfrcv.NotificationReceiver(snmpEngine, _trap_callback)
    snmpEngine.transport_dispatcher.job_started(1)

    thread = threading.Thread(target=_run_dispatcher, args=(snmpEngine,), daemon=True)
    thread.start()
    logger.info("SNMP Trap listener started on 0.0.0.0:%s (community=%s)", port, community)


def stop_trap_listener():
    global _snmp_engine
    if _snmp_engine:
        try:
            _snmp_engine.close_dispatcher()
        except Exception as e:
            logger.warning("Error closing SNMP trap dispatcher: %s", e)
        _snmp_engine = None


def _run_dispatcher(snmpEngine: snmp_engine_mod.SnmpEngine):
    try:
        snmpEngine.open_dispatcher()
    except Exception:
        snmpEngine.close_dispatcher()
        raise


def _store_transport_address(snmpEngine, execpoint, variables, cbCtx):
    """Observer 在 prepareDataElements 时触发，记录最近一次 Trap 来源地址。"""
    global _last_transport_address
    transportDomain = variables.get("transportDomain")
    transportAddress = variables.get("transportAddress")
    if transportAddress is not None:
        _last_transport_address = (transportDomain, transportAddress)


# ============================================================
# Trap 回调处理
# ============================================================
def _trap_callback(
    snmpEngine: snmp_engine_mod.SnmpEngine,
    stateReference: Any,
    contextEngineId: Any,
    contextName: Any,
    varBinds: list,
    cbCtx: Any,
):
    """PySNMP 收到 Trap 后回调（在后台线程中执行）。"""
    global _last_transport_address
    transportDomain, transportAddress = _last_transport_address
    _last_transport_address = (None, None)
    if transportAddress:
        source_ip = str(transportAddress[0]) if transportAddress else "unknown"
        source_port = int(transportAddress[1]) if len(transportAddress) > 1 else 0
    else:
        source_ip, source_port = "unknown", 0

    variables: list[dict[str, Any]] = []
    raw_hex = ""
    try:
        raw_hex = binascii.hexlify(b"").decode()  # 占位：pysnmp 未直接暴露 raw bytes
        for name, val in varBinds:
            variables.append({
                "oid": name.prettyPrint(),
                "value": val.prettyPrint(),
                "type": val.__class__.__name__,
            })
    except Exception as e:
        logger.warning("Error parsing varbinds: %s", e)

    # 提交到主事件循环执行数据库操作
    if _main_loop and _main_loop.is_running():
        asyncio.run_coroutine_threadsafe(
            _handle_trap(source_ip, source_port, variables, raw_hex),
            _main_loop,
        )
    else:
        logger.warning("Main event loop not available, dropping trap from %s", source_ip)


async def _handle_trap(
    source_ip: str,
    source_port: int,
    variables: list[dict[str, Any]],
    raw_hex: str,
):
    from sqlalchemy import select

    async with async_session() as session:
        # 根据来源 IP 找设备
        device = (await session.execute(
            select(Device).where(Device.ip == source_ip)
        )).scalar_one_or_none()

        # 保存 Trap 日志
        log = SnmpTrapLog(
            source_ip=source_ip,
            source_port=source_port,
            version="v2c",
            community="public",
            pdu_type="Trap",
            variables=variables,
            raw_hex=raw_hex,
        )
        session.add(log)
        await session.flush()

        # 匹配规则
        rule = await _match_trap_rule(session, variables)
        if rule and device:
            message = _render_message(rule.message_template, variables)
            alert = Alert(
                rule_id=None,
                device_id=device.id,
                metric_name="snmp_trap",
                severity=rule.severity,
                status="active",
                message=message,
                value=None,
                fired_at=datetime.now(timezone.utc),
            )
            session.add(alert)
            await session.flush()
            log.mapped_alert_id = alert.id
            logger.info("Created alert from trap %s for device %s", source_ip, device.name)

        await session.commit()


async def _match_trap_rule(session, variables: list[dict[str, Any]]) -> Optional[TrapRule]:
    from sqlalchemy import select
    if not variables:
        return None

    # 找到 snmpTrapOID（1.3.6.1.6.3.1.1.4.1.0）的值，即 Trap 类型 OID
    trap_oid = ""
    for v in variables:
        if v.get("oid") == "1.3.6.1.6.3.1.1.4.1.0":
            trap_oid = v.get("value", "")
            break

    # 没找到 snmpTrapOID 时 fallback 到第一个 OID
    if not trap_oid and variables:
        trap_oid = variables[0].get("oid", "")

    rows = await session.execute(select(TrapRule).where(TrapRule.enabled == True))
    rules = list(rows.scalars().all())

    best: Optional[TrapRule] = None
    best_len = 0
    for rule in rules:
        prefix = rule.oid_prefix.strip()
        if trap_oid.startswith(prefix) and len(prefix) > best_len:
            best = rule
            best_len = len(prefix)
    return best


def _render_message(template: str, variables: list[dict[str, Any]]) -> str:
    message = template
    for idx, v in enumerate(variables):
        message = message.replace(f"{{v{idx}}}", v.get("value", "")[:64])
    # 常用变量名
    for v in variables:
        oid = v.get("oid", "")
        val = v.get("value", "")
        if oid == "1.3.6.1.2.1.1.3.0":
            message = message.replace("{uptime}", val)
        if oid == "1.3.6.1.2.1.2.2.1.1.1":
            message = message.replace("{ifIndex}", val)
    return message
