import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError, mediaUrl, type MineDetail, type PlaceDetail as Place, type Visit } from '../api'
import AddVisitSheet from '../components/AddVisitSheet'
import { KIND_ICON, formatWithRelative, localName, placeName, placeSubName } from '../format'
import { useI18n } from '../i18n'

export default function PlaceDetail() {
  const { id = '' } = useParams()
  const { t, locale } = useI18n()
  const [place, setPlace] = useState<Place | null>(null)
  const [visits, setVisits] = useState<Visit[]>([])
  const [missing, setMissing] = useState(false)
  const [sheet, setSheet] = useState<{ visitId?: string } | null>(null)
  const [toast, setToast] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const [p, v] = await Promise.all([api<Place>(`/places/${id}`), api<Visit[]>(`/places/${id}/visits`)])
      setPlace(p)
      setVisits(v)
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setMissing(true)
      else console.error(err)
    }
  }, [id])

  useEffect(() => {
    setPlace(null)
    setMissing(false)
    void load()
  }, [load])

  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(() => setToast(null), 2500)
    return () => clearTimeout(timer)
  }, [toast])

  async function toggle(field: 'wishlist' | 'favorite') {
    if (!place) return
    const { wishlist, favorite, notes } = place.mine
    const body = { wishlist, favorite, notes, [field]: !place.mine[field] }
    const mine = await api<MineDetail>(`/places/${id}/mine`, { method: 'PUT', json: body })
    setPlace({ ...place, mine: { ...place.mine, ...mine } })
  }

  async function removeVisit(visit: Visit) {
    if (visit.stamps.length > 0 && !confirm(t('place.confirm_delete'))) return
    await api(`/visits/${visit.id}`, { method: 'DELETE' })
    await load()
  }

  if (missing) return <main className="page"><p>404</p><Link to="/places">{t('common.back')}</Link></main>
  if (!place) return <main className="page muted">{t('common.loading')}</main>

  const { mine } = place
  const sub = placeSubName(place)
  const header =
    mine.visit_count === 0
      ? t('place.not_visited')
      : `${t(mine.visit_count === 1 ? 'place.visited_1' : 'place.visited_n', { n: String(mine.visit_count) })} · ${t('place.last', {
          date: formatWithRelative(mine.last_visit, mine.last_visit_precision ?? 'unknown', locale, t),
        })}`

  return (
    <main className="page">
      {place.status === 'merged' && place.merged_into && (
        <p className="notice">
          {t('place.merged')} <Link to={`/places/${place.merged_into}`}>{t('place.go_merged')}</Link>
        </p>
      )}
      {place.status === 'pending' && <p className="notice">{t('place.pending')}</p>}

      <h1>
        <span aria-hidden>{KIND_ICON[place.kind]}</span> {placeName(place, locale)} {sub && <span className="ja">{sub}</span>}
      </h1>
      <p className="muted">
        {t(`kind.${place.kind}`)} · {localName(place.prefecture, locale)}
        {place.area && ` · ${localName(place.area, locale)}`}
        {place.tradition && ` · ${place.tradition}`}
      </p>
      <p className="headline">{header}</p>
      {mine.first_visit && mine.visit_count > 1 && (
        <p className="muted small">{t('place.first', { date: formatWithRelative(mine.first_visit, mine.first_visit_precision ?? 'unknown', locale, t) })}</p>
      )}

      <div className="row wrap">
        {place.status !== 'merged' && <button onClick={() => setSheet({})}>＋ {t('place.add_visit')}</button>}
        <button className={`toggle ${mine.wishlist ? 'on' : ''}`} aria-pressed={mine.wishlist} onClick={() => void toggle('wishlist')}>
          {mine.wishlist ? '♥' : '♡'} {t('place.wishlist')}
        </button>
        <button className={`toggle ${mine.favorite ? 'on' : ''}`} aria-pressed={mine.favorite} onClick={() => void toggle('favorite')}>
          {mine.favorite ? '★' : '☆'} {t('place.favorite')}
        </button>
      </div>

      {place.categories.length > 0 && (
        <p className="chips">
          {place.categories.map((c) => (
            <Link key={c.slug} className="chip" to={`/places?category=${c.slug}`}>
              {localName(c, locale)}{c.seq != null && ` #${c.seq}`}
            </Link>
          ))}
        </p>
      )}
      <p className="small muted">
        {place.goshuin_available === true && `${t('place.goshuin_yes')} · `}
        {place.goshuin_available === false && `${t('place.goshuin_no')} · `}
        {place.address && `${place.address} · `}
        {place.website && <><a href={place.website} target="_blank" rel="noreferrer">{t('place.website')}</a> · </>}
        {place.lat != null && (
          <a href={`https://www.openstreetmap.org/?mlat=${place.lat}&mlon=${place.lon}#map=17/${place.lat}/${place.lon}`} target="_blank" rel="noreferrer">
            {t('place.map')}
          </a>
        )}
      </p>
      {place.goshuin_info && <p className="small">{place.goshuin_info}</p>}

      <h2>{t('place.history')}</h2>
      {visits.length === 0 && <p className="muted">{t('place.no_history')}</p>}
      <ol className="history">
        {visits.map((v) => (
          <li key={v.id} className="card">
            <div className="row">
              <strong className="grow">
                {formatWithRelative(v.visited_on, v.visited_precision, locale, t)}
                {v.kind !== 'in_person' && <span className="pill">{t(`visit.kind.${v.kind}`)}</span>}
                {v.event_location && <span className="muted small"> · {v.event_location}</span>}
              </strong>
              <button className="link small" onClick={() => setSheet({ visitId: v.id })}>＋ {t('place.add_stamp')}</button>
              <button className="link small" aria-label={t('place.delete_visit')} title={t('place.delete_visit')} onClick={() => void removeVisit(v)}>🗑</button>
            </div>
            {v.notes && <p className="small">{v.notes}</p>}
            <div className="stamps">
              {v.stamps.map((s) => (
                <figure key={s.id}>
                  {s.media[0] ? (
                    <a href={mediaUrl(s.media[0].id, 'medium')} target="_blank" rel="noreferrer">
                      <img src={mediaUrl(s.media[0].id)} alt={s.title ?? t(`stamp.${s.kind}`)} loading="lazy" />
                    </a>
                  ) : (
                    <span className="no-photo">印</span>
                  )}
                  <figcaption>
                    {s.title || t(`stamp.${s.kind}`)}
                    {s.donation_yen != null && <span className="muted"> · ¥{s.donation_yen}</span>}
                  </figcaption>
                </figure>
              ))}
              {v.media.map((m) => (
                <figure key={m.id}>
                  <a href={mediaUrl(m.id, 'medium')} target="_blank" rel="noreferrer"><img src={mediaUrl(m.id)} alt="" loading="lazy" /></a>
                </figure>
              ))}
            </div>
          </li>
        ))}
      </ol>

      {sheet && (
        <AddVisitSheet
          placeId={place.id}
          visitId={sheet.visitId}
          onClose={() => setSheet(null)}
          onSaved={() => {
            setSheet(null)
            setToast(t('sheet.saved'))
            void load()
          }}
        />
      )}
      {toast && <div className="toast" role="status">{toast}</div>}
    </main>
  )
}
