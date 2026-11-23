import { useEffect, useState } from 'react'
import { api, mediaUrl, type Stamp } from '../api'
import { useI18n } from '../i18n'
import { InscriptionField, KanjiReading } from './Kanji'

interface Props {
  stamp: Stamp
  onClose: () => void
  onSaved: (stamp: Stamp) => void
}

/** Detalle de un goshuin: foto, inscripción con su lectura y edición de la inscripción. */
export default function StampSheet({ stamp, onClose, onSaved }: Props) {
  const { t } = useI18n()
  const [editing, setEditing] = useState(!stamp.inscription)
  const [value, setValue] = useState(stamp.inscription ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  async function save() {
    setSaving(true)
    setError(false)
    try {
      const updated = await api<Stamp>(`/stamps/${stamp.id}`, { method: 'PATCH', json: { inscription: value.trim() || null } })
      onSaved(updated)
      setEditing(!updated.inscription)
    } catch {
      setError(true)
    } finally {
      setSaving(false)
    }
  }

  const photo = stamp.media[0]
  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="sheet stamp-sheet" role="dialog" aria-label={stamp.title || t(`stamp.${stamp.kind}`)} onClick={(e) => e.stopPropagation()}>
        <div className="section" style={{ margin: 0 }}><small>御朱印</small><h2>{stamp.title || t(`stamp.${stamp.kind}`)}</h2></div>
        {photo && (
          <a href={mediaUrl(photo.id, 'original')} target="_blank" rel="noreferrer">
            <img className="stamp-photo" src={mediaUrl(photo.id, 'medium')} alt="" />
          </a>
        )}
        {editing ? (
          <form
            onSubmit={(e) => {
              e.preventDefault()
              void save()
            }}
          >
            <InscriptionField placeId={stamp.place_id} value={value} onChange={setValue} />
            {error && <p className="error" role="alert">{t('sheet.error')}</p>}
            <div className="row end">
              {stamp.inscription && <button type="button" className="link" onClick={() => setEditing(false)}>{t('sheet.cancel')}</button>}
              <button type="submit" disabled={saving}>{saving ? t('common.loading') : t('sheet.save')}</button>
            </div>
          </form>
        ) : (
          <>
            <div className="section" style={{ margin: 0 }}><small>読み</small><h3>{t('kanji.inscription')}</h3></div>
            <KanjiReading text={stamp.inscription ?? ''} />
            <div className="row end">
              <button type="button" className="link" onClick={() => setEditing(true)}>{t('kanji.edit')}</button>
              <button type="button" className="secondary" onClick={onClose}>{t('common.close')}</button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
