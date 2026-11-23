import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api, sharedMediaUrl, type SharedCollection, type SharedStamp } from '../api'
import { formatDate, placeName } from '../format'
import { useI18n } from '../i18n'

/** Colección compartida por enlace: pública, de solo lectura y sin datos privados. */
export default function SharedPage() {
  const { token = '' } = useParams()
  return <Shared key={token} token={token} />
}

function Shared({ token }: { token: string }) {
  const { t, locale, setLocale } = useI18n()
  const [data, setData] = useState<SharedCollection | null>(null)
  const [missing, setMissing] = useState(false)
  const [open, setOpen] = useState<SharedStamp | null>(null)

  useEffect(() => {
    api<SharedCollection>(`/shared/${encodeURIComponent(token)}`)
      .then(setData)
      .catch(() => setMissing(true))
  }, [token])

  useEffect(() => {
    if (!open) return
    const close = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(null)
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [open])

  async function more() {
    if (data?.next_offset == null) return
    const next = await api<SharedCollection>(`/shared/${encodeURIComponent(token)}?offset=${data.next_offset}`)
    setData({ ...next, items: [...data.items, ...next.items] })
  }

  const heading = data?.title || data?.book?.name || t('shared.default_title', { owner: data?.owner ?? '' })

  return (
    <main className="page shared">
      <div className="shared-top">
        <span className="hanko vertical logo" aria-hidden>朱印</span>
        <b>Goshuinchō</b>
        <select aria-label={t('nav.language')} value={locale} onChange={(e) => setLocale(e.target.value as 'es' | 'en')}>
          <option value="es">ES</option>
          <option value="en">EN</option>
        </select>
      </div>
      {missing && (
        <div className="card">
          <h1>{t('shared.missing_title')}</h1>
          <p className="muted">{t('shared.missing')}</p>
        </div>
      )}
      {!data && !missing && <p className="muted">{t('common.loading')}</p>}
      {data && (
        <>
          <div className="section">
            <small>御朱印帳</small>
            <h1>{heading}</h1>
          </div>
          <p className="muted shared-meta">
            {t('shared.meta', { owner: data.owner, n: String(data.count), places: String(data.place_count) })}
            {data.book?.description && <><br />{data.book.description}</>}
          </p>
          {data.count === 0 && <p className="muted">{t('collection.empty')}</p>}
          {data.items.length > 0 && (
            <div className="book-spread">
              {data.items.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  className="tile"
                  onClick={() => setOpen(s)}
                  title={`${placeName(s.place, locale)} · ${s.title || t(`stamp.${s.kind}`)}`}
                >
                  {s.media[0] ? (
                    <img src={sharedMediaUrl(token, s.media[0])} alt="" loading="lazy" />
                  ) : (
                    <span className="no-photo"><span>印</span></span>
                  )}
                  <span className="label">{s.place.name_ja || placeName(s.place, locale)}</span>
                  <span className="date">{formatDate(s.visited_on, s.visited_precision, locale, t)}</span>
                </button>
              ))}
            </div>
          )}
          {data.next_offset != null && (
            <button className="secondary wide" onClick={() => void more()}>{t('places.more')}</button>
          )}
        </>
      )}
      {open && (
        <div className="sheet-backdrop shared-viewer" role="dialog" aria-modal onClick={() => setOpen(null)}>
          <figure onClick={(e) => e.stopPropagation()}>
            {open.media.map((m) => <img key={m} src={sharedMediaUrl(token, m, 'medium')} alt="" />)}
            <figcaption>
              <b>{open.place.name_ja || placeName(open.place, locale)}</b>
              {open.place.name_ja && <span>{placeName(open.place, locale)}</span>}
              <span>
                {open.title || t(`stamp.${open.kind}`)} · {formatDate(open.visited_on, open.visited_precision, locale, t)}
              </span>
            </figcaption>
            <button type="button" className="secondary" onClick={() => setOpen(null)}>{t('common.close')}</button>
          </figure>
        </div>
      )}
    </main>
  )
}
