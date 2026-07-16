# CI/CD

## Pipeline atual

Arquivo: `.github/workflows/ci.yml`

Dispara em `push` e `pull_request`.

### Job `backend`

1. Python 3.12
2. `pip install './backend[dev]'`
3. `ruff check backend/app backend/tests`
4. `pytest backend/tests`

### Job `frontend`

1. Node 20 + cache npm via `frontend/package-lock.json`
2. `npm ci` (exige lockfile versionado)
3. `npm run lint`
4. `npm run typecheck`
5. `npm run build`

## Boas práticas

- Sempre versionar `frontend/package-lock.json`.
- Não usar `npm install` no CI — use `npm ci`.
- Novos testes de contrato (auth, sync, value) devem ir em `backend/tests`.

## Deploy

Não há pipeline de deploy automatizado neste repositório. Produção exige checklist do README (TLS, secrets, backup, rate limit, observabilidade, etc.).
