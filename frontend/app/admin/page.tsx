'use client';

import { useCallback, useEffect, useState } from 'react';
import { KeyRound, RefreshCw, ScrollText, Users } from 'lucide-react';
import { apiFetch, clearToken, getToken } from '@/lib/api';

type Overview = {
  users: number;
  teams: number;
  matches: number;
  logs: { job: string; status: string; detail: unknown; created_at: string }[];
};

type Provider = { name: string; healthy: boolean; error?: string };

export default function Admin() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [actionBusy, setActionBusy] = useState(false);

  const load = useCallback(async () => {
    if (!getToken()) {
      location.href = '/login';
      return;
    }
    setLoading(true);
    setError('');
    const [ov, pr] = await Promise.all([
      apiFetch('/admin/overview'),
      apiFetch('/admin/providers'),
    ]);
    if (ov.status === 401 || ov.status === 403 || pr.status === 401 || pr.status === 403) {
      clearToken();
      location.href = '/login';
      return;
    }
    if (!ov.ok) {
      setError('Não foi possível carregar o painel.');
      setLoading(false);
      return;
    }
    setOverview(await ov.json());
    if (pr.ok) setProviders(await pr.json());
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
      if (r.status === 401 || r.status === 403) {
        clearToken();
        location.href = '/login';
        return;
      }
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        setError(typeof body.detail === 'string' ? body.detail : `Falha em ${label}`);
        return;
      }
      setMessage(`${label} concluído.`);
      await load();
    } finally {
      setActionBusy(false);
    }
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
        </div>
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
                  <span className={log.status === 'success' ? 'text-brand' : 'text-red-400'}>
                    {log.status}
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
