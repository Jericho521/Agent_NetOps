"""广泛测试华为 CPU OID"""
import asyncio
from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine, CommunityData, UdpTransportTarget,
    ContextData, get_cmd, next_cmd,
)
from pysnmp.smi.rfc1902 import ObjectType, ObjectIdentity

TARGET = "10.1.100.2"
COMMUNITY = "Read102419"
TIMEOUT = 5
RETRIES = 2

async def snmp_get(oid: str) -> str:
    engine = SnmpEngine()
    cd = CommunityData(COMMUNITY, mpModel=1)
    t = await UdpTransportTarget.create((TARGET, 161), timeout=TIMEOUT, retries=RETRIES)
    ctx = ContextData()
    err_ind, err_st, err_idx, var_binds = await get_cmd(engine, cd, t, ctx, ObjectType(ObjectIdentity(oid)))
    if err_ind: return f"ERROR: {err_ind}"
    for vb in var_binds:
        return str(vb[1]) if vb[1] is not None else "NULL"
    return "NO_DATA"

async def snmp_walk(oid_root: str, max_count=20):
    engine = SnmpEngine()
    cd = CommunityData(COMMUNITY, mpModel=1)
    t = await UdpTransportTarget.create((TARGET, 161), timeout=TIMEOUT, retries=RETRIES)
    ctx = ContextData()
    results = []
    vbs = [ObjectType(ObjectIdentity(oid_root))]
    while len(results) < max_count:
        (err_ind, err_st, err_idx, vbt) = await next_cmd(engine, cd, t, ctx, *vbs, lookupMib=False, lexicographicMode=False)
        if err_ind or err_st or not vbt or not vbt[0]: break
        for vb in vbt[0]:
            oid_str = str(vb[0])
            if not oid_str.startswith(oid_root): return results
            results.append(f"{vb[0]} = {vb[1]}")
            if len(results) >= max_count: return results
        vbs = vbt[0]
    return results

async def main():
    oids_to_test = [
        ("hwCpuDevDuty", "1.3.6.1.4.1.2011.6.1.2.1.2.1"),
        ("hwCpuUsage", "1.3.6.1.4.1.2011.6.1.2.1.1.11"),
        ("hwEntityCpuUsage", "1.3.6.1.4.1.2011.5.3.1.10"),
        ("hwCpuMemStatCpuFreeRate", "1.3.6.1.4.1.2011.6.3.4.1.2"),
        ("entPhysicalDescr (entity)", "1.3.6.1.2.1.47.1.1.1.1.2"),
        ("entPhyClass (CPU=cpu?)", "1.3.6.1.2.1.47.1.1.1.1.5"),
        # 华为 eKitEngine 特有
        ("eKitCpuUsage", "1.3.6.1.4.1.2011.6.163.1.1.1.1"),
        # 通用
        ("ssCpuRawUser", "1.3.6.1.4.1.2021.11.50.0"),
        ("ssCpuRawSystem", "1.3.6.1.4.1.2021.11.52.0"),
        ("ssCpuRawIdle", "1.3.6.1.4.1.2021.11.53.0"),
    ]

    print("=== 广泛 CPU OID 测试 ===\n")
    for name, oid in oids_to_test:
        try:
            rows = await snmp_walk(oid, 5)
            status = f"({len(rows)} 条)" if rows else "(空)"
            print(f"  [{status}] {name} ({oid})")
            for r in rows[:3]:
                print(f"       {r}")
        except Exception as e:
            print(f"  [异常] {name}: {e}")

    # 额外：直接 GET 几个单点
    print("\n=== 单点 GET ===")
    single_oids = [
        ("ssCpuRawUser", "1.3.6.1.4.1.2021.11.50.0"),
        ("ssCpuRawIdle", "1.3.6.1.4.1.2021.11.53.0"),
    ]
    for name, oid in single_oids:
        val = await snmp_get(oid)
        print(f"  {name} = {val}")

asyncio.run(main())
