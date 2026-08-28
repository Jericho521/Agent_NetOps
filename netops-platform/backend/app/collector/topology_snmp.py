"""
拓扑邻居采集 - 通过 LLDP / CDP 自动发现设备间的连接关系
依赖 pysnmp 异步采集（复用 snmp.py 的 _snmp_walk）
"""
import logging
import re
from typing import Optional

from app.collector.snmp import _snmp_get, _snmp_walk, STANDARD_OIDS

logger = logging.getLogger(__name__)

# 设备自身 sysName（SNMPv2-MIB）
OID_SYS_NAME = STANDARD_OIDS["sysName"]

# LLDP-MIB: lldpRemTable 列（1.0.8802.1.1.2.1.4.1.1）
# 注意：lldpRemLocalPortId(.7) 与 lldpRemPortId(.4) 多为二进制/十六进制编码，
# 不可读；优先使用 *_Desc 文本列（.8 本端端口描述 / .6 对端端口描述）。
OID_LLDP_REM_SYSNAME = "1.0.8802.1.1.2.1.4.1.1.9"      # 对端系统名
OID_LLDP_REM_PORTDESC = "1.0.8802.1.1.2.1.4.1.1.6"     # 对端端口描述（可读文本）
OID_LLDP_REM_LOCALPORTDESC = "1.0.8802.1.1.2.1.4.1.1.8"  # 本端端口描述（可读文本）
OID_LLDP_REM_MAN_ADDR = "1.0.8802.1.1.2.1.4.1.1.10"    # 对端管理地址（子树下）

# CISCO-CDP-MIB: cdpCacheEntry 列（1.3.6.1.4.1.9.9.23.1.2.1.1）
OID_CDP_CACHE_DEVICEID = "1.3.6.1.4.1.9.9.23.1.2.1.1.6"   # 对端设备名
OID_CDP_CACHE_DEVICEPORT = "1.3.6.1.4.1.9.9.23.1.2.1.1.7" # 对端端口
OID_CDP_CACHE_IFINDEX = "1.3.6.1.4.1.9.9.23.1.2.1.1.3"    # 本端 ifIndex
OID_CDP_CACHE_ADDRESS = "1.3.6.1.4.1.9.9.23.1.2.1.1.4"    # 对端管理地址

# 聚合口/LAG 端口名称匹配模式（华为 Eth-Trunk、H3C AggregatePort、Cisco Port-Channel 等）
LAG_PORT_PATTERN = re.compile(
    r'(?i)^(Eth-Trunk|Trunk|Aggregate|Port-Channel|Po|Bundle-Ether|LAG)\s*\d+'
)

# 堆叠/集群互联口模式：通过这些业务口学到的 LLDP 邻居通常是"自己"（对端就是本机另一成员），
# 应排除，避免一台堆叠设备自己连自己的假链路。
# 覆盖：华为 Stack-Port / StackPort / 堆叠逻辑口；H3C Bridge-Aggregation(堆叠) / Ten-GigabitEthernet 堆叠口；
#       Cisco StackWise Port / Switch(虚拟) / StackPort；以及含"堆叠"关键字的端口。
STACK_PORT_PATTERN = re.compile(
    r'(?i)(stack-?port|stackport|bridge-aggregation|sw[0-9]+/-|switch\s*\d+|堆叠|cluster-port|css-port|istack)'
)


async def _try_walk(ip: str, port: int, oid: str, device_info: dict) -> list:
    """封装 _snmp_walk（return_full_oid=True），失败时返回空列表。"""
    try:
        return await _snmp_walk(ip, port, oid, device_info, max_index=400, return_full_oid=True)
    except Exception as e:
        logger.debug(f"WALK {oid} on {ip} 失败: {e}")
        return []


def _index_parts(full_suffix: str) -> tuple:
    """将完整索引后缀（如 "1.2.3"）按 '.' 分割为元组。"""
    if not full_suffix:
        return tuple()
    return tuple(full_suffix.split("."))


async def collect_lldp_neighbors(device_info: dict) -> list[dict]:
    """采集 LLDP 邻居。返回 [{"local_port","remote_sysname","remote_port","remote_ip"}]"""
    ip = device_info["ip"]
    port = device_info.get("snmp_port", 161)
    neighbors: list[dict] = []

    sysnames = await _try_walk(ip, port, OID_LLDP_REM_SYSNAME, device_info)
    if not sysnames:
        return neighbors

    localdescs = await _try_walk(ip, port, OID_LLDP_REM_LOCALPORTDESC, device_info)
    portdescs = await _try_walk(ip, port, OID_LLDP_REM_PORTDESC, device_info)
    # Fallback：若 LocalPortDesc 为空，尝试读 LocalPortId（可能不可读但有值）
    if not localdescs:
        localids = await _try_walk(ip, port, "1.0.8802.1.1.2.1.4.1.1.7", device_info)

    # 按索引三段 (timemark, localportnum, msap) 组织
    by_index: dict[tuple, dict] = {}
    for oid, val in sysnames:
        idx = _index_parts(oid)
        by_index.setdefault(idx, {})["remote_sysname"] = str(val)
    for oid, val in localdescs:
        idx = _index_parts(oid)
        by_index.setdefault(idx, {})["local_port"] = str(val)
    # Fallback：用 localids 填充缺少 local_port 的条目
    if not localdescs and 'localids' in dir():
        for oid, val in localids:
            idx = _index_parts(oid)
            by_index.setdefault(idx, {}).setdefault("local_port", str(val))
    for oid, val in portdescs:
        idx = _index_parts(oid)
        by_index.setdefault(idx, {})["remote_port"] = str(val)

    self_name = (device_info.get("sys_name") or "").strip().lower()
    for idx, info in by_index.items():
        if "remote_sysname" not in info or not info["remote_sysname"]:
            continue
        local_port = (info.get("local_port") or "").strip()
        remote_port = (info.get("remote_port") or "").strip()
        remote_sysname = info["remote_sysname"].strip()
        # 过滤：通过堆叠业务口学到的、且对端就是自己(sysName 相同)的邻居
        # → 这是堆叠设备成员间内部互联，不应画成"自己连自己"的假链路
        if self_name and remote_sysname.lower() == self_name and STACK_PORT_PATTERN.search(local_port):
            logger.info(
                "跳过堆叠口自连邻居: %s local_port=%s remote=%s",
                device_info.get("ip"), local_port, remote_sysname,
            )
            continue
        neighbors.append({
            "protocol": "lldp",
            "local_port": local_port,
            "remote_sysname": remote_sysname,
            "remote_port": remote_port,
            "remote_ip": None,
            "link_type": "lag" if LAG_PORT_PATTERN.match(local_port) else "unknown",
        })
    return neighbors


async def collect_cdp_neighbors(device_info: dict) -> list[dict]:
    """采集 CDP 邻居。返回 [{"local_port","remote_sysname","remote_port","remote_ip"}]"""
    ip = device_info["ip"]
    port = device_info.get("snmp_port", 161)
    neighbors: list[dict] = []

    device_ids = await _try_walk(ip, port, OID_CDP_CACHE_DEVICEID, device_info)
    if not device_ids:
        return neighbors

    device_ports = await _try_walk(ip, port, OID_CDP_CACHE_DEVICEPORT, device_info)
    if_indexes = await _try_walk(ip, port, OID_CDP_CACHE_IFINDEX, device_info)
    addresses = await _try_walk(ip, port, OID_CDP_CACHE_ADDRESS, device_info)

    # 本地端口: ifIndex → ifName
    if_names = await _try_walk(ip, port, "1.3.6.1.2.1.31.1.1.1.1", device_info)
    ifname_map = {_index_parts(oid)[-1]: str(val) for oid, val in if_names}

    # 索引: cdpCacheEntry 索引为 (ifIndex, deviceIndex)
    by_index: dict[tuple, dict] = {}
    for oid, val in device_ids:
        idx = _index_parts(oid)
        by_index.setdefault(idx, {})["remote_sysname"] = str(val)
    for oid, val in device_ports:
        idx = _index_parts(oid)
        by_index.setdefault(idx, {})["remote_port"] = str(val)
    for oid, val in if_indexes:
        idx = _index_parts(oid)
        by_index.setdefault(idx, {})["_local_ifindex"] = str(val)
    for oid, val in addresses:
        idx = _index_parts(oid)
        # CDP 地址索引比设备索引多一段（地址子类型），取前两段对齐
        dev_idx = idx[:2]
        by_index.setdefault(dev_idx, {})["remote_ip"] = _normalize_ip(val)

    for idx, info in by_index.items():
        if "remote_sysname" not in info or not info["remote_sysname"]:
            continue
        local_ifindex = info.get("_local_ifindex", "")
        local_port = ifname_map.get(local_ifindex, local_ifindex)
        neighbors.append({
            "protocol": "cdp",
            "local_port": local_port or "",
            "remote_sysname": info["remote_sysname"].strip(),
            "remote_port": info.get("remote_port") or "",
            "remote_ip": info.get("remote_ip"),
        })
    return neighbors


def _normalize_ip(raw) -> Optional[str]:
    """CDP 管理地址可能是 4 字节（IPv4）或 16 字节（IPv6），这里只解析 IPv4。"""
    try:
        b = bytes(raw) if not isinstance(raw, bytes) else raw
    except Exception:
        return str(raw)
    if len(b) == 4:
        return ".".join(str(x) for x in b)
    return None


async def collect_topology_neighbors(device_info: dict) -> list[dict]:
    """优先 LLDP，其次 CDP，合并返回邻居列表。"""
    neighbors = await collect_lldp_neighbors(device_info)
    if not neighbors:
        neighbors = await collect_cdp_neighbors(device_info)
    return neighbors


async def collect_device_sysname(device_info: dict) -> Optional[str]:
    """采集设备自身的 sysName（SNMPv2-MIB 1.3.6.1.2.1.1.5.0）。

    注意：device_info 必须包含正确的 community / auth_password 等认证字段，
    否则 SNMP GET 会因无响应而超时。
    """
    ip = device_info["ip"]
    port = device_info.get("snmp_port", 161)
    try:
        # 确保认证字段存在，避免 _get_auth 拿到空 community 导致超时
        if not device_info.get("community") and not device_info.get("auth_password"):
            logger.warning(f"采集 {ip} sysName 跳过：缺少 SNMP 认证信息")
            return None
        result = await _snmp_get(ip, port, {"sysName": OID_SYS_NAME}, device_info)
        name = result.get("sysName")
        if name:
            return str(name).strip()
    except Exception as e:
        logger.debug(f"采集 {ip} sysName 失败: {e}")
    return None
