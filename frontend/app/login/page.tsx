'use client';

import { FormEvent, useEffect, useState } from 'react';
import { API, getToken, setToken } from '@/lib/api';

export default function Login() {
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (getToken()) {
      location.href = '/';
    }
  }, []);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      const f = new FormData(e.currentTarget);
      const r = await fetch(`${API}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: f.get('email'), password: f.get('password') }),
      });
      if (!r.ok) {
        setError(
          r.status === 429 ? 'Muitas tentativas. Aguarde um minuto.' : 'Credenciais inválidas',
        );
        return;
      }
      const d = await r.json();
      setToken(d.access_token);
      location.href = d.role === 'admin' ? '/admin' : '/';
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto max-w-md px-5 py-20">
      <form onSubmit={submit} className="card p-8" aria-busy={submitting}>
        <div className="label text-brand">Área segura</div>
        <h1 className="mt-2 text-3xl font-black">Entrar no IABet</h1>
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
            autoComplete="current-password"
            required
            disabled={submitting}
            aria-invalid={Boolean(error)}
            className="mt-2 w-full rounded-xl border border-line bg-ink p-3 text-white"
          />
        </label>
        {error && (
          <p id="login-error" role="alert" className="mt-3 text-sm text-red-400">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={submitting}
          className="mt-6 w-full rounded-xl bg-brand p-3 font-bold text-ink disabled:opacity-60"
        >
          {submitting ? 'Entrando…' : 'Entrar'}
        </button>
      </form>
    </main>
  );
}
