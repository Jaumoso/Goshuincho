import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, newId, type PlaceDetail, type PlaceKind, type SimilarPlace } from '../api'
import { usePrefectures, useRegions } from '../data'
import { KIND_ICON, localName, placeName } from '../format'
import { useI18n, type MessageKey } from '../i18n'

export default function NewPlace() {
  const { t, locale } = useI18n()
  const navigate = useNavigate()
  const regions = useRegions()
  const prefectures = usePrefectures()
  const id = useRef(newId())
  const [kind, setKind] = useState<PlaceKind>('shrine')
  const [nameJa, setNameJa] = useState('')
  const [nameRomaji, setNameRomaji] = useState('')
  const [prefecture, setPrefecture] = useState('')
  const [lat, setLat] = useState('')
  const [lon, setLon] = useState('')
  const [similar, setSimilar] = useState<SimilarPlace[]>([])
  const [error, setError] = useState<MessageKey | null>(null)
  const [saving, setSaving] = useState(false)

  const name = nameJa.trim() || nameRomaji.trim()

  useEffect(() => {
    if (name.length < 2) {
      setSimilar([])
      return
    }
    const timer = setTimeout(() => {
      const qs = new URLSearchParams({ name })
      if (lat && lon) {
        qs.set('lat', lat)
        qs.set('lon', lon)
      }
      api<SimilarPlace[]>(`/places/similar?${qs}`).then(setSimilar).catch(() => setSimilar([]))
    }, 400)
    return () => clearTimeout(timer)
  }, [name, lat, lon])

  function locate() {
    navigator.geolocation?.getCurrentPosition((pos) => {
      setLat(pos.coords.latitude.toFixed(6))
      setLon(pos.coords.longitude.toFixed(6))
    })
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!name) return setError('newplace.need_name')
    if (!prefecture && !(lat && lon)) return setError('newplace.need_location')
    setSaving(true)
    setError(null)
    try {
      const place = await api<PlaceDetail>('/places', {
        method: 'POST',
        json: {
          id: id.current,
          kind,
          name_ja: nameJa.trim() || null,
          name_romaji: nameRomaji.trim() || null,
          prefecture_id: prefecture ? Number(prefecture) : null,
          lat: lat ? Number(lat) : null,
          lon: lon ? Number(lon) : null,
        },
      })
      navigate(`/places/${place.id}`, { replace: true })
    } catch {
      setError('common.error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <main className="page narrow">
      <h1>{t('newplace.title')}</h1>
      <p className="muted">{t('newplace.intro')}</p>
      <form className="stack" onSubmit={(e) => void submit(e)}>
        <label>
          {t('newplace.kind')}
          <select value={kind} onChange={(e) => setKind(e.target.value as PlaceKind)}>
            {(['shrine', 'temple', 'station', 'site'] as const).map((k) => <option key={k} value={k}>{t(`kind.${k}`)}</option>)}
          </select>
        </label>
        <label>
          {t('newplace.name_ja')}
          <input lang="ja" value={nameJa} maxLength={200} onChange={(e) => setNameJa(e.target.value)} />
        </label>
        <label>
          {t('newplace.name_romaji')}
          <input value={nameRomaji} maxLength={200} onChange={(e) => setNameRomaji(e.target.value)} />
        </label>
        {similar.length > 0 && (
          <div className="notice">
            <p>{t('newplace.similar')}</p>
            <ul>
              {similar.map((s) => (
                <li key={s.id}>
                  <Link to={`/places/${s.id}`}>
                    {KIND_ICON[s.kind]} {placeName(s, locale)} {s.name_ja && <span className="ja">{s.name_ja}</span>}
                  </Link>
                  {s.distance_m != null && <span className="muted small"> · {Math.round(s.distance_m)} m</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
        <label>
          {t('newplace.prefecture')}
          <select value={prefecture} onChange={(e) => setPrefecture(e.target.value)}>
            <option value="">{t('newplace.choose')}</option>
            {regions.map((r) => (
              <optgroup key={r.id} label={localName(r, locale)}>
                {prefectures.filter((p) => p.region_id === r.id).map((p) => (
                  <option key={p.id} value={p.id}>{localName(p, locale)} ({p.name_ja})</option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        <div className="row">
          <label className="grow">
            {t('newplace.lat')}
            <input type="number" step="any" min={20} max={46} value={lat} onChange={(e) => setLat(e.target.value)} />
          </label>
          <label className="grow">
            {t('newplace.lon')}
            <input type="number" step="any" min={122} max={154} value={lon} onChange={(e) => setLon(e.target.value)} />
          </label>
        </div>
        <button type="button" className="secondary" onClick={locate}>📍 {t('newplace.here')}</button>
        {error && <p className="error">{t(error)}</p>}
        <button type="submit" disabled={saving}>{t('newplace.create')}</button>
      </form>
    </main>
  )
}
