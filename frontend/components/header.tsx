'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Activity, ChartNoAxesCombined, Menu, X } from 'lucide-react';
import { AuthNav } from '@/components/auth-nav';
import { useAuth } from '@/lib/use-auth';

export function Header() {
  const pathname = usePathname();
  const { isAdmin } = useAuth();
  const [open, setOpen] = useState(false);

  const jogosActive = pathname === '/';
  const adminActive = pathname.startsWith('/admin');
  const mlActive = pathname.startsWith('/machine-learning');
  const ajudaActive = pathname.startsWith('/ajuda');

  function close() {
    setOpen(false);
  }

  const linkClass = (active: boolean) =>
    `text-sm transition ${active ? 'text-white' : 'text-muted hover:text-white'}`;

  return (
    <header className="sticky top-0 z-20 border-b border-line/70 bg-ink/85 backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-5 py-4">
        <Link href="/" className="flex items-center gap-3" onClick={close}>
          <div className="rounded-xl bg-brand p-2 text-ink" aria-hidden>
            <ChartNoAxesCombined size={22} />
          </div>
          <div>
            <b className="text-lg">
              IA<span className="text-brand">Bet</span>
            </b>
            <div className="label">Inteligência esportiva</div>
          </div>
        </Link>

        <nav className="hidden items-center gap-6 md:flex" aria-label="Principal">
          <Link href="/" className={linkClass(jogosActive)}>
            Jogos
          </Link>
          {isAdmin && (
            <Link href="/machine-learning" className={linkClass(mlActive)}>
              Machine Learning
            </Link>
          )}
          <Link href="/ajuda" className={linkClass(ajudaActive)}>
            Ajuda
          </Link>
          {isAdmin && (
            <Link href="/admin" className={linkClass(adminActive)}>
              Admin
            </Link>
          )}
        </nav>

        <div className="flex items-center gap-2 sm:gap-3">
          <div className="hidden items-center gap-2 rounded-full border border-brand/20 bg-brand/5 px-3 py-2 text-xs text-brand sm:flex">
            <Activity size={14} aria-hidden /> dados monitorados
          </div>
          <AuthNav />
          <button
            type="button"
            className="rounded-xl border border-line p-2 text-muted hover:text-white md:hidden"
            aria-expanded={open}
            aria-controls="mobile-nav"
            aria-label={open ? 'Fechar menu' : 'Abrir menu'}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? <X size={20} aria-hidden /> : <Menu size={20} aria-hidden />}
          </button>
        </div>
      </div>

      {open && (
        <nav
          id="mobile-nav"
          className="border-t border-line/70 px-5 py-4 md:hidden"
          aria-label="Menu mobile"
        >
          <ul className="flex flex-col gap-3">
            <li>
              <Link href="/" className={linkClass(jogosActive)} onClick={close}>
                Jogos
              </Link>
            </li>
            {isAdmin && (
              <li>
                <Link href="/machine-learning" className={linkClass(mlActive)} onClick={close}>
                  Machine Learning
                </Link>
              </li>
            )}
            <li>
              <Link href="/ajuda" className={linkClass(ajudaActive)} onClick={close}>
                Ajuda
              </Link>
            </li>
            {isAdmin && (
              <li>
                <Link href="/admin" className={linkClass(adminActive)} onClick={close}>
                  Admin
                </Link>
              </li>
            )}
          </ul>
        </nav>
      )}
    </header>
  );
}
