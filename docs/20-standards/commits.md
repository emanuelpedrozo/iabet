# Commits

## Formato

Mensagens curtas em português (ou Conventional Commits em inglês, se o time preferir um padrão único). Foque no **porquê**.

Exemplos:

```text
Corrige retenção de odds no sync a cada 15 min

Adiciona painel admin com sync e logs de jobs

Documenta arquitetura e padrões em docs/
```

Ou:

```text
fix(sync): keep last N odds per market key
feat(admin): wire overview and sync actions
docs: add architecture and local-dev guides
```

## Boas práticas

- Um assunto por commit quando possível.
- Não commitar `.env`, chaves ou artefatos locais.
- Não usar `--no-verify` sem motivo explícito.
