'use client';

import Link from 'next/link';
import { useAuth } from '@/lib/use-auth';

export function AuthNav() {
  const { loggedIn, logout } = useAuth();

  if (loggedIn) {
    return (
      <button
        type="button"
        onClick={logout}
        className="rounded-xl border border-line px-3 py-2 text-sm text-muted hover:text-white"
      >
        Sair
      </button>
    );
  }

  return (
    <Link
      href="/login"
      className="rounded-xl border border-line px-3 py-2 text-sm text-muted hover:text-white"
    >
      Entrar
    </Link>
  );
}
