import type { Locale, PlaceNames, Precision } from './api'
import type { MessageKey } from './i18n'

type T = (key: MessageKey, vars?: Record<string, string>) => string

const SEASONS: Record<number, MessageKey> = { 12: 'season.winter', 3: 'season.spring', 6: 'season.summer', 9: 'season.autumn' }

function parse(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d)
}

export function todayIso(): string {
  return new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Tokyo' })
}

/** «hace 1 año», «hace unos 7 años»… aproximado si la precisión no es de día. */
export function relative(iso: string, precision: Precision, locale: Locale): string {
  const then = parse(iso)
  const now = parse(todayIso())
  const days = Math.round((now.getTime() - then.getTime()) / 86_400_000)
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' })
  let text: string
  if (days < 30) text = precision === 'day' ? rtf.format(-days, 'day') : rtf.format(0, 'month')
  else if (days < 365) text = rtf.format(-Math.round(days / 30.4), 'month')
  else text = rtf.format(-Math.floor(days / 365.25), 'year')
  if (precision === 'day' || days < 30) return text
  if (locale === 'es') return text.replace(/^hace /, 'hace unos ').replace(/unos 1 (año|mes)/, 'un $1')
  return text.replace(/^(\d+)/, 'about $1').replace(/^last /, 'about a ').replace(/^about 1 (year|month)/, 'about a $1')
}

export function formatDate(iso: string | null, precision: Precision, locale: Locale, t: T): string {
  if (!iso || precision === 'unknown') return t('date.unknown')
  const d = parse(iso)
  const year = String(precision === 'season' && d.getMonth() === 11 ? d.getFullYear() + 1 : d.getFullYear())
  switch (precision) {
    case 'day':
      return t('date.day', { date: d.toLocaleDateString(locale === 'es' ? 'es-ES' : 'en-GB') })
    case 'month':
      return t('date.month', { month: d.toLocaleDateString(locale, { month: 'long' }), year })
    case 'season':
      return t('date.season', { season: t(SEASONS[d.getMonth() + 1]).toLowerCase(), year })
    default:
      return t('date.year', { year })
  }
}

export function formatWithRelative(iso: string | null, precision: Precision, locale: Locale, t: T): string {
  const base = formatDate(iso, precision, locale, t)
  if (!iso || precision === 'unknown') return base
  return `${base} (${relative(iso, precision, locale)})`
}

export function placeName(p: PlaceNames, locale: Locale): string {
  return (locale === 'en' ? p.name_en || p.name_romaji : p.name_romaji || p.name_en) || p.name_ja || '—'
}

export function placeSubName(p: PlaceNames): string | null {
  return p.name_ja && (p.name_romaji || p.name_en) ? p.name_ja : null
}

export function localName(item: { name_es?: string | null; name_en: string }, locale: Locale): string {
  return (locale === 'es' && item.name_es) || item.name_en
}

export const KIND_ICON = { shrine: '⛩️', temple: '🛕', station: '🚉', site: '📍' } as const
