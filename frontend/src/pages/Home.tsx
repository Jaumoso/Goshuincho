import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, mediaUrl, type Stats, type VisitWithPlace } from '../api'
import { useAuth } from '../auth'
import { KindBadge, Search } from '../components/Icons'
import { formatWithRelative, placeName } from '../format'
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
      <section className="hero">
        <span className="kicker">ようこそ</span>
        <h1>{t('home.welcome', { name: user?.display_name ?? '' })}</h1>
        <p className="meta">{t('app.tagline')}</p>
        <span className="tategaki faint" aria-hidden>御朱印帳</span>
        <Link className="searchbox" to="/places">
          <Search /> {t('home.find')}
        </Link>
      </section>
      {stats && (
        <div className="stats">
          <div className="stat"><span className="seal">{stats.places_visited}</span><span><span className="ja">参拝地</span>{t('stats.places')}</span></div>
          <div className="stat"><span className="seal">{stats.visits}</span><span><span className="ja">参拝</span>{t('stats.visits')}</span></div>
          <div className="stat"><span className="seal">{stats.goshuin}</span><span><span className="ja">御朱印</span>{t('stats.goshuin')}</span></div>
          <div className="stat"><span className="seal">{stats.prefectures_visited}<small>/47</small></span><span><span className="ja">都道府県</span>{t('stats.prefectures')}</span></div>
        </div>
      )}
      <div className="section"><small>最近の参拝</small><h2>{t('home.recent')}</h2></div>
      {visits?.length === 0 && <p className="muted">{t('home.empty')}</p>}
      <ul className="list">
        {visits?.map((v) => {
          const thumb = v.stamps.flatMap((s) => s.media)[0] ?? v.media[0]
          return (
            <li key={v.id}>
              <Link to={`/places/${v.place.id}`} className="place-row card visited">
                {thumb ? <img className="thumb" src={mediaUrl(thumb.id)} alt="" loading="lazy" /> : <KindBadge kind={v.place.kind} />}
                <span className="grow">
                  <strong>{placeName(v.place, locale)}</strong>
                  <br />
                  <span className="muted small">
                    {formatWithRelative(v.visited_on, v.visited_precision, locale, t)}
                    {v.kind !== 'in_person' && ` · ${t(`visit.kind.${v.kind}`)}`}
                  </span>
                </span>
                {v.stamps.length > 0 && <span className="mini-seal">印 {v.stamps.length}</span>}
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
