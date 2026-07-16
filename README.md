# IABet

Plataforma web de inteligência estatística para apostas esportivas. O projeto transforma estatísticas, contexto de elenco e preços de mercado em probabilidades auditáveis, value bets e relatórios PDF. Ele **não promete lucro** e não trata aposta como investimento.

## O que já funciona

- Dashboard Next.js responsivo, tema escuro e visão detalhada de cada partida.
- FastAPI com OpenAPI/Swagger, autenticação JWT e autorização por papel.
- PostgreSQL com SQLAlchemy assíncrono e migração Alembic.
- Times, campeonatos, partidas, estatísticas JSON extensíveis, jogadores, odds históricas, predições, credenciais e logs.
- Ensemble de Poisson (matriz de placares), ELO e 30 mil simulações Monte Carlo.
- Probabilidade implícita, edge, EV/ROI esperado, Kelly fracionado, stake e força.
- Mercados implementados no motor: 1X2, over/under 2,5 e ambas marcam. A estrutura aceita props, cartões, chutes, escanteios e handicaps ao adicionar o modelo específico.
- PDF por partida com resumo, xG, value bets e gestão de banca.
- Celery + Redis: pipeline diário e atualização de odds a cada 15 minutos.
- Interface de providers e conector opcional para The Odds API.
- Dados demonstrativos dos cinco jogos de 16–17/07/2026.
- Testes unitários e pipeline CI.

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

Chaves nunca devem ser enviadas ao frontend ou versionadas. Para produção, use Docker Secrets/Vault/KMS e criptografia de envelope para `api_credentials`.

## Endpoints principais

- `POST /api/v1/auth/login`
- `GET /api/v1/matches`
- `GET /api/v1/matches/{id}`
- `GET /api/v1/reports/{id}.pdf`
- `GET /api/v1/admin/overview` (admin)
- `POST /api/v1/admin/refresh` (admin)

Filtros de data e campeonato são aceitos na listagem. A documentação completa e os schemas ficam no Swagger.

## Modelagem e value bets

O Poisson calcula gols esperados a partir das forças ofensiva/defensiva e médias da liga. A matriz 0–8 fornece 1X2, totais, BTTS e placar modal. O ELO inclui vantagem de mando. Monte Carlo amostra 30 mil placares com seed reproduzível. O ensemble atual usa pesos versionados.

```text
probabilidade implícita = 1 / odd decimal
edge = probabilidade estimada - probabilidade implícita
EV = probabilidade estimada × odd - 1
Kelly = (p × odd - 1) / (odd - 1)
```

A aplicação usa ¼ de Kelly e teto de stake. Antes de produção, pesos precisam ser calibrados em dados históricos fora da amostra, avaliados com Brier score/log loss e monitorados contra closing line value. Random Forest, Gradient Boosting e XGBoost exigem dataset versionado e validação temporal; não foram simulados com dados fictícios. A interface de predição permite adicioná-los ao ensemble quando houver treinamento legítimo.

## Conectores de dados

`app/providers/base.py` define contratos independentes para fixtures, estatísticas e odds. Um provider só deve ser criado quando existir API oficial, licença, export autorizado ou acordo comercial. SofaScore, WhoScored, Flashscore, FotMob, Transfermarkt e casas podem bloquear automação ou proibi-la em seus termos; o projeto não inclui bypass, captura de sessão ou scraping clandestino.

### Fontes gratuitas configuradas

- `FOOTBALL_DATA_KEY`: sincroniza os 380 jogos, resultados, horários e times do Brasileirão (`BSA`).
- `ODDS_API_KEY`: captura odds atuais do Brasileirão e preserva casa, mercado, linha e horário.
- `API_FUTEBOL_KEY` (ou o legado `API_FOOTBALL_KEY`): API Futebol brasileira (`api.api-futebol.com.br`), usada para estatísticas, escalações, cartões e arbitragem.

No Swagger, autentique-se como administrador e use `GET /api/v1/admin/providers` para diagnóstico, `POST /api/v1/admin/sync/fixtures` para agenda, `POST /api/v1/admin/sync/odds` para preços e `POST /api/v1/admin/sync/api-futebol-index` para vincular os IDs brasileiros. Detalhes de uma partida são importados sob demanda por `POST /api/v1/admin/sync/api-futebol-match/{match_id}` para preservar a franquia. As rotinas gerais também são executadas pelo Celery Beat.

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
pytest

cd ../frontend
npm install
npm run build
```

Migrações:

```bash
docker compose run --rm api alembic revision --autogenerate -m "descricao"
docker compose run --rm api alembic upgrade head
```

## Produção

Antes de expor publicamente: TLS e reverse proxy; segredo JWT externo; rotação de credenciais; backup/PITR do PostgreSQL; réplicas de workers; filas separadas por SLA; Sentry/OpenTelemetry; métricas Prometheus; rate limiting; política de retenção; consentimento/LGPD; termos de uso; alertas de jogo responsável; testes de carga e análise de segurança. Troque o servidor único por múltiplos workers conforme a infraestrutura escolhida.

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
