import type { PlaceKind } from '../api'

export type IconPath = { d: string; evenodd?: boolean }

/** Trazados de los iconos por tipo (viewBox 24×24); el mapa los pinta también en canvas. */
export const KIND_PATHS: Record<PlaceKind, IconPath[]> = {
  shrine: [
    { d: 'M1.5 3.6c4.2 1.3 16.8 1.3 21 0v2.7c-4.2 1-16.8 1-21 0z' },
    { d: 'M3.5 9.2h17v2h-17zM11.2 6.8h1.6v2.4h-1.6zM5.6 6.4h2.2V22H5.6zM16.2 6.4h2.2V22h-2.2z' },
  ],
  temple: [
    { d: 'M11.3 1.5h1.4v3h-1.4z' },
    { d: 'M12 4c-3 3.3-6.3 5.4-10.5 6.2v1.6h21v-1.6C18.3 9.4 15 7.3 12 4z' },
    { d: 'M5 11.8h14V20H5zM10 14.2h4V20h-4z', evenodd: true },
    { d: 'M3 20h18v2H3z' },
  ],
  station: [
    {
      d: 'M8 2.5h8a3 3 0 0 1 3 3v9.5a3 3 0 0 1-3 3H8a3 3 0 0 1-3-3V5.5a3 3 0 0 1 3-3zM7.5 6v4.8h9V6zM7.5 13.5V15h2v-1.5zM14.5 13.5V15h2v-1.5z',
      evenodd: true,
    },
    { d: 'M8.2 18.6h2.1L8 22H5.8zM13.7 18.6h2.1l2.4 3.4H16z' },
  ],
  site: [
    {
      d: 'M12 2a7 7 0 0 0-7 7c0 5.2 7 13 7 13s7-7.8 7-13a7 7 0 0 0-7-7zm0 4.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5z',
      evenodd: true,
    },
  ],
}
