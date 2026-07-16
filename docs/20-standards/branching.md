# Branching

## Branches principais

- `main` — código estável; protegida por CI.
- Features e correções saem de `main` e voltam por pull request.

## Nomes sugeridos

| Tipo | Prefixo | Exemplo |
|---|---|---|
| Funcionalidade | `feat/` | `feat/admin-panel` |
| Correção | `fix/` | `fix/odds-retention` |
| Docs / chore | `docs/` ou `chore/` | `docs/architecture` |

## Fluxo

1. Criar branch a partir de `main` atualizado.
2. Commits pequenos e focados (ver [commits.md](commits.md)).
3. Abrir PR; CI (backend + frontend) deve passar.
4. Merge após review (quando houver time).

Evite commits diretos em `main` no fluxo habitual.
