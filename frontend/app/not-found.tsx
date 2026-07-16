import Link from 'next/link';

export default function NotFound() {
  return (
    <main className="mx-auto max-w-lg px-5 py-20 text-center">
      <h1 className="text-3xl font-black">Página não encontrada</h1>
      <p role="status" className="mt-3 text-muted">
        O recurso pedido não existe ou foi removido.
      </p>
      <Link href="/" className="mt-6 inline-block rounded-xl bg-brand px-5 py-3 font-bold text-ink">
        Voltar aos jogos
      </Link>
    </main>
  );
}
