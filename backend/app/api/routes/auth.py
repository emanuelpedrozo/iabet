from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_session
from app.core.rate_limit import check_login_rate
from app.core.security import create_token, hash_password, verify_password
from app.models.entities import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, session: AsyncSession = Depends(get_session)):
    email = data.email.lower().strip()
    await check_login_rate(email)
    user = await session.scalar(select(User).where(User.email == email))
    if not user or not user.active or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Credenciais inválidas")
    return TokenResponse(access_token=create_token(user.email, user.role), role=user.role)


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(data: RegisterRequest, session: AsyncSession = Depends(get_session)):
    email = data.email.lower().strip()
    if await session.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Este e-mail já está cadastrado")
    user = User(email=email, password_hash=hash_password(data.password), role="user", active=True)
    session.add(user)
    await session.commit()
    return TokenResponse(access_token=create_token(user.email, user.role), role=user.role)
