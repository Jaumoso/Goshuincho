import { useEffect, useState } from 'react'
import { api, type Category, type Goshuincho, type Prefecture, type Region } from './api'

const cache = new Map<string, Promise<unknown>>()

function cached<T>(path: string): Promise<T> {
  if (!cache.has(path)) {
    const p = api<T>(path)
    p.catch(() => cache.delete(path))
    cache.set(path, p)
  }
  return cache.get(path) as Promise<T>
}

export function invalidate(path: string) {
  cache.delete(path)
}

export function useCached<T>(path: string, initial: T): T {
  const [value, setValue] = useState<T>(initial)
  useEffect(() => {
    let alive = true
    cached<T>(path).then((v) => alive && setValue(v)).catch(console.error)
    return () => {
      alive = false
    }
  }, [path])
  return value
}

export const usePrefectures = () => useCached<Prefecture[]>('/prefectures', [])
export const useRegions = () => useCached<Region[]>('/regions', [])
export const useCategories = () => useCached<Category[]>('/categories', [])
export const useBooks = () => useCached<Goshuincho[]>('/goshuincho', [])
