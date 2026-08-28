"""
SNMP 采集器核心 - 使用 pysnmp 异步采集设备指标
支持 SNMPv2c 和 SNMPv3，采集 sysName、CPU、内存、ifTable/ifXTable
"""
import asyncio
import logging
from typing import Optional

from pysnmp.hlapi.v3arch.asyncio import (
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    get_cmd,
    next_cmd,
    SnmpEngine,
    CommunityData,
    UsmUserData,
    usmHMACSHAAuthProtocol,
    usmHMACMD5AuthProtocol,
    usmAesCfb128Protocol,
    usmDESPrivProtocol as usmDESProtocol,  # pysnmp>=6 起 usmDESProtocol 更名为 usmDESPrivProtocol
)

from app.config import settings

logger = logging.getLogger(__name__)

# ============================================================
# 标准 OID 映射（HOST-RESOURCES-MIB / IF-MIB / IF-X-MIB / SNMPv2-MIB）
# ============================================================
STANDARD_OIDS = {
    # 系统信息 (SNMPv2-MIB)
    "sysDescr": "1.3.6.1.2.1.1.1.0",
    "sysObjectID": "1.3.6.1.2.1.1.2.0",
    "sysUpTime": "1.3.6.1.2.1.1.3.0",
    "sysName": "1.3.6.1.2.1.1.5.0",
    "sysLocation": "1.3.6.1.2.1.1.6.0",

    # CPU - HOST-RESOURCES-MIB（多核取均值）- 通用设备备用
    "hrProcessorLoad": "1.3.6.1.2.1.25.3.3.1.2",

    # 内存 - HOST-RESOURCES-MIB hrStorage - 通用设备备用
    "hrStorageType": "1.3.6.1.2.1.25.2.3.1.2",
    "hrStorageUsed": "1.3.6.1.2.1.25.2.3.1.5",
    "hrStorageSize": "1.3.6.1.2.1.25.2.3.1.4",

    # 接口表 - IF-MIB
    "ifIndex": "1.3.6.1.2.1.2.2.1.1",
    "ifDescr": "1.3.6.1.2.1.2.2.1.2",
    "ifOperStatus": "1.3.6.1.2.1.2.2.1.8",
    "ifAdminStatus": "1.3.6.1.2.1.2.2.1.7",
    "ifInErrors": "1.3.6.1.2.1.2.2.1.14",
    "ifOutErrors": "1.3.6.1.2.1.2.2.1.20",
    "ifInDiscards": "1.3.6.1.2.1.2.2.1.13",

    # 接口表 - IF-X-MIB（64 位计数器，避免翻转）
    "ifHCInOctets": "1.3.6.1.2.1.31.1.1.1.6",
    "ifHCOutOctets": "1.3.6.1.2.1.31.1.1.1.10",
    "ifHighSpeed": "1.3.6.1.2.1.31.1.1.1.15",
    "ifName": "1.3.6.1.2.1.31.1.1.1.1",
    "ifAlias": "1.3.6.1.2.1.31.1.1.1.18",
    "sysObjectID": "1.3.6.1.2.1.1.2.0",
}

# sysObjectID 前缀 → (厂商, 型号关键词)；用于自动识别设备型号
# 华为/华三/思科的 SYS OID 前段可唯一定位厂商
SYS_OBJECT_ID_PREFIX_MAP = {
    "1.3.6.1.4.1.2011": "huawei",   # 华为
    "1.3.6.1.4.1.25506": "h3c",     # 华三
    "1.3.6.1.4.1.9": "cisco",       # 思科
}


# ============================================================
# 厂商私有 OID（优先于标准 OID 使用）
# ============================================================
VENDOR_OIDS = {
    "huawei": {
        # ===== CPU =====
        # 优先：HUAWEI-ENTITY-EXTENT-MIB hwEntityStateTable（S7700/S9700/S12700 等 VRPV8 通用）
        #   hwEntityCpuUsage 1.3.6.1.4.1.2011.5.25.31.1.1.1.1.5 （按 entPhysicalIndex，WALK 取所有部件均值）
        "cpu_usage_entity": "1.3.6.1.4.1.2011.5.25.31.1.1.1.1.5",
        # 回退：HUAWEI-CPU-MIB（S5700/S6700 等旧机型）
        #   hwCpuDevDuty 1.3.6.1.4.1.2011.6.3.4.1.2 （TABLE，WALK）
        "cpu_usage": "1.3.6.1.4.1.2011.6.3.4.1.2",
        # ===== 内存 =====
        # 优先：HUAWEI-ENTITY-EXTENT-MIB（与 CPU 同源，取使用率百分比，最直观）
        #   hwEntityMemUsage 1.3.6.1.4.1.2011.5.25.31.1.1.1.1.7 （WALK）
        "mem_usage_entity": "1.3.6.1.4.1.2011.5.25.31.1.1.1.1.7",
        # 回退：HUAWEI-MEMORY-MIB hwMemoryDevTable（标量取不到 → 必须 WALK）
        #   hwMemoryDevSize    1.3.6.1.4.1.2011.6.3.5.1.1.2  内存总量(bytes)，索引 .框.槽位.CPU（如 .0.6.0）
        #   hwMemoryDevFree    1.3.6.1.4.1.2011.6.3.5.1.1.3  空闲内存(bytes)
        "mem_total": "1.3.6.1.4.1.2011.6.3.5.1.1.2",
        "mem_free": "1.3.6.1.4.1.2011.6.3.5.1.1.3",
        # 实体描述 OID（用于提取干净型号）
        "entPhysicalDescr": "1.3.6.1.2.1.47.1.1.1.1.2",
    },
    "h3c": {
        # H3C CPU 利用率 (%)
        "cpu_usage": "1.3.6.1.4.1.25506.1.1.1.1.1.2",
        # H3C 内存使用量
        "mem_used": "1.3.6.1.4.1.25506.1.6.1.1.1.1.10.6",
        "mem_total": "1.3.6.1.4.1.25506.1.6.1.1.1.1.10.5",
    },
}

# sysObjectID 公共前缀 → 厂商（用于自动识别）
SYS_OBJECT_ID_PREFIX_MAP = {
    "1.3.6.1.4.1.2011": "huawei",
    "1.3.6.1.4.1.25506": "h3c",
    "1.3.6.1.4.1.9": "cisco",
}

# 型号关键词（从 sysDescr / entPhysicalDescr 中提取，匹配到即作为型号）
MODEL_PATTERNS = [
    r"S\d{4,4}(?:-[A-Z0-9]+)?",       # S7700 / S7710 等
    r"S\d{3,4}(?:-[A-Z0-9]+)?",
    r"CE\d{3,4}", r"NE\d{2,4}", r"AR\d{2,4}",
    r"H3C\s+S\d{3,4}", r"H3C\s+SR\d+", r"H3C\s+MSR\d+",
    r"Catalyst\s+\d{3,4}", r"ISR\d{3,4}", r"Nexus\s+\d{3,4}",
]


def _get_auth(device_info: dict):
    """
    根据 SNMP 版本构造认证对象。
    device_info 需包含: snmp_version, community, snmp_user, auth_password, priv_password
    """
    version = device_info.get("snmp_version", 3)

    if version == 2:
        community = device_info.get("community", "public")
        return CommunityData(community), None  # v2c 不需要 UsmUser

    elif version == 3:
        username = device_info.get("snmp_user", "snmpuser")
        auth_pass = device_info.get("auth_password", "")
        priv_pass = device_info.get("priv_password", "")

        # 认证协议（默认 SHA）
        auth_proto = usmHMACSHAAuthProtocol
        # 加密协议（默认 AES）
        priv_proto = usmAesCfb128Protocol

        user_data = UsmUserData(
            userName=username,
            authKey=auth_pass if auth_pass else None,
            authProtocol=auth_proto if auth_pass else None,
            privKey=priv_pass if priv_pass else None,
            privProtocol=priv_proto if priv_pass else None,
        )
        return None, user_data

    else:
        raise ValueError(f"不支持的 SNMP 版本: {version}")


async def _snmp_get(ip: str, port: int, oids: dict[str, str], device_info: dict) -> dict:
    """
    执行 SNMP GET 操作（单个 OID 或标量 OID）。
    返回 {name: value_str} 字典。
    """
    engine = SnmpEngine()
    community_data, user_data = _get_auth(device_info)
    transport = await UdpTransportTarget.create(
        (ip, port),
        timeout=settings.collect_timeout_seconds,
        retries=settings.collect_retry_times,
    )
    ctx = ContextData()

    results = {}
    for name, oid in oids.items():
        try:
            auth_param = community_data or user_data
            err_indication, err_status, err_idx, var_binds = await get_cmd(
                engine,
                auth_param,
                transport,
                ctx,
                ObjectType(ObjectIdentity(oid)),
            )

            if err_indication:
                logger.warning(f"SNMP GET {name}({oid}) @ {ip} 错误: {err_indication}")
                continue

            for var_bind in var_binds:
                results[name] = str(var_bind[1]) if var_bind[1] is not None else ""

        except Exception as e:
            logger.warning(f"SNMP GET {name}({oid}) @ {ip} 异常: {e}")

    return results


async def _snmp_walk(ip: str, port: int, oid: str, device_info: dict, max_index: int = 200, return_full_oid: bool = False) -> list[tuple]:
    """
    执行 SNMP WALK 操作（表格 OID）。
    由于部分设备（如华为 S620）对 GETBULK 响应异常，
    这里改用「循环 GETNEXT」方式逐条获取，更稳定可靠。
    返回 [(index_value, value), ...] 列表。
    若 return_full_oid=True，则 index 为 base 之后的完整 OID 后缀（用于多段索引的表如 LLDP）。
    """
    engine = SnmpEngine()
    community_data, user_data = _get_auth(device_info)
    transport = await UdpTransportTarget.create(
        (ip, port),
        timeout=settings.collect_timeout_seconds,
        retries=settings.collect_retry_times,
    )
    ctx = ContextData()

    results = []
    auth_param = community_data or user_data

    try:
        # GETNEXT 起始 OID
        current_oid = oid
        for _ in range(max_index):
            err_indication, err_status, err_idx, var_binds = await next_cmd(
                engine,
                auth_param,
                transport,
                ctx,
                ObjectType(ObjectIdentity(current_oid)),
            )

            if err_indication or err_status:
                break

            found = False
            for var_bind in var_binds:
                oid_obj = var_bind[0]
                val = var_bind[1]
                oid_str = str(oid_obj)

                # 检查是否还在该子树内（OID 必须以目标 OID 为前缀）
                if not oid_str.startswith(oid + "."):
                    # 已经走出该子树，结束 walk
                    found = True
                    break

                if val is not None:
                    if return_full_oid:
                        idx = oid_str[len(oid) + 1:]  # base 之后的全索引（如 "1.2.3"）
                    else:
                        idx = oid_str.rsplit(".", 1)[-1]  # 兼容：只取末段
                    results.append((idx, str(val)))

                # 更新下一个 GETNEXT 的起始 OID
                current_oid = oid_str
                found = True

            if not found:
                break

            # 防止无限循环（异常情况下 current_oid 没变）
            if len(results) >= max_index:
                break

    except Exception as e:
        logger.warning(f"SNMP WALK {oid} @ {ip} 异常: {e}")

    return results


def _parse_cpu(processor_loads: list[tuple]) -> float:
    """从 hrProcessorLoad 表计算 CPU 平均使用率 (%)"""
    if not processor_loads:
        return 0.0
    values = [float(v[1]) for v in processor_loads if v[1].isdigit() or (v[1].lstrip("-").replace(".", "").isdigit())]
    return sum(values) / len(values) if values else 0.0


def _parse_memory(storage_table: list[tuple], storage_types: list[tuple]) -> float:
    """从 hrStorage 计算内存使用率 (%)"""
    # 物理内存的 hrStorageType OID 是 1.3.6.1.2.1.25.2.1.2 (hrStorageRam)
    ram_type_oid = "1.3.6.1.2.1.25.2.1.2"

    type_map = {}
    for idx, stype in storage_types:
        type_map[idx] = stype.strip(".")

    used_map = {}
    size_map = {}

    # 这里简化处理：取第一个物理内存条目
    # 实际应匹配 type_map 中为 RAM 的索引
    # MVP 简化：假设第一个存储条目就是内存
    total_used = 0
    total_size = 0

    for idx, used in storage_table:
        try:
            total_used += int(used)
        except (ValueError, TypeError):
            pass

    for idx, size in storage_table:
        try:
            total_size += int(size)
        except (ValueError, TypeError):
            pass

    if total_size == 0:
        return 0.0

    return round((total_used / total_size) * 100, 2)


async def _collect_cpu(ip: str, port: int, vendor: str, device_info: dict) -> float:
    """
    采集 CPU 使用率 (%)。
    策略：
      华为：优先 hwCpuDevDuty (HUAWEI-CPU-MIB) — 返回各核/各板占用率，取 **最大值**
           （因为 display cpu-usage 显示的整机 CPU ≈ 最繁忙核心的负载）
           → 回退 hwEntityCpuUsage (HUAWEI-ENTITY-EXTENT-MIB)
      其他：厂商私有 OID → 回退 hrProcessorLoad → 0
    """
    vendor_oids = VENDOR_OIDS.get(vendor)

    # 华为：优先 hwCpuDevDuty（多核多板设备，取最大值代表整机负载）
    if vendor == "huawei" and vendor_oids:
        for key in ("cpu_usage", "cpu_usage_entity"):
            oid = vendor_oids.get(key)
            if not oid:
                continue
            try:
                raw = await _snmp_walk(ip, port, oid, device_info)
                values = [float(v[1]) for v in raw if v[1].lstrip("-").replace(".", "").isdigit()]
                vals = [v for v in values if 0 <= v <= 100]
                if vals:
                    # 华为多核设备：取最大值（≈ display cpu-usage 整机值）
                    result = max(vals)
                    # 如果最大值也过低（<1）且还有下一个策略可尝试，继续
                    if result < 1 and key == "cpu_usage_entity":
                        continue
                    logger.debug(f"{ip} CPU ({key}): {vals} → max={result:.1f}%")
                    return result
            except Exception as e:
                logger.debug(f"{ip} 华为 CPU OID {key} 失败: {e}")

    # 其他厂商 / 通用：厂商私有 OID（取均值）
    if vendor_oids and "cpu_usage" in vendor_oids:
        try:
            cpu_raw = await _snmp_walk(ip, port, vendor_oids["cpu_usage"], device_info)
            if cpu_raw:
                values = [float(v[1]) for v in cpu_raw if v[1].lstrip("-").replace(".", "").isdigit()]
                vals = [v for v in values if 0 <= v <= 100]
                if vals:
                    logger.debug(f"{ip} CPU (vendor): {vals}")
                    return sum(vals) / len(vals)
        except Exception as e:
            logger.debug(f"{ip} 厂商 CPU OID 失败: {e}")

    # 回退标准 HOST-RESOURCES-MIB
    try:
        cpu_raw = await _snmp_walk(ip, port, STANDARD_OIDS["hrProcessorLoad"], device_info)
        cpu_usage = _parse_cpu(cpu_raw)
        if cpu_usage > 0:
            logger.debug(f"{ip} CPU (hrProcessorLoad): {cpu_usage}")
            return cpu_usage
    except Exception as e:
        logger.debug(f"{ip} 标准 CPU OID 失败: {e}")

    return 0.0


async def _collect_memory(ip: str, port: int, vendor: str, device_info: dict) -> float:
    """
    采集内存使用率 (%)。
    策略：
      华为：优先 hwMemoryDevTable (WALK used/total 计算, 对 S7700/S5700/S6700 均有效)
           → hwEntityMemUsage 仅作为辅助验证（若 hwMemoryDevTable 无数据时尝试）
      其他：厂商私有 OID → 回退 hrStorage → 0
    """
    vendor_oids = VENDOR_OIDS.get(vendor)

    if vendor == "huawei" and vendor_oids:
        # 1) 主策略：hwMemoryDevTable（HUAWEI-MEMORY-MIB）— 实测对 S7706 可靠
        total_oid = vendor_oids.get("mem_total")
        free_oid = vendor_oids.get("mem_free")
        if total_oid and free_oid:
            try:
                total_raw = await _snmp_walk(ip, port, total_oid, device_info)
                free_raw = await _snmp_walk(ip, port, free_oid, device_info)
                totals = [float(v[1]) for v in total_raw if v[1].replace(".", "").isdigit()]
                frees = [float(v[1]) for v in free_raw if v[1].replace(".", "").isdigit()]
                if totals:
                    sum_total = sum(totals)
                    sum_free = sum(frees) if frees else 0
                    used = sum_total - sum_free
                    if sum_total > 0:
                        usage = round((used / sum_total) * 100, 2)
                        logger.debug(f"{ip} 内存 (hwMemoryDevTable): used={used/1024/1024:.0f}MB total={sum_total/1024/1024:.0f}MB = {usage}%")
                        return usage
            except Exception as e:
                logger.debug(f"{ip} 华为内存 hwMemoryDevTable 失败: {e}")

        # 2) 辅助：hwEntityMemUsage（部分新固件支持，但 S7706 返回全 0）
        oid = vendor_oids.get("mem_usage_entity")
        if oid:
            try:
                raw = await _snmp_walk(ip, port, oid, device_info)
                values = [float(v[1]) for v in raw if v[1].lstrip("-").replace(".", "").isdigit()]
                vals = [v for v in values if 1 <= v <= 99]  # 过滤掉 0 和异常值
                if vals:
                    avg = sum(vals) / len(vals)
                    logger.debug(f"{ip} 内存 (hwEntityMemUsage): {vals} → {avg:.1f}%")
                    return avg
            except Exception as e:
                logger.debug(f"{ip} 华为内存 hwEntityMemUsage 失败: {e}")

    # 其他厂商 / 通用：厂商私有 OID
    if vendor_oids and "mem_used" in vendor_oids and "mem_total" in vendor_oids:
        try:
            mem_used_raw = await _snmp_walk(ip, port, vendor_oids["mem_used"], device_info)
            mem_total_raw = await _snmp_walk(ip, port, vendor_oids["mem_total"], device_info)
            used_vals = [float(v[1]) for v in mem_used_raw if v[1].replace(".", "").isdigit()]
            total_vals = [float(v[1]) for v in mem_total_raw if v[1].replace(".", "").isdigit()]
            if used_vals and total_vals:
                usage_pct = round((sum(used_vals) / sum(total_vals)) * 100, 2)
                logger.debug(f"{ip} 内存 (vendor): {usage_pct}%")
                return usage_pct
        except Exception as e:
            logger.debug(f"{ip} 厂商内存 OID 失败: {e}")

    # 回退标准 HOST-RESOURCES-MIB
    try:
        mem_type = await _snmp_walk(ip, port, STANDARD_OIDS["hrStorageType"], device_info)
        mem_used = await _snmp_walk(ip, port, STANDARD_OIDS["hrStorageUsed"], device_info)
        mem_size = await _snmp_walk(ip, port, STANDARD_OIDS["hrStorageSize"], device_info)
        usage_pct = _parse_memory(mem_used, mem_type)
        if usage_pct > 0:
            logger.debug(f"{ip} 内存 (hrStorage): {usage_pct}%")
            return usage_pct
    except Exception as e:
        logger.debug(f"{ip} 标准内存 OID 失败: {e}")

    return 0.0


def _extract_model(sys_descr: str, ent_descr: str = "", sys_object_id: str = "") -> Optional[str]:
    """
    从 sysDescr / entPhysicalDescr / sysObjectID 提取干净的设备型号。
    例如 sysDescr='Huawei Versatile Routing Platform Software ... Quidway S7700 ...'
    提取出 'S7700'。若无匹配则返回 None。
    """
    import re
    text = (ent_descr or "").strip() or (sys_descr or "").strip()
    if not text:
        return None
    for pat in MODEL_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(0).strip()
    return None


async def collect_device_metrics(device_info: dict) -> list[dict]:
    """
    采集单台设备的所有指标。

    Args:
        device_info: 设备信息字典，需包含 ip, snmp_port, snmp_version, vendor 等

    Returns:
        指标列表，每项格式：
        {
            "metric_name": "snmp_xxx",
            "value": float,
            "labels": {"device": "...", ...},
            "timestamp": int (epoch seconds),
        }
    """
    ip = device_info["ip"]
    port = device_info.get("snmp_port", 161)
    vendor = device_info.get("vendor", "generic")
    device_name = device_info.get("name", ip)

    import time
    now_ts = int(time.time())
    metrics = []

    try:
        # ---- 1. 采集系统信息（标量） ----
        sys_oids = {
            k: v for k, v in STANDARD_OIDS.items()
            if k in ("sysName", "sysDescr", "sysUpTime")
        }
        sys_data = await _snmp_get(ip, port, sys_oids, device_info)

        if not sys_data:
            logger.warning(f"设备 {ip} 无响应（系统信息获取失败）")
            return []

        # ---- 2. 采集 CPU（优先厂商私有 OID，回退标准 OID） ----
        cpu_usage = await _collect_cpu(ip, port, vendor, device_info)
        # 用 -1 标记"设备不支持此指标"，与真正的 0% 区分
        metrics.append({
            "metric_name": "snmp_cpu_usage_percent",
            "value": round(cpu_usage, 2) if cpu_usage > 0 else -1,
            "labels": {"device": device_name, "ip": ip},
            "timestamp": now_ts,
        })

        # ---- 3. 采集内存（优先厂商私有 OID，回退标准 OID） ----
        mem_usage = await _collect_memory(ip, port, vendor, device_info)
        metrics.append({
            "metric_name": "snmp_memory_usage_percent",
            "value": mem_usage if mem_usage > 0 else -1,
            "labels": {"device": device_name, "ip": ip},
            "timestamp": now_ts,
        })

        # ---- 4. 采集接口表（ifXTable）----
        if_names = await _snmp_walk(ip, port, STANDARD_OIDS["ifName"], device_info)
        if_oper = await _snmp_walk(ip, port, STANDARD_OIDS["ifOperStatus"], device_info)
        if_hc_in = await _snmp_walk(ip, port, STANDARD_OIDS["ifHCInOctets"], device_info)
        if_hc_out = await _snmp_walk(ip, port, STANDARD_OIDS["ifHCOutOctets"], device_info)
        if_high_speed = await _snmp_walk(ip, port, STANDARD_OIDS["ifHighSpeed"], device_info)
        if_in_err = await _snmp_walk(ip, port, STANDARD_OIDS["ifInErrors"], device_info)
        if_out_err = await _snmp_walk(ip, port, STANDARD_OIDS["ifOutErrors"], device_info)

        # 构建接口索引 → 值 的映射
        def build_map(raw_list):
            m = {}
            for idx, val in raw_list:
                m[idx] = val
            return m

        name_map = build_map(if_names)
        oper_map = build_map(if_oper)
        hc_in_map = build_map(if_hc_in)
        hc_out_map = build_map(if_hc_out)
        speed_map = build_map(if_high_speed)
        in_err_map = build_map(if_in_err)
        out_err_map = build_map(if_out_err)

        for idx, if_name in name_map.items():
            labels_base = {"device": device_name, "ip": ip, "ifIndex": idx, "ifName": if_name}

            # 接口状态
            oper_val = oper_map.get(idx, "0")
            metrics.append({
                "metric_name": "snmp_interface_oper_status",
                "value": int(oper_val) if oper_val.isdigit() else 0,
                "labels": dict(labels_base),
                "timestamp": now_ts,
            })

            # 接口速率（64位计数器的原始值，VM 用 rate() 计算 bps）
            hc_in_val = hc_in_map.get(idx, "0")
            hc_out_val = hc_out_map.get(idx, "0")

            metrics.append({
                "metric_name": "snmp_if_hc_in_octets",
                "value": float(hc_in_val) if hc_in_val.isdigit() else 0,
                "labels": dict(labels_base),
                "timestamp": now_ts,
            })
            metrics.append({
                "metric_name": "snmp_if_hc_out_octets",
                "value": float(hc_out_val) if hc_out_val.isdigit() else 0,
                "labels": dict(labels_base),
                "timestamp": now_ts,
            })

            # 接口带宽（Mbps）
            speed_val = speed_map.get(idx, "0")
            metrics.append({
                "metric_name": "snmp_interface_high_speed_mbps",
                "value": float(speed_val) if speed_val.replace(".", "").isdigit() else 0,
                "labels": dict(labels_base),
                "timestamp": now_ts,
            })

            # 错包数
            in_e = in_err_map.get(idx, "0")
            out_e = out_err_map.get(idx, "0")
            metrics.append({
                "metric_name": "snmp_interface_in_errors",
                "value": float(in_e) if in_e.isdigit() else 0,
                "labels": dict(labels_base),
                "timestamp": now_ts,
            })
            metrics.append({
                "metric_name": "snmp_interface_out_errors",
                "value": float(out_e) if out_e.isdigit() else 0,
                "labels": dict(labels_base),
                "timestamp": now_ts,
            })

        logger.info(f"设备 {device_name}({ip}) 采集完成: {len(metrics)} 个指标")
        return metrics

    except Exception as e:
        logger.error(f"采集设备 {ip} 失败: {e}", exc_info=True)
        return []


async def test_connectivity_progress(device_info: dict):
    """
    测试设备连通性的分阶段进度生成器（供 SSE 流式返回）。
    每个阶段 yield 一个 dict: {stage, status, message, progress, detail}
    status: pending | running | success | failed
    """
    ip = device_info["ip"]
    port = device_info.get("snmp_port", 161)
    vendor = device_info.get("vendor", "generic")
    device_name = device_info.get("name", ip)

    stages = [
        ("connect", "建立 SNMP 连接", "正在向设备发送 SNMP 请求..."),
        ("sysinfo", "采集系统信息", "读取 sysName / sysDescr..."),
        ("interfaces", "采集接口表", "遍历 ifXTable 接口信息..."),
        ("finish", "完成", "测试结束"),
    ]

    def emit(stage_key, status, message, progress, detail=None):
        return {
            "stage": stage_key,
            "status": status,
            "message": message,
            "progress": progress,
            "detail": detail or {},
        }

    # 阶段 1：连接测试（短超时，快速失败）
    yield emit("connect", "running", stages[0][2], 10)
    engine = SnmpEngine()
    community_data, user_data = _get_auth(device_info)
    auth_param = community_data or user_data
    try:
        transport = await UdpTransportTarget.create((ip, port), timeout=5, retries=1)
    except Exception as e:
        yield emit("connect", "failed", f"无法创建传输通道: {e}", 10, {"error": str(e)})
        yield emit("finish", "failed", "连接失败：网络不可达", 100, {"error": "transport_create_failed"})
        return

    ctx = ContextData()
    try:
        err_ind, err_status, err_idx, var_binds = await get_cmd(
            engine, auth_param, transport, ctx,
            ObjectType(ObjectIdentity("1.3.6.1.2.1.1.5.0")),  # sysName
        )
        if err_ind:
            yield emit("connect", "failed", f"SNMP 无响应: {err_ind}", 10,
                       {"error": str(err_ind), "hint": "请检查设备 IP、SNMP 端口、community 是否正确，或设备是否放行本机 IP 的 SNMP 访问"})
            yield emit("finish", "failed", "连接失败", 100, {"error": "snmp_timeout"})
            return
        if err_status:
            yield emit("connect", "failed", f"SNMP 错误: {err_status.prettyPrint()}", 10,
                       {"error": err_status.prettyPrint()})
            yield emit("finish", "failed", "连接失败", 100, {"error": "snmp_error"})
            return
        sys_name = str(var_binds[0][1]) if var_binds else "未知"
        yield emit("connect", "success", f"连接成功，设备名: {sys_name}", 35, {"sysName": sys_name})
    except Exception as e:
        yield emit("connect", "failed", f"异常: {e}", 10, {"error": str(e)})
        yield emit("finish", "failed", "连接失败", 100, {"error": "exception"})
        return

    # 阶段 2：系统信息
    yield emit("sysinfo", "running", stages[1][2], 50)
    sysinfo_ok = True
    discovered = {}
    try:
        get_oids = {
            "sysDescr": STANDARD_OIDS["sysDescr"],
            "sysUpTime": STANDARD_OIDS["sysUpTime"],
            "sysObjectID": STANDARD_OIDS["sysObjectID"],
        }
        # 华为额外取 entPhysicalDescr（用于提取干净型号）
        if vendor == "huawei":
            get_oids["entPhysicalDescr"] = VENDOR_OIDS["huawei"]["entPhysicalDescr"]

        sys_data = await _snmp_get(ip, port, get_oids, device_info)
        descr = sys_data.get("sysDescr", "")[:80]
        uptime = sys_data.get("sysUpTime", "")
        sys_object_id = sys_data.get("sysObjectID", "").strip(".")
        ent_descr = sys_data.get("entPhysicalDescr", "")

        # 解析厂商
        discovered_vendor = None
        for prefix, v in SYS_OBJECT_ID_PREFIX_MAP.items():
            if sys_object_id.startswith(prefix):
                discovered_vendor = v
                break
        # 若 sysObjectID 未识别但厂商字段已指定，则以指定为准
        if not discovered_vendor and vendor and vendor != "generic":
            discovered_vendor = vendor

        # 提取干净型号
        discovered_model = _extract_model(descr, ent_descr, sys_object_id)
        discovered = {
            "vendor": discovered_vendor,
            "model": discovered_model or (descr if not discovered_vendor else None),
            "sysObjectID": sys_object_id,
        }
        yield emit("sysinfo", "success", f"系统信息获取成功", 70,
                   {"sysDescr": descr, "sysUpTime": uptime, "sysObjectID": sys_object_id,
                    "model": discovered_model})
    except Exception as e:
        sysinfo_ok = False
        yield emit("sysinfo", "failed", f"系统信息采集异常: {e}", 70, {"error": str(e)})
        # 不致命，继续

    # 阶段 3：接口表
    yield emit("interfaces", "running", stages[2][2], 80)
    interfaces_ok = True
    try:
        if_names = await _snmp_walk(ip, port, STANDARD_OIDS["ifName"], device_info)
        if_count = len(if_names)
        yield emit("interfaces", "success", f"发现 {if_count} 个接口", 95,
                   {"interface_count": if_count, "sample": [v[1] for v in if_names[:5]]})
    except Exception as e:
        interfaces_ok = False
        yield emit("interfaces", "failed", f"接口采集异常: {e}", 95, {"error": str(e)})

    # 阶段 4：完成（根据前面阶段结果决定最终状态）
    # 注意：如果 connect 阶段已经 failed 并 return，不会走到这里
    has_partial_failure = not (sysinfo_ok and interfaces_ok)
    if has_partial_failure:
        yield emit("finish", "failed", "测试完成，部分项目失败", 100,
                   {"ip": ip, "vendor": vendor, "device": device_name, "discovered": discovered})
    else:
        yield emit("finish", "success", "设备在线，连接成功", 100,
                   {"ip": ip, "vendor": vendor, "device": device_name, "discovered": discovered})
