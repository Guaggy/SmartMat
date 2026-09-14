const CASES = [
  {
    title: 'Rullestoler',
    body: 'Kontinuerlig overvåkning for brukere som sitter lenge i samme stilling, uten at belastningen blir usynlig for personalet.',
  },
  {
    title: 'Rehabilitering',
    body: 'Oversikt over trykk i setet under opptrening, langvarige samtaler eller transport i individuelle løsninger.',
  },
  {
    title: 'Høyrisiko brukere',
    body: 'Presis måling i de områdene som får mest belastning, slik at justering og støtte kan skje før ubehag utvikler seg.',
  },
  {
    title: 'Hjemme og kommune',
    body: 'Lokalt grensesnitt og varsler på telefon gir en enkel, proaktiv oppfølging i hverdagen uten behov for ekstra administrasjon.',
  },
]

export function UseCases() {
  return (
    <section id="use-cases" className="mx-auto max-w-6xl px-5 py-14 sm:px-8 sm:py-20">
      <div className="max-w-2xl">
        <p className="mb-3 text-xs font-semibold tracking-[0.16em] text-brand">
          Hvor det passer
        </p>
        <h2 className="text-balance text-3xl font-medium tracking-[-0.01em] text-ink sm:text-4xl">
          Byggd for bruk der en person sitter lenge i samme stilling.
        </h2>
      </div>

      <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {CASES.map((c) => (
          <div
            key={c.title}
            className="group flex flex-col rounded-xl bg-card p-6 ring-1 ring-border transition-all duration-300 ease-out hover:-translate-y-1 hover:shadow-lg hover:ring-brand/30"
          >
            <span aria-hidden="true" className="mb-4 h-0.5 w-6 rounded bg-brand transition-all duration-300 group-hover:w-10" />
            <h3 className="text-lg font-semibold tracking-tight text-ink">
              {c.title}
            </h3>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              {c.body}
            </p>
          </div>
        ))}
      </div>
    </section>
  )
}
