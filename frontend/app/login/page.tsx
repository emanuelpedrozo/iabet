'use client';

import { FormEvent, useEffect, useState } from 'react';
import { API, getToken, setToken } from '@/lib/api';

export default function Login() {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [inviteCode, setInviteCode] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (getToken()) {
      location.href = '/';
      return;
    }
    const invite = new URLSearchParams(location.search).get('invite');
    if (invite) { setInviteCode(invite); setMode('register'); }
  }, []);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError('');
    setNotice('');
    setSubmitting(true);
    try {
      const f = new FormData(e.currentTarget);
      const password = String(f.get('password') || '');
      const confirmation = String(f.get('password_confirmation') || '');
      if (mode === 'register' && password !== confirmation) {
        setError('As senhas não coincidem');
        return;
      }
      const r = await fetch(`${API}/auth/${mode === 'register' ? 'register' : 'login'}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: f.get('email'), password,
          invite_code: mode === 'register' ? inviteCode.trim() || null : undefined,
        }),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        setError(
          r.status === 429 ? 'Muitas tentativas. Aguarde um minuto.'
            : r.status === 409 ? 'Este e-mail já está cadastrado'
            : r.status === 403 ? 'Seu cadastro ainda aguarda aprovação do administrador.'
            : typeof body.detail === 'string' ? body.detail
            : mode === 'register' ? 'Não foi possível criar a conta' : 'Credenciais inválidas',
        );
        return;
      }
      const d = await r.json();
      if (d.status === 'pending') {
        setNotice('Conta criada. Aguarde a aprovação do administrador para entrar.');
        setMode('login');
        return;
      }
      setToken(d.access_token, d.role);
      location.href = d.role === 'admin' ? '/admin' : '/';
    } catch {
      setError('Não foi possível conectar à API. Tente novamente em alguns instantes.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto max-w-md px-5 py-20">
      <form onSubmit={submit} className="card p-8" aria-busy={submitting}>
        <div className="label text-brand">Área segura</div>
        <h1 className="mt-2 text-3xl font-black">{mode === 'login' ? 'Entrar no IABet' : 'Criar sua conta'}</h1>
        <label className="mt-7 block text-sm text-muted">
          E-mail
          <input
            name="email"
            type="email"
            autoComplete="email"
            required
            disabled={submitting}
            aria-invalid={Boolean(error)}
            aria-describedby={error ? 'login-error' : undefined}
            className="mt-2 w-full rounded-xl border border-line bg-ink p-3 text-white"
          />
        </label>
        <label className="mt-4 block text-sm text-muted">
          Senha
          <input
            name="password"
            type="password"
            autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
            minLength={8}
            required
            disabled={submitting}
            aria-invalid={Boolean(error)}
            className="mt-2 w-full rounded-xl border border-line bg-ink p-3 text-white"
          />
        </label>
        {mode === 'register' && <label className="mt-4 block text-sm text-muted">
          Confirmar senha
          <input name="password_confirmation" type="password" autoComplete="new-password"
            minLength={8} required disabled={submitting}
            className="mt-2 w-full rounded-xl border border-line bg-ink p-3 text-white"/>
        </label>}
        {mode === 'register' && <label className="mt-4 block text-sm text-muted">
          Código de convite <span className="text-xs">(opcional)</span>
          <input name="invite_code" value={inviteCode} onChange={event => setInviteCode(event.target.value)}
            autoComplete="off" disabled={submitting} placeholder="Sem convite, o cadastro ficará pendente"
            className="mt-2 w-full rounded-xl border border-line bg-ink p-3 text-sm text-white"/>
        </label>}
        {error && (
          <p id="login-error" role="alert" className="mt-3 text-sm text-red-400">
            {error}
          </p>
        )}
        {notice && <p role="status" className="mt-3 text-sm text-brand">{notice}</p>}
        <button
          type="submit"
          disabled={submitting}
          className="mt-6 w-full rounded-xl bg-brand p-3 font-bold text-ink disabled:opacity-60"
        >
          {submitting ? (mode === 'login' ? 'Entrando…' : 'Criando…') : (mode === 'login' ? 'Entrar' : 'Cadastrar')}
        </button>
        <button type="button" disabled={submitting}
          onClick={() => { setError(''); setNotice(''); setMode(mode === 'login' ? 'register' : 'login'); }}
          className="mt-4 w-full text-sm text-muted transition hover:text-brand">
          {mode === 'login' ? 'Ainda não tenho conta' : 'Já tenho uma conta'}
        </button>
      </form>
    </main>
  );
}
