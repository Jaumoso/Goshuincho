import type { PlaceKind } from '../api'

type Props = { size?: number; className?: string }

function Svg({ size = 24, className, children }: Props & { children: React.ReactNode }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden focusable="false">
      {children}
    </svg>
  )
}

export const Torii = (p: Props) => (
  <Svg {...p}>
    <path d="M1.5 3.6c4.2 1.3 16.8 1.3 21 0v2.7c-4.2 1-16.8 1-21 0z" />
    <path d="M3.5 9.2h17v2h-17zM11.2 6.8h1.6v2.4h-1.6zM5.6 6.4h2.2V22H5.6zM16.2 6.4h2.2V22h-2.2z" />
  </Svg>
)

export const Temple = (p: Props) => (
  <Svg {...p}>
    <path d="M11.3 1.5h1.4v3h-1.4z" />
    <path d="M12 4c-3 3.3-6.3 5.4-10.5 6.2v1.6h21v-1.6C18.3 9.4 15 7.3 12 4z" />
    <path fillRule="evenodd" d="M5 11.8h14V20H5zM10 14.2h4V20h-4z" />
    <path d="M3 20h18v2H3z" />
  </Svg>
)

export const Train = (p: Props) => (
  <Svg {...p}>
    <path
      fillRule="evenodd"
      d="M8 2.5h8a3 3 0 0 1 3 3v9.5a3 3 0 0 1-3 3H8a3 3 0 0 1-3-3V5.5a3 3 0 0 1 3-3zM7.5 6v4.8h9V6zM7.5 13.5V15h2v-1.5zM14.5 13.5V15h2v-1.5z"
    />
    <path d="M8.2 18.6h2.1L8 22H5.8zM13.7 18.6h2.1l2.4 3.4H16z" />
  </Svg>
)

export const Pin = (p: Props) => (
  <Svg {...p}>
    <path fillRule="evenodd" d="M12 2a7 7 0 0 0-7 7c0 5.2 7 13 7 13s7-7.8 7-13a7 7 0 0 0-7-7zm0 4.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5z" />
  </Svg>
)

export const Lantern = (p: Props) => (
  <Svg {...p}>
    <path d="M8.5 1.5h7v2.2h-7zM8.5 19.3h7v2.2h-7z" />
    <path
      fillRule="evenodd"
      d="M6.5 4.6h11c1.6 2 2.4 4.3 2.4 6.9s-.8 4.9-2.4 6.9h-11C4.9 16.4 4.1 14.1 4.1 11.5s.8-4.9 2.4-6.9zM4.6 8.6v1h14.8v-1zM4.3 13.2v1h15.4v-1z"
    />
  </Svg>
)

export const Seal = (p: Props) => (
  <Svg {...p}>
    <path fillRule="evenodd" d="M4.5 2.5h15a2 2 0 0 1 2 2v15a2 2 0 0 1-2 2h-15a2 2 0 0 1-2-2v-15a2 2 0 0 1 2-2zm.5 2.5v14h14V5z" />
    <text x="12" y="16.4" fontSize="10.5" fontWeight="700" textAnchor="middle" fontFamily="var(--mincho)">印</text>
  </Svg>
)

export const Book = (p: Props) => (
  <Svg {...p}>
    <path fillRule="evenodd" d="M5.5 1.5h13a1.5 1.5 0 0 1 1.5 1.5v18a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 21V3a1.5 1.5 0 0 1 1.5-1.5zm8 3v10h3v-10z" />
  </Svg>
)

export const Camera = (p: Props) => (
  <Svg {...p}>
    <path fillRule="evenodd" d="M8.5 4h7l1.6 2.5H20a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V8.5a2 2 0 0 1 2-2h2.9zM12 9a4 4 0 1 0 0 8 4 4 0 0 0 0-8zm0 2a2 2 0 1 1 0 4 2 2 0 0 1 0-4z" />
  </Svg>
)

export const Search = (p: Props) => (
  <Svg {...p}>
    <path fillRule="evenodd" d="M10.5 3a7.5 7.5 0 0 1 6 12l4.8 4.8-1.5 1.5-4.8-4.8A7.5 7.5 0 1 1 10.5 3zm0 2a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11z" />
  </Svg>
)

export const Trash = (p: Props) => (
  <Svg {...p}>
    <path d="M9 2.5h6l.8 1.8H20v2H4v-2h4.2zM5.5 7.5h13l-1 14h-11zM9.3 10v9h1.5v-9zM13.2 10v9h1.5v-9z" fillRule="evenodd" />
  </Svg>
)

const KIND_ICONS = { shrine: Torii, temple: Temple, station: Train, site: Pin }

export function KindIcon({ kind, ...p }: Props & { kind: PlaceKind }) {
  const Icon = KIND_ICONS[kind] ?? Pin
  return <Icon {...p} />
}

/** Round emblem tinted by place kind. */
export function KindBadge({ kind, size = 44 }: { kind: PlaceKind; size?: number }) {
  return (
    <span className={`kind-badge kind-${kind}`} style={{ width: size, height: size }}>
      <KindIcon kind={kind} size={Math.round(size * 0.55)} />
    </span>
  )
}

/** 地図 — a folded paper map */
export const MapIcon = (p: Props) => (
  <Svg {...p}>
    <path fillRule="evenodd" d="M2 5.2 8.5 2.5l7 2.6L22 2.4v16.4l-6.5 2.7-7-2.6L2 21.6zM9.5 4.9v13.9l5 1.9V6.8z" />
  </Svg>
)
