import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Prefecture, type StatsDetail } from '../api'
import { KindBadge } from '../components/Icons'
import { ProgressBar } from '../components/RouteProgress'
import { usePrefectures, useRegions } from '../data'
import { localName } from '../format'
import { useI18n } from '../i18n'

/** 京都府 → 京都, 北海道 stays whole. */
function shortJa(p: Prefecture): string {
  return p.name_ja === '北海道' ? p.name_ja : p.name_ja.replace(/[都府県]$/, '')
}

function level(count: number, max: number): number {
  if (!count) return 0
  return Math.max(1, Math.ceil((count / Math.max(max, 1)) * 4))
}

function iso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function Heatmap({ year, days }: { year: number; days: StatsDetail['heatmap'] }) {
  const { t, locale } = useI18n()
  const counts = new Map(days.map((d) => [d.date, d.count]))
  const max = Math.max(0, ...days.map((d) => d.count))
  const start = new Date(year, 0, 1)
  const offset = (start.getDay() + 6) % 7 // lunes primero
  const cells: (Date | null)[] = Array.from({ length: offset }, () => null)
  for (let d = new Date(start); d.getFullYear() === year; d.setDate(d.getDate() + 1)) cells.push(new Date(d))
  const monthFmt = new Intl.DateTimeFormat(locale, { month: 'short' })
  const months = Array.from({ length: 12 }, (_, m) => {
    const first = new Date(year, m, 1)
    const index = offset + Math.round((first.getTime() - start.getTime()) / 86400000)
    return { label: monthFmt.format(first), col: Math.floor(index / 7) + 1 }
  })
  return (
    <div className="heatmap-wrap">
      <div className="heatmap-months" aria-hidden>
        {months.map((m) => <span key={m.label} style={{ gridColumn: m.col }}>{m.label}</span>)}
      </div>
      <div className="heatmap" role="img" aria-label={t('stats.days', { n: String(days.length) })}>
        {cells.map((d, i) => {
          if (!d) return <span key={`e${i}`} className="empty" />
          const key = iso(d)
          const n = counts.get(key) ?? 0
          return <span key={key} className={`l${level(n, max)}`} title={n ? `${key} · ${n}` : key} />
        })}
      </div>
      <div className="heatmap-legend muted small">
        {t('stats.less')} {[0, 1, 2, 3, 4].map((l) => <span key={l} className={`l${l}`} />)} {t('stats.more_visits')}
      </div>
    </div>
  )
}

export default function StatsPage() {
  const { t, locale } = useI18n()
  const prefectures = usePrefectures()
  const regions = useRegions()
  const [year, setYear] = useState<number | null>(null)
  const [thisYear] = useState(() => new Date().getFullYear())
  const [stats, setStats] = useState<StatsDetail | null>(null)

  useEffect(() => {
    api<StatsDetail>(`/stats/detail${year ? `?year=${year}` : ''}`).then(setStats).catch(console.error)
  }, [year])

  const byPref = useMemo(() => new Map(stats?.by_prefecture.map((p) => [p.id, p]) ?? []), [stats])
  if (!stats) return <main className="page muted">{t('common.loading')}</main>

  const maxPref = Math.max(0, ...stats.by_prefecture.map((p) => p.visited))
  const visitedPrefs = stats.by_prefecture.filter((p) => p.visited > 0 || p.goshuin > 0).sort((a, b) => b.visited - a.visited || b.goshuin - a.goshuin)
  const maxYear = Math.max(0, ...stats.goshuin_by_year.map((y) => y.count))
  const yearOptions = [...new Set([thisYear, ...stats.years])].sort((a, b) => b - a)

  return (
    <main className="page stats-page">
      <div className="section"><small>記録</small><h1>{t('stats.title')}</h1></div>

      <div className="stats streaks">
        <div className="stat"><span className="seal">{stats.current_streak_months}</span><span><span className="ja">連続</span>{t('stats.streak_current')}</span></div>
        <div className="stat"><span className="seal">{stats.longest_streak_months}</span><span><span className="ja">最長</span>{t('stats.streak_longest')}</span></div>
      </div>

      <div className="section row">
        <span className="grow"><small>参拝暦</small><h2>{t('stats.heatmap')}</h2></span>
        <select value={stats.heatmap_year} onChange={(e) => setYear(Number(e.target.value))} aria-label={t('stats.heatmap')}>
          {yearOptions.map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
      </div>
      <div className="card">
        <Heatmap year={stats.heatmap_year} days={stats.heatmap} />
        <p className="muted small">
          {stats.heatmap.length
            ? t('stats.days', { n: String(stats.heatmap.length) })
            : t('stats.heatmap_empty', { year: String(stats.heatmap_year) })}
        </p>
      </div>

      <div className="section"><small>都道府県</small><h2>{t('stats.prefecture_map')}</h2></div>
      <div className="pref-grid">
        {prefectures.map((p) => {
          const s = byPref.get(p.id)
          const visited = s?.visited ?? 0
          return (
            <Link
              key={p.id}
              to={`/places?prefecture=${p.id}${visited ? '&state=visited' : ''}`}
              className={`pref-tile l${level(visited, maxPref)}`}
              title={`${localName(p, locale)}: ${t('stats.prefecture_line', { n: String(visited), g: String(s?.goshuin ?? 0) })}`}
            >
              <span className="ja">{shortJa(p)}</span>
              {visited > 0 && <b>{visited}</b>}
            </Link>
          )
        })}
      </div>
      <ul className="stat-lines">
        {visitedPrefs.map((s) => {
          const p = prefectures.find((x) => x.id === s.id)
          return (
            <li key={s.id}>
              <strong>{p ? localName(p, locale) : s.id}</strong>
              <span className="muted">{t('stats.prefecture_line', { n: String(s.visited), g: String(s.goshuin) })}</span>
            </li>
          )
        })}
      </ul>

      <div className="section"><small>地方</small><h2>{t('stats.regions')}</h2></div>
      <ul className="list">
        {stats.by_region.map((r) => {
          const region = regions.find((x) => x.id === r.id)
          return (
            <li key={r.id} className="card region-line">
              <span className="row">
                <strong className="grow">{region ? localName(region, locale) : r.id} {region && <span className="ja">{region.name_ja}</span>}</strong>
                <span><b>{r.visited}</b> <span className="muted small">{t('stats.of', { n: r.places.toLocaleString(locale) })}</span></span>
              </span>
              <ProgressBar done={r.visited} total={r.places} />
            </li>
          )
        })}
      </ul>

      {stats.goshuin_by_year.length > 0 && (
        <>
          <div className="section"><small>年別御朱印</small><h2>{t('stats.goshuin_year')}</h2></div>
          <div className="card year-bars">
            {stats.goshuin_by_year.map((y) => (
              <span key={y.key} className="year-bar">
                <b>{y.count}</b>
                <span className="bar" style={{ height: `${(y.count / Math.max(maxYear, 1)) * 100}%` }} />
                <small>{y.key}</small>
              </span>
            ))}
          </div>
        </>
      )}

      {stats.by_place_kind.length > 0 && (
        <>
          <div className="section"><small>種類</small><h2>{t('stats.kinds')}</h2></div>
          <div className="row wrap kind-counts">
            {stats.by_place_kind.map((k) => (
              <span key={k.key} className="card row">
                <KindBadge kind={k.key} /> <b>{k.count}</b> {t(`kind.${k.key}`)}
              </span>
            ))}
          </div>
        </>
      )}
    </main>
  )
}
