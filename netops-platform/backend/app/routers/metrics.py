"""
指标查询 API - 从 VictoriaMetrics 用 PromQL 查询时序数据
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session
from app.models import Device
from app.schemas import MetricsQuery, MetricsResponse, MetricSeries, MetricDataPoint
from app.security.jwt_auth import get_current_user, User
from app.collector.victoriametrics import query_vm_range

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/query", response_model=list[MetricsResponse])
async def query_metrics(
    device_id: str = Query(..., description="设备 ID"),
    metric_names: str = Query(
        default="snmp_cpu_usage_percent,snmp_memory_usage_percent",
        description="逗号分隔的指标名列表"
    ),
    range_hours: int = Query(default=1, ge=1, le=168, description="时间范围（小时）"),
    step_seconds: int = Query(default=60, ge=10, le=3600, description="采样间隔（秒）"),
    current_user: User = Depends(get_current_user),
):
    """
    查询设备的时序指标数据。
    返回 PromQL query_range 结果，供前端 ECharts 绘制曲线图。

    常用指标名：
    - snmp_cpu_usage_percent: CPU 使用率
    - snmp_memory_usage_percent: 内存使用率
    - snmp_interface_in_bits_per_second: 接口入向速率
    - snmp_interface_out_bits_per_second: 接口出向速率
    - snmp_interface_in_errors: 接口入向错包
    - snmp_interface_out_errors: 接口出向错包
    """
    # 验证设备存在
    async with async_session() as session:
        result = await session.execute(select(Device).where(Device.id == device_id))
        device = result.scalar_one_or_none()
        if not device:
            raise HTTPException(status_code=404, detail="设备不存在")

    # 解析指标名列表
    metrics = [m.strip() for m in metric_names.split(",") if m.strip()]

    # 计数器类指标：需要 rate() 换算速率，并从字节转 bit
    COUNTER_METRICS = {
        "snmp_if_hc_in_octets", "snmp_if_hc_out_octets",
        "snmp_if_in_octets", "snmp_if_out_octets",
        "snmp_interface_in_errors", "snmp_interface_out_errors",
        "snmp_if_in_discards", "snmp_if_out_discards",
    }

    results = []
    for metric_name in metrics:
        try:
            # 构建 PromQL：按设备名过滤
            if metric_name in COUNTER_METRICS:
                # 计数器：rate() 算每秒增量，* 8 转 bps
                promql = f'rate({metric_name}{{device="{device.name}"}}[{step_seconds}s]) * 8'
            else:
                promql = f'{metric_name}{{device="{device.name}"}}'

            # 查询 VM
            vm_data = await query_vm_range(promql, range_hours=range_hours, step=step_seconds)

            if vm_data:
                series_list = []
                for item in vm_data:
                    metric_labels = item.get("metric", {})
                    values = [
                        MetricDataPoint(timestamp=v[0], value=v[1])
                        for v in item.get("values", [])
                    ]
                    series_list.append(MetricSeries(metric=metric_labels, values=values))
                results.append(MetricsResponse(metric_name=metric_name, data=series_list))
            else:
                # 无数据也返回空结构
                results.append(MetricsResponse(metric_name=metric_name, data=[]))

        except Exception as e:
            logger.error(f"查询指标 {metric_name} 失败: {e}")
            results.append(MetricsResponse(metric_name=metric_name, data=[], error=str(e)))

    return results


@router.get("/latest/{device_id}", response_model=dict)
async def get_latest_metrics(
    device_id: str,
    current_user: User = Depends(get_current_user),
):
    """获取设备最新一次采集的所有指标快照（即时查询，用于仪表盘概览）"""
    async with async_session() as session:
        result = await session.execute(select(Device).where(Device.id == device_id))
        device = result.scalar_one_or_none()
        if not device:
            raise HTTPException(status_code=404, detail="设备不存在")

    from app.collector.victoriametrics import query_vm_instant

    promql = f'{{device="{device.name}"}}'
    latest = await query_vm_instant(promql)

    # 按 metric name 分组
    grouped = {}
    for item in latest or []:
        metric_name = item.get("metric", {}).get("__name__", "unknown")
        value = item.get("value", [None, None])[1]
        labels = {k: v for k, v in item.get("metric", {}).items() if k != "__name__"}

        if metric_name not in grouped:
            grouped[metric_name] = []
        grouped[metric_name].append({"labels": labels, "value": value})

    return {"device_id": device_id, "device_name": device.name, "metrics": grouped}
