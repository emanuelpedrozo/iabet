# IABet

Plataforma web de inteligência estatística para apostas esportivas. O projeto transforma estatísticas, contexto de elenco e preços de mercado em probabilidades auditáveis, value bets e relatórios PDF. Ele **não promete lucro** e não trata aposta como investimento.

Documentação detalhada (fonte de verdade do repositório):

- [Arquitetura](docs/10-architecture/architecture.md)
- [Padrões de código](docs/20-standards/code-standards.md) · [Branching](docs/20-standards/branching.md) · [Commits](docs/20-standards/commits.md)
- [Dev local](docs/30-build-deploy/local-dev.md) · [CI/CD](docs/30-build-deploy/ci-cd.md)
- [Design system](docs/40-design-system/design-system.md)

## O que já funciona

- Dashboard Next.js responsivo, tema escuro e visão detalhada de cada partida.
- FastAPI com OpenAPI/Swagger, autenticação JWT e autorização por papel.
- PostgreSQL com SQLAlchemy assíncrono e migração Alembic.
- Times, campeonatos, partidas, estatísticas JSON extensíveis, jogadores, odds históricas, predições, credenciais e logs.
- Ensemble **1.3**: forma recente + splits casa/fora + Dixon–Coles + ELO; value com de-vig, consenso, movimento de odd e H2H.
- Probabilidade implícita, edge, EV/ROI esperado, Kelly fracionado, stake e força.
- Mercados implementados no motor: 1X2, over/under 2,5 e ambas marcam. A estrutura aceita props, cartões, chutes, escanteios e handicaps ao adicionar o modelo específico.
- PDF por partida com resumo, xG, value bets e gestão de banca.
- Celery + Redis: pipeline diário, odds a cada 15 minutos (com retenção) e logs de sucesso/falha.
- Painel admin no frontend (overview, providers, sync) protegido por JWT.
- Interface de providers e conector opcional para The Odds API.
- Dados demonstrativos dos cinco jogos de 16–17/07/2026.
- Testes unitários e pipeline CI (ruff, pytest, lint, typecheck, build).

## Arquitetura

```text
frontend (Next.js) ──HTTP──> api (FastAPI)
                              │
                     repositories/services
                       │              │
                  PostgreSQL      Redis/Celery
                                      │
                              providers autorizados
```

O backend separa modelos persistentes, repositórios, serviços matemáticos, rotas, providers e workers. Os campos de métricas são JSON para permitir evolução sem uma migração a cada nova estatística; identificadores, relacionamentos e campos de busca permanecem normalizados e indexados.

## Execução rápida

Requisitos: Docker Desktop com Compose v2.

```bash
cp .env.example .env
# troque POSTGRES_PASSWORD, JWT_SECRET e ADMIN_PASSWORD
docker compose up --build
```

Acessos:

- Dashboard: http://localhost:3000 (use `WEB_PORT=3001 docker compose up` se a porta estiver ocupada)
- API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- Health check: http://localhost:8000/health

O seed é idempotente. No primeiro boot cria campeonato, dez times, cinco partidas, odds agregadas, predições e o administrador definido no `.env`.

## Configuração

| Variável | Uso |
|---|---|
| `DATABASE_URL` | PostgreSQL assíncrono (`postgresql+asyncpg`) |
| `REDIS_URL` | broker e backend do Celery |
| `JWT_SECRET` | assinatura HS256; use ao menos 32 bytes aleatórios |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | administrador inicial |
| `NEXT_PUBLIC_API_URL` | URL pública da API para o navegador |
| `ODDS_API_KEY` | habilita The Odds API |
| `FOOTYSTATS_API_KEY` | reservado ao provider licenciado |

Chaves nunca devem ser enviadas ao frontend ou versionadas. Fora de `development`, a API recusa `JWT_SECRET`/`ADMIN_PASSWORD` padrão. Para produção, use Docker Secrets/Vault/KMS; criptografia de envelope para `api_credentials` ainda é roadmap.

## Endpoints principais

- `POST /api/v1/auth/login`
- `GET /api/v1/matches`
- `GET /api/v1/matches/{id}`
- `GET /api/v1/reports/{id}.pdf`
- `GET /api/v1/admin/overview` (admin)
- `POST /api/v1/admin/refresh` (admin)
- `POST /api/v1/admin/sync/*` (admin)

Filtros de data e campeonato são aceitos na listagem. A documentação completa e os schemas ficam no Swagger.

## Modelagem e value bets

Forças e ELO vêm de placares `finished`. O blend é **40% temporada + 60% forma** (últimos 8 jogos com decay). No kickoff, o mandante usa forças “em casa” e o visitante “fora”.

Poisson + Dixon–Coles + ELO formam o **ensemble 1.3** (1X2; totals 1,5/2,5/3,5; BTTS).

```text
probabilidade implícita justa = de-vig multiplicativo no mercado
edge = modelo − implícita justa
EV = modelo × odd − 1
Kelly = ¼ × (p × odd − 1) / (odd − 1)
```

Value exige EV ≥ 3%, edge ≥ 2%, Kelly mínimo e odd não “fofa” vs mediana das casas. Queda de odd (≥3%) reduz confiança. Ranking por `rank_score`. H2H histórico entra na confiança de over 2,5.

## Conectores de dados

`app/providers/base.py` define contratos independentes para fixtures, estatísticas e odds. Um provider só deve ser criado quando existir API oficial, licença, export autorizado ou acordo comercial. SofaScore, WhoScored, Flashscore, FotMob, Transfermarkt e casas podem bloquear automação ou proibi-la em seus termos; o projeto não inclui bypass, captura de sessão ou scraping clandestino.

### Fontes gratuitas configuradas

- `FOOTBALL_DATA_KEY`: sincroniza os 380 jogos, resultados, horários e times do Brasileirão (`BSA`).
- `ODDS_API_KEY`: captura odds atuais do Brasileirão e preserva casa, mercado, linha e horário (retenção das últimas capturas por chave).
- `API_FUTEBOL_KEY` (ou o legado `API_FOOTBALL_KEY`): API Futebol brasileira (`api.api-futebol.com.br`), usada para estatísticas, escalações, cartões e arbitragem.

No Swagger ou no painel `/admin`, autentique-se como administrador e use os endpoints de sync. Detalhes de uma partida são importados sob demanda por `POST /api/v1/admin/sync/api-futebol-match/{match_id}` para preservar a franquia. As rotinas gerais também são executadas pelo Celery Beat.

O plano gratuito da API Futebol permite 100 chamadas diárias. A carga histórica automática roda às 06:15 (America/Sao_Paulo) e importa no máximo 80 partidas ainda ausentes, deixando margem para diagnóstico e atualização corrente. O processo é idempotente e continua no dia seguinte.

Para criar um provider:

1. Implemente `SportsDataProvider` ou `OddsProvider`.
2. Normalize IDs externos e preserve o payload bruto para auditoria.
3. Registre-o no `registry.py`.
4. Faça upsert transacional e idempotente no worker.
5. Aplique rate limit, retry exponencial, timeout e observabilidade.
6. Registre casa, mercado, seleção, linha e instante de cada odd.

## Desenvolvimento e testes

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
ruff check app tests
pytest

cd ../frontend
npm ci
npm run lint
npm run typecheck
npm run build
```

Migrações:

```bash
docker compose run --rm api alembic revision --autogenerate -m "descricao"
docker compose run --rm api alembic upgrade head
```

## Produção (roadmap)

Antes de expor publicamente: TLS e reverse proxy; segredo JWT externo; rotação de credenciais; backup/PITR do PostgreSQL; réplicas de workers; filas separadas por SLA; Sentry/OpenTelemetry; métricas Prometheus; política LGPD; termos de uso; alertas de jogo responsável; testes de carga e análise de segurança; cookie httpOnly no lugar de `localStorage`; criptografia de envelope para `api_credentials`.

## Próximas extensões

- Agregações reais de 5/10/20 partidas, splits casa/fora e H2H.
- xG/xA, big chances e métricas de jogadores via fornecedor licenciado.
- Dixon–Coles e Poisson bivariado calibrados.
- Pipeline ML temporal com MLflow/feature store e monitoramento de drift.
- Linhas de cartões, escanteios, chutes e handicap com liquidação correta.
- Gestão de usuários completa, auditoria de ações e UI de credenciais.
- Novas competições e esportes por adaptadores de domínio.

## Aviso

Probabilidades e stakes são estimativas. Odds mudam e dados podem conter atrasos ou erros. Valide escalações, mercado e regras da casa. Somente maiores de 18 anos; estabeleça limites e procure ajuda se apostar deixar de ser entretenimento.
