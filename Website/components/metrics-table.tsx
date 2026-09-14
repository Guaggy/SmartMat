const COLS = ['Utgangspunkt', 'Uke 2', 'Uke 4', 'Uke 6', 'Uke 8']

type Row = {
  label: string
  values: string[]
  emphasis?: boolean
}

const ROWS: Row[] = [
  { label: 'Overvåkede sittetimer', values: ['0', '412', '840', '1 290', '1 760'] },
  { label: 'Gjennomsnittlig tid i høyt trykk', values: ['112 min', '74 min', '58 min', '49 min', '41 min'] },
  { label: 'Varsler bekreftet', values: ['0', '86 %', '91 %', '94 %', '96 %'] },
  { label: 'Justeringer per dag', values: ['3,1', '4,4', '4,8', '5,2', '5,3'] },
  { label: 'Nye trykksår grad 1+', values: ['9', '6', '4', '2', '1'] },
  {
    label: 'Relativ reduksjon mot utgangspunkt',
    values: ['0', '33 %', '56 %', '78 %', '89 %'],
    emphasis: true,
  },
]

export function MetricsTable() {
  return (
    <section id="evidence" className="mx-auto max-w-6xl px-5 py-4 sm:px-8">
      <div className="rounded-2xl bg-card p-6 shadow-sm ring-1 ring-border sm:p-10 lg:p-14">
        <div className="mb-8 max-w-2xl">
          <p className="mb-3 text-xs font-semibold tracking-[0.16em] text-brand">
            Dokumentasjon
          </p>
          <h3 className="text-balance text-2xl font-semibold tracking-tight text-ink sm:text-3xl">
            <span className="text-brand">Færre høyrisikominutter,</span> målt i bruktiden.
          </h3>
          <p className="mt-4 text-pretty leading-relaxed text-muted-foreground">
            Illustrative results from an eight-week deployment on standard seating support. Verdia Stol tracks relative pressure only, without storing identifiable health data.
          </p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="py-3 pr-4 text-left font-medium text-muted-foreground" />
                {COLS.map((c) => (
                  <th
                    key={c}
                    className="px-4 py-3 text-right font-semibold text-ink tabular-nums"
                  >
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ROWS.map((row) => (
                <tr
                  key={row.label}
                  className={
                    row.emphasis
                      ? 'border-t border-border bg-brand/[0.06]'
                      : 'border-t border-border/70'
                  }
                >
                  <td
                    className={`py-3 pr-4 text-left ${
                      row.emphasis ? 'font-semibold text-ink' : 'text-muted-foreground'
                    }`}
                  >
                    {row.label}
                  </td>
                  {row.values.map((v, i) => (
                    <td
                      key={i}
                      className={`px-4 py-3 text-right tabular-nums ${
                        row.emphasis ? 'font-semibold text-brand-strong' : 'text-ink/90'
                      }`}
                    >
                      {v}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="mt-6 text-xs text-muted-foreground">
          Tallene som vises er representative for designmål og pilotmodellering,
          ikke en påstand om kliniske resultater.
        </p>
      </div>
    </section>
  )
}
