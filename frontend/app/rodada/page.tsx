import { CalendarDays, CheckCircle2, Clock3 } from 'lucide-react';
import { MatchCard } from '@/components/match-card';
import { getNextRound, getStandings, type RoundMatches, type Standings } from '@/lib/api';

export default async function RoundPage() {
  let round: RoundMatches | null = null;
  let standings: Standings | null = null;
  let error = '';
  const [roundResult, standingsResult] = await Promise.allSettled([
    getNextRound(),
    getStandings(),
  ]);
  if (roundResult.status === 'fulfilled') round = roundResult.value;
  else error = 'Não foi possível carregar a próxima rodada.';
  if (standingsResult.status === 'fulfilled') standings = standingsResult.value;

  const positions = Object.fromEntries(
    (standings?.table || []).map((row) => [row.team.id, row.position]),
  );
  const completed = round?.matches.filter((match) => match.status === 'finished').length || 0;
  const scheduled = round?.matches.filter((match) => match.status === 'scheduled').length || 0;

  return (
    <main className="mx-auto max-w-7xl px-5 pb-14 pt-9">
      <section className="hero-panel rounded-[28px] border border-line px-6 py-7 md:px-9">
        <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
          <div>
            <div className="label">Agenda completa · {round?.competition || 'Brasileirão Série A'}</div>
            <h1 className="mt-2 text-3xl font-black md:text-5xl">
              {round ? `Rodada ${round.round}` : 'Próxima rodada'}
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-muted md:text-base">
              Todos os jogos da rodada em ordem cronológica, com probabilidades, classificação e acesso à análise completa.
            </p>
          </div>
          {round && (
            <div className="flex flex-wrap gap-2 text-xs">
              <Summary icon={<CalendarDays size={16} />} label={`${round.matches.length} jogos`} />
              <Summary icon={<Clock3 size={16} />} label={`${scheduled} agendados`} />
              <Summary icon={<CheckCircle2 size={16} />} label={`${completed} finalizados`} />
            </div>
          )}
        </div>
      </section>

      <section className="mt-8" aria-labelledby="round-games-title">
        <div className="mb-5">
          <div className="label">Temporada {round?.season || 'atual'}</div>
          <h2 id="round-games-title" className="mt-1 text-2xl font-bold">Todos os confrontos</h2>
          <p className="mt-1 text-sm text-muted">Os jogos concluídos continuam visíveis para completar a leitura da rodada.</p>
        </div>
        {error ? (
          <div role="alert" className="card border-red-900 p-5 text-red-300">{error}</div>
        ) : round?.matches.length ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {round.matches.map((match, index) => (
              <MatchCard key={match.id} m={match} index={index} positions={positions} />
            ))}
          </div>
        ) : (
          <div className="card p-8 text-center text-muted">Nenhum jogo encontrado para a próxima rodada.</div>
        )}
      </section>
    </main>
  );
}

function Summary({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <div className="flex items-center gap-2 rounded-xl border border-line bg-black/20 px-3 py-2 text-muted">
      <span className="text-brand">{icon}</span>
      <b className="text-white">{label}</b>
    </div>
  );
}
