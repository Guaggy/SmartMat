import { buildPressureGrid, pressureColor } from '@/lib/pressure'

type Props = {
  cols?: number
  rows?: number
  className?: string
  label?: string
}

export function PressureHeatmap({
  cols = 12,
  rows = 24,
  className,
  label = 'Verdia Stol · seated pressure map',
}: Props) {
  const grid = buildPressureGrid(cols, rows)

  return (
    <figure
      className={`relative overflow-hidden rounded-xl bg-hero p-4 sm:p-6 ${className ?? ''}`}
    >
      <div className="mb-4 flex items-center justify-between">
        <span className="text-[11px] font-medium uppercase tracking-[0.18em] text-hero-muted">
          {label}
        </span>
        <span className="flex items-center gap-1.5 text-[11px] font-medium text-hero-muted">
          <span className="inline-block size-1.5 animate-pulse rounded-full bg-brand" />
          Direkte
        </span>
      </div>

      <div className="flex items-stretch gap-4">
        {/* the mat */}
        <div
          className="grid flex-1 gap-[3px] rounded-lg bg-black/30 p-2"
          style={{
            gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
            aspectRatio: `${cols} / ${rows}`,
          }}
          role="img"
          aria-label="Sanntids trykkvarmekart av en pasient som ligger på ryggen, med høyest trykk ved korsrygg og hæler."
        >
          {grid.flatMap((row, r) =>
            row.map((v, c) => (
              <span
                key={`${r}-${c}`}
                className="rounded-[2px]"
                style={{ backgroundColor: pressureColor(v) }}
              />
            )),
          )}
        </div>

        {/* legend */}
        <div className="flex w-9 shrink-0 flex-col items-center">
          <span className="mb-2 text-[10px] font-medium text-hero-muted">
            Høyt
          </span>
          <div
            className="w-2.5 flex-1 rounded-full"
            style={{
              background:
                'linear-gradient(to top, rgb(12 26 51), rgb(24 84 140), rgb(30 150 170), rgb(60 170 110), rgb(214 188 74), rgb(222 130 54), rgb(206 62 62))',
            }}
          />
          <span className="mt-2 text-[10px] font-medium text-hero-muted">
            Lavt
          </span>
        </div>
      </div>
    </figure>
  )
}
