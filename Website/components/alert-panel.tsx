// Mock nurse-facing alert surface.

const ALERTS = [
  {
    room: 'Rom 14 · Seng A',
    status: 'action',
    title: 'Snuing forfalt',
    detail: 'Høyt korsryggtrykk i 1t 58m',
    time: 'nå',
  },
  {
    room: 'Rom 09 · Seng B',
    status: 'watch',
    title: 'Nærmer seg grensen',
    detail: 'Venstre hæl stigende siste 40m',
    time: '6m',
  },
  {
    room: 'Rom 22 · Seng A',
    status: 'ok',
    title: 'Snudd',
    detail: 'Trykk omfordelt — tidtaker nullstilt',
    time: '18m',
  },
]

const STATUS: Record<string, { dot: string; chip: string; label: string }> = {
  action: {
    dot: 'bg-[rgb(206_62_62)]',
    chip: 'bg-[rgb(206_62_62)]/15 text-[rgb(240_140_140)]',
    label: 'Handle nå',
  },
  watch: {
    dot: 'bg-[rgb(222_130_54)]',
    chip: 'bg-[rgb(222_130_54)]/15 text-[rgb(232_170_110)]',
    label: 'Følg med',
  },
  ok: {
    dot: 'bg-brand',
    chip: 'bg-brand/15 text-brand',
    label: 'OK',
  },
}

export function AlertPanel() {
  return (
    <figure className="sensor-grid rounded-xl bg-hero p-5 sm:p-6">
      <div className="mb-5 flex items-center justify-between">
        <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-hero-muted">
          Ward view · turning queue
        </p>
        <span className="flex items-center gap-1.5 text-[11px] font-medium text-hero-muted">
          <span className="inline-block size-1.5 animate-pulse rounded-full bg-brand" />
          Live
        </span>
      </div>

      <ul className="space-y-3">
        {ALERTS.map((a) => {
          const s = STATUS[a.status]
          return (
            <li
              key={a.room}
              className="flex items-start gap-3 rounded-lg bg-white/[0.04] p-3.5 ring-1 ring-white/10"
            >
              <span className={`mt-1 inline-block size-2.5 shrink-0 rounded-full ${s.dot}`} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate text-sm font-semibold text-hero-foreground">
                    {a.title}
                  </p>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${s.chip}`}>
                    {s.label}
                  </span>
                </div>
                <p className="mt-0.5 text-xs text-hero-foreground/70">{a.detail}</p>
                <p className="mt-1 text-[11px] text-hero-muted">
                  {a.room} · {a.time}
                </p>
              </div>
            </li>
          )
        })}
      </ul>
    </figure>
  )
}
