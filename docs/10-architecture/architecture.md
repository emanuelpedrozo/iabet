# Arquitetura — IABet

## Propósito

Plataforma web de inteligência estatística para apostas esportivas (foco em futebol / Brasileirão). Combina estatísticas, odds de mercado e modelos matemáticos para gerar probabilidades, value bets e relatórios PDF. **Não promete lucro.**

## Visão geral

```text
frontend (Next.js) ──HTTP──> api (FastAPI)
                              │
                     repositories/services
                       │              │
                  PostgreSQL      Redis/Celery
                                      │
                              providers autorizados
```

## Componentes

| Camada | Tecnologia | Responsabilidade |
|---|---|---|
| Frontend | Next.js 14 (App Router), React, Tailwind | Dashboard público, análise por partida, login e admin |
| API | FastAPI, Pydantic, SQLAlchemy async | Auth JWT, partidas, PDF, admin/sync |
| Banco | PostgreSQL 16 | Times, partidas, odds, predições, usuários, logs |
| Filas | Redis 7 + Celery (worker + beat) | Sync fixtures/odds, histórico API Futebol, materialização de predições |
| Modelos | NumPy | Ensemble 1.3 (forma, splits, Dixon–Coles + ELO); value com de-vig/consenso/movimento |

## Backend (`backend/app`)

- `api/routes` — HTTP (auth, matches, reports, admin)
- `core` — config, DB, security, rate limit
- `models` — entidades SQLAlchemy
- `repositories` — acesso a dados
- `services` — sync, strengths/ELO, modelos matemáticos, value bets, PDF
- `providers` — Football-Data, The Odds API, API Futebol
- `workers` — tarefas Celery

Métricas estatísticas flexíveis ficam em JSON; relacionamentos e busca permanecem normalizados.

## Frontend (`frontend`)

- `/` — listagem de partidas (pública)
- `/jogos/[id]` — análise detalhada (pública)
- `/login` — JWT em `localStorage`
- `/admin` — painel operacional (requer JWT admin)

## Fluxo de dados

1. Celery Beat dispara sync diário de fixtures e odds periódicas.
2. `DataSyncService` faz upsert de partidas/times e retém as últimas N odds por chave.
3. `StrengthService` estima ataque/defesa (temporada + forma recente com decay, splits casa/fora) e atualiza ELO (`metadata.elo_applied`).
4. Predições do **ensemble 1.3** materializam Poisson+Dixon–Coles + ELO com forças condicionadas ao mando; totals 1,5 / 2,5 / 3,5.
5. Value bets: de-vig, **consenso** entre casas, **movimento** de odd, limiares e `rank_score`. H2H vem do banco na análise.

## Autorização

- Leitura de partidas e PDF: pública.
- Rotas `/api/v1/admin/*`: JWT com papel `admin`.

## Roadmap de modelagem

Shin além do de-vig multiplicativo, calibração Brier/CLV e ML com dataset versionado permanecem fora do núcleo atual.
