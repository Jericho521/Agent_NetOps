"""
MCP Server 骨架 - 暴露 list_devices / get_device_metrics 工具
供后续 LLM Agent 通过 MCP 协议调用平台能力。
当前为 stdio 模式骨架，未对接真实 LLM。
"""
import json
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

# 创建 MCP 实例
mcp = FastMCP("NetOps Platform")


@mcp.tool()
async def list_devices(
    vendor: str | None = None,
    role: str | None = None,
    status: str | None = None,
) -> str:
    """
    列出平台中已注册的网络设备。

    Args:
        vendor: 可选，按厂商过滤（如 huawei、h3c）
        role: 可选，按角色过滤（如 switch、router、firewall）
        status: 可选，按状态过滤（online、offline、error）

    Returns:
        JSON 字符串格式的设备列表
    """
    from sqlalchemy import select
    from app.db import async_session
    from app.models import Device

    async with async_session() as session:
        query = select(Device)
        if vendor:
            query = query.where(Device.vendor.ilike(f"%{vendor}%"))
        if role:
            query = query.where(Device.role == role)
        if status:
            query = query.where(Device.status == status)

        result = await session.execute(query)
        devices = result.scalars().all()

        device_list = []
        for d in devices:
            device_list.append({
                "id": d.id,
                "name": d.name,
                "ip": d.ip,
                "vendor": d.vendor,
                "role": d.role,
                "model": d.model,
                "status": d.status,
                "snmp_version": f"v{d.snmp_version}",
                "last_seen": d.last_seen_at.isoformat() if d.last_seen_at else None,
            })

        return json.dumps(device_list, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_device_metrics(
    device_id: str | None = None,
    device_name: str | None = None,
    metric_names: str = "snmp_cpu_usage_percent,snmp_memory_usage_percent",
    range_hours: int = 1,
) -> str:
    """
    查询设备的监控指标数据。

    Args:
        device_id: 设备 ID（与 device_name 二选一）
        device_name: 设备名称（与 device_id 二选一）
        metric_names: 逗号分隔的指标名列表
        range_hours: 时间范围（小时），默认 1 小时

    Returns:
        JSON 字符串格式的指标数据
    """
    from sqlalchemy import select
    from app.db import async_session
    from app.models import Device
    from app.collector.victoriametrics import query_vm_range

    # 查找设备
    async with async_session() as session:
        if device_id:
            result = await session.execute(select(Device).where(Device.id == device_id))
        elif device_name:
            result = await session.execute(select(Device).where(Device.name == device_name))
        else:
            return json.dumps({"error": "必须提供 device_id 或 device_name"}, ensure_ascii=False)

        device = result.scalar_one_or_none()
        if not device:
            return json.dumps({"error": "设备不存在"}, ensure_ascii=False)

    # 查询各指标
    metrics = [m.strip() for m in metric_names.split(",") if m.strip()]
    results = {}

    for metric_name in metrics:
        promql = f'{metric_name}{{device="{device.name}"}}'
        data = await query_vm_range(promql, range_hours=range_hours, step=60)

        series_list = []
        for item in data or []:
            labels = item.get("metric", {})
            values = [
                {"timestamp": v[0], "value": v[1]}
                for v in item.get("values", [])
            ]
            series_list.append({"labels": labels, "values": values})

        results[metric_name] = {
            "device": device.name,
            "series_count": len(series_list),
            "data": series_list,
        }

    return json.dumps(results, ensure_ascii=False, indent=2)


def run_mcp_server():
    """启动 MCP Server（stdio 模式）"""
    logger.info("启动 NetOps MCP Server (stdio 模式)...")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run_mcp_server()
