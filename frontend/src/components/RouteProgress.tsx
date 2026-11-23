import { Link } from 'react-router-dom'
import type { CategoryProgress } from '../api'
import { localName } from '../format'
import { useI18n } from '../i18n'

export function ProgressBar({ done, total }: { done: number; total: number }) {
  const pct = total ? Math.min(100, (done / total) * 100) : 0
  return (
    <span className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done}>
      <span style={{ width: `${pct}%` }} />
    </span>
  )
}

export default function RouteCard({ route }: { route: CategoryProgress }) {
  const { t, locale } = useI18n()
  const complete = route.total > 0 && route.done >= route.total
  return (
    <li>
      <Link to={`/routes/${route.slug}`} className={`route-card card ${complete ? 'complete' : ''}`}>
        <span className="grow">
          <strong>{localName(route, locale)}</strong> {route.name_ja && <span className="ja">{route.name_ja}</span>}
          <ProgressBar done={route.done} total={route.total} />
          <span className="muted small">
            {t('routes.stamped', { n: String(route.stamped) })}
            {route.members < route.total && ` · ${t('routes.linked', { n: String(route.members), total: String(route.total) })}`}
          </span>
        </span>
        <span className="route-count">
          {complete ? <span className="hanko">満願</span> : <><b>{route.done}</b><small>/{route.total}</small></>}
        </span>
      </Link>
    </li>
  )
}
