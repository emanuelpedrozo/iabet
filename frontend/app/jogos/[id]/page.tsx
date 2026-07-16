import { API, getAnalysis } from '@/lib/api';
import { Download, ShieldAlert, TrendingUp } from 'lucide-react';
import { notFound } from 'next/navigation';

type Prediction = {
  home: number;
  draw: number;
  away: number;
  score: string;
  xg_home: number;
  xg_away: number;
  over_2_5: number;
  btts_yes: number;
};

export default async function Analysis({ params }: { params: { id: string } }) {
  let d;
  try {
    d = await getAnalysis(params.id);
  } catch {
    notFound();
  }
  const p = d.prediction as Prediction | null | undefined;
  const m = d.match;
  const valueBets = Array.isArray(d.value_bets) ? d.value_bets : [];

  return (
    <main className="mx-auto max-w-6xl px-5 py-10">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="label">
            {m.competition} • análise pré-jogo
          </div>
          <h1 className="mt-2 break-words text-2xl font-black md:text-4xl">
            {m.home_team.name} <span className="text-muted">×</span> {m.away_team.name}
          </h1>
          <p className="mt-2 text-muted">
            {new Date(m.kickoff).toLocaleString('pt-BR')} • {m.venue || 'A definir'}
          </p>
        </div>
        <a
          className="flex items-center gap-2 rounded-xl bg-brand px-4 py-3 font-bold text-ink"
          href={`${API}/reports/${m.id}.pdf`}
          aria-label={`Baixar PDF da análise ${m.home_team.name} versus ${m.away_team.name}`}
        >
          <Download size={18} aria-hidden />
          Gerar PDF
        </a>
      </div>

      {!p ? (
        <div role="status" className="card border-amber-900/40 p-6 text-amber-200">
          <h2 className="text-xl font-bold">Predição pendente</h2>
          <p className="mt-2 text-sm leading-6 text-muted">
            O ensemble ainda não foi materializado para esta partida. Aguarde o próximo ciclo do
            pipeline ou peça a um administrador para sincronizar as predições.
          </p>
        </div>
      ) : (
        <>
          <section className="grid gap-4 md:grid-cols-4">
            <Kpi label="Casa" value={`${Math.round(p.home * 100)}%`} />
            <Kpi label="Empate" value={`${Math.round(p.draw * 100)}%`} />
            <Kpi label="Fora" value={`${Math.round(p.away * 100)}%`} />
            <Kpi label="Placar modal" value={p.score} />
          </section>
          <section className="mt-5 grid gap-5 lg:grid-cols-[1.5fr_1fr]">
            <div className="card p-6">
              <h2 className="text-xl font-bold">Value bets</h2>
              <p className="mt-1 text-sm text-muted">
                De-vig, consenso entre casas, movimento de odd e ranking por confiança.
              </p>
              <div className="mt-5 space-y-3">
                {valueBets.length ? (
                  valueBets.map(
                    (
                      v: {
                        market: string;
                        selection: string;
                        line?: number | null;
                        odd: number;
                        estimated_probability: number;
                        implied_probability: number;
                        edge: number;
                        suggested_stake_units: number;
                        confidence?: number;
                        strength?: string;
                        odds_move_pct?: number | null;
                        consensus_odd?: number | null;
                        books_covering?: number;
                      },
                      i: number,
                    ) => (
                      <div key={i} className="rounded-xl border border-line p-4">
                        <div className="flex justify-between gap-3">
                          <b>
                            {v.market} · {v.selection}
                            {v.line != null ? ` (${v.line})` : ''}
                            {i === 0 ? (
                              <span className="ml-2 text-xs font-semibold text-brand">melhor</span>
                            ) : null}
                          </b>
                          <span className="text-brand">{v.odd.toFixed(2)}</span>
                        </div>
                        <div className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-3 lg:grid-cols-6">
                          <Data
                            label="Modelo"
                            value={`${(v.estimated_probability * 100).toFixed(1)}%`}
                          />
                          <Data
                            label="Justa"
                            value={`${(v.implied_probability * 100).toFixed(1)}%`}
                          />
                          <Data label="Edge" value={`+${(v.edge * 100).toFixed(1)}%`} />
                          <Data label="Stake" value={`${v.suggested_stake_units}u`} />
                          <Data
                            label="Confiança"
                            value={
                              typeof v.confidence === 'number'
                                ? `${Math.round(v.confidence * 100)}%`
                                : v.strength || '—'
                            }
                          />
                          <Data
                            label="Movimento"
                            value={
                              typeof v.odds_move_pct === 'number'
                                ? `${v.odds_move_pct >= 0 ? '+' : ''}${(v.odds_move_pct * 100).toFixed(1)}%`
                                : '—'
                            }
                          />
                        </div>
                        {typeof v.consensus_odd === 'number' ? (
                          <p className="mt-2 text-xs text-muted">
                            Consenso {v.consensus_odd.toFixed(2)}
                            {v.books_covering ? ` · ${v.books_covering} casas` : ''}
                          </p>
                        ) : null}
                      </div>
                    ),
                  )
                ) : (
                  <p className="rounded-xl bg-white/[.03] p-4 text-muted">
                    Nenhuma linha supera o preço justo com os limiares atuais.
                  </p>
                )}
              </div>
            </div>
            <div className="space-y-5">
              <div className="card p-6">
                <TrendingUp className="text-brand" aria-hidden />
                <h2 className="mt-3 font-bold">Gols esperados</h2>
                <div className="mt-4 flex justify-between text-3xl font-black">
                  <span>{p.xg_home}</span>
                  <span className="text-muted">—</span>
                  <span>{p.xg_away}</span>
                </div>
                <div className="mt-4 text-sm text-muted">
                  Over 2,5: {(p.over_2_5 * 100).toFixed(1)}%
                  <br />
                  Ambas marcam: {(p.btts_yes * 100).toFixed(1)}%
                </div>
              </div>
              <div className="card p-6">
                <ShieldAlert className="text-amber-300" aria-hidden />
                <h2 className="mt-3 font-bold">Nota de risco</h2>
                <p className="mt-2 text-sm leading-6 text-muted">
                  Probabilidades são estimativas. Confirme escalações e preços; use stakes pequenas e
                  limites de perda.
                </p>
              </div>
            </div>
          </section>
        </>
      )}
    </main>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="card p-5">
      <div className="label">{label}</div>
      <b className="mt-2 block text-3xl">{value}</b>
    </div>
  );
}

function Data({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-muted">{label}</span>
      <b className="mt-1 block">{value}</b>
    </div>
  );
}
