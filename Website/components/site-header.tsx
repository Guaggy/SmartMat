import { BrandMark } from '@/components/brand-mark'

const NAV = [
  { label: 'Teknologi', href: '#technology' },
  { label: 'Klinisk bruk', href: '#use-cases' },
  { label: 'Dokumentasjon', href: '#evidence' },
]

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-50 bg-hero text-hero-foreground">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5 sm:px-8">
        <a href="#top" className="flex items-center gap-2.5">
          <BrandMark className="h-6 w-6 text-brand" />
          <span className="text-lg font-semibold tracking-tight">
            Vilia<span className="text-hero-muted"> Medical</span>
          </span>
        </a>

        <nav className="hidden items-center gap-8 md:flex">
          {NAV.map((item) => (
            <a
              key={item.href}
              href={item.href}
              className="text-sm text-hero-foreground/80 transition-colors hover:text-hero-foreground"
            >
              {item.label}
            </a>
          ))}
        </nav>

        <a
          href="#contact"
          className="group inline-flex items-center gap-2 rounded-md border border-white/25 px-4 py-2 text-sm font-medium transition-colors hover:border-white/50 hover:bg-white/5"
        >
          Be om en demo
          <span aria-hidden="true" className="transition-transform group-hover:translate-x-0.5">
            →
          </span>
        </a>
      </div>
    </header>
  )
}
