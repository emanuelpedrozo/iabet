'use client';

import { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';

export function LineupTeam({ team, lineup, unavailable, status, updatedAt, officialConfirmedAt, align = 'left' }: {
  team: any; lineup?: any; unavailable?: any[]; status?: string; updatedAt?: string; officialConfirmedAt?: string;
  align?: 'left' | 'right';
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const hasPlayers = Boolean(lineup?.players?.length);
  const missing = unavailable || [];
  const substitutes = (lineup?.substitutes || []).slice(0, status === 'predicted' ? 12 : 99);
  const label = status === 'confirmed' ? 'Oficial' : status === 'predicted' ? 'Provável' : 'Aguardando';

  useEffect(() => {
    if (!open) return;
    function outside(event: PointerEvent) {
      if (root.current && !root.current.contains(event.target as Node)) setOpen(false);
    }
    function keyboard(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false);
    }
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', keyboard);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('keydown', keyboard);
    };
  }, [open]);

  return <div ref={root} className="relative">
    <button type="button" onClick={() => setOpen(value => !value)} aria-expanded={open}
      className="flex items-center gap-3 rounded-xl p-1 text-left transition hover:bg-white/[.03]">
      <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-line bg-white/[.04]">
        {team.crest_url ? <img src={team.crest_url} alt="" className="h-11 w-11 object-contain" /> : <b>{team.short_name}</b>}
      </div>
      <div><div className="text-xs text-muted">{team.short_name}</div>
        <div className="text-lg font-black underline decoration-brand/40 decoration-1 underline-offset-4 md:text-2xl">{team.name}</div>
        <span className={`mt-1 inline-flex rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide ${status === 'confirmed' ? 'bg-brand/10 text-brand' : status === 'predicted' ? 'bg-amber-300/10 text-amber-200' : 'bg-white/[.05] text-muted'}`}>{label}</span>
      </div>
    </button>
    {open && <div role="dialog" aria-label={`Escalação do ${team.name}`}
      className={`absolute top-[calc(100%+.5rem)] z-30 max-h-[78vh] w-[min(560px,88vw)] overflow-y-auto rounded-2xl border border-line bg-panel p-4 shadow-2xl md:p-5 ${align === 'right' ? 'right-0' : 'left-0'}`}>
      <div className="flex items-start justify-between gap-3 border-b border-line pb-3">
        <div><b>{team.name}</b><div className="mt-1 text-xs text-muted">{hasPlayers ? `Formação ${lineup.formation || 'não informada'}` : 'Escalação ainda não publicada'}</div></div>
        <div className="flex items-center gap-2"><span className="text-xs text-brand">{label}</span>
          <button type="button" onClick={() => setOpen(false)} aria-label="Fechar escalação"
            className="rounded-lg border border-line p-1.5 text-muted transition hover:border-brand/40 hover:text-white"><X size={16} /></button>
        </div>
      </div>
      {hasPlayers ? <><LineupPitch players={lineup.players} formation={lineup.formation} />
        {substitutes.length > 0 && <div className="mt-4"><div className="label">{status === 'predicted' ? 'Principais alternativas' : 'Reservas'}</div><div className="mt-2 grid grid-cols-2 gap-1.5 sm:grid-cols-3">{substitutes.map((player: any) => <PlayerLine key={`${player.id}-${player.name}`} player={player} />)}</div></div>}</>
        : <p className="py-5 text-center text-sm text-muted">O IABet continuará consultando a fonte automaticamente antes do jogo.</p>}
      {missing.length > 0 && <div className="mt-4 border-t border-line pt-3"><div className="label text-amber-200">Desfalques e dúvidas</div><div className="mt-2 space-y-1">{missing.map((player: any) => <div key={`${player.id}-${player.name}`} className="text-xs"><b>{player.short_name || player.name}</b><span className="text-muted"> · {player.reason || player.status}</span></div>)}</div></div>}
      {(updatedAt || officialConfirmedAt) && <div className="mt-3 space-y-1 border-t border-line pt-2 text-[10px] text-muted">
        {status === 'confirmed' && officialConfirmedAt && <div className="font-semibold text-brand">Oficial confirmada no IABet em {new Date(officialConfirmedAt).toLocaleString('pt-BR')}</div>}
        {updatedAt && <div>Fonte atualizada em {new Date(updatedAt).toLocaleString('pt-BR')} · Bzzoiro</div>}
      </div>}
    </div>}
  </div>;
}

function LineupPitch({ players, formation }: { players: any[]; formation?: string }) {
  const starters = players.slice(0, 11); const goalkeeper = starters.slice(0, 1); const outfield = starters.slice(1);
  const shape = (formation || '').split('-').map(Number).filter(number => Number.isFinite(number) && number > 0);
  const valid = shape.reduce((sum, number) => sum + number, 0) === outfield.length ? shape : defaultShape(outfield);
  let cursor = 0; const rows = [goalkeeper, ...valid.map(size => { const row = outfield.slice(cursor, cursor + size); cursor += size; return row; })];
  return <div className="mt-4"><div className="mb-2 flex items-center justify-between"><span className="label">Em campo</span><span className="text-[10px] text-muted">Ataque ↑</span></div><div className="relative overflow-hidden rounded-2xl border border-emerald-200/25 bg-[linear-gradient(180deg,rgba(16,110,67,.96),rgba(8,77,47,.96))] px-2 py-4 shadow-inner"><div className="pointer-events-none absolute inset-3 rounded-xl border border-white/25"/><div className="pointer-events-none absolute left-1/2 top-3 h-[18%] w-[42%] -translate-x-1/2 border border-t-0 border-white/25"/><div className="pointer-events-none absolute bottom-3 left-1/2 h-[18%] w-[42%] -translate-x-1/2 border border-b-0 border-white/25"/><div className="pointer-events-none absolute left-3 right-3 top-1/2 border-t border-white/25"/><div className="pointer-events-none absolute left-1/2 top-1/2 h-14 w-14 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/25"/><div className="relative z-10 flex min-h-[390px] flex-col-reverse justify-between gap-3 py-2">{rows.map((row, rowIndex) => <div key={rowIndex} className="flex min-h-12 items-center justify-around gap-1">{row.map((player: any) => <PitchPlayer key={`${player.id}-${player.name}`} player={player} />)}</div>)}</div></div></div>;
}

function defaultShape(players: any[]) { const counts = ['D', 'M', 'F'].map(position => players.filter(player => (player.position || '').toUpperCase().startsWith(position)).length).filter(Boolean); return counts.reduce((sum, number) => sum + number, 0) === players.length ? counts : [4, 3, Math.max(1, players.length - 7)]; }
function PitchPlayer({ player }: { player: any }) { return <div className="flex min-w-0 max-w-[88px] flex-col items-center text-center"><span className="flex h-8 w-8 items-center justify-center rounded-full border-2 border-white/80 bg-slate-950 text-[11px] font-black shadow-lg">{player.jersey_number ?? '—'}</span><b className="mt-1 max-w-full truncate rounded bg-black/45 px-1.5 py-0.5 text-[9px] text-white shadow-sm sm:text-[10px]">{player.short_name || player.name}</b></div>; }
function PlayerLine({ player }: { player: any }) { return <div className="flex min-w-0 items-center gap-1.5 rounded-lg bg-white/[.025] px-2 py-1.5 text-[11px]"><span className="w-5 shrink-0 text-center text-muted">{player.jersey_number ?? '—'}</span><b className="truncate">{player.short_name || player.name}</b><span className="ml-auto text-[8px] text-muted">{player.position}</span></div>; }
