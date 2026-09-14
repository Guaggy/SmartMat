// Utilities for the mock pressure-mapping visuals.
// These stand in for the live, interactive heatmaps that plug in later.

export type Hotspot = {
  x: number // 0..1 column position
  y: number // 0..1 row position
  intensity: number // peak value 0..1
  radius: number // falloff radius in grid units
}

// A supine (lying on back) patient: the classic pressure-ulcer risk points.
// Head, shoulders, sacrum (the big one), and heels.
const SUPINE_HOTSPOTS: Hotspot[] = [
  { x: 0.5, y: 0.06, intensity: 0.72, radius: 0.12 }, // head
  { x: 0.34, y: 0.24, intensity: 0.58, radius: 0.13 }, // shoulder L
  { x: 0.66, y: 0.24, intensity: 0.58, radius: 0.13 }, // shoulder R
  { x: 0.5, y: 0.55, intensity: 1.0, radius: 0.16 }, // sacrum
  { x: 0.5, y: 0.44, intensity: 0.5, radius: 0.14 }, // lower back
  { x: 0.4, y: 0.93, intensity: 0.86, radius: 0.09 }, // heel L
  { x: 0.6, y: 0.93, intensity: 0.86, radius: 0.09 }, // heel R
]

export function buildPressureGrid(cols = 12, rows = 24): number[][] {
  const grid: number[][] = []
  for (let r = 0; r < rows; r++) {
    const row: number[] = []
    for (let c = 0; c < cols; c++) {
      const px = (c + 0.5) / cols
      const py = (r + 0.5) / rows
      let value = 0
      for (const h of SUPINE_HOTSPOTS) {
        const dx = px - h.x
        const dy = py - h.y
        const dist2 = dx * dx + dy * dy
        value += h.intensity * Math.exp(-dist2 / (2 * h.radius * h.radius))
      }
      // faint ambient contact
      value += 0.06
      row.push(Math.min(1, value))
    }
    grid.push(row)
  }
  return grid
}

// Map a 0..1 pressure value onto a clinical blue→cyan→green→yellow→red ramp.
export function pressureColor(v: number): string {
  const stops: [number, [number, number, number]][] = [
    [0.0, [12, 26, 51]], // deep navy (no contact)
    [0.22, [24, 84, 140]], // blue
    [0.42, [30, 150, 170]], // teal
    [0.58, [60, 170, 110]], // green
    [0.72, [214, 188, 74]], // yellow
    [0.86, [222, 130, 54]], // orange
    [1.0, [206, 62, 62]], // red (highest risk)
  ]
  const t = Math.max(0, Math.min(1, v))
  for (let i = 0; i < stops.length - 1; i++) {
    const [s0, c0] = stops[i]
    const [s1, c1] = stops[i + 1]
    if (t >= s0 && t <= s1) {
      const f = (t - s0) / (s1 - s0)
      const r = Math.round(c0[0] + (c1[0] - c0[0]) * f)
      const g = Math.round(c0[1] + (c1[1] - c0[1]) * f)
      const b = Math.round(c0[2] + (c1[2] - c0[2]) * f)
      return `rgb(${r} ${g} ${b})`
    }
  }
  return 'rgb(206 62 62)'
}
