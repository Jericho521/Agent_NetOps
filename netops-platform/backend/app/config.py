"""
配置模块 - 从环境变量读取所有配置项
"""
from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache

# 项目根目录（netops-platform/），.env 文件所在位置
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """应用全局配置"""

    # 数据库
    database_url: str = "sqlite+aiosqlite:///./netops.db"

    # 安全密钥
    credentials_key: str = ""  # AES-256-GCM 加密密钥（Base64 编码）
    jwt_secret: str = ""       # JWT 签名密钥
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 小时

    # VictoriaMetrics 时序库
    vm_url: str = "http://localhost:8428"

    # 采集参数
    collect_interval_seconds: int = 60
    collect_retry_times: int = 3
    collect_timeout_seconds: int = 10

    # 默认管理员
    default_admin_username: str = "admin"
    default_admin_password: str = "admin123"

    # SNMP Trap 监听
    trap_listen_port: int = 1620
    trap_community: str = "public"

    class Config:
        env_file = PROJECT_ROOT / ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """获取全局配置单例"""
    return Settings()


settings = get_settings()
