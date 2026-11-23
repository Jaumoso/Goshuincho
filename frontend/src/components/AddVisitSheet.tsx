import { useEffect, useMemo, useRef, useState } from 'react'
import {
  api, ApiError, newId, uploadMedia,
  type MediaOut, type Medium, type Precision, type StampKind, type Visit, type VisitKind,
} from '../api'
import { useBooks } from '../data'
import { todayIso } from '../format'
import { useI18n, type MessageKey } from '../i18n'
import { Camera } from './Icons'

const STAMP_KINDS: StampKind[] = ['goshuin', 'goshuin_limited', 'goshuin_seasonal', 'station_stamp', 'other_stamp']
const MEDIUMS: Medium[] = ['jikigaki', 'kakioki', 'stamped_paper', 'digital', 'other']
const PRECISIONS: Precision[] = ['day', 'month', 'season', 'year', 'unknown']
const VISIT_KINDS: VisitKind[] = ['in_person', 'mail', 'event']
const SEASON_MONTH = { winter: '01', spring: '03', summer: '06', autumn: '09' } as const
type Season = keyof typeof SEASON_MONTH

interface Props {
  placeId: string
  /** Si se indica, añade un goshuin a esta visita en lugar de crear otra. */
  visitId?: string
  onClose: () => void
  onSaved: (visit?: Visit) => void
}

export default function AddVisitSheet({ placeId, visitId, onClose, onSaved }: Props) {
  const { t } = useI18n()
  const books = useBooks()
  const ids = useRef({ visit: newId(), stamp: newId() })
  const today = todayIso()
  const year = Number(today.slice(0, 4))

  const [day, setDay] = useState(today)
  const [month, setMonth] = useState(today.slice(0, 7))
  const [season, setSeason] = useState<Season>('spring')
  const [yearValue, setYearValue] = useState(String(year))
  const [precision, setPrecision] = useState<Precision>('day')
  const [visitKind, setVisitKind] = useState<VisitKind>('in_person')
  const [eventLocation, setEventLocation] = useState('')
  const [stampKind, setStampKind] = useState<StampKind | ''>(visitId ? 'goshuin' : 'goshuin')
  const [medium, setMedium] = useState<Medium | ''>('')
  const [title, setTitle] = useState('')
  const [donation, setDonation] = useState('')
  const [book, setBook] = useState('')
  const [notes, setNotes] = useState('')
  const [more, setMore] = useState(false)

  const [file, setFile] = useState<File | null>(null)
  const [upload, setUpload] = useState<Promise<MediaOut> | null>(null)
  const [uploading, setUploading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<MessageKey | null>(null)
  const preview = useMemo(() => (file ? URL.createObjectURL(file) : null), [file])
  useEffect(() => () => void (preview && URL.revokeObjectURL(preview)), [preview])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  function startUpload(f: File) {
    setFile(f)
    setError(null)
    setUploading(true)
    const p = uploadMedia(f)
    p.catch(() => setError('sheet.error_photo')).finally(() => setUploading(false))
    setUpload(p)
  }

  function visitedOn(): string | null {
    switch (precision) {
      case 'day': return day
      case 'month': return `${month}-01`
      case 'season': return `${yearValue}-${SEASON_MONTH[season]}-01`
      case 'year': return `${yearValue}-01-01`
      default: return null
    }
  }

  async function save() {
    setSaving(true)
    setError(null)
    try {
      let media: MediaOut | null = null
      if (upload) media = await upload
      const stamp = stampKind
        ? {
            id: ids.current.stamp,
            kind: stampKind,
            medium: medium || null,
            title: title || null,
            donation_yen: donation ? Number(donation) : null,
            goshuincho_id: book || null,
            media: media ? [{ media_id: media.id }] : [],
          }
        : null
      if (visitId) {
        if (stamp) await api(`/visits/${visitId}/stamps`, { method: 'POST', json: { ...stamp, notes: notes || null } })
        onSaved()
        return
      }
      const visit = await api<Visit>(`/places/${placeId}/visits`, {
        method: 'POST',
        json: {
          id: ids.current.visit,
          kind: visitKind,
          event_location: visitKind === 'event' ? eventLocation || null : null,
          visited_on: visitedOn(),
          visited_precision: precision,
          notes: notes || null,
          media: !stamp && media ? [media.id] : [],
          stamps: stamp ? [stamp] : [],
        },
      })
      onSaved(visit)
    } catch (err) {
      if (err instanceof ApiError && err.detail === 'date_in_future') setError('sheet.error_future')
      else if (err instanceof ApiError && (err.status === 413 || err.status === 415)) setError('sheet.error_photo')
      else setError('sheet.error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <form
        className="sheet"
        role="dialog"
        aria-label={t(visitId ? 'place.add_stamp' : 'sheet.title')}
        onClick={(e) => e.stopPropagation()}
        onSubmit={(e) => {
          e.preventDefault()
          void save()
        }}
      >
        <div className="section" style={{ margin: 0 }}><small>{visitId ? '御朱印' : '参拝記録'}</small><h2>{t(visitId ? 'place.add_stamp' : 'sheet.title')}</h2></div>

        {!visitId && (
          <label>
            {t('sheet.date')}
            {precision === 'day' && <input type="date" max={today} value={day} onChange={(e) => setDay(e.target.value)} required />}
            {precision === 'month' && (
              <input type="month" max={today.slice(0, 7)} value={month} onChange={(e) => setMonth(e.target.value)} required />
            )}
            {precision === 'season' && (
              <span className="row">
                <select value={season} onChange={(e) => setSeason(e.target.value as Season)}>
                  {(Object.keys(SEASON_MONTH) as Season[]).map((s) => (
                    <option key={s} value={s}>{t(`season.${s}`)}</option>
                  ))}
                </select>
                <input type="number" min={1900} max={year} value={yearValue} onChange={(e) => setYearValue(e.target.value)} required />
              </span>
            )}
            {precision === 'year' && (
              <input type="number" min={1900} max={year} value={yearValue} onChange={(e) => setYearValue(e.target.value)} required />
            )}
            {precision === 'unknown' && <span className="muted">{t('date.unknown')}</span>}
          </label>
        )}

        <div className="photo-field">
          {preview ? <img src={preview} alt="" /> : <span className="photo-placeholder"><Camera size={28} /></span>}
          <label className="button secondary">
            {t(file ? 'sheet.photo_change' : 'sheet.photo_add')}
            <input
              type="file"
              accept="image/*"
              capture="environment"
              hidden
              onChange={(e) => e.target.files?.[0] && startUpload(e.target.files[0])}
            />
          </label>
          {uploading && <span className="muted">{t('sheet.uploading')}</span>}
        </div>

        <label>
          {t('sheet.stamp_kind')}
          <select value={stampKind} onChange={(e) => setStampKind(e.target.value as StampKind | '')}>
            {STAMP_KINDS.map((k) => (
              <option key={k} value={k}>{t(`stamp.${k}`)}</option>
            ))}
            {!visitId && <option value="">{t('sheet.no_stamp')}</option>}
          </select>
        </label>

        <button type="button" className="link" onClick={() => setMore(!more)}>
          {t(more ? 'sheet.less' : 'sheet.more')}
        </button>

        {more && (
          <div className="more">
            {!visitId && (
              <>
                <label>
                  {t('sheet.precision')}
                  <select value={precision} onChange={(e) => setPrecision(e.target.value as Precision)}>
                    {PRECISIONS.map((p) => <option key={p} value={p}>{t(`precision.${p}`)}</option>)}
                  </select>
                </label>
                <label>
                  {t('sheet.visit_kind')}
                  <select value={visitKind} onChange={(e) => setVisitKind(e.target.value as VisitKind)}>
                    {VISIT_KINDS.map((k) => <option key={k} value={k}>{t(`visit.kind.${k}`)}</option>)}
                  </select>
                </label>
                {visitKind === 'event' && (
                  <label>
                    {t('sheet.event_location')}
                    <input value={eventLocation} maxLength={200} onChange={(e) => setEventLocation(e.target.value)} />
                  </label>
                )}
              </>
            )}
            {stampKind && (
              <>
                <label>
                  {t('sheet.medium')}
                  <select value={medium} onChange={(e) => setMedium(e.target.value as Medium | '')}>
                    <option value="">—</option>
                    {MEDIUMS.map((m) => <option key={m} value={m}>{t(`medium.${m}`)}</option>)}
                  </select>
                </label>
                <label>
                  {t('sheet.title_field')}
                  <input value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} />
                </label>
                <label>
                  {t('sheet.donation')}
                  <input type="number" min={0} step={100} value={donation} onChange={(e) => setDonation(e.target.value)} />
                </label>
                {books.length > 0 && (
                  <label>
                    {t('sheet.book')}
                    <select value={book} onChange={(e) => setBook(e.target.value)}>
                      <option value="">{t('sheet.no_book')}</option>
                      {books.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                    </select>
                  </label>
                )}
              </>
            )}
            <label>
              {t('sheet.notes')}
              <textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
            </label>
          </div>
        )}

        {error && <p className="error" role="alert">{t(error)}</p>}
        <div className="row end">
          <button type="button" className="link" onClick={onClose}>{t('sheet.cancel')}</button>
          <button type="submit" disabled={saving}>{saving ? t('common.loading') : t('sheet.save')}</button>
        </div>
      </form>
    </div>
  )
}
