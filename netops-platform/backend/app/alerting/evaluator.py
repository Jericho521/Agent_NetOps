"""
告警评估器 - 定时调用规则引擎评估
集成到 APScheduler 中运行
"""

# 简单封装：供调度器调用
from app.alerting.rules import evaluate_alert_rules


async def run_evaluation():
    """执行一轮告警规则评估"""
    await evaluate_alert_rules()
