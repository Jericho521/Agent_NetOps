"""
数据库引擎 - 异步 SQLAlchemy，支持 SQLite 和 PostgreSQL
通过 DATABASE_URL 环境变量自动切换
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

# 创建异步引擎（自动根据 URL 选择驱动）
engine = create_async_engine(
    settings.database_url,
    echo=False,          # 设为 True 可看 SQL 日志（调试用）
    future=True,
)

# 异步会话工厂
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类"""
    pass


async def get_db() -> AsyncSession:
    """FastAPI 依赖注入：获取数据库会话"""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """初始化数据库：创建所有表，并执行轻量迁移补齐新增列。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _run_migrations(conn)


async def _run_migrations(conn):
    """轻量迁移：自动添加新增列。"""
    from sqlalchemy import inspect

    def migrate(sync_conn):
        inspector = inspect(sync_conn)

        # device 表添加 ssh_port 列
        if "device" in inspector.get_table_names():
            columns = {col["name"] for col in inspector.get_columns("device")}
            if "ssh_port" not in columns:
                sync_conn.execute(text("ALTER TABLE device ADD COLUMN ssh_port INTEGER DEFAULT 22"))

        # 新增报表相关表
        existing = set(inspector.get_table_names())
        if "report_template" not in existing:
            sync_conn.execute(text("""
                CREATE TABLE report_template (
                    id VARCHAR(36) PRIMARY KEY,
                    name VARCHAR(128) NOT NULL,
                    report_type VARCHAR(16) DEFAULT 'daily',
                    widgets TEXT,
                    schedule VARCHAR(100),
                    enabled BOOLEAN DEFAULT 1,
                    created_at DATETIME,
                    updated_at DATETIME
                )
            """))
        if "report_instance" not in existing:
            sync_conn.execute(text("""
                CREATE TABLE report_instance (
                    id VARCHAR(36) PRIMARY KEY,
                    template_id VARCHAR(36),
                    report_type VARCHAR(16) DEFAULT 'daily',
                    created_by VARCHAR(64),
                    pdf_path VARCHAR(255),
                    excel_path VARCHAR(255),
                    status VARCHAR(16) DEFAULT 'completed',
                    error_message TEXT,
                    created_at DATETIME
                )
            """))

        # 区域/子区域表
        if "region" not in existing:
            sync_conn.execute(text("""
                CREATE TABLE region (
                    id VARCHAR(36) PRIMARY KEY,
                    name VARCHAR(64) NOT NULL UNIQUE,
                    description TEXT,
                    sort_order INTEGER DEFAULT 0,
                    created_at DATETIME
                )
            """))
        if "sub_region" not in existing:
            sync_conn.execute(text("""
                CREATE TABLE sub_region (
                    id VARCHAR(36) PRIMARY KEY,
                    region_id VARCHAR(36) NOT NULL REFERENCES region(id) ON DELETE CASCADE,
                    name VARCHAR(64) NOT NULL,
                    description TEXT,
                    sort_order INTEGER DEFAULT 0,
                    created_at DATETIME
                )
            """))

        # device 表迁移：region 字符串 → region_id/sub_region_id 外键
        if "device" in inspector.get_table_names():
            columns = {col["name"] for col in inspector.get_columns("device")}
            if "ssh_port" not in columns:
                sync_conn.execute(text("ALTER TABLE device ADD COLUMN ssh_port INTEGER DEFAULT 22"))
            if "region_id" not in columns:
                sync_conn.execute(text("ALTER TABLE device ADD COLUMN region_id VARCHAR(36) REFERENCES region(id)"))
            if "sub_region_id" not in columns:
                sync_conn.execute(text("ALTER TABLE device ADD COLUMN sub_region_id VARCHAR(36) REFERENCES sub_region(id)"))

        # alert 表迁移：补齐缺失列（fired_at/acknowledged_at/resolved_at/acknowledged_by/category/value）
        if "alert" in inspector.get_table_names():
            alert_cols = {col["name"] for col in inspector.get_columns("alert")}
            missing = {
                "category": "VARCHAR(16) DEFAULT 'threshold'",
                "value": "FLOAT",
                "fired_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
                "acknowledged_at": "DATETIME",
                "resolved_at": "DATETIME",
                "acknowledged_by": "VARCHAR(64)",
            }
            for col, ddl in missing.items():
                if col not in alert_cols:
                    sync_conn.execute(text(f"ALTER TABLE alert ADD COLUMN {col} {ddl}"))
            # alert.severity 改为可空（设备离线/异常告警不进 P 级别体系）
            if "severity" in alert_cols:
                sev_col = next(c for c in inspector.get_columns("alert") if c["name"] == "severity")
                if sev_col.get("nullable") is False:
                    sync_conn.execute(text("ALTER TABLE alert RENAME TO alert_old"))
                    sync_conn.execute(text("""
                        CREATE TABLE alert (
                            id VARCHAR(36) PRIMARY KEY,
                            rule_id VARCHAR(36),
                            device_id VARCHAR(36),
                            status VARCHAR(16) DEFAULT 'active',
                            severity INTEGER,
                            category VARCHAR(16) DEFAULT 'threshold',
                            message TEXT NOT NULL,
                            value FLOAT,
                            fired_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            acknowledged_at DATETIME,
                            resolved_at DATETIME,
                            acknowledged_by VARCHAR(64)
                        )
                    """))
                    sync_conn.execute(text(
                        "INSERT INTO alert (id, rule_id, device_id, status, severity, category, message, value, fired_at, acknowledged_at, resolved_at, acknowledged_by) "
                        "SELECT id, rule_id, device_id, status, severity, category, message, value, fired_at, acknowledged_at, resolved_at, acknowledged_by FROM alert_old"
                    ))
                    sync_conn.execute(text("DROP TABLE alert_old"))

        # device 表迁移：加 sys_name / device_type
        if "device" in inspector.get_table_names():
            dev_cols = {col["name"] for col in inspector.get_columns("device")}
            if "sys_name" not in dev_cols:
                sync_conn.execute(text("ALTER TABLE device ADD COLUMN sys_name VARCHAR(128)"))
            if "device_type" not in dev_cols:
                sync_conn.execute(text("ALTER TABLE device ADD COLUMN device_type VARCHAR(16) DEFAULT 'single'"))

        # alert_rule 表迁移：加 critical_threshold 列
        if "alert_rule" in inspector.get_table_names():
            ar_cols = {col["name"] for col in inspector.get_columns("alert_rule")}
            if "critical_threshold" not in ar_cols:
                sync_conn.execute(text("ALTER TABLE alert_rule ADD COLUMN critical_threshold FLOAT"))

        # link 表（拓扑连接）：不存在则创建
        if "link" not in inspector.get_table_names():
            sync_conn.execute(text("""
                CREATE TABLE link (
                    id VARCHAR(36) PRIMARY KEY,
                    local_device_id VARCHAR(36),
                    local_port VARCHAR(64),
                    remote_device_id VARCHAR(36),
                    remote_sysname VARCHAR(128),
                    remote_port VARCHAR(64),
                    remote_ip VARCHAR(64),
                    protocol VARCHAR(16) DEFAULT 'lldp',
                    link_type VARCHAR(16) DEFAULT 'unknown',
                    is_critical INTEGER DEFAULT 0,
                    discovered_at DATETIME
                )
            """))
        else:
            link_cols = {col["name"] for col in inspector.get_columns("link")}
            if "is_critical" not in link_cols:
                sync_conn.execute(text("ALTER TABLE link ADD COLUMN is_critical INTEGER DEFAULT 0"))

    await conn.run_sync(migrate)
