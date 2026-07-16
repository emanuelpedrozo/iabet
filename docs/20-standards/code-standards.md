# Padrões de código

## Princípios

- **YAGNI** — só o necessário para o problema atual.
- **Simplicidade** — nomes claros; evite abstrações prematuras.
- **Português** — comentários, docs e mensagens de UI em pt-BR.
- **Fonte de verdade** — comportamento transversal documentado em `docs/`; detalhes pontuais em comentário no código.

## Comentários e documentação

| Vai em `docs/` | Vai no código |
|---|---|
| Arquitetura, fluxo entre serviços, padrões do time | Por que uma decisão local não óbvia |
| Como rodar, CI, branching, commits | Aviso em trecho perigoso ou contrato externo |
| Design system / tokens compartilhados | Não repetir o óbvio do código |

Prefira comentário curto no ponto de uso a páginas longas e específicas demais.

## Backend (Python)

- Python 3.12+, tipagem onde ajuda o contrato.
- Rotas finas; lógica em `services` / `repositories`.
- Schemas Pydantic com `response_model` nas rotas públicas principais.
- Lint: `ruff check` (veja ignores em `pyproject.toml` para estilo legado denso).

## Frontend (TypeScript / Next)

- App Router; componentes client só quando há estado/interação.
- Chamadas autenticadas via `apiFetch` com Bearer do `localStorage`.
- Lint: `next lint`; tipos: `npm run typecheck`.

## Segurança

- Segredos só em env / secrets; nunca no frontend.
- Fora de `development`, `JWT_SECRET` (≥32) e `ADMIN_PASSWORD` não podem ser os defaults.
- Login tem rate limit (Redis, com fallback em memória).
