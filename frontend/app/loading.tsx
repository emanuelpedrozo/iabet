export default function Loading() {
  return (
    <main className="mx-auto max-w-7xl px-5 pb-14 pt-8" aria-busy="true" aria-label="Carregando">
      <div className="hero-panel animate-pulse overflow-hidden rounded-[28px] border border-line px-6 py-7 md:px-9 md:py-9">
        <div className="h-4 w-40 rounded bg-white/10" />
        <div className="mt-4 h-10 max-w-xl rounded bg-white/10" />
        <div className="mt-3 h-4 max-w-md rounded bg-white/5" />
        <div className="mt-8 grid grid-cols-3 gap-2 lg:max-w-sm">
          <div className="h-20 rounded-2xl bg-white/5" />
          <div className="h-20 rounded-2xl bg-white/5" />
          <div className="h-20 rounded-2xl bg-white/5" />
        </div>
      </div>
      <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="card min-h-[280px] animate-pulse p-5">
            <div className="h-3 w-24 rounded bg-white/10" />
            <div className="mt-6 flex justify-center gap-8">
              <div className="h-14 w-14 rounded-2xl bg-white/5" />
              <div className="h-14 w-14 rounded-2xl bg-white/5" />
            </div>
            <div className="mt-8 h-16 rounded-xl bg-white/5" />
            <div className="mt-4 h-10 rounded-xl bg-white/10" />
          </div>
        ))}
      </div>
    </main>
  );
}
