export function Hero() {
  return (
    <section id="top" className="relative isolate overflow-hidden bg-hero">
      {/* background */}
      <div className="absolute inset-0 -z-10">
        <img
          src="https://images.unsplash.com/photo-1576765608535-5f04d1e3f289?auto=format&fit=crop&w=1600&q=80"
          alt="Eldreomsorg og hjemmehjelp i et varmt, trygt omsorgsmiljø"
          className="h-full w-full object-cover opacity-90"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-hero/65 via-hero/45 to-hero/20" />
        <div className="absolute inset-0 bg-gradient-to-r from-hero/50 to-transparent" />
      </div>

      <div className="mx-auto flex min-h-[calc(100svh-4rem)] max-w-6xl flex-col justify-end px-5 pb-16 pt-24 sm:px-8 sm:pb-24">
        <h1 className="max-w-4xl text-balance text-4xl font-medium leading-[1.05] tracking-[-0.02em] text-hero-foreground sm:text-6xl">
          Få kontroll over trykksår{' '}
          <span className="text-brand">før de oppstår.</span>
        </h1>

        <p className="mt-6 max-w-lg text-pretty text-[17px] leading-relaxed text-hero-foreground/75">
          En sensor som legges i en stolpute og måler trykk i sanntid, slik at personalet kan reagere før trykksår utvikler seg.
        </p>

        <div className="mt-9 flex flex-wrap items-center gap-3">
          <a
            href="#contact"
            className="inline-flex items-center gap-2 rounded-md bg-brand px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-brand-strong"
          >
            Be om en demo
            <span aria-hidden="true">→</span>
          </a>
        </div>
      </div>
    </section>
  )
}
