// Mock analytics visual: average pressure distribution over time.
// Placeholder for the live interactive chart added later.

const SERIES = [
  38, 42, 40, 47, 55, 62, 58, 66, 74, 82, 79, 71, 64, 52, 46, 41, 44, 39,
]
const THRESHOLD = 70

function buildPath(values: number[], w: number, h: number, pad = 6) {
  const max = 100
  const step = (w - pad * 2) / (values.length - 1)
  return values
    .map((v, i) => {
      const x = pad + i * step
      const y = pad + (1 - v / max) * (h - pad * 2)
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`
    })
    .join(' ')
}

export function AnalyticsPanel() {
  const w = 520
  const h = 240
  const line = buildPath(SERIES, w, h)
  const area = `${line} L${w - 6} ${h - 6} L6 ${h - 6} Z`
  const thresholdY = 6 + (1 - THRESHOLD / 100) * (h - 12)

  return (
    <figure className="rounded-xl bg-hero p-5 sm:p-6">
      <div className="mb-5 flex items-end justify-between">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-hero-muted">
            Gjennomsnittstrykk · korsrygg
          </p>
          <p className="mt-1 text-2xl font-semibold text-hero-foreground">
            82<span className="text-base font-normal text-hero-muted"> / 100 topp</span>
          </p>
        </div>
        <span className="rounded-full bg-brand/15 px-2.5 py-1 text-[11px] font-medium text-brand">
          Siste 90 min
        </span>
      </div>

      <svg viewBox={`0 0 ${w} ${h}`} className="w-full" role="img" aria-label="Line chart of average sacral pressure over the last 90 minutes, crossing the risk threshold near the end.">
        <defs>
          <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="rgb(63 158 139)" stopOpacity="0.35" />
            <stop offset="100%" stopColor="rgb(63 158 139)" stopOpacity="0" />
          </linearGradient>
        </defs>

        {[25, 50, 75].map((g) => (
          <line
            key={g}
            x1="6"
            x2={w - 6}
            y1={6 + (1 - g / 100) * (h - 12)}
            y2={6 + (1 - g / 100) * (h - 12)}
            stroke="white"
            strokeOpacity="0.07"
          />
        ))}

        <line
          x1="6"
          x2={w - 6}
          y1={thresholdY}
          y2={thresholdY}
          stroke="rgb(222 130 54)"
          strokeOpacity="0.7"
          strokeDasharray="4 4"
        />

        <path d={area} fill="url(#fill)" />
        <path
          d={line}
          fill="none"
          stroke="rgb(88 190 165)"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>

      <div className="mt-4 flex items-center gap-5 text-[11px] text-hero-muted">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 rounded bg-[rgb(88_190_165)]" />
          Gjennomsnittstrykk
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 rounded bg-[rgb(222_130_54)]" />
          Risikoterskel
        </span>
      </div>
    </figure>
  )
}
