from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_session
from app.core.security import create_token, verify_password
from app.models.entities import User
from app.schemas.auth import LoginRequest, TokenResponse
router=APIRouter(prefix="/auth",tags=["Autenticação"])
@router.post("/login",response_model=TokenResponse)
async def login(data:LoginRequest,session:AsyncSession=Depends(get_session)):
    user=await session.scalar(select(User).where(User.email==data.email))
    if not user or not verify_password(data.password,user.password_hash): raise HTTPException(401,"Credenciais inválidas")
    return TokenResponse(access_token=create_token(user.email,user.role),role=user.role)

