'use client';

import { useMemo, useState } from 'react';
import {
  CalendarDays,
  ChevronDown,
  CircleDollarSign,
  Search,
  Sparkles,
  Target,
  TrendingUp,
} from 'lucide-react';
import { MatchCard } from '@/components/match-card';
import type { Match } from '@/lib/api';

type Filter = 'all' | 'value' | 'today' | 'tomorrow';
const filters: { id: Filter; label: string }[] = [
  { id: 'all', label: 'Próximos' },
  { id: 'value', label: 'Com value' },
  { id: 'today', label: 'Hoje' },
  { id: 'tomorrow', label: 'Amanhã' },
];

export function HomeDashboard({ matches, error }: { matches: Match[]; error: string }) {
  const [filter, setFilter] = useState<Filter>('all');
  const [query, setQuery] = useState('');
  const [expanded, setExpanded] = useState(false);
  const sorted = useMemo(
    () =>
      [...matches].sort((a, b) => {
        if (Boolean(a.best_value) !== Boolean(b.best_value)) return a.best_value ? -1 : 1;
        return new Date(a.kickoff).getTime() - new Date(b.kickoff).getTime();
      }),
    [matches],
  );
  const filtered = useMemo(
    () =>
      sorted.filter((m) => {
        const text = `${m.home_team.name} ${m.away_team.name} ${m.competition}`.toLowerCase();
        if (query && !text.includes(query.toLowerCase())) return false;
        if (filter === 'value' && !m.best_value) return false;
        if (filter === 'today' || filter === 'tomorrow') {
          const date = new Date(m.kickoff);
          const target = new Date();
          if (filter === 'tomorrow') target.setDate(target.getDate() + 1);
          if (date.toDateString() !== target.toDateString()) return false;
        }
        return true;
      }),
    [sorted, filter, query],
  );
  const visible = expanded ? filtered : filtered.slice(0, 6);
  const values = matches.filter((m) => m.best_value);
  const best = values.reduce<Match['best_value'] | undefined>(
    (current, m) =>
      !current || (m.best_value?.edge || 0) > current.edge ? m.best_value : current,
    undefined,
  );

  return (
    <main className="mx-auto max-w-7xl px-5 pb-14 pt-8">
      <section className="hero-panel overflow-hidden rounded-[28px] border border-line px-6 py-7 md:px-9 md:py-9">
        <div className="grid items-end gap-8 lg:grid-cols-[1fr_auto]">
          <div>
            <div className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-[.16em] text-brand">
              <Sparkles size={15} aria-hidden /> Inteligência para a rodada
            </div>
            <h1 className="max-w-3xl text-3xl font-black leading-tight md:text-5xl">
              As melhores oportunidades,
              <br className="hidden md:block" /> sem o ruído da agenda inteira.
            </h1>
            <p className="mt-4 max-w-2xl text-sm leading-6 text-muted md:text-base">
              O IABet cruza probabilidades, preços e contexto para destacar primeiro o que merece
              sua análise.
            </p>
          </div>
          <div className="grid w-full grid-cols-3 gap-2 lg:w-auto lg:min-w-0">
            <Summary icon={<Target aria-hidden />} value={String(matches.length)} label="monitorados" />
            <Summary icon={<TrendingUp aria-hidden />} value={String(values.length)} label="com value" />
            <Summary
              icon={<CircleDollarSign aria-hidden />}
              value={best ? `+${Math.round(best.edge * 100)}%` : '—'}
              label="maior edge"
              accent
            />
          </div>
        </div>
      </section>

      <section className="mt-8" id="value">
        <div className="mb-5 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="label">Agenda inteligente</div>
            <h2 className="mt-1 text-2xl font-bold">Jogos em destaque</h2>
            <p className="mt-1 text-sm text-muted">Oportunidades com value aparecem primeiro.</p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row">
            <div
              className="flex rounded-xl border border-line bg-panel/70 p-1"
              role="group"
              aria-label="Filtros da agenda"
            >
              {filters.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  aria-pressed={filter === item.id}
                  onClick={() => {
                    setFilter(item.id);
                    setExpanded(false);
                  }}
                  className={`rounded-lg px-3 py-2 text-xs font-semibold transition ${
                    filter === item.id ? 'bg-white/10 text-white' : 'text-muted hover:text-white'
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <label className="flex min-w-[220px] items-center gap-2 rounded-xl border border-line bg-panel/70 px-3 text-muted focus-within:border-brand/50">
              <Search size={16} aria-hidden />
              <span className="sr-only">Buscar time</span>
              <input
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setExpanded(false);
                }}
                placeholder="Buscar time"
                aria-label="Buscar time"
                className="w-full bg-transparent py-2.5 text-sm text-white outline-none placeholder:text-muted"
              />
            </label>
          </div>
        </div>
        {error ? (
          <div role="alert" className="card border-red-900 p-5 text-red-300">
            {error}
          </div>
        ) : visible.length ? (
          <>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {visible.map((m, i) => (
                <MatchCard key={m.id} m={m} index={i} />
              ))}
            </div>
            {filtered.length > 6 && (
              <div className="mt-6 flex justify-center">
                <button
                  type="button"
                  onClick={() => setExpanded(!expanded)}
                  aria-expanded={expanded}
                  className="flex items-center gap-2 rounded-xl border border-line bg-panel px-5 py-3 text-sm font-semibold text-muted transition hover:border-brand/40 hover:text-white"
                >
                  {expanded ? 'Mostrar menos' : `Ver agenda completa (${filtered.length})`}
                  <ChevronDown
                    size={17}
                    aria-hidden
                    className={expanded ? 'rotate-180 transition' : 'transition'}
                  />
                </button>
              </div>
            )}
          </>
        ) : (
          <Empty />
        )}
      </section>
    </main>
  );
}

function Summary({
  icon,
  value,
  label,
  accent,
}: {
  icon: React.ReactNode;
  value: string;
  label: string;
  accent?: boolean;
}) {
  return (
    <div className="rounded-2xl border border-white/[.07] bg-black/20 p-3.5">
      <div className={accent ? 'text-brand' : 'text-muted'}>{icon}</div>
      <div className="mt-3 text-xl font-black">{value}</div>
      <div className="mt-0.5 text-[11px] text-muted">{label}</div>
    </div>
  );
}

function Empty() {
  return (
    <div className="card flex flex-col items-center px-5 py-14 text-center">
      <div className="rounded-2xl bg-white/[.04] p-4 text-muted">
        <CalendarDays aria-hidden />
      </div>
      <h3 className="mt-4 font-bold">Nenhum jogo neste filtro</h3>
      <p className="mt-1 text-sm text-muted">Tente outro período ou busque por outro time.</p>
    </div>
  );
}
