import type { ReactNode } from 'react'

type Props = {
  id?: string
  eyebrow: string
  titleLead: string
  title: string
  body: string
  points: string[]
  visual: ReactNode
  reverse?: boolean
}

export function FeatureRow({
  id,
  eyebrow,
  titleLead,
  title,
  body,
  points,
  visual,
  reverse,
}: Props) {
  return (
    <section id={id} className="mx-auto max-w-6xl px-5 py-4 sm:px-8">
      <div className="group rounded-2xl bg-card p-6 shadow-sm ring-1 ring-border transition-all duration-300 ease-out hover:-translate-y-1 hover:shadow-xl hover:ring-brand/30 sm:p-10 lg:p-14">
        <div className="grid items-center gap-10 lg:grid-cols-2 lg:gap-16">
          <div className={reverse ? 'lg:order-2' : ''}>
            <p className="mb-3 text-xs font-semibold uppercase tracking-[0.16em] text-brand">
              {eyebrow}
            </p>
            <h3 className="text-balance text-2xl font-medium tracking-[-0.01em] text-ink sm:text-3xl">
              <span className="text-brand">{titleLead}</span> {title}
            </h3>
            <p className="mt-4 text-pretty text-[17px] leading-relaxed text-muted-foreground">
              {body}
            </p>
            <ul className="mt-6 space-y-3">
              {points.map((p) => (
                <li key={p} className="flex gap-3 text-[15px] text-ink/90">
                  <span aria-hidden="true" className="mt-2.5 h-px w-4 shrink-0 bg-brand transition-all duration-300 group-hover:w-6" />
                  <span>{p}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className={reverse ? 'lg:order-1' : ''}>
            <div className="transition-transform duration-300 ease-out group-hover:scale-[1.015]">
              {visual}
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
