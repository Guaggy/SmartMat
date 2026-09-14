export function Hero() {
  return (
    <section id="top" className="relative isolate overflow-hidden bg-hero">
      {/* background */}
      <div className="absolute inset-0 -z-10">
        <img
          src="/hero-ward.png"
          alt=""
          className="h-full w-full object-cover opacity-70"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-hero via-hero/70 to-hero/30" />
        <div className="absolute inset-0 bg-gradient-to-r from-hero/80 to-transparent" />
      </div>

      <div className="mx-auto flex min-h-[calc(100svh-4rem)] max-w-6xl flex-col justify-end px-5 pb-16 pt-24 sm:px-8 sm:pb-24">
        <p className="mb-6 flex items-center gap-2 text-sm font-medium text-hero-muted">
          <span className="inline-block size-1.5 rounded-full bg-brand" />
          SmartMat trykksensor-matte
        </p>

        <h1 className="max-w-4xl text-balance text-4xl font-medium leading-[1.05] tracking-[-0.02em] text-hero-foreground sm:text-6xl">
          Stopp liggesår{' '}
          <span className="text-brand">før de oppstår.</span>
        </h1>

        <p className="mt-6 max-w-lg text-pretty text-[17px] leading-relaxed text-hero-foreground/75">
          En tynn matte som måler trykk i sanntid og varsler når en pasient
          bør snus.
        </p>

        <div className="mt-9 flex flex-wrap items-center gap-3">
          <a
            href="#contact"
            className="inline-flex items-center gap-2 rounded-md bg-brand px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-brand-strong"
          >
            Be om en klinisk demo
            <span aria-hidden="true">→</span>
          </a>
          <a
            href="#technology"
            className="inline-flex items-center gap-2 rounded-md border border-white/25 px-5 py-3 text-sm font-medium text-hero-foreground transition-colors hover:border-white/50 hover:bg-white/5"
          >
            Slik fungerer det
          </a>
        </div>
      </div>
    </section>
  )
}
