"""Rate limit simples para login (Redis com fallback em memória)."""
import time
from fastapi import HTTPException
from app.core.config import settings

_memory: dict[str, list[float]] = {}


async def check_login_rate(key: str, limit: int = 10, window: int = 60) -> None:
    now = time.time()
    try:
        import redis.asyncio as redis

        client = redis.from_url(settings.redis_url, decode_responses=True)
        try:
            pipe_key = f"rl:login:{key}"
            count = await client.incr(pipe_key)
            if count == 1:
                await client.expire(pipe_key, window)
            if count > limit:
                raise HTTPException(429, "Muitas tentativas. Aguarde e tente novamente.")
        finally:
            await client.aclose()
    except HTTPException:
        raise
    except Exception:
        hits = [t for t in _memory.get(key, []) if now - t < window]
        hits.append(now)
        _memory[key] = hits
        if len(hits) > limit:
            raise HTTPException(429, "Muitas tentativas. Aguarde e tente novamente.")
