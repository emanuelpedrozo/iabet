# Design system — IABet

Tema escuro com acento verde de marca. Tokens usados no frontend (Tailwind + CSS).

## Cores

| Token | Uso | Valor de referência |
|---|---|---|
| Brand | CTAs, destaques, links ativos | `#36e38b` |
| Ink | Fundo base | `#080d0b` |
| Line | Bordas | `#26322d` |
| Muted | Texto secundário | `#8ea39a` |
| Panel | Superfícies | tons escuros com leve gradiente |

Definidos em `frontend/tailwind.config.ts` e `frontend/app/globals.css`.

## Tipografia

Inter carregada via `next/font/google` (`--font-inter` / `className` no `layout`). Fallback: `ui-sans-serif, system-ui`. Títulos usam peso alto (`font-black` / `font-bold`).

## Componentes de superfície

- `.card` — bloco de conteúdo com borda e gradiente suave (usado em listagens e análise, não como “dashboard cards” genéricos no hero).
- `.hero-panel` — faixa de abertura da home.
- `.label` — rótulo uppercase pequeno.
- `.bar` — barra de probabilidade.
- `.skip-link` — link “Ir para o conteúdo” (visível no foco).

## Foco e teclado

Interativos (`a`, `button`, `input`) usam `focus-visible` com outline brand (`#36e38b`) e offset de 2px.

## Motion

Framer Motion em cards de partida (entrada com delay curto). Com `prefers-reduced-motion`, animações Framer são desligadas (`useReducedMotion`) e o CSS reduz transitions/animations globais.

## Tom visual

Atmosfera escura com brilho radial verde suave no fundo. Marca **IABet** no header como âncora de produto.
