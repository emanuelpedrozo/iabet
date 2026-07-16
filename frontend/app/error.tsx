'use client';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="mx-auto max-w-lg px-5 py-20 text-center">
      <h1 className="text-3xl font-black">Algo deu errado</h1>
      <p role="alert" className="mt-3 text-muted">
        {error.message || 'Não foi possível carregar esta página.'}
      </p>
      <button
        type="button"
        onClick={reset}
        className="mt-6 rounded-xl bg-brand px-5 py-3 font-bold text-ink"
      >
        Tentar de novo
      </button>
    </main>
  );
}
