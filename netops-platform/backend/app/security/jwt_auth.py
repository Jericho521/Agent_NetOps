"""
JWT 认证模块 - 登录/鉴权/权限控制
MVP 阶段简化为两个角色：admin（管理员）、viewer（只读）
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import async_session
from app.models import User

logger = logging.getLogger(__name__)

# 密码哈希
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# Bearer Token 认证方案
security_scheme = HTTPBearer()


def hash_password(password: str) -> str:
    """密码 → 哈希值"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码与哈希是否匹配"""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """生成 JWT Token"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.jwt_expire_minutes))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """解码并验证 JWT Token，返回 payload"""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    session: AsyncSession = Depends(lambda: async_session()),
) -> User:
    """
    FastAPI 依赖：从 Bearer Token 获取当前登录用户。
    在需要认证的 API 端点中使用。
    """
    token = credentials.credentials
    payload = decode_access_token(token)

    user_id: str = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token 格式错误")

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已被禁用")

    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """FastAPI 依赖：要求管理员角色"""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


async def authenticate_user(username: str, password: str, session: AsyncSession) -> Optional[User]:
    """验证用户名+密码，返回用户对象或 None"""
    result = await session.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


async def create_default_admin():
    """启动时检查并创建默认管理员账号（如果不存在）"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.username == settings.default_admin_username)
        )
        existing = result.scalar_one_or_none()

        if not existing:
            admin_user = User(
                username=settings.default_admin_username,
                hashed_password=hash_password(settings.default_admin_password),
                role="admin",
                is_active=True,
            )
            session.add(admin_user)
            await session.commit()
            logger.info(f"默认管理员账号已创建: {settings.default_admin_username}")
        else:
            logger.debug(f"管理员账号已存在: {settings.default_admin_username}")
