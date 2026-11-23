import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, newId, type Goshuincho } from '../api'
import { invalidate } from '../data'
import { useI18n } from '../i18n'

export default function Books() {
  const { t } = useI18n()
  const [books, setBooks] = useState<Goshuincho[] | null>(null)
  const [name, setName] = useState('')
  const [started, setStarted] = useState('')
  const [error, setError] = useState(false)

  const load = () => api<Goshuincho[]>('/goshuincho').then(setBooks).catch(console.error)
  useEffect(() => void load(), [])

  async function create(e: React.FormEvent) {
    e.preventDefault()
    setError(false)
    try {
      await api('/goshuincho', { method: 'POST', json: { id: newId(), name: name.trim(), started_on: started || null } })
      setName('')
      setStarted('')
      invalidate('/goshuincho')
      await load()
    } catch {
      setError(true)
    }
  }

  async function finish(book: Goshuincho, finished_on: string) {
    await api(`/goshuincho/${book.id}`, { method: 'PATCH', json: { finished_on: finished_on || null } })
    invalidate('/goshuincho')
    await load()
  }

  async function remove(book: Goshuincho) {
    if (!confirm(t('books.confirm_delete'))) return
    await api(`/goshuincho/${book.id}`, { method: 'DELETE' })
    invalidate('/goshuincho')
    await load()
  }

  return (
    <main className="page">
      <h1>{t('books.title')}</h1>
      {books?.length === 0 && <p className="muted">{t('books.empty')}</p>}
      <ul className="list">
        {books?.map((b) => (
          <li key={b.id} className="card row wrap">
            <span className="grow">
              <Link to={`/collection?book=${b.id}`}><strong>📕 {b.name}</strong></Link>
              <br />
              <span className="muted small">
                {t('place.stamps_n', { n: String(b.stamp_count) })}
                {b.started_on && ` · ${t('books.started')} ${b.started_on}`}
              </span>
            </span>
            <label className="inline small">
              {t('books.finished')}
              <input type="date" value={b.finished_on ?? ''} onChange={(e) => void finish(b, e.target.value)} />
            </label>
            <button className="link small" onClick={() => void remove(b)}>{t('books.delete')}</button>
          </li>
        ))}
      </ul>
      <h2>{t('books.new')}</h2>
      <form className="row wrap" onSubmit={(e) => void create(e)}>
        <input placeholder={t('books.name')} value={name} maxLength={100} onChange={(e) => setName(e.target.value)} required />
        <label className="inline small">
          {t('books.started')}
          <input type="date" value={started} onChange={(e) => setStarted(e.target.value)} />
        </label>
        <button type="submit">{t('books.create')}</button>
      </form>
      {error && <p className="error">{t('common.error')}</p>}
    </main>
  )
}
