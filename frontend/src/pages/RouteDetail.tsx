import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type CategoryDetail } from '../api'
import PlaceRow from '../components/PlaceRow'
import { ProgressBar } from '../components/RouteProgress'
import { localName } from '../format'
import { useI18n } from '../i18n'

export default function RouteDetail() {
  const { slug } = useParams()
  const { t, locale } = useI18n()
  const [route, setRoute] = useState<CategoryDetail | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    api<CategoryDetail>(`/categories/${slug}`).then(setRoute).catch(() => setError(true))
  }, [slug])

  if (error) return <main className="page"><p className="error">{t('common.error')}</p></main>
  if (!route) return <main className="page muted">{t('common.loading')}</main>
  const missing = route.total - route.members
  return (
    <main className="page">
      <Link to="/books" className="small">← {t('books.title')}</Link>
      <div className="section">
        <small>{route.name_ja ?? t(`category.${route.type}`)}</small>
        <h1>{localName(route, locale)}</h1>
      </div>
      <div className="card route-head">
        <span className="route-count big"><b>{route.done}</b><small>/{route.total}</small></span>
        <span className="grow">
          <ProgressBar done={route.done} total={route.total} />
          <span className="muted small">
            {t('routes.visited', { n: String(route.visited) })} · {t('routes.stamped', { n: String(route.stamped) })}
          </span>
        </span>
      </div>
      {route.description && <p className="muted">{route.description}</p>}
      <ul className="list">
        {route.places.map((p) => <PlaceRow key={p.id} place={p} seq={route.type === 'pilgrimage' ? p.seq : undefined} />)}
      </ul>
      {missing > 0 && <p className="muted small">{t('routes.missing', { n: String(missing) })}</p>}
    </main>
  )
}
