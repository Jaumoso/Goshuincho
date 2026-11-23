import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, mediaUrl, type Page, type StampKind, type StampWithContext, type Stats } from '../api'
import { useBooks } from '../data'
import { formatDate, placeName } from '../format'
import { useI18n } from '../i18n'

const KINDS: StampKind[] = ['goshuin', 'goshuin_limited', 'goshuin_seasonal', 'station_stamp', 'other_stamp']

export default function Collection() {
  const { t, locale } = useI18n()
  const books = useBooks()
  const [kind, setKind] = useState('')
  const [year, setYear] = useState('')
  const [params] = useSearchParams()
  const [book, setBook] = useState(params.get('book') ?? '')
  const [years, setYears] = useState<string[]>([])
  const [page, setPage] = useState<Page<StampWithContext> | null>(null)

  const qs = new URLSearchParams(Object.entries({ kind, year, goshuincho: book }).filter(([, v]) => v)).toString()

  useEffect(() => {
    api<Stats>('/stats/summary').then((s) => setYears(s.by_year.map((y) => y.key))).catch(console.error)
  }, [])

  useEffect(() => {
    let alive = true
    setPage(null)
    api<Page<StampWithContext>>(`/stamps?${qs}`).then((p) => alive && setPage(p)).catch(console.error)
    return () => {
      alive = false
    }
  }, [qs])

  async function more() {
    if (!page?.next_offset) return
    const next = await api<Page<StampWithContext>>(`/stamps?${qs}&offset=${page.next_offset}`)
    setPage({ ...next, items: [...page.items, ...next.items] })
  }

  return (
    <main className="page">
      <div className="section"><small>御朱印コレクション</small><h1>{t('collection.title')}</h1></div>
      <div className="filters">
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">{t('places.all_kinds')}</option>
          {KINDS.map((k) => <option key={k} value={k}>{t(`stamp.${k}`)}</option>)}
        </select>
        <select value={year} onChange={(e) => setYear(e.target.value)}>
          <option value="">{t('collection.all_years')}</option>
          {years.map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
        {books.length > 0 && (
          <select value={book} onChange={(e) => setBook(e.target.value)}>
            <option value="">{t('collection.all_books')}</option>
            {books.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        )}
      </div>
      {!page && <p className="muted">{t('common.loading')}</p>}
      {page?.count === 0 && <p className="muted">{t('collection.empty')}</p>}
      {!!page?.items.length && <div className="book-spread">
        {page?.items.map((s) => (
          <Link
            key={s.id}
            to={`/places/${s.place.id}`}
            className="tile"
            title={`${placeName(s.place, locale)} · ${s.title || t(`stamp.${s.kind}`)}`}
          >
            {s.media[0] ? <img src={mediaUrl(s.media[0].id)} alt="" loading="lazy" /> : <span className="no-photo"><span>印</span></span>}
            <span className="label">{s.place.name_ja || placeName(s.place, locale)}</span>
            <span className="date">{formatDate(s.visited_on, s.visited_precision, locale, t)}</span>
          </Link>
        ))}
      </div>}
      {page?.next_offset != null && <button className="secondary wide" onClick={() => void more()}>{t('places.more')}</button>}
    </main>
  )
}
