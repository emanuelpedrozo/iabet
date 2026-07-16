# Desenvolvimento local

## Requisitos

- Docker Desktop com Compose v2
- (Opcional) Node 20+ e Python 3.12+ para rodar fora do Compose

## Subir tudo

```bash
cp .env.example .env
# troque POSTGRES_PASSWORD, JWT_SECRET e ADMIN_PASSWORD
docker compose up --build
```

Acessos:

- Dashboard: http://localhost:3000
- API / Swagger: http://localhost:8000/docs
- Health: http://localhost:8000/health

O seed é idempotente (campeonato demo, partidas, odds, predições, admin).

## Backend isolado

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -e '.[dev]'
pytest
ruff check app tests
```

## Frontend isolado

```bash
cd frontend
npm ci
npm run dev
# opcional: npm run lint && npm run typecheck && npm run build
```

Defina `NEXT_PUBLIC_API_URL` apontando para a API (ex.: `http://localhost:8000/api/v1`).

## Providers

Chaves opcionais no `.env`: `FOOTBALL_DATA_KEY`, `ODDS_API_KEY`, `API_FUTEBOL_KEY`. Sem chave, o sync correspondente fica vazio ou inativo. Diagnóstico: `GET /api/v1/admin/providers` (JWT admin).

## Migrações

```bash
docker compose run --rm api alembic revision --autogenerate -m "descricao"
docker compose run --rm api alembic upgrade head
```

A revisão `0001` cria o schema inicial via metadata. Revisões seguintes devem ser incrementais (sem novo `create_all`).
