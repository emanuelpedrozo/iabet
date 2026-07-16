from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_session
from app.core.security import decode_token
from app.models.entities import User
security=HTTPBearer(auto_error=False)
async def current_user(creds:HTTPAuthorizationCredentials|None=Depends(security),session:AsyncSession=Depends(get_session)):
    if not creds: raise HTTPException(401,"Autenticação necessária")
    try: email=decode_token(creds.credentials)["sub"]
    except Exception: raise HTTPException(401,"Token inválido")
    user=await session.scalar(select(User).where(User.email==email,User.active.is_(True)))
    if not user: raise HTTPException(401,"Usuário inválido")
    return user
async def admin(user=Depends(current_user)):
    if user.role!="admin": raise HTTPException(403,"Acesso administrativo necessário")
    return user

