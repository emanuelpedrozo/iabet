'use client';

import { useState } from 'react';
import Link from 'next/link';
import { motion, useReducedMotion } from 'framer-motion';
import { ArrowUpRight, Download, MapPin, Star } from 'lucide-react';
import type { Match, Team as TeamType } from '@/lib/api';
import { API } from '@/lib/api';

const pct = (n: number) => `${Math.round(n * 100)}%`;

const marketLabels: Record<string, string> = {
  match_result: 'Resultado da partida',
  goals_2_5: 'Total de gols',
  totals: 'Total de gols',
  btts: 'Ambas marcam',
  corners: 'Escanteios',
  cards: 'Cartões',
  shots: 'Finalizações',
};

const selectionLabels: Record<string, string> = {
  home: 'Vitória do mandante',
  away: 'Vitória do visitante',
  draw: 'Empate',
  over: 'Mais de',
  under: 'Menos de',
  yes: 'Sim',
  no: 'Não',
};

function bestValueLabel(value: NonNullable<Match['best_value']>) {
  const market = marketLabels[value.market] ?? value.market.replaceAll('_', ' ');
  let selection = selectionLabels[value.selection] ?? value.selection.replaceAll('_', ' ');

  if (value.line != null && (value.selection === 'over' || value.selection === 'under')) {
    selection += ` ${value.line.toLocaleString('pt-BR', { maximumFractionDigits: 2 })}`;
  }

  return `${market} · ${selection}`;
}

export function MatchCard({ m, index, positions = {} }: { m: Match; index: number; positions?: Record<number, number> }) {
  const reduceMotion = useReducedMotion();
  const motionProps = reduceMotion
    ? {}
    : {
        initial: { opacity: 0, y: 14 },
        animate: { opacity: 1, y: 0 },
        transition: { delay: Math.min(index, 6) * 0.06 },
      };

  return (
    <motion.article
      {...motionProps}
      className="card flex min-h-[390px] flex-col p-5 shadow-glow"
    >
      <div className="flex min-h-[45px] items-start justify-between gap-3">
        <div className="min-w-0">
          <span className="label block truncate">{m.competition}</span>
          <div className="mt-1 flex items-center gap-1 truncate text-xs text-muted">
            <MapPin size={12} className="shrink-0" aria-hidden />
            {m.venue || 'A definir'} ·{' '}
            {new Date(m.kickoff).toLocaleString('pt-BR', {
              day: '2-digit',
              month: '2-digit',
              hour: '2-digit',
              minute: '2-digit',
            })}
          </div>
        </div>
        {m.best_value && (
          <span className="shrink-0 rounded-full bg-brand/10 px-2.5 py-1 text-xs font-semibold text-brand">
            Value +{pct(m.best_value.edge)}
          </span>
        )}
      </div>
      <div className="my-4 grid min-h-[104px] grid-cols-[1fr_28px_1fr] items-center">
        <Team team={m.home_team} position={positions[m.home_team.id]} />
        <div className="text-center text-sm text-muted">×</div>
        <Team team={m.away_team} position={positions[m.away_team.id]} />
      </div>
      <div className="grid grid-cols-3 gap-3 border-t border-line/70 pt-4">
        <Probability label="Casa" value={m.probabilities?.home} />
        <Probability label="Empate" value={m.probabilities?.draw} />
        <Probability label="Fora" value={m.probabilities?.away} />
      </div>
      <div className="mt-auto pt-4">
        {m.best_value ? (
          <div className="rounded-xl border border-brand/20 bg-brand/[.04] p-3">
            <div className="flex justify-between text-xs">
              <span className="text-muted">Melhor oportunidade</span>
              <span className="flex items-center gap-1 text-amber-300">
                <Star size={12} aria-hidden />
                {m.best_value.strength}
              </span>
            </div>
            <div className="mt-1 flex min-h-[40px] items-end justify-between gap-3">
              <b className="min-w-0 flex-1 line-clamp-2 leading-5" title={bestValueLabel(m.best_value)}>
                {bestValueLabel(m.best_value)}
              </b>
              <b className="shrink-0 text-xl text-brand">{m.best_value.odd.toFixed(2)}</b>
            </div>
          </div>
        ) : (
          <ModelPick m={m} />
        )}
        <div className="mt-4 flex gap-2">
          <Link
            href={`/jogos/${m.id}`}
            className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-brand py-2.5 text-sm font-bold text-ink"
          >
            Análise completa <ArrowUpRight size={16} aria-hidden />
          </Link>
          <a
            href={`${API}/reports/${m.id}.pdf`}
            aria-label={`Baixar PDF da análise ${m.home_team.name} versus ${m.away_team.name}`}
            className="rounded-xl border border-line p-2.5 text-muted hover:text-white"
          >
            <Download size={18} aria-hidden />
          </a>
        </div>
      </div>
    </motion.article>
  );
}

function ModelPick({ m }: { m: Match }) {
  const pick = m.model_pick;
  if (!pick) {
    return <div className="rounded-xl bg-white/[.03] p-3 text-sm text-muted">Análise em processamento</div>;
  }
  const label = pick.selection === 'home'
    ? `Vitória do ${m.home_team.name}`
    : pick.selection === 'away'
      ? `Vitória do ${m.away_team.name}`
      : 'Empate';
  return (
    <div className="rounded-xl border border-line bg-white/[.025] p-3">
      <div className="flex items-center justify-between gap-3 text-xs text-muted">
        <span>Resultado mais provável</span>
        <b className="text-white">{pct(pick.estimated_probability)}</b>
      </div>
      <div className="mt-1 flex min-h-[40px] items-end justify-between gap-3">
        <b className="min-w-0 flex-1 line-clamp-2 leading-5" title={label}>{label}</b>
        {pick.odd != null && <b className="shrink-0 text-lg">{pick.odd.toFixed(2)}</b>}
      </div>
      <div className="mt-1 text-[11px] text-muted">
        Odd justa {pick.fair_odd?.toFixed(2) ?? '—'} · sem value no preço atual
      </div>
    </div>
  );
}

function Team({ team, position }: { team: TeamType; position?: number }) {
  return (
    <div className="flex min-w-0 flex-col items-center text-center">
      <Crest team={team} />
      <div className="mt-2 flex min-h-[40px] max-w-[150px] items-start justify-center gap-1.5 text-sm font-semibold leading-5">
        <span className="line-clamp-2">{team.name}</span>
        {position && <span className="mt-0.5 shrink-0 rounded bg-white/[.06] px-1.5 py-0.5 text-[10px] leading-4 text-muted">{position}º</span>}
      </div>
    </div>
  );
}

function Crest({ team }: { team: TeamType }) {
  const [failed, setFailed] = useState(false);
  return (
    <div className="relative flex h-14 w-14 items-center justify-center rounded-2xl border border-line bg-white/[.04] font-black text-white">
      {(!team.crest_url || failed) && <span>{team.short_name.slice(0, 3)}</span>}
      {team.crest_url && !failed && (
        <img
          src={team.crest_url}
          alt={`Escudo do ${team.name}`}
          onError={() => setFailed(true)}
          className="absolute inset-1 h-12 w-12 object-contain"
        />
      )}
    </div>
  );
}

function Probability({ label, value }: { label: string; value?: number }) {
  const ready = typeof value === 'number';
  return (
    <div className="min-w-0">
      <div className="mb-1.5 flex items-center justify-between gap-1 text-xs">
        <span className="truncate text-muted">{label}</span>
        <b>{ready ? pct(value) : '—'}</b>
      </div>
      <div className="bar">
        <span style={{ width: ready ? pct(value) : '0%' }} />
      </div>
    </div>
  );
}
