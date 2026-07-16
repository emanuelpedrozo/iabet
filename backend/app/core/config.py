from functools import lru_cache
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT = "development-only-secret-change-it"
DEFAULT_ADMIN_PASSWORD = "ChangeMe123!"


class Settings(BaseSettings):
    app_name: str = "IABet API"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://iabet:change-me@localhost:5432/iabet"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = DEFAULT_JWT
    jwt_minutes: int = 480
    admin_email: str = "admin@iabet.com"
    admin_password: str = DEFAULT_ADMIN_PASSWORD
    odds_api_key: str | None = None
    api_football_key: str | None = None
    api_sports_key: str | None = None
    api_sports_host: str = "https://v3.football.api-sports.io"
    api_futebol_key: str | None = None
    football_data_key: str | None = None
    footystats_api_key: str | None = None
    cors_origins: str = "http://localhost:3000"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def origins(self):
        return [x.strip() for x in self.cors_origins.split(",")]

    @model_validator(mode="after")
    def reject_insecure_defaults(self):
        if self.environment == "development":
            return self
        problems: list[str] = []
        if not self.jwt_secret or self.jwt_secret == DEFAULT_JWT or len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET (mín. 32 caracteres, sem valor padrão)")
        if not self.admin_password or self.admin_password == DEFAULT_ADMIN_PASSWORD:
            problems.append("ADMIN_PASSWORD (sem valor padrão de desenvolvimento)")
        if problems:
            raise ValueError(
                "Ambiente não-development com segredos inseguros: " + "; ".join(problems)
            )
        return self


@lru_cache
def get_settings():
    return Settings()


settings = get_settings()
