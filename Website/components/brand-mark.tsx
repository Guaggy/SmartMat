// Vilia mark: a stylized pressure pulse / contour reading.
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M2 14h4l2-5 3 9 3-13 2.5 9H22" />
    </svg>
  )
}
