import { useEffect, useState } from 'react'
import { api, type KanjiReading as Reading, type KanjiToken } from '../api'
import { useI18n } from '../i18n'

const hintCache = new Map<string, Promise<KanjiToken[]>>()

function gloss(token: KanjiToken, locale: string) {
  return locale === 'es' ? token.gloss_es ?? token.gloss_en : token.gloss_en ?? token.gloss_es
}

/** Furigana, rōmaji y glosario de un texto japonés. */
export function KanjiReading({ text }: { text: string }) {
  const { t, locale } = useI18n()
  const [reading, setReading] = useState<Reading | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let alive = true
    const timer = setTimeout(() => {
      api<Reading>('/kanji/read', { method: 'POST', json: { text } })
        .then((r) => alive && (setReading(r), setFailed(false)))
        .catch(() => alive && setFailed(true))
    }, 350)
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [text])

  if (failed) return <p className="small muted">{t('kanji.offline')}</p>
  if (!reading) return <p className="small muted">{t('common.loading')}</p>
  const glossed = reading.tokens.filter((tk, i, all) => gloss(tk, locale) && all.findIndex((o) => o.text === tk.text) === i)
  return (
    <div className="kanji-reading">
      <p className="ruby-line" lang="ja">
        {reading.tokens.map((tk, i) =>
          tk.kana ? <ruby key={i}>{tk.text}<rt>{tk.kana}</rt></ruby> : <span key={i}>{tk.text}</span>,
        )}
      </p>
      <p className="romaji">{reading.romaji}</p>
      {glossed.length > 0 && (
        <dl className="glossary">
          {glossed.map((tk) => (
            <div key={tk.text}>
              <dt lang="ja">{tk.text}</dt>
              <dd>{gloss(tk, locale)}</dd>
            </div>
          ))}
        </dl>
      )}
      <p className="small muted">{t('kanji.disclaimer')}</p>
    </div>
  )
}

interface FieldProps {
  placeId: string
  value: string
  onChange: (value: string) => void
}

/** Campo para transcribir la inscripción con piezas sugeridas y vista de lectura. */
export function InscriptionField({ placeId, value, onChange }: FieldProps) {
  const { t, locale } = useI18n()
  const [hints, setHints] = useState<KanjiToken[]>([])
  const [show, setShow] = useState(false)

  useEffect(() => {
    let alive = true
    if (!hintCache.has(placeId)) {
      const p = api<KanjiToken[]>(`/kanji/hints?place_id=${placeId}`)
      p.catch(() => hintCache.delete(placeId))
      hintCache.set(placeId, p)
    }
    hintCache.get(placeId)!.then((h) => alive && setHints(h)).catch(() => {})
    return () => {
      alive = false
    }
  }, [placeId])

  function add(text: string) {
    const sep = value && !/\s$/.test(value) ? ' ' : ''
    onChange(value + sep + text)
  }

  return (
    <div className="inscription-field">
      <label>
        {t('kanji.inscription')}
        <textarea rows={2} lang="ja" maxLength={500} value={value} onChange={(e) => onChange(e.target.value)} placeholder="奉拝 …" />
      </label>
      {hints.length > 0 && (
        <div className="kanji-chips" aria-label={t('kanji.hints')}>
          {hints.map((h) => (
            <button
              type="button"
              key={h.text}
              className="kanji-chip"
              title={[h.romaji, gloss(h, locale)].filter(Boolean).join(' · ')}
              onClick={() => add(h.text)}
            >
              <span lang="ja">{h.text}</span>
              <small>{h.romaji}</small>
            </button>
          ))}
        </div>
      )}
      {value.trim() && (
        <button type="button" className="link small" onClick={() => setShow(!show)}>
          {t(show ? 'kanji.hide' : 'kanji.read')}
        </button>
      )}
      {show && value.trim() && <KanjiReading text={value.trim()} />}
    </div>
  )
}
