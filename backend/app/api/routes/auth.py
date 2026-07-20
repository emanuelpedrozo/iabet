from datetime import datetime, timezone
from hashlib import sha256
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_session
from app.core.rate_limit import check_login_rate
from app.core.security import create_token, hash_password, verify_password
from app.models.entities import Invitation, User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, session: AsyncSession = Depends(get_session)):
    email = data.email.lower().strip()
    await check_login_rate(email)
    user = await session.scalar(select(User).where(User.email == email))
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Credenciais inválidas")
    if not user.active:
        raise HTTPException(403, "Cadastro aguardando aprovação do administrador")
    return TokenResponse(access_token=create_token(user.email, user.role), role=user.role)


@router.post("/register", status_code=201)
async def register(data: RegisterRequest, session: AsyncSession = Depends(get_session)):
    email = data.email.lower().strip()
    if await session.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Este e-mail já está cadastrado")
    invitation = None
    if data.invite_code:
        token_hash = sha256(data.invite_code.strip().encode()).hexdigest()
        invitation = await session.scalar(select(Invitation).where(
            Invitation.token_hash == token_hash,
            Invitation.used_at.is_(None),
            Invitation.expires_at > datetime.now(timezone.utc),
        ))
        if not invitation:
            raise HTTPException(400, "Convite inválido ou expirado")
    user = User(
        email=email,
        password_hash=hash_password(data.password),
        role=invitation.role if invitation else "user",
        active=invitation is not None,
    )
    session.add(user)
    await session.flush()
    if invitation:
        invitation.used_at = datetime.now(timezone.utc)
        invitation.used_by_user_id = user.id
    await session.commit()
    if not user.active:
        return {"status": "pending", "message": "Cadastro criado e aguardando aprovação"}
    return TokenResponse(access_token=create_token(user.email, user.role), role=user.role)
