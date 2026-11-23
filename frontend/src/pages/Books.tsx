import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, newId, type Goshuincho } from '../api'
import { invalidate } from '../data'
import { useI18n } from '../i18n'

const COVERS = ['#c8321a', '#1f3557', '#5d7d34', '#7a2e4d', '#1b1714', '#b7862f']

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
      <div className="section"><small>御朱印帳</small><h1>{t('books.title')}</h1></div>
      {books?.length === 0 && <p className="muted">{t('books.empty')}</p>}
      <ul className="books">
        {books?.map((b, i) => (
          <li key={b.id}>
            <Link to={`/collection?book=${b.id}`} className="cover" style={{ '--c': COVERS[i % COVERS.length] } as React.CSSProperties}>
              <span className="daisen">{b.name}</span>
              <span className="count"><span className="mini-seal">印 {b.stamp_count}</span></span>
            </Link>
            <div className="book-meta">
              {b.started_on && <span>{t('books.started')} {b.started_on}</span>}
              <label className="inline">
                {t('books.finished')}
                <input type="date" value={b.finished_on ?? ''} onChange={(e) => void finish(b, e.target.value)} />
              </label>
              <button className="link small" style={{ justifySelf: 'start', padding: 0 }} onClick={() => void remove(b)}>{t('books.delete')}</button>
            </div>
          </li>
        ))}
      </ul>
      <div className="section"><small>新しい御朱印帳</small><h2>{t('books.new')}</h2></div>
      <form className="card row wrap" onSubmit={(e) => void create(e)}>
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
