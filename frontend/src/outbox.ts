/**
 * Cola de visitas y goshuin guardados sin conexión.
 *
 * Cada elemento se guarda en IndexedDB con su foto y se envía cuando vuelve la conexión. La API es
 * idempotente por UUID, así que reenviar algo que ya llegó no lo duplica.
 */
import { useEffect, useState } from 'react'
import { api, ApiError, uploadMedia } from './api'

export interface OutboxItem {
  /** UUID de la visita o del goshuin que se crea. */
  id: string
  userId: string
  type: 'visit' | 'stamp'
  placeId: string
  placeName: string
  /** Visita a la que se añade el goshuin (solo `stamp`). */
  visitId?: string
  body: Record<string, unknown>
  /** Foto aún no subida (como bytes: WebKit no guarda Blobs en IndexedDB), o id de la ya subida. */
  photo?: { data: ArrayBuffer; type: string; name: string }
  photoId: string
  mediaId?: string
  /** Dónde va la foto: en el goshuin o en la visita. */
  photoOn: 'stamp' | 'visit' | null
  createdAt: number
  /** Rechazo definitivo del servidor; no se reintenta solo. */
  error?: string
}

const DB = 'goshuincho'
const STORE = 'outbox'
let dbPromise: Promise<IDBDatabase> | null = null
let currentUser: string | null = null
let syncing: Promise<void> | null = null
const listeners = new Set<(items: OutboxItem[]) => void>()

function open(): Promise<IDBDatabase> {
  dbPromise ??= new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1)
    req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: 'id' })
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
  return dbPromise
}

async function tx<T>(mode: IDBTransactionMode, fn: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await open()
  return new Promise((resolve, reject) => {
    const req = fn(db.transaction(STORE, mode).objectStore(STORE))
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

export async function listOutbox(): Promise<OutboxItem[]> {
  if (!currentUser) return []
  const all = await tx<OutboxItem[]>('readonly', (s) => s.getAll() as IDBRequest<OutboxItem[]>)
  return all.filter((i) => i.userId === currentUser).sort((a, b) => a.createdAt - b.createdAt)
}

async function notify() {
  const items = await listOutbox()
  listeners.forEach((fn) => fn(items))
}

export async function enqueue(
  item: Omit<OutboxItem, 'userId' | 'createdAt' | 'photo'> & { photo?: File },
): Promise<void> {
  if (!currentUser) throw new Error('sin usuario')
  const { photo, ...rest } = item
  const stored: OutboxItem = { ...rest, userId: currentUser, createdAt: Date.now() }
  if (photo) stored.photo = { data: await photo.arrayBuffer(), type: photo.type, name: photo.name }
  await tx('readwrite', (s) => s.put(stored))
  await notify()
}

export async function discard(id: string): Promise<void> {
  await tx('readwrite', (s) => s.delete(id))
  await notify()
}

export async function retry(id: string): Promise<void> {
  const item = await tx<OutboxItem | undefined>('readonly', (s) => s.get(id) as IDBRequest<OutboxItem | undefined>)
  if (item) await tx('readwrite', (s) => s.put({ ...item, error: undefined }))
  await notify()
  void syncOutbox()
}

/** Error de red (sin respuesta), a diferencia de un rechazo del servidor. */
export function isNetworkError(err: unknown): boolean {
  return err instanceof TypeError || (err instanceof ApiError && (err.status >= 500 || err.status === 408 || err.status === 429))
}

async function send(item: OutboxItem): Promise<void> {
  let mediaId = item.mediaId
  if (!mediaId && item.photo) {
    const file = new File([item.photo.data], item.photo.name, { type: item.photo.type })
    mediaId = (await uploadMedia(file, item.photoId)).id
    await tx('readwrite', (s) => s.put({ ...item, photo: undefined, mediaId }))
  }
  const body = structuredClone(item.body) as Record<string, unknown> & { stamps?: Record<string, unknown>[] }
  if (mediaId && item.photoOn === 'visit') body.media = [mediaId]
  if (mediaId && item.photoOn === 'stamp') {
    const stamp = item.type === 'stamp' ? body : body.stamps?.[0]
    if (stamp) stamp.media = [{ media_id: mediaId }]
  }
  if (item.type === 'visit') await api(`/places/${item.placeId}/visits`, { method: 'POST', json: body })
  else await api(`/visits/${item.visitId}/stamps`, { method: 'POST', json: body })
}

async function run() {
  for (const item of await listOutbox()) {
    if (item.error) continue
    try {
      await send(item)
      await tx('readwrite', (s) => s.delete(item.id))
    } catch (err) {
      // Sin conexión o sesión caducada: se reintenta más tarde, en orden.
      if (isNetworkError(err) || (err instanceof ApiError && (err.status === 401 || err.status === 403))) break
      const detail = err instanceof ApiError ? err.detail ?? `HTTP ${err.status}` : String(err)
      await tx('readwrite', (s) => s.put({ ...item, error: detail }))
    }
    await notify()
  }
  await notify()
}

export function syncOutbox(): Promise<void> {
  if (!currentUser || !navigator.onLine) return Promise.resolve()
  syncing ??= run().finally(() => (syncing = null))
  return syncing
}

export function setOutboxUser(id: string | null) {
  currentUser = id
  void notify()
  void syncOutbox()
}

if (typeof window !== 'undefined') {
  window.addEventListener('online', () => void syncOutbox())
  document.addEventListener('visibilitychange', () => document.visibilityState === 'visible' && void syncOutbox())
  setInterval(() => void syncOutbox(), 60_000)
}

export function useOutbox(): OutboxItem[] {
  const [items, setItems] = useState<OutboxItem[]>([])
  useEffect(() => {
    listeners.add(setItems)
    void listOutbox().then(setItems)
    return () => void listeners.delete(setItems)
  }, [])
  return items
}

/** Borra las respuestas de la API guardadas para usar sin conexión (al cerrar sesión). */
export async function clearOfflineCaches() {
  if (!('caches' in window)) return
  await Promise.all(['api', 'media'].map((name) => caches.delete(name)))
}
