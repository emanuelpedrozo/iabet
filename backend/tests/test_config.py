import pytest
from pydantic import ValidationError
from app.core.config import DEFAULT_ADMIN_PASSWORD, DEFAULT_JWT, Settings


def test_development_allows_default_secrets():
    s = Settings(environment="development", jwt_secret=DEFAULT_JWT, admin_password=DEFAULT_ADMIN_PASSWORD)
    assert s.environment == "development"


def test_production_rejects_default_jwt():
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            jwt_secret=DEFAULT_JWT,
            admin_password="SenhaForteProducao123!",
        )


def test_production_rejects_short_jwt():
    with pytest.raises(ValidationError):
        Settings(
            environment="staging",
            jwt_secret="curto-demais",
            admin_password="SenhaForteProducao123!",
        )


def test_production_accepts_strong_secrets():
    s = Settings(
        environment="production",
        jwt_secret="x" * 32,
        admin_password="SenhaForteProducao123!",
    )
    assert len(s.jwt_secret) >= 32
