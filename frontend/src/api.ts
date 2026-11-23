export class ApiError extends Error {
  status: number
  detail?: string

  constructor(status: number, detail?: string) {
    super(detail ?? `HTTP ${status}`)
    this.status = status
    this.detail = detail
  }
}

function cookie(name: string): string | undefined {
  return document.cookie
    .split('; ')
    .find((c) => c.startsWith(`${name}=`))
    ?.slice(name.length + 1)
}

let csrfReady: Promise<void> | null = null

async function ensureCsrf(): Promise<void> {
  if (cookie('csrftoken')) return
  csrfReady ??= fetch('/api/auth/csrf', { credentials: 'same-origin' }).then(() => undefined)
  await csrfReady
  csrfReady = null
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, ...rest } = init
  const method = (rest.method ?? 'GET').toUpperCase()
  const headers = new Headers(rest.headers)
  if (json !== undefined) headers.set('Content-Type', 'application/json')
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    await ensureCsrf()
    headers.set('X-CSRFToken', cookie('csrftoken') ?? '')
  }
  const response = await fetch(`/api${path}`, {
    ...rest,
    method,
    headers,
    credentials: 'same-origin',
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  })
  if (!response.ok) {
    let detail: string | undefined
    try {
      detail = (await response.json()).detail
    } catch {
      /* respuesta sin JSON */
    }
    throw new ApiError(response.status, typeof detail === 'string' ? detail : undefined)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export type Locale = 'es' | 'en'

export interface Me {
  id: string
  email: string
  display_name: string
  role: 'admin' | 'user'
  locale: Locale
}

export interface Region {
  id: number
  slug: string
  name_ja: string
  name_en: string
  name_es: string
}

export interface Prefecture {
  id: number
  iso_code: string
  region_id: number
  name_ja: string
  name_romaji: string
  name_en: string
  name_es: string
}

export type PlaceKind = 'shrine' | 'temple' | 'station' | 'site'
export type VisitKind = 'in_person' | 'mail' | 'event'
export type Precision = 'day' | 'month' | 'season' | 'year' | 'unknown'
export type StampKind = 'goshuin' | 'goshuin_limited' | 'goshuin_seasonal' | 'station_stamp' | 'other_stamp'
export type Medium = 'jikigaki' | 'kakioki' | 'stamped_paper' | 'digital' | 'other'
export type PlaceState = 'visited' | 'wishlist' | 'unvisited' | 'favorite'

export interface Page<T> {
  items: T[]
  count: number
  next_offset: number | null
}

export interface PlaceNames {
  name_ja: string | null
  name_romaji: string | null
  name_en: string | null
}

export interface MineSummary {
  visit_count: number
  last_visit: string | null
  last_visit_precision: Precision | null
  stamp_count: number
  wishlist: boolean
  favorite: boolean
}

export interface MineDetail extends MineSummary {
  first_visit: string | null
  first_visit_precision: Precision | null
  notes: string | null
}

export interface PlaceListItem extends PlaceNames {
  id: string
  kind: PlaceKind
  prefecture_id: number
  area_id: number | null
  lat: number | null
  lon: number | null
  status: string
  mine: MineSummary
}

export type CategoryType = 'pilgrimage' | 'theme' | 'deity' | 'collection'

export interface CategoryRef {
  slug: string
  type: CategoryType
  name_ja: string | null
  name_en: string
  name_es: string | null
  seq: number | null
}

export interface Category extends Omit<CategoryRef, 'seq'> {
  id: number
  total_items: number | null
}

export interface CategoryProgress extends Category {
  description: string | null
  members: number
  total: number
  done: number
  visited: number
  stamped: number
}

export interface CategoryDetail extends CategoryProgress {
  places: (PlaceListItem & { seq: number | null })[]
}

export interface PlaceDetail extends PlaceNames {
  id: string
  kind: PlaceKind
  name_romaji_generated: boolean
  alt_names: string[]
  tradition: string | null
  operator: string | null
  prefecture: { id: number; name_ja: string; name_en: string; name_es: string; region: string }
  area: { id: number; name_ja: string | null; name_en: string; name_es: string | null } | null
  address: string | null
  lat: number | null
  lon: number | null
  website: string | null
  goshuin_available: boolean | null
  goshuin_info: string | null
  source: string
  status: 'approved' | 'pending' | 'rejected' | 'merged'
  merged_into: string | null
  is_mine: boolean
  categories: CategoryRef[]
  mine: MineDetail
}

export interface SimilarPlace extends PlaceNames {
  id: string
  kind: PlaceKind
  prefecture_id: number
  distance_m: number | null
}

export interface MediaOut {
  id: string
  mime: string
  width: number | null
  height: number | null
  taken_at: string | null
  role?: string | null
}

export interface PlaceRef extends PlaceNames {
  id: string
  kind: PlaceKind
  prefecture_id: number
}

export interface Stamp {
  id: string
  visit_id: string
  place_id: string
  kind: StampKind
  medium: Medium | null
  title: string | null
  event_name: string | null
  donation_yen: number | null
  goshuincho_id: string | null
  page_label: string | null
  notes: string | null
  media: MediaOut[]
}

export interface StampWithContext extends Stamp {
  place: PlaceRef
  visited_on: string | null
  visited_precision: Precision
  visit_kind: VisitKind
}

export interface Visit {
  id: string
  place_id: string
  kind: VisitKind
  event_location: string | null
  visited_on: string | null
  visited_precision: Precision
  notes: string | null
  created_at: string
  stamps: Stamp[]
  media: MediaOut[]
}

export interface VisitWithPlace extends Visit {
  place: PlaceRef
}

export interface StampIn {
  id?: string
  kind?: StampKind
  medium?: Medium | null
  title?: string | null
  donation_yen?: number | null
  goshuincho_id?: string | null
  notes?: string | null
  media?: { media_id: string; role?: string }[]
}

export interface Goshuincho {
  id: string
  name: string
  description: string | null
  started_on: string | null
  finished_on: string | null
  stamp_count: number
}

export interface Stats {
  places_visited: number
  visits: number
  stamps: number
  goshuin: number
  prefectures_visited: number
  by_prefecture: { key: string; count: number }[]
  by_kind: { key: string; count: number }[]
  by_year: { key: string; count: number }[]
}

export interface StatsDetail {
  by_prefecture: { id: number; places: number; visited: number; goshuin: number }[]
  by_region: { id: number; places: number; visited: number }[]
  by_place_kind: { key: PlaceKind; count: number }[]
  goshuin_by_year: { key: string; count: number }[]
  longest_streak_months: number
  current_streak_months: number
  heatmap_year: number
  heatmap: { date: string; count: number }[]
  years: number[]
}

export function newId(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  const b = crypto.getRandomValues(new Uint8Array(16))
  b[6] = (b[6] & 0x0f) | 0x40
  b[8] = (b[8] & 0x3f) | 0x80
  const h = [...b].map((x) => x.toString(16).padStart(2, '0')).join('')
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`
}

export function uploadMedia(file: File): Promise<MediaOut> {
  const body = new FormData()
  body.append('file', file)
  return api<MediaOut>('/media', { method: 'POST', body })
}

export function mediaUrl(id: string, variant: 'thumb' | 'medium' | 'original' = 'thumb'): string {
  return `/api/media/${id}/${variant}`
}
