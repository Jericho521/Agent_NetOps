"""
VictoriaMetrics 写入/查询客户端
- 指标通过 HTTP API 推送到 VM（Prometheus 格式）
- 查询通过 PromQL query / query_range 接口
"""
import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def vm_health_check() -> bool:
    """检查 VictoriaMetrics 是否可达"""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.vm_url}/health")
            return resp.status_code == 200
    except Exception as e:
        logger.debug(f"VM 健康检查失败: {e}")
        return False


async def write_metrics_to_vm(metrics: list[dict]) -> bool:
    """
    将采集到的指标写入 VictoriaMetrics。
    使用 Prometheus exposition format 通过 /api/v1/import/prometheus 推送。

    Args:
        metrics: 指标列表，每项格式：
            {
                "metric_name": str,
                "value": float,
                "labels": dict,
                "timestamp": int (epoch seconds),
            }

    Returns:
        True 表示写入成功
    """
    if not metrics:
        return True

    # 构造 Prometheus 行协议文本
    lines = []
    for m in metrics:
        metric_name = m["metric_name"]
        value = m["value"]
        labels = m.get("labels", {})
        timestamp = m.get("timestamp", 0)

        # 格式: metric{label1="val1",label2="val2"} value timestamp
        label_str = ",".join(f'{k}="{_escape_label_value(v)}"' for k, v in labels.items())
        if label_str:
            line = f'{metric_name}{{{label_str}}} {value} {timestamp}'
        else:
            line = f'{metric_name} {value} {timestamp}'
        lines.append(line)

    body = "\n".join(lines) + "\n"

    url = f"{settings.vm_url}/api/v1/import/prometheus"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, content=body, headers={"Content-Type": "text/plain"})
            if resp.status_code == 204:
                logger.debug(f"成功写入 {len(metrics)} 条指标到 VM")
                return True
            else:
                logger.error(f"VM 写入失败: HTTP {resp.status_code}, {resp.text[:200]}")
                return False
    except Exception as e:
        logger.error(f"VM 写入异常: {e}")
        return False


async def query_vm_range(promql: str, range_hours: int = 1, step: int = 60) -> Optional[list]:
    """
    使用 PromQL query_range 查询时序数据（用于绘制曲线图）

    Args:
        promql: PromQL 查询语句
        range_hours: 时间范围（小时）
        step: 采样间隔（秒）

    Returns:
        VM API 返回的 data.result 列表，或 None
    """
    import time
    end_time = int(time.time())
    start_time = end_time - range_hours * 3600

    params = {
        "query": promql,
        "start": start_time,
        "end": end_time,
        "step": step,
    }

    url = f"{settings.vm_url}/api/v1/query_range"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("data", {}).get("result", [])
            else:
                logger.error(f"VM query_range 查询失败: HTTP {resp.status_code}")
                return None
    except Exception as e:
        logger.error(f"VM query_range 异常: {e}")
        return None


async def query_vm_instant(promql: str) -> Optional[list]:
    """
    使用 PromQL query 即时查询最新值（用于仪表盘概览）

    Returns:
        VM API 返回的 data.result 列表，或 None
    """
    params = {"query": promql}
    url = f"{settings.vm_url}/api/v1/query"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("data", {}).get("result", [])
            else:
                logger.error(f"VM query 查询失败: HTTP {resp.status_code}")
                return None
    except Exception as e:
        logger.error(f"VM query 异常: {e}")
        return None


def _escape_label_value(value: str) -> str:
    """转义 Prometheus label 值中的特殊字符"""
    return (
        value.replace("\\", "\\\\")
             .replace('"', '\\"')
             .replace("\n", "\\n")
    )
