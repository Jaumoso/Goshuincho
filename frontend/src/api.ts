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
