import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, type Page, type PlaceListItem } from '../api'
import PlaceRow from '../components/PlaceRow'
import { useCategories, usePrefectures, useRegions } from '../data'
import { localName } from '../format'
import { useI18n } from '../i18n'
import { Search } from '../components/Icons'

const FILTERS = ['q', 'kind', 'prefecture', 'category', 'state'] as const

export default function Places() {
  const { t, locale } = useI18n()
  const [params, setParams] = useSearchParams()
  const [query, setQuery] = useState(params.get('q') ?? '')
  const [page, setPage] = useState<Page<PlaceListItem> | null>(null)
  const [loadingMore, setLoadingMore] = useState(false)
  const regions = useRegions()
  const prefectures = usePrefectures()
  const categories = useCategories()

  const search = new URLSearchParams()
  for (const key of FILTERS) {
    const v = params.get(key)
    if (v) search.set(key, v)
  }
  const qs = search.toString()

  useEffect(() => {
    const id = setTimeout(() => {
      if ((params.get('q') ?? '') !== query) update('q', query)
    }, 300)
    return () => clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query])

  useEffect(() => {
    let alive = true
    setPage(null)
    api<Page<PlaceListItem>>(`/places?${qs}`).then((p) => alive && setPage(p)).catch(console.error)
    return () => {
      alive = false
    }
  }, [qs])

  function update(key: string, value: string) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  async function more() {
    if (!page?.next_offset) return
    setLoadingMore(true)
    try {
      const next = await api<Page<PlaceListItem>>(`/places?${qs}&offset=${page.next_offset}`)
      setPage({ ...next, items: [...page.items, ...next.items] })
    } finally {
      setLoadingMore(false)
    }
  }

  return (
    <main className="page">
      <div className="section"><small>寺社を探す</small><h1>{t('nav.places')}</h1></div>
      <label className="search-field">
        <Search size={22} />
        <input
        type="search"
        placeholder={t('places.search')}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        autoFocus
        aria-label={t('places.search')}
      />
      </label>
      <div className="filters">
        <select value={params.get('kind') ?? ''} onChange={(e) => update('kind', e.target.value)}>
          <option value="">{t('places.all_kinds')}</option>
          {(['shrine', 'temple', 'station', 'site'] as const).map((k) => (
            <option key={k} value={k}>{t(`kind.${k}`)}</option>
          ))}
        </select>
        <select value={params.get('prefecture') ?? ''} onChange={(e) => update('prefecture', e.target.value)}>
          <option value="">{t('places.all_prefectures')}</option>
          {regions.map((r) => (
            <optgroup key={r.id} label={localName(r, locale)}>
              {prefectures.filter((p) => p.region_id === r.id).map((p) => (
                <option key={p.id} value={p.id}>{localName(p, locale)}</option>
              ))}
            </optgroup>
          ))}
        </select>
        <select value={params.get('category') ?? ''} onChange={(e) => update('category', e.target.value)}>
          <option value="">{t('places.all_categories')}</option>
          {categories.map((c) => (
            <option key={c.slug} value={c.slug}>{localName(c, locale)}</option>
          ))}
        </select>
        <select value={params.get('state') ?? ''} onChange={(e) => update('state', e.target.value)}>
          <option value="">{t('places.any_state')}</option>
          {(['visited', 'wishlist', 'favorite'] as const).map((s) => (
            <option key={s} value={s}>{t(`state.${s}`)}</option>
          ))}
        </select>
      </div>
      {!page && <p className="muted">{t('common.loading')}</p>}
      {page && <p className="count">{t('places.count', { n: String(page.count) })}</p>}
      {page?.count === 0 && <p className="muted">{t('places.none')}</p>}
      <ul className="list">
        {page?.items.map((p) => <PlaceRow key={p.id} place={p} />)}
      </ul>
      {page?.next_offset != null && (
        <button className="secondary wide" disabled={loadingMore} onClick={() => void more()}>{t('places.more')}</button>
      )}
      <p>
        <Link className="button secondary" to="/places/new">＋ {t('places.new')}</Link>
      </p>
    </main>
  )
}
