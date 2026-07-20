'use client';

import { useCallback, useEffect, useState } from 'react';
import { KeyRound, RefreshCw, ScrollText, Users } from 'lucide-react';
import { apiFetch, clearToken, getToken } from '@/lib/api';

type Overview = {
  users: number;
  pending_users?: number;
  teams: number;
  matches: number;
  logs: { job: string; status: string; detail: unknown; created_at: string }[];
};
type ManagedUser = { id: number; email: string; role: 'user' | 'admin'; active: boolean; created_at: string };
type Invitation = { id: number; role: string; status: 'active' | 'used' | 'expired'; expires_at: string; used_at?: string | null };

type Provider = { name: string; healthy: boolean; error?: string };
type MlQuality = {
  matches?: number;
  usable_matches?: number;
  valid_matches?: number;
  review_matches?: number;
  excluded_matches?: number;
  teams?: number;
  eligible_for_training?: boolean;
};
type MlOverview = {
  seasons: { year: number; source: string; status: string; quality: MlQuality }[];
  matches: number;
  team_stats: number;
  player_stats: number;
  model_runs: {
    version: string;
    status: string;
    train_seasons: number[];
    test_season: number;
    train_samples: number;
    test_samples: number;
    metrics: { accuracy?: number; log_loss?: number; brier?: number; majority_baseline_accuracy?: number; baseline_log_loss?: number; baseline_brier?: number };
    created_at: string;
  }[];
  shadow: {
    active: boolean;
    model?: string;
    model_status?: string;
    round?: number | null;
    predictions: number;
    agreement_rate?: number | null;
    comparisons: {
      match_id: number;
      home_team: string;
      away_team: string;
      kickoff: string;
      status?: string;
      home_score?: number | null;
      away_score?: number | null;
      probabilities: Record<'home' | 'draw' | 'away', number>;
      comparison: {
        active_probabilities: Record<'home' | 'draw' | 'away', number>;
        active_pick: 'home' | 'draw' | 'away';
        shadow_pick: 'home' | 'draw' | 'away';
        same_pick: boolean;
        max_probability_delta: number;
      };
    }[];
    backtest?: {
      games: number;
      shadow_accuracy: number | null;
      active_accuracy: number | null;
      shadow_log_loss: number | null;
      active_log_loss: number | null;
      matches: {
        match_id: number;
        home_team: string;
        away_team: string;
        home_score: number;
        away_score: number;
        kickoff: string;
        probabilities: Record<'home' | 'draw' | 'away', number>;
        comparison: {
          outcome: 'home' | 'draw' | 'away';
          active_pick: 'home' | 'draw' | 'away';
          shadow_pick: 'home' | 'draw' | 'away';
          active_correct: boolean;
          shadow_correct: boolean;
        };
      }[];
    };
  };
};

export default function Admin() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [inviteLink, setInviteLink] = useState('');
  const [mlOverview, setMlOverview] = useState<MlOverview | null>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [actionBusy, setActionBusy] = useState(false);
  const [mlYear, setMlYear] = useState(2025);
  const [mlDetails, setMlDetails] = useState(false);
  const [mlMessage, setMlMessage] = useState('');

  const load = useCallback(async () => {
    if (!getToken()) {
      location.href = '/login';
      return;
    }
    setLoading(true);
    setError('');
    const [ov, pr, ml, us, inv] = await Promise.all([
      apiFetch('/admin/overview'),
      apiFetch('/admin/providers'),
      apiFetch('/admin/ml/overview'),
      apiFetch('/admin/users'),
      apiFetch('/admin/invitations'),
    ]);
    if (ov.status === 401 || pr.status === 401) {
      clearToken();
      location.href = '/login';
      return;
    }
    if (ov.status === 403 || pr.status === 403) {
      setError('Sua conta está autenticada, mas não possui permissão de administrador.');
      setLoading(false);
      return;
    }
    if (!ov.ok) {
      setError('Não foi possível carregar o painel.');
      setLoading(false);
      return;
    }
    setOverview(await ov.json());
    if (pr.ok) setProviders(await pr.json());
    if (ml.ok) setMlOverview(await ml.json());
    if (us.ok) setUsers(await us.json());
    if (inv.ok) setInvitations(await inv.json());
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function runAction(path: string, label: string) {
    setMessage('');
    setError('');
    setActionBusy(true);
    try {
      const r = await apiFetch(path, { method: 'POST' });
      if (r.status === 401) {
        clearToken();
        location.href = '/login';
        return;
      }
      if (r.status === 403) {
        setError('Sua conta não possui permissão para executar esta ação.');
        return;
      }
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        setError(typeof body.detail === 'string' ? body.detail : `Falha em ${label}`);
        return;
      }
      setMessage(body.status === 'queued'
        ? `${label} enviado para a fila.`
        : `${label} concluído.`);
      await load();
      return body;
    } catch {
      setError(`Não foi possível executar ${label}.`);
      return null;
    } finally {
      setActionBusy(false);
    }
  }

  async function runMlImport() {
    setMlMessage('Enviando importação…');
    const result = await runAction(
      `/admin/ml/import-bzzoiro?year=${mlYear}&include_details=${mlDetails}`,
      `Histórico ML ${mlYear}`,
    );
    if (result?.status === 'queued') {
      setMlMessage('Importação na fila. O resultado aparecerá em “Últimos jobs”.');
      [2500, 5000, 10000].forEach(delay => window.setTimeout(() => load(), delay));
    } else if (result) {
      setMlMessage('Importação concluída.');
    } else {
      setMlMessage('A importação não pôde ser iniciada. Veja a mensagem de erro acima.');
    }
  }

  async function runMlTraining() {
    setMlMessage('Enviando treinamento…');
    const result = await runAction('/admin/ml/train', 'Treinamento do modelo');
    if (result?.status === 'queued') {
      setMlMessage('Treinamento na fila. As métricas aparecerão abaixo quando terminar.');
      [2500, 5000, 10000, 20000, 40000, 60000].forEach(delay => window.setTimeout(() => load(), delay));
    } else if (!result) {
      setMlMessage('Não foi possível iniciar o treinamento.');
    }
  }

  async function runShadow() {
    setMlMessage('Atualizando previsões em modo sombra…');
    const result = await runAction('/admin/ml/shadow/materialize', 'ML sombra');
    if (result?.status === 'queued') {
      setMlMessage('ML sombra na fila. As comparações aparecerão abaixo.');
      [2500, 5000, 10000].forEach(delay => window.setTimeout(() => load(), delay));
    }
  }

  async function updateUser(user: ManagedUser, changes: Partial<Pick<ManagedUser, 'active' | 'role'>>) {
    setActionBusy(true); setError(''); setMessage('');
    try {
      const response = await apiFetch(`/admin/users/${user.id}`, {
        method: 'PATCH', body: JSON.stringify(changes),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) { setError(body.detail || 'Não foi possível alterar o acesso.'); return; }
      setMessage(`Acesso de ${user.email} atualizado.`);
      await load();
    } finally { setActionBusy(false); }
  }

  async function createInvite() {
    setActionBusy(true); setError(''); setInviteLink('');
    try {
      const response = await apiFetch('/admin/invitations', {
        method: 'POST', body: JSON.stringify({ role: 'user', expires_hours: 72 }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) { setError(body.detail || 'Não foi possível criar o convite.'); return; }
      const link = `${location.origin}/login?invite=${encodeURIComponent(body.invite_code)}`;
      setInviteLink(link);
      await navigator.clipboard?.writeText(link).catch(() => undefined);
      setMessage('Convite criado e copiado. Ele vale por 72 horas e pode ser usado uma vez.');
      await load();
    } finally { setActionBusy(false); }
  }

  if (loading && !overview) {
    return (
      <main className="mx-auto max-w-6xl px-5 py-10" aria-busy="true">
        <p className="text-muted">Carregando painel…</p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-6xl px-5 py-10">
      <div className="label text-brand">Operação</div>
      <h1 className="mt-2 text-4xl font-black">Painel administrativo</h1>
      <p className="mt-3 text-muted">Visão operacional e disparo de sincronizações (JWT admin).</p>

      {error && (
        <p role="alert" className="mt-4 text-sm text-red-400">
          {error}
        </p>
      )}
      {message && (
        <p role="status" className="mt-4 text-sm text-brand">
          {message}
        </p>
      )}

      <section className="mt-8 grid gap-4 sm:grid-cols-3">
        <Stat icon={<Users aria-hidden />} label="Usuários" value={overview?.users ?? 0} />
        <Stat icon={<KeyRound aria-hidden />} label="Times" value={overview?.teams ?? 0} />
        <Stat icon={<ScrollText aria-hidden />} label="Partidas" value={overview?.matches ?? 0} />
      </section>

      <section className="card mt-8 overflow-hidden">
        <div className="flex flex-col justify-between gap-4 border-b border-line p-5 md:flex-row md:items-end md:px-6">
          <div><div className="label text-brand">Controle de acesso</div><h2 className="mt-1 text-xl font-bold">Usuários e convites</h2><p className="mt-1 text-sm text-muted">Cadastros sem convite aguardam sua aprovação.</p></div>
          <Action disabled={actionBusy} label="Gerar convite de usuário" onClick={createInvite}/>
        </div>
        {inviteLink && <div className="border-b border-line bg-brand/[.04] p-4 md:px-6"><div className="text-xs text-muted">Link de uso único · válido por 72 horas</div><div className="mt-2 flex gap-2"><input readOnly value={inviteLink} className="min-w-0 flex-1 rounded-lg border border-line bg-black/20 px-3 py-2 text-xs text-white"/><button type="button" onClick={() => navigator.clipboard.writeText(inviteLink)} className="rounded-lg border border-line px-3 text-xs font-bold hover:text-brand">Copiar</button></div></div>}
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="bg-black/15 text-xs uppercase tracking-wide text-muted"><tr><th className="px-5 py-3">Usuário</th><th className="px-3 py-3">Situação</th><th className="px-3 py-3">Perfil</th><th className="px-5 py-3 text-right">Ações</th></tr></thead>
            <tbody>{users.map(user => <tr key={user.id} className="border-t border-line/70"><td className="px-5 py-3"><b className="block text-white">{user.email}</b><span className="text-xs text-muted">Cadastro {new Date(user.created_at).toLocaleDateString('pt-BR')}</span></td><td className="px-3 py-3"><span className={user.active ? 'text-brand' : 'text-amber-300'}>{user.active ? 'Liberado' : 'Pendente/bloqueado'}</span></td><td className="px-3 py-3"><span className={user.role === 'admin' ? 'text-brand' : 'text-muted'}>{user.role === 'admin' ? 'Administrador' : 'Usuário'}</span></td><td className="px-5 py-3"><div className="flex justify-end gap-2">{!user.active ? <SmallAction label="Aprovar" onClick={() => updateUser(user, { active: true })}/> : <SmallAction label="Bloquear" danger onClick={() => updateUser(user, { active: false })}/>}<SmallAction label={user.role === 'admin' ? 'Remover admin' : 'Tornar admin'} onClick={() => updateUser(user, { role: user.role === 'admin' ? 'user' : 'admin' })}/></div></td></tr>)}</tbody>
          </table>
          {!users.length && <p className="p-5 text-sm text-muted">Nenhum usuário encontrado.</p>}
        </div>
        {!!invitations.length && <div className="border-t border-line px-5 py-4 text-xs text-muted md:px-6"><b className="mr-3 text-white">Convites recentes</b>{invitations.slice(0,6).map(invitation => <span key={invitation.id} className="mr-3 inline-block">#{invitation.id} · {invitation.status === 'active' ? 'ativo' : invitation.status === 'used' ? 'utilizado' : 'expirado'}</span>)}</div>}
      </section>

      <section className="mt-8" aria-busy={actionBusy}>
        <h2 className="text-xl font-bold">Ações</h2>
        <div className="mt-4 flex flex-wrap gap-3">
          <Action
            disabled={actionBusy}
            onClick={() => runAction('/admin/refresh', 'Pipeline completo')}
            label={actionBusy ? 'Executando…' : 'Fila refresh'}
          />
          <Action
            disabled={actionBusy}
            onClick={() => runAction('/admin/sync/fixtures', 'Sync fixtures')}
            label="Sync fixtures"
          />
          <Action
            disabled={actionBusy}
            onClick={() => runAction('/admin/sync/odds', 'Sync odds')}
            label="Sync odds"
          />
          <Action
            disabled={actionBusy}
            onClick={() => runAction('/admin/sync/api-futebol-index', 'Índice API Futebol')}
            label="Índice API Futebol"
          />
          <Action
            disabled={actionBusy}
            onClick={() => runAction('/admin/sync/predictions', 'Predições')}
            label="Materializar predições"
          />
          <Action
            disabled={actionBusy}
            onClick={() => runAction('/admin/sync/bzzoiro-today', 'Bzzoiro e escalações')}
            label="Importar Bzzoiro"
          />
        </div>
        <div className="mt-5 flex flex-wrap items-end gap-3 rounded-2xl border border-line bg-white/[.02] p-4">
          <label className="text-xs text-muted">Temporada Série A
            <input type="number" min="2001" max={new Date().getFullYear()} value={mlYear}
              onChange={event => setMlYear(Number(event.target.value))}
              className="mt-1 block w-28 rounded-lg border border-line bg-black/20 px-3 py-2 text-sm text-white"/>
          </label>
          <label className="mb-2 flex items-center gap-2 text-xs text-muted">
            <input type="checkbox" checked={mlDetails}
              onChange={event => setMlDetails(event.target.checked)}/>
            Incluir estatísticas e jogadores (mais demorado)
          </label>
          <Action disabled={actionBusy} label="Importar histórico para ML"
            onClick={runMlImport}/>
          <Action disabled={actionBusy || (mlOverview?.seasons || []).filter(s => s.quality?.eligible_for_training).length < 2}
            label="Treinar modelo de resultados" onClick={runMlTraining}/>
          <Action disabled={actionBusy || !mlOverview?.model_runs?.length}
            label="Atualizar ML sombra" onClick={runShadow}/>
          {mlMessage && (
            <p role="status" className="w-full text-sm text-brand">{mlMessage}</p>
          )}
        </div>
      </section>

      <section className="mt-8 card p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="label text-brand">Base histórica de ML</div>
            <h2 className="mt-1 text-xl font-bold">Qualidade para treinamento</h2>
          </div>
          <div className="text-sm text-muted">
            {mlOverview?.matches ?? 0} registros brutos · {mlOverview?.team_stats ?? 0} scouts de time · {mlOverview?.player_stats ?? 0} scouts de jogador
          </div>
        </div>
        <div className="mt-5 rounded-xl border border-brand/30 bg-brand/[.04] p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <b>Modo sombra · {mlOverview?.shadow?.round ? `rodada ${mlOverview.shadow.round}` : 'próxima rodada'}</b>
            <span className={mlOverview?.shadow?.active ? 'text-brand' : 'text-amber-300'}>
              {mlOverview?.shadow?.active
                ? `${mlOverview.shadow.model_status === 'approved' ? 'modelo aprovado' : 'modelo experimental'}, sem afetar recomendações`
                : 'aguardando a primeira execução'}
            </span>
          </div>
          <p className="mt-2 text-sm text-muted">
            {mlOverview?.shadow?.predictions ?? 0} jogos da rodada comparados
            {mlOverview?.shadow?.agreement_rate != null
              ? ` · concordância com o modelo atual: ${(mlOverview.shadow.agreement_rate * 100).toFixed(1)}%`
              : ' · aguardando comparações'}
          </p>
          <p className="mt-1 text-xs text-muted">
            Comparação do mercado 1X2 somente para todos os jogos da próxima rodada. Partidas de rodadas posteriores não entram nesta tabela.
          </p>
          {!!mlOverview?.shadow?.comparisons?.length && (
            <div className="mt-4 overflow-x-auto rounded-xl border border-line">
              <table className="w-full min-w-[760px] text-left text-sm">
                <thead className="bg-black/20 text-xs uppercase tracking-wide text-muted">
                  <tr>
                    <th className="px-3 py-3">Jogo</th>
                    <th className="px-3 py-3">Modelo atual</th>
                    <th className="px-3 py-3">ML sombra</th>
                    <th className="px-3 py-3">Diferença</th>
                    <th className="px-3 py-3">Leitura</th>
                  </tr>
                </thead>
                <tbody>
                  {mlOverview.shadow.comparisons.slice(0, 10).map(row => {
                    const labels = { home: row.home_team, draw: 'Empate', away: row.away_team };
                    const activePick = row.comparison.active_pick;
                    const shadowPick = row.comparison.shadow_pick;
                    return (
                      <tr key={row.match_id} className="border-t border-line/70">
                        <td className="px-3 py-3">
                          <b className="block text-white">{row.home_team} × {row.away_team}</b>
                          <span className="text-xs text-muted">{new Date(row.kickoff).toLocaleString('pt-BR')}</span>
                          {row.status === 'finished' && (
                            <span className="ml-2 rounded bg-brand/10 px-1.5 py-0.5 text-[10px] text-brand">
                              Final: {row.home_score}–{row.away_score}
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-3">
                          <b className="block text-white">{labels[activePick]}</b>
                          <span className="text-muted">{((row.comparison.active_probabilities[activePick] || 0) * 100).toFixed(1)}%</span>
                        </td>
                        <td className="px-3 py-3">
                          <b className="block text-white">{labels[shadowPick]}</b>
                          <span className="text-muted">{((row.probabilities[shadowPick] || 0) * 100).toFixed(1)}%</span>
                        </td>
                        <td className="px-3 py-3 font-bold text-amber-300">
                          {((row.comparison.max_probability_delta || 0) * 100).toFixed(1)} p.p.
                        </td>
                        <td className={row.comparison.same_pick ? 'px-3 py-3 text-brand' : 'px-3 py-3 text-amber-300'}>
                          {row.comparison.same_pick ? 'Concordam' : 'Divergem'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          {!!mlOverview?.shadow?.backtest?.games && (
            <div className="mt-5 border-t border-line pt-5">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <div className="label text-brand">Últimos 7 dias</div>
                  <h3 className="mt-1 font-bold text-white">Backtest com resultados reais</h3>
                </div>
                <span className="text-xs text-muted">Sem usar dados posteriores a cada partida</span>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                <span className="rounded-lg bg-black/15 p-3 text-sm text-muted"><b className="block text-xl text-white">{mlOverview.shadow.backtest.games}</b>jogos</span>
                <span className="rounded-lg bg-black/15 p-3 text-sm text-muted"><b className="block text-xl text-white">{((mlOverview.shadow.backtest.active_accuracy || 0) * 100).toFixed(1)}%</b>acerto atual</span>
                <span className="rounded-lg bg-black/15 p-3 text-sm text-muted"><b className="block text-xl text-white">{((mlOverview.shadow.backtest.shadow_accuracy || 0) * 100).toFixed(1)}%</b>acerto ML</span>
                <span className="rounded-lg bg-black/15 p-3 text-sm text-muted"><b className="block text-xl text-white">{(mlOverview.shadow.backtest.shadow_log_loss || 0).toFixed(3)}</b>log loss ML</span>
              </div>
              <div className="mt-4 overflow-x-auto rounded-xl border border-line">
                <table className="w-full min-w-[720px] text-left text-sm">
                  <thead className="bg-black/20 text-xs uppercase tracking-wide text-muted">
                    <tr><th className="px-3 py-3">Jogo</th><th className="px-3 py-3">Placar</th><th className="px-3 py-3">Modelo atual</th><th className="px-3 py-3">ML sombra</th></tr>
                  </thead>
                  <tbody>
                    {mlOverview.shadow.backtest.matches.map(row => {
                      const labels = { home: row.home_team, draw: 'Empate', away: row.away_team };
                      return (
                        <tr key={row.match_id} className="border-t border-line/70">
                          <td className="px-3 py-3"><b className="block text-white">{row.home_team} × {row.away_team}</b><span className="text-xs text-muted">{new Date(row.kickoff).toLocaleString('pt-BR')}</span></td>
                          <td className="px-3 py-3"><b className="text-white">{row.home_score}–{row.away_score}</b><span className="ml-2 text-xs text-muted">{labels[row.comparison.outcome]}</span></td>
                          <td className={row.comparison.active_correct ? 'px-3 py-3 text-brand' : 'px-3 py-3 text-red-400'}>{labels[row.comparison.active_pick]} · {row.comparison.active_correct ? 'acertou' : 'errou'}</td>
                          <td className={row.comparison.shadow_correct ? 'px-3 py-3 text-brand' : 'px-3 py-3 text-red-400'}>{labels[row.comparison.shadow_pick]} · {row.comparison.shadow_correct ? 'acertou' : 'errou'}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
        <div className="mt-5 grid gap-3 md:grid-cols-2">
          {(mlOverview?.seasons || []).map(season => {
            const quality = season.quality || {};
            return (
              <div key={`${season.source}-${season.year}`} className="rounded-xl border border-line bg-black/10 p-4">
                <div className="flex items-center justify-between gap-3">
                  <b>Brasileirão {season.year} <small className="ml-1 font-normal text-muted">{season.source}</small></b>
                  <span className={quality.eligible_for_training ? 'text-brand' : 'text-amber-300'}>
                    {quality.eligible_for_training ? 'pronto para treinar' : 'requer revisão'}
                  </span>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2 text-sm text-muted sm:grid-cols-4">
                  <span><b className="block text-white">{quality.valid_matches ?? 0}</b>válidas</span>
                  <span><b className="block text-white">{quality.excluded_matches ?? 0}</b>excluídas</span>
                  <span><b className="block text-white">{quality.review_matches ?? 0}</b>em revisão</span>
                  <span><b className="block text-white">{quality.teams ?? 0}</b>clubes</span>
                </div>
              </div>
            );
          })}
          {!mlOverview?.seasons?.length && <p className="text-sm text-muted">Nenhuma temporada importada.</p>}
        </div>
        {mlOverview?.model_runs?.[0] && (() => {
          const run = mlOverview.model_runs[0];
          return (
            <div className="mt-5 rounded-xl border border-brand/30 bg-brand/[.04] p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <b>Modelo mais recente</b>
                <span className={run.status === 'approved' ? 'text-xs text-brand' : 'text-xs text-amber-300'}>
                  {run.status === 'approved' ? 'aprovado para integração' : 'experimental — não ativo'}
                </span>
              </div>
              <div className="mt-1 text-xs text-muted">{run.version}</div>
              <p className="mt-2 text-sm text-muted">
                Treino: {run.train_seasons.join(', ')} ({run.train_samples} jogos) · Teste temporal: {run.test_season} ({run.test_samples} jogos)
              </p>
              <div className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                <span><b className="block text-xl text-white">{((run.metrics.accuracy || 0) * 100).toFixed(1)}%</b>acurácia</span>
                <span><b className="block text-xl text-white">{(run.metrics.log_loss || 0).toFixed(3)}</b>log loss</span>
                <span><b className="block text-xl text-white">{(run.metrics.brier || 0).toFixed(3)}</b>Brier</span>
                <span><b className="block text-xl text-white">{((run.metrics.majority_baseline_accuracy || 0) * 100).toFixed(1)}%</b>baseline simples</span>
              </div>
              <p className="mt-3 text-xs text-muted">
                Baseline probabilística: log loss {(run.metrics.baseline_log_loss || 0).toFixed(3)} · Brier {(run.metrics.baseline_brier || 0).toFixed(3)}
              </p>
            </div>
          );
        })()}
      </section>

      <section className="mt-10 grid gap-6 lg:grid-cols-2">
        <div className="card p-6">
          <div className="flex items-center gap-2 text-brand">
            <RefreshCw size={18} aria-hidden />
            <h2 className="font-bold text-white">Providers</h2>
          </div>
          <ul className="mt-4 space-y-3">
            {providers.map((p) => (
              <li key={p.name} className="flex items-center justify-between text-sm">
                <span>{p.name}</span>
                <span className={p.healthy ? 'text-brand' : 'text-red-400'}>
                  {p.healthy ? 'ok' : p.error || 'falha'}
                </span>
              </li>
            ))}
            {!providers.length && <li className="text-muted">Sem diagnóstico.</li>}
          </ul>
        </div>
        <div className="card p-6">
          <div className="flex items-center gap-2 text-brand">
            <ScrollText size={18} aria-hidden />
            <h2 className="font-bold text-white">Últimos jobs</h2>
          </div>
          <ul className="mt-4 max-h-80 space-y-3 overflow-auto text-sm">
            {(overview?.logs || []).map((log, i) => (
              <li key={`${log.job}-${log.created_at}-${i}`} className="border-b border-line/50 pb-2">
                <div className="flex justify-between gap-2">
                  <b>{log.job}</b>
                  <span className={log.status === 'success' ? 'text-brand' : log.status === 'queued' ? 'text-amber-300' : 'text-red-400'}>
                    {log.status === 'success' ? 'concluído' : log.status === 'queued' ? 'na fila' : 'falhou'}
                  </span>
                </div>
                <div className="mt-1 text-xs text-muted">
                  {new Date(log.created_at).toLocaleString('pt-BR')}
                </div>
              </li>
            ))}
            {!overview?.logs?.length && <li className="text-muted">Nenhum log ainda.</li>}
          </ul>
        </div>
      </section>
    </main>
  );
}

function Stat({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
}) {
  return (
    <div className="card p-5">
      <div className="text-brand">{icon}</div>
      <div className="label mt-3">{label}</div>
      <b className="mt-1 block text-3xl">{value}</b>
    </div>
  );
}

function Action({
  onClick,
  label,
  disabled,
}: {
  onClick: () => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="rounded-xl border border-line bg-white/[.03] px-4 py-2 text-sm font-medium hover:border-brand/40 disabled:cursor-not-allowed disabled:opacity-50"
    >
      {label}
    </button>
  );
}

function SmallAction({ label, onClick, danger = false }: { label: string; onClick: () => void; danger?: boolean }) {
  return <button type="button" onClick={onClick}
    className={`rounded-lg border px-2.5 py-1.5 text-xs transition ${danger ? 'border-red-400/20 text-red-300 hover:border-red-400/50' : 'border-line text-muted hover:border-brand/40 hover:text-white'}`}>
    {label}
  </button>;
}
