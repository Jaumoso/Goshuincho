import { useEffect, useRef, useState, type FormEvent } from 'react'
import { api, ApiError, downloadExport, importArchive, shareUrl, type ImportResult, type Me, type ShareLink } from '../api'
import { useBooks } from '../data'
import { useAuth } from '../auth'
import { useI18n } from '../i18n'
import { discard, retry, syncOutbox, useOutbox } from '../outbox'

type Notice = { kind: 'ok' | 'error'; text: string } | null

function Message({ notice }: { notice: Notice }) {
  if (!notice) return null
  return (
    <p className={notice.kind === 'ok' ? 'success' : 'error'} role={notice.kind === 'ok' ? 'status' : 'alert'}>
      {notice.text}
    </p>
  )
}

function Profile() {
  const { user, update, setLocale } = useAuth()
  const { t, locale } = useI18n()
  const [name, setName] = useState(user?.display_name ?? '')
  const [notice, setNotice] = useState<Notice>(null)

  async function save(event: FormEvent) {
    event.preventDefault()
    try {
      update(await api<Me>('/me', { method: 'PATCH', json: { display_name: name } }))
      setNotice({ kind: 'ok', text: t('settings.saved') })
    } catch {
      setNotice({ kind: 'error', text: t('common.error') })
    }
  }

  return (
    <form className="card settings-card" onSubmit={save}>
      <p className="muted small">{user?.email}</p>
      <label>
        {t('settings.display_name')}
        <input required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label>
        {t('nav.language')}
        <select value={locale} onChange={(e) => setLocale(e.target.value as 'es' | 'en')}>
          <option value="es">Español</option>
          <option value="en">English</option>
        </select>
      </label>
      <Message notice={notice} />
      <button type="submit">{t('sheet.save')}</button>
    </form>
  )
}

function Password() {
  const { t } = useI18n()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [notice, setNotice] = useState<Notice>(null)
  const [busy, setBusy] = useState(false)

  async function save(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setNotice(null)
    try {
      await api('/me/password', { method: 'POST', json: { current_password: current, new_password: next } })
      setCurrent('')
      setNext('')
      setNotice({ kind: 'ok', text: t('settings.password_changed') })
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) setNotice({ kind: 'error', text: t('settings.wrong_password') })
      else if (err instanceof ApiError && err.status === 400 && err.detail) setNotice({ kind: 'error', text: err.detail })
      else setNotice({ kind: 'error', text: t('common.error') })
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card settings-card" onSubmit={save}>
      <label>
        {t('settings.current_password')}
        <input type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} />
      </label>
      <label>
        {t('settings.new_password')}
        <input type="password" autoComplete="new-password" required minLength={8} value={next} onChange={(e) => setNext(e.target.value)} />
      </label>
      <Message notice={notice} />
      <button type="submit" disabled={busy}>{t('settings.change_password')}</button>
    </form>
  )
}

function Sharing() {
  const { t, locale } = useI18n()
  const books = useBooks()
  const [links, setLinks] = useState<ShareLink[] | null>(null)
  const [book, setBook] = useState('')
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<Notice>(null)

  useEffect(() => {
    api<ShareLink[]>('/share-links').then(setLinks).catch(() => setLinks([]))
  }, [])

  async function create(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setNotice(null)
    try {
      const link = await api<ShareLink>('/share-links', {
        method: 'POST',
        json: { goshuincho_id: book || null, title: title || null },
      })
      setLinks([link, ...(links ?? [])])
      setTitle('')
      await copy(link)
    } catch {
      setNotice({ kind: 'error', text: t('common.error') })
    } finally {
      setBusy(false)
    }
  }

  async function copy(link: ShareLink) {
    const url = shareUrl(link.token)
    try {
      if (navigator.share && matchMedia('(pointer: coarse)').matches) await navigator.share({ url })
      else await navigator.clipboard.writeText(url)
      setNotice({ kind: 'ok', text: t('share.copied') })
    } catch {
      window.prompt(t('share.copy_prompt'), url)
    }
  }

  async function remove(link: ShareLink) {
    if (!window.confirm(t('share.revoke_confirm'))) return
    await api(`/share-links/${link.id}`, { method: 'DELETE' })
    setLinks((links ?? []).filter((l) => l.id !== link.id))
  }

  return (
    <div className="card settings-card">
      <p className="muted small">{t('share.help')}</p>
      <form onSubmit={create}>
        <label>
          {t('share.scope')}
          <select value={book} onChange={(e) => setBook(e.target.value)}>
            <option value="">{t('share.all')}</option>
            {books.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        </label>
        <label>
          {t('share.title_label')}
          <input maxLength={200} value={title} placeholder={t('share.title_placeholder')} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <button className="primary" disabled={busy}>{t('share.create')}</button>
      </form>
      <Message notice={notice} />
      {!!links?.length && (
        <ul className="outbox-list share-list">
          {links.map((l) => (
            <li key={l.id}>
              <div>
                <b>{l.title || l.goshuincho_name || t('share.all')}</b>
                <small>
                  {l.goshuincho_name ?? t('share.all')} · {t('share.views', { n: String(l.view_count) })}
                  {l.last_viewed_at && ` · ${new Date(l.last_viewed_at).toLocaleDateString(locale)}`}
                </small>
              </div>
              <div className="outbox-actions">
                <a href={shareUrl(l.token)} target="_blank" rel="noreferrer">{t('share.open')}</a>
                <button type="button" onClick={() => void copy(l)}>{t('share.copy')}</button>
                <button type="button" className="danger" onClick={() => void remove(l)}>{t('share.revoke')}</button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Backup() {
  const { t } = useI18n()
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState<'export' | 'import' | null>(null)
  const [notice, setNotice] = useState<Notice>(null)
  const [result, setResult] = useState<ImportResult | null>(null)

  async function exportNow() {
    setBusy('export')
    setNotice(null)
    try {
      await downloadExport()
    } catch {
      setNotice({ kind: 'error', text: t('common.error') })
    } finally {
      setBusy(null)
    }
  }

  async function importFile(file: File | undefined) {
    if (!file) return
    setBusy('import')
    setNotice(null)
    setResult(null)
    try {
      setResult(await importArchive(file))
    } catch (err) {
      const invalid = err instanceof ApiError && err.status === 400
      setNotice({ kind: 'error', text: t(invalid ? 'settings.import_invalid' : 'common.error') })
    } finally {
      setBusy(null)
      if (input.current) input.current.value = ''
    }
  }

  return (
    <div className="card settings-card">
      <p className="muted small">{t('settings.export_help')}</p>
      <button type="button" onClick={exportNow} disabled={busy !== null}>
        {busy === 'export' ? t('settings.exporting') : t('settings.export')}
      </button>
      <hr className="dashed" />
      <p className="muted small">{t('settings.import_help')}</p>
      <input ref={input} type="file" accept=".zip,application/zip" hidden onChange={(e) => importFile(e.target.files?.[0])} />
      <button type="button" className="secondary" onClick={() => input.current?.click()} disabled={busy !== null}>
        {busy === 'import' ? t('settings.importing') : t('settings.import')}
      </button>
      <Message notice={notice} />
      {result && (
        <p className="success" role="status">
          {t('settings.import_done', {
            visits: String(result.visits),
            stamps: String(result.stamps),
            media: String(result.media),
            created: String(result.places_created),
          })}
        </p>
      )}
    </div>
  )
}

function DangerZone() {
  const { t } = useI18n()
  const { logout, forget } = useAuth()
  const [open, setOpen] = useState(false)
  const [password, setPassword] = useState('')
  const [notice, setNotice] = useState<Notice>(null)

  async function remove(event: FormEvent) {
    event.preventDefault()
    try {
      await api('/me/delete', { method: 'POST', json: { password } })
      forget()
    } catch (err) {
      const key =
        err instanceof ApiError && err.status === 403
          ? 'settings.wrong_password'
          : err instanceof ApiError && err.status === 409
            ? 'settings.last_admin'
            : 'common.error'
      setNotice({ kind: 'error', text: t(key) })
    }
  }

  return (
    <div className="card settings-card">
      <button type="button" className="secondary" onClick={() => logout()}>{t('nav.logout')}</button>
      <hr className="dashed" />
      {!open ? (
        <button type="button" className="link danger" onClick={() => setOpen(true)}>{t('settings.delete_account')}</button>
      ) : (
        <form onSubmit={remove} className="settings-delete">
          <p className="notice">{t('settings.delete_warning')}</p>
          <label>
            {t('settings.confirm_password')}
            <input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
          <Message notice={notice} />
          <div className="row">
            <button type="button" className="secondary" onClick={() => setOpen(false)}>{t('sheet.cancel')}</button>
            <button type="submit" className="danger">{t('settings.delete_forever')}</button>
          </div>
        </form>
      )}
    </div>
  )
}

function Outbox() {
  const { t, locale } = useI18n()
  const items = useOutbox()
  if (items.length === 0) return null
  return (
    <>
      <div className="section"><small>未送信</small><h2>{t('offline.title')}</h2></div>
      <div className="card settings-card">
        <p className="muted">{navigator.onLine ? t('offline.help_online') : t('offline.help_offline')}</p>
        <ul className="outbox-list">
          {items.map((i) => (
            <li key={i.id} className={i.error ? 'failed' : ''}>
              <div>
                <b>{i.placeName}</b>
                <small>
                  {t(i.type === 'visit' ? 'offline.kind_visit' : 'offline.kind_stamp')} ·{' '}
                  {new Date(i.createdAt).toLocaleString(locale)}
                </small>
                {i.error && <small className="error">{t('offline.failed', { error: i.error })}</small>}
              </div>
              <div className="outbox-actions">
                {i.error && <button type="button" onClick={() => void retry(i.id)}>{t('offline.retry')}</button>}
                <button
                  type="button"
                  className="danger"
                  onClick={() => window.confirm(t('offline.discard_confirm')) && void discard(i.id)}
                >
                  {t('offline.discard')}
                </button>
              </div>
            </li>
          ))}
        </ul>
        <button type="button" className="primary" onClick={() => void syncOutbox()}>{t('offline.sync')}</button>
      </div>
    </>
  )
}

export default function Settings() {
  const { t } = useI18n()
  return (
    <main className="page settings">
      <div className="section"><small>設定</small><h1>{t('settings.title')}</h1></div>

      <Outbox />

      <div className="section"><small>名前</small><h2>{t('settings.profile')}</h2></div>
      <Profile />

      <div className="section"><small>合言葉</small><h2>{t('settings.password')}</h2></div>
      <Password />

      <div className="section"><small>共有</small><h2>{t('share.section')}</h2></div>
      <Sharing />

      <div className="section"><small>控え</small><h2>{t('settings.backup')}</h2></div>
      <Backup />

      <div className="section"><small>退会</small><h2>{t('settings.account')}</h2></div>
      <DangerZone />
    </main>
  )
}
