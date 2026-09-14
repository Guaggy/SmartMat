import { BrandMark } from '@/components/brand-mark'

export function CallToAction() {
  return (
    <section id="contact" className="mx-auto max-w-6xl px-5 py-8 sm:px-8">
      <div className="relative overflow-hidden rounded-2xl bg-hero px-6 py-14 text-center sm:px-12 sm:py-20">
        <h2 className="mx-auto max-w-2xl text-balance text-3xl font-medium tracking-[-0.01em] text-hero-foreground sm:text-4xl">
          Se Verdia Stol overvåke en stol i sanntid.
        </h2>
        <p className="mx-auto mt-4 max-w-xl text-pretty text-[17px] leading-relaxed text-hero-foreground/75">
          Vi samarbeider med et lite utvalg av teams og kliniske partnere om tidlig evaluering av produktet. Fortell oss om deres situasjon, så kan vi avtale en live demo.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <a
            href="mailto:hello@verdia.medical"
            className="inline-flex items-center gap-2 rounded-md bg-brand px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-brand-strong"
          >
            Be om en demo
            <span aria-hidden="true">→</span>
          </a>
          <a
            href="#technology"
            className="inline-flex items-center gap-2 rounded-md border border-white/25 px-5 py-3 text-sm font-medium text-hero-foreground transition-colors hover:border-white/50 hover:bg-white/5"
          >
            Les om teknologien
          </a>
        </div>
      </div>
    </section>
  )
}

export function SiteFooter() {
  return (
    <footer className="mx-auto max-w-6xl px-5 py-12 sm:px-8">
      <div className="flex flex-col items-start justify-between gap-6 border-t border-border pt-8 sm:flex-row sm:items-center">
        <div className="flex items-center gap-2.5">
          <BrandMark className="h-5 w-5 text-brand" />
          <span className="font-semibold tracking-tight text-ink">
            Verdia Medical
          </span>
        </div>
        <p className="max-w-md text-sm text-muted-foreground">
          Verdia Stol er et prototypekonsept og er ikke en erstatning for klinisk skjønn eller etablerte behandlingsrutiner.
        </p>
        <p className="text-sm text-muted-foreground">
          © {new Date().getFullYear()} Verdia Medical
        </p>
      </div>
    </footer>
  )
}
