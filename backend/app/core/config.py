from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "IABet API"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://iabet:change-me@localhost:5432/iabet"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "development-only-secret-change-it"
    jwt_minutes: int = 480
    admin_email: str = "admin@iabet.com"
    admin_password: str = "ChangeMe123!"
    odds_api_key: str | None = None
    footystats_api_key: str | None = None
    cors_origins: str = "http://localhost:3000"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def origins(self): return [x.strip() for x in self.cors_origins.split(",")]

@lru_cache
def get_settings(): return Settings()
settings = get_settings()
