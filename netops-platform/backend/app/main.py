"""
FastAPI 应用入口 - 网络 AI 运维监控平台
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.config import settings
from app.db import init_db
from app.routers import devices, metrics, alerts, auth, config, trap, ai, reports, regions, topology

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化数据库、创建默认管理员"""
    logger.info("正在初始化数据库...")
    await init_db()

    # 创建默认管理员账号（如果不存在）
    from app.security import jwt_auth
    await jwt_auth.create_default_admin()

    # 启动采集调度器
    from app.collector.scheduler import start_scheduler, stop_scheduler
    start_scheduler()
    logger.info("采集调度器已启动")

    # 启动 SNMP Trap 监听
    import asyncio
    from app.trap_listener import start_trap_listener, stop_trap_listener, ensure_default_trap_rules
    await ensure_default_trap_rules()
    start_trap_listener(asyncio.get_event_loop())
    logger.info("SNMP Trap 监听已启动")

    yield  # 应用运行中...

    # 关闭时停止调度器与 Trap 监听
    stop_scheduler()
    stop_trap_listener()
    logger.info("采集调度器与 SNMP Trap 监听已停止")


# 创建 FastAPI 实例
app = FastAPI(
    title="网络 AI 运维监控平台",
    description="NetOps Platform MVP - SNMP 设备监控 + 时序存储 + 告警",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 中间件（允许前端跨域访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],  # Vite 默认端口
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局异常处理
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"message": "请求参数校验失败", "detail": exc.errors()},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"未处理的异常: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"message": "服务器内部错误", "detail": str(exc)},
    )


# 注册路由
app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(devices.router, prefix="/api/devices", tags=["设备管理"])
app.include_router(metrics.router, prefix="/api/metrics", tags=["指标查询"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["告警"])
app.include_router(config.router, prefix="/api", tags=["配置管理"])
app.include_router(trap.router, prefix="/api/traps", tags=["SNMP Trap"])
app.include_router(ai.router, prefix="/api/ai", tags=["AI 助手"])
app.include_router(reports.router, prefix="/api/reports", tags=["报表中心"])
app.include_router(regions.router, prefix="/api", tags=["区域管理"])
app.include_router(topology.router, prefix="/api/topology", tags=["拓扑管理"])


# 健康检查端点
@app.get("/healthz", response_model=dict, tags=["系统"])
async def health_check():
    """健康检查 - 用于探活和平台自监控"""
    from app.collector.victoriametrics import vm_health_check
    db_ok = False
    try:
        from app.db import async_session
        async with async_session() as session:
            await session.execute("SELECT 1")
            db_ok = True
    except Exception:
        pass

    vm_ok = await vm_health_check()

    return {
        "status": "ok" if (db_ok and vm_ok) else "degraded",
        "version": "1.0.0",
        "db_connected": db_ok,
        "vm_connected": vm_ok,
    }


# 根路径
@app.get("/", tags=["系统"])
async def root():
    return {"message": "网络 AI 运维监控平台 API", "docs": "/docs"}
