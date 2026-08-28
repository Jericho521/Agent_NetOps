"""
认证路由 - 登录 / 获取当前用户信息
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session
from app.schemas import LoginRequest, TokenResponse, UserInfo
from app.security.jwt_auth import (
    authenticate_user, create_access_token, get_current_user, User
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    """用户登录，返回 JWT Token"""
    async with async_session() as session:
        user = await authenticate_user(body.username, body.password, session)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 生成 Token
        token = create_access_token({"sub": user.id, "username": user.username, "role": user.role})

        return TokenResponse(
            access_token=token,
            token_type="bearer",
            user_info={
                "id": user.id,
                "username": user.username,
                "role": user.role,
            },
        )


@router.get("/me", response_model=UserInfo)
async def get_me(current_user: User = Depends(get_current_user)):
    """获取当前登录用户信息"""
    return UserInfo(id=current_user.id, username=current_user.username, role=current_user.role)
