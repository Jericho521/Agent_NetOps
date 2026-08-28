"""
厂商 OID 模板定义
以 JSON 格式存储各厂商私有 MIB 的 OID 映射，方便后续扩展。
MVP 阶段主要依赖标准 MIB（HOST-RESOURCES / IF-MIB / IF-X-MIB），此处预留扩展点。
"""

TEMPLATES = {
    "generic": {
        "description": "通用标准 MIB 模板（IF-MIB / HOST-RESOURCES-MIB / IF-X-MIB）",
        "cpu_oid": "1.3.6.1.2.1.25.3.3.1.2",       # hrProcessorLoad
        "memory_used_oid": "1.3.6.1.2.1.25.2.3.1.5",  # hrStorageUsed
        "memory_total_oid": "1.3.6.1.2.1.25.2.3.1.4", # hrStorageSize
        "cpu_calc": "avg",                               # 多核取平均
    },

    "huawei_vrp": {
        "description": "华为 VRP 私有 MIB（HUAWEI-CPU-MIB / HUAWEI-MEMORY-MIB）",
        "extends": "generic",
        "cpu_oid": "1.3.6.1.4.1.2011.6.3.4.1",         # hwCpuDevUsage (华为私有)
        "memory_oid": "1.3.6.1.4.1.2011.6.3.5.1.1",    # hwMemDevUsage (华为私有)
        "note": "优先使用私有 OID，回退到标准 MIB",
    },

    "h3c_comware": {
        "description": "H3C Comware 私有 MIB",
        "extends": "generic",
        "cpu_oid": "1.3.6.1.4.1.25506.1.60.1.1.1.1",  # hh3cEntityExtCpuUsage
        "memory_oid": "1.3.6.1.4.1.25506.1.60.1.1.1.2", # hh3cEntityExtMemUsage
        "note": "H3C MSR36 / S 系列交换机适用",
    },
}


def get_template(vendor: str) -> dict:
    """
    获取指定厂商的 OID 模板。
    如果找不到精确匹配，返回 generic 模板。
    """
    vendor_key = vendor.lower().strip() if vendor else "generic"
    return TEMPLATES.get(vendor_key, TEMPLATES["generic"])
