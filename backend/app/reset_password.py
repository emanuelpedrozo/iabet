"""Recuperação interativa de senha executada dentro do container da API."""

import asyncio
from getpass import getpass

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.entities import User


async def reset_password() -> None:
    email = input("E-mail da conta: ").strip().lower()
    password = getpass("Nova senha (mínimo 8 caracteres): ")
    confirmation = getpass("Confirme a nova senha: ")
    if len(password) < 8:
        raise SystemExit("A senha precisa ter pelo menos 8 caracteres.")
    if password != confirmation:
        raise SystemExit("As senhas não coincidem.")

    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email))
        if not user:
            raise SystemExit("Conta não encontrada.")
        user.password_hash = hash_password(password)
        user.active = True
        await session.commit()
    print("Senha atualizada com sucesso.")


if __name__ == "__main__":
    asyncio.run(reset_password())
