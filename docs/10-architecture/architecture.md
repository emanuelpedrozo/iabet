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
| Filas | Redis 7 + Celery (worker + beat) | Sync fixtures/odds, histórico API Futebol / API-Sports, materialização de predições |
| Modelos | NumPy | Ensemble 1.4 (gols + Poisson de escanteios/cartões/chutes); value com de-vig/consenso/movimento |

## Backend (`backend/app`)

- `api/routes` — HTTP (auth, matches, reports, admin)
- `core` — config, DB, security, rate limit
- `models` — entidades SQLAlchemy
- `repositories` — acesso a dados
- `services` — sync, strengths/ELO, modelos matemáticos, value bets, PDF
- `providers` — Football-Data, The Odds API, API Futebol, API-Sports
- `workers` — tarefas Celery

Métricas de time (`team_stats`) e por jogador (`player_match_stats`) ficam em JSON flexível.
Médias de chutes/escanteios/amarelos alimentam a análise histórica **e** o ensemble 1.4 (Poisson over/under).
Odds de escanteios/cartões vêm do endpoint por evento da Odds API (`alternate_totals_*`). Chutes: modelo pronto; odds só entram no value se existirem no banco.

## Frontend (`frontend`)

- `/` — listagem de partidas (pública)
- `/jogos/[id]` — análise detalhada (pública)
- `/login` — JWT em `localStorage`
- `/admin` — painel operacional (requer JWT admin)

## Fluxo de dados

1. Celery Beat dispara sync diário de fixtures e odds periódicas.
2. `DataSyncService` faz upsert de partidas/times e retém as últimas N odds por chave.
3. `StrengthService` estima ataque/defesa (temporada + forma recente com decay, splits casa/fora) e atualiza ELO (`metadata.elo_applied`).
4. Predições do **ensemble 1.4** materializam 1X2/gols (Dixon–Coles + ELO) e totals Poisson de escanteios/cartões/chutes a partir de `TeamStat`.
5. Value bets: de-vig, **consenso** entre casas, **movimento** de odd, limiares e `rank_score` (inclui corners/cards quando há odd). H2H vem do banco na análise.
6. Histórico detalhado: API Futebol e API-Sports gravam `TeamStat` com **merge**; API-Sports grava `PlayerMatchStat`. Médias/λ de stats usam **somente os últimos 10 finished** do time na competição (sem janela de temporada antiga). Odds extras de corners/cards: até N eventos por sync.
7. Sync de odds featured (h2h/totals/btts) + evento (`alternate_totals_corners`, `alternate_totals_cards`).

## Autorização

- Leitura de partidas e PDF: pública.
- Rotas `/api/v1/admin/*`: JWT com papel `admin`.

## Roadmap de modelagem

Shin além do de-vig multiplicativo, calibração Brier/CLV, ML com dataset versionado e odds de chutes (quando a casa não publica) permanecem fora do núcleo atual.
