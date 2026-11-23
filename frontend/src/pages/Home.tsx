import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, mediaUrl, type Stats, type VisitWithPlace } from '../api'
import { useAuth } from '../auth'
import { KIND_ICON, formatWithRelative, placeName } from '../format'
import { useI18n } from '../i18n'

export default function Home() {
  const { user } = useAuth()
  const { t, locale } = useI18n()
  const [stats, setStats] = useState<Stats | null>(null)
  const [visits, setVisits] = useState<VisitWithPlace[] | null>(null)

  useEffect(() => {
    api<Stats>('/stats/summary').then(setStats).catch(console.error)
    api<VisitWithPlace[]>('/visits?limit=10').then(setVisits).catch(console.error)
  }, [])

  return (
    <main className="page">
      <h1>{t('home.welcome', { name: user?.display_name ?? '' })}</h1>
      {stats && (
        <div className="stats">
          <div className="card"><b>{stats.places_visited}</b>{t('stats.places')}</div>
          <div className="card"><b>{stats.visits}</b>{t('stats.visits')}</div>
          <div className="card"><b>{stats.goshuin}</b>{t('stats.goshuin')}</div>
          <div className="card"><b>{stats.prefectures_visited}<small>/47</small></b>{t('stats.prefectures')}</div>
        </div>
      )}
      <p>
        <Link className="button" to="/places">🔍 {t('home.find')}</Link>
      </p>
      <h2>{t('home.recent')}</h2>
      {visits?.length === 0 && <p className="muted">{t('home.empty')}</p>}
      <ul className="list">
        {visits?.map((v) => {
          const thumb = v.stamps.flatMap((s) => s.media)[0] ?? v.media[0]
          return (
            <li key={v.id}>
              <Link to={`/places/${v.place.id}`} className="place-row card">
                {thumb ? <img className="thumb" src={mediaUrl(thumb.id)} alt="" loading="lazy" /> : <span className="kind-icon">{KIND_ICON[v.place.kind]}</span>}
                <span className="grow">
                  <strong>{placeName(v.place, locale)}</strong>
                  <br />
                  <span className="muted small">
                    {formatWithRelative(v.visited_on, v.visited_precision, locale, t)}
                    {v.kind !== 'in_person' && ` · ${t(`visit.kind.${v.kind}`)}`}
                  </span>
                </span>
                {v.stamps.length > 0 && <span className="pill">{v.stamps.length} 印</span>}
              </Link>
            </li>
          )
        })}
      </ul>
      {user?.role === 'admin' && (
        <p className="small"><a href="/admin/">{t('home.admin')}</a></p>
      )}
    </main>
  )
}
