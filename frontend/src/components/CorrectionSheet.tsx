import { useEffect, useState } from 'react'
import { api, ApiError, type PlaceDetail, type PlaceKind } from '../api'
import { useI18n, type MessageKey } from '../i18n'
import { Pin } from './Icons'

const KINDS: PlaceKind[] = ['shrine', 'temple', 'station', 'site']
type Goshuin = '' | 'yes' | 'no'

interface Props {
  place: PlaceDetail
  onClose: () => void
  onSaved: () => void
}

/** Propuesta de corrección de un lugar aprobado; la revisa un administrador. */
export default function CorrectionSheet({ place, onClose, onSaved }: Props) {
  const { t } = useI18n()
  const initial = {
    kind: place.kind,
    name_ja: place.name_ja ?? '',
    name_romaji: place.name_romaji_generated ? '' : place.name_romaji ?? '',
    name_en: place.name_en ?? '',
    address: place.address ?? '',
    website: place.website ?? '',
    goshuin: (place.goshuin_available == null ? '' : place.goshuin_available ? 'yes' : 'no') as Goshuin,
    goshuin_info: place.goshuin_info ?? '',
    lat: place.lat?.toFixed(6) ?? '',
    lon: place.lon?.toFixed(6) ?? '',
  }
  const [form, setForm] = useState(initial)
  const [comment, setComment] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<MessageKey | null>(null)
  const set = <K extends keyof typeof initial>(k: K, v: (typeof initial)[K]) => setForm((f) => ({ ...f, [k]: v }))

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  function locate() {
    navigator.geolocation?.getCurrentPosition((pos) => {
      set('lat', pos.coords.latitude.toFixed(6))
      set('lon', pos.coords.longitude.toFixed(6))
    })
  }

  async function save() {
    const changes: Record<string, unknown> = {}
    if (form.kind !== initial.kind) changes.kind = form.kind
    for (const f of ['name_ja', 'name_romaji', 'name_en', 'address', 'website', 'goshuin_info'] as const) {
      if (form[f].trim() !== initial[f]) changes[f] = form[f].trim() || null
    }
    if (form.goshuin !== initial.goshuin) changes.goshuin_available = form.goshuin === '' ? null : form.goshuin === 'yes'
    if (form.lat !== initial.lat || form.lon !== initial.lon) {
      const lat = Number(form.lat), lon = Number(form.lon)
      if (!form.lat || !form.lon || Number.isNaN(lat) || Number.isNaN(lon)) return setError('correction.bad_location')
      changes.lat = lat
      changes.lon = lon
    }
    if (Object.keys(changes).length === 0 && !comment.trim()) return setError('correction.nothing')
    setSaving(true)
    setError(null)
    try {
      await api(`/places/${place.id}/corrections`, { method: 'POST', json: { changes, comment: comment.trim() || null } })
      onSaved()
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0
      setError(status === 422 ? 'correction.invalid' : status === 429 ? 'correction.too_many' : 'sheet.error')
      setSaving(false)
    }
  }

  const text = (k: 'name_ja' | 'name_romaji' | 'name_en' | 'address' | 'website', label: MessageKey, extra = {}) => (
    <label>
      {t(label)}
      <input value={form[k]} onChange={(e) => set(k, e.target.value)} {...extra} />
    </label>
  )

  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <form
        className="sheet"
        role="dialog"
        aria-label={t('correction.title')}
        onClick={(e) => e.stopPropagation()}
        onSubmit={(e) => {
          e.preventDefault()
          void save()
        }}
      >
        <div className="section" style={{ margin: 0 }}><small>訂正</small><h2>{t('correction.title')}</h2></div>
        <p className="small muted">{t('correction.intro')}</p>

        <label>
          {t('newplace.kind')}
          <select value={form.kind} onChange={(e) => set('kind', e.target.value as PlaceKind)}>
            {KINDS.map((k) => <option key={k} value={k}>{t(`kind.${k}`)}</option>)}
          </select>
        </label>
        {text('name_ja', 'newplace.name_ja', { lang: 'ja' })}
        {text('name_romaji', 'newplace.name_romaji', { placeholder: place.name_romaji_generated ? place.name_romaji ?? '' : '' })}
        {text('name_en', 'correction.name_en')}
        {text('address', 'correction.address')}
        {text('website', 'correction.website', { type: 'url', placeholder: 'https://' })}
        <label>
          {t('correction.goshuin')}
          <select value={form.goshuin} onChange={(e) => set('goshuin', e.target.value as Goshuin)}>
            <option value="">—</option>
            <option value="yes">{t('place.goshuin_yes')}</option>
            <option value="no">{t('place.goshuin_no')}</option>
          </select>
        </label>
        <label>
          {t('correction.goshuin_info')}
          <textarea rows={2} value={form.goshuin_info} onChange={(e) => set('goshuin_info', e.target.value)} />
        </label>
        <div className="row">
          <label className="grow">
            {t('newplace.lat')}
            <input inputMode="decimal" value={form.lat} onChange={(e) => set('lat', e.target.value)} />
          </label>
          <label className="grow">
            {t('newplace.lon')}
            <input inputMode="decimal" value={form.lon} onChange={(e) => set('lon', e.target.value)} />
          </label>
        </div>
        <button type="button" className="secondary" onClick={locate}><Pin size={18} /> {t('newplace.here')}</button>
        <label>
          {t('correction.comment')}
          <textarea rows={3} maxLength={2000} value={comment} onChange={(e) => setComment(e.target.value)} placeholder={t('correction.comment_hint')} />
        </label>

        {error && <p className="error" role="alert">{t(error)}</p>}
        <div className="row end">
          <button type="button" className="link" onClick={onClose}>{t('sheet.cancel')}</button>
          <button type="submit" disabled={saving}>{saving ? t('common.loading') : t('correction.send')}</button>
        </div>
      </form>
    </div>
  )
}
