'use client';

import { useEffect, useState } from 'react';
import { BrainCircuit, Database, FlaskConical, Gauge, RefreshCw } from 'lucide-react';
import { apiFetch } from '@/lib/api';

export default function MachineLearningPage() {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    apiFetch('/ml/overview').then(async response => {
      if (!response.ok) { setError('Não foi possível carregar os dados de Machine Learning.'); return; }
      setData(await response.json());
    }).catch(() => setError('Não foi possível carregar os dados de Machine Learning.'));
  }, []);

  if (error) return <main className="mx-auto max-w-7xl px-5 py-10"><p className="text-red-400">{error}</p></main>;
  if (!data) return <main className="mx-auto max-w-7xl px-5 py-10"><div className="flex items-center gap-2 text-muted"><RefreshCw className="animate-spin" size={17}/>Carregando modelos…</div></main>;

  const shadow = data.shadow || {};
  const backtest = shadow.backtest || {};
  const run = data.model_runs?.[0];
  return <main className="mx-auto max-w-7xl px-5 pb-16 pt-10">
    <div className="label text-brand">Inteligência preditiva</div>
    <div className="mt-2 flex flex-col justify-between gap-4 md:flex-row md:items-end">
      <div><h1 className="text-4xl font-black">Machine Learning</h1><p className="mt-2 max-w-3xl text-muted">Painel somente de leitura para acompanhar qualidade, previsões e desempenho dos modelos.</p></div>
      <span className={`w-fit rounded-full border px-3 py-1.5 text-xs ${shadow.active?'border-brand/30 bg-brand/5 text-brand':'border-amber-300/30 text-amber-300'}`}>{shadow.active?'Modo sombra ativo':'Aguardando modelo sombra'}</span>
    </div>

    <section className="mt-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Metric icon={<Database/>} label="Partidas históricas" value={data.matches || 0}/>
      <Metric icon={<BrainCircuit/>} label="Modelos treinados" value={data.model_runs?.length || 0}/>
      <Metric icon={<FlaskConical/>} label="Jogos comparados" value={shadow.predictions || 0}/>
      <Metric icon={<Gauge/>} label="Concordância" value={shadow.agreement_rate == null?'—':pct(shadow.agreement_rate,1)}/>
    </section>

    <section className="card mt-6 p-5 md:p-6">
      <SectionTitle eyebrow={`Modo sombra · ${shadow.round ? `rodada ${shadow.round}` : 'próxima rodada'}`} title="Modelo atual × ML sombra" description="Comparação 1X2 e mercados auxiliares. As cores indicam probabilidade, não valor contra a odd."/>
      {shadow.comparisons?.length ? <div className="mt-5 overflow-x-auto rounded-xl border border-line"><table className="w-full min-w-[900px] text-left text-sm"><thead className="bg-black/20 text-xs uppercase text-muted"><tr><th className="p-3">Jogo</th><th className="p-3">Modelo atual</th><th className="p-3">ML sombra</th><th className="p-3">Diferença</th><th className="p-3">Leitura</th></tr></thead><tbody>{shadow.comparisons.map((row:any)=><ComparisonRow key={row.match_id} row={row}/>)}</tbody></table></div>:<Empty text="Ainda não há jogos comparados para a próxima rodada."/>}
    </section>

    <section className="card mt-6 p-5 md:p-6">
      <SectionTitle eyebrow={`Últimos ${backtest.window_days || 30} dias`} title="Backtest com resultados reais" description="Avaliação temporal sem utilizar informações posteriores à partida."/>
      <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-6">
        <SmallMetric value={backtest.games || 0} label="jogos"/><SmallMetric value={pct(backtest.active_accuracy)} label="acerto atual"/><SmallMetric value={pct(backtest.shadow_accuracy)} label="acerto ML"/><SmallMetric value={number(backtest.shadow_log_loss)} label="log loss ML"/><SmallMetric value={backtest.draws || 0} label="empates reais"/><SmallMetric value={`Atual ${pct(backtest.active_draw_recall,0)} · ML ${pct(backtest.shadow_draw_recall,0)}`} label="empates detectados" compact/>
      </div>
      {backtest.matches?.length ? <div className="mt-5 overflow-x-auto rounded-xl border border-line"><table className="w-full min-w-[760px] text-left text-sm"><thead className="bg-black/20 text-xs uppercase text-muted"><tr><th className="p-3">Jogo</th><th className="p-3">Placar</th><th className="p-3">Modelo atual</th><th className="p-3">ML sombra</th></tr></thead><tbody>{backtest.matches.map((row:any)=><BacktestRow key={row.match_id} row={row}/>)}</tbody></table></div>:<Empty text="Ainda não existem partidas finalizadas nesta janela."/>}
    </section>

    <div className="mt-6 grid gap-6 xl:grid-cols-[1.1fr_.9fr]">
      <section className="card p-5 md:p-6"><SectionTitle eyebrow="Base histórica" title="Qualidade das temporadas" description={`${data.team_stats || 0} scouts de time · ${data.player_stats || 0} scouts de jogador`}/><div className="mt-5 grid gap-3 sm:grid-cols-2">{(data.seasons||[]).map((season:any)=><Season key={`${season.source}-${season.year}`} season={season}/>)}</div></section>
      <section className="card p-5 md:p-6"><SectionTitle eyebrow="Versão mais recente" title="Desempenho do modelo" description={run?.version || 'Nenhum treinamento concluído'}/>{run?<ModelRun run={run}/>:<Empty text="Nenhum modelo treinado."/>}</section>
    </div>
  </main>;
}

function ComparisonRow({row}:{row:any}) { const c=row.comparison||{}; const labels:any={home:row.home_team,draw:'Empate',away:row.away_team}; return <tr className="border-t border-line/70"><td className="p-3"><a href={`/jogos/${row.match_id}`} className="font-bold text-white hover:text-brand">{row.home_team} × {row.away_team}</a><span className="mt-1 block text-xs text-muted">{date(row.kickoff)}</span></td><td className="p-3"><b>{labels[c.active_pick]}</b><span className="block text-muted">{pct(c.active_probabilities?.[c.active_pick])}</span><Chips p={c.active_probabilities}/></td><td className="p-3"><b>{labels[c.shadow_pick]}</b><span className="block text-muted">{pct(row.probabilities?.[c.shadow_pick])}</span><Chips p={row.probabilities}/></td><td className="p-3 font-bold text-amber-300">{pct(c.max_probability_delta,1)} p.p.</td><td className={c.same_pick?'p-3 text-brand':'p-3 text-amber-300'}>{c.same_pick?'Concordam':'Divergem'}</td></tr> }
function BacktestRow({row}:{row:any}) { const c=row.comparison; const labels:any={home:row.home_team,draw:'Empate',away:row.away_team}; return <tr className="border-t border-line/70"><td className="p-3"><a href={`/jogos/${row.match_id}`} className="font-bold hover:text-brand">{row.home_team} × {row.away_team}</a><span className="block text-xs text-muted">{date(row.kickoff)}</span></td><td className="p-3"><b>{row.home_score}–{row.away_score}</b><span className="ml-2 text-xs text-muted">{labels[c.outcome]}</span></td><Pick correct={c.active_correct} label={labels[c.active_pick]} probabilities={c.active_probabilities}/><Pick correct={c.shadow_correct} label={labels[c.shadow_pick]} probabilities={row.probabilities}/></tr> }
function Pick({correct,label,probabilities}:{correct:boolean;label:string;probabilities:any}) { return <td className={correct?'p-3 text-brand':'p-3 text-red-400'}>{label} · {correct?'acertou':'errou'}<span className="block text-[11px] text-muted">C {pct(probabilities?.home,0)} · E {pct(probabilities?.draw,0)} · F {pct(probabilities?.away,0)}</span></td> }
function Chips({p}:{p:any}) { return <div className="mt-2 flex flex-wrap gap-1"><Chip label="+2,5 gols" value={p?.goals_over_2_5??p?.over_2_5}/><Chip label="+9,5 esc." value={p?.corners_over_9_5}/><Chip label="+4,5 cartões" value={p?.cards_over_4_5}/></div> }
function Chip({label,value}:{label:string;value?:number}) { if(value==null)return null; const tone=value>=.6?'bg-brand/10 text-brand':value>=.5?'bg-amber-300/10 text-amber-300':'bg-white/[.05] text-muted'; return <span className={`rounded px-1.5 py-1 text-[10px] ${tone}`}>{label} {pct(value,0)}</span> }
function Season({season}:{season:any}) { const q=season.quality||{}; return <div className="rounded-xl border border-line bg-black/10 p-4"><div className="flex justify-between gap-2"><b>Brasileirão {season.year} <small className="font-normal text-muted">{season.source}</small></b><span className={q.eligible_for_training?'text-brand':'text-amber-300'}>{q.eligible_for_training?'pronta':'revisão'}</span></div><div className="mt-3 grid grid-cols-4 gap-2 text-xs text-muted"><span><b className="block text-base text-white">{q.valid_matches||0}</b>válidas</span><span><b className="block text-base text-white">{q.excluded_matches||0}</b>excluídas</span><span><b className="block text-base text-white">{q.review_matches||0}</b>revisão</span><span><b className="block text-base text-white">{q.teams||0}</b>clubes</span></div></div> }
function ModelRun({run}:{run:any}) { const m=run.metrics||{}; return <><div className="mt-5 grid grid-cols-2 gap-3"><SmallMetric value={pct(m.accuracy)} label="acurácia"/><SmallMetric value={number(m.log_loss)} label="log loss"/><SmallMetric value={number(m.brier)} label="Brier"/><SmallMetric value={pct(m.majority_baseline_accuracy)} label="baseline simples"/></div><p className="mt-4 text-xs text-muted">Treino: {run.train_seasons?.join(', ')} ({run.train_samples} jogos) · teste: {run.test_season} ({run.test_samples} jogos)</p><div className="mt-4 space-y-2">{[['goals_over_2_5','Mais de 2,5 gols'],['corners_over_9_5','Mais de 9,5 escanteios'],['cards_over_4_5','Mais de 4,5 cartões']].map(([key,label])=>{const market=m.markets?.[key];return <div key={key} className="flex justify-between rounded-lg bg-black/15 p-3 text-xs"><b>{label}</b><span className={market?.available?(market.approved?'text-brand':'text-amber-300'):'text-muted'}>{market?.available?`${pct(market.accuracy)} · ${market.approved?'validado':'experimental'}`:'sem amostra'}</span></div>})}</div></> }
function Metric({icon,label,value}:{icon:React.ReactNode;label:string;value:any}) { return <div className="card p-5"><div className="text-brand">{icon}</div><div className="label mt-3">{label}</div><b className="mt-1 block text-3xl">{value}</b></div> }
function SmallMetric({value,label,compact=false}:{value:any;label:string;compact?:boolean}) { return <div className="rounded-xl bg-black/15 p-3 text-sm text-muted"><b className={`block text-white ${compact?'text-sm':'text-xl'}`}>{value}</b>{label}</div> }
function SectionTitle({eyebrow,title,description}:{eyebrow:string;title:string;description:string}) { return <div><div className="label text-brand">{eyebrow}</div><h2 className="mt-1 text-xl font-bold">{title}</h2><p className="mt-1 text-sm text-muted">{description}</p></div> }
function Empty({text}:{text:string}) { return <p className="mt-5 rounded-xl border border-line bg-black/10 p-5 text-sm text-muted">{text}</p> }
function pct(value:any,digits=1){return value==null?'—':`${(Number(value)*100).toFixed(digits)}%`}
function number(value:any){return value==null?'—':Number(value).toFixed(3)}
function date(value:string){return new Date(value).toLocaleString('pt-BR')}
