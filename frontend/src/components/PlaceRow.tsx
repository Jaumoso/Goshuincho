import { Link } from 'react-router-dom'
import type { PlaceListItem } from '../api'
import { usePrefectures } from '../data'
import { KindBadge } from './Icons'
import { formatWithRelative, localName, placeName, placeSubName } from '../format'
import { useI18n } from '../i18n'

export default function PlaceRow({ place, seq }: { place: PlaceListItem; seq?: number | null }) {
  const { t, locale } = useI18n()
  const prefectures = usePrefectures()
  const pref = prefectures.find((p) => p.id === place.prefecture_id)
  const sub = placeSubName(place)
  const { mine } = place
  return (
    <li>
      <Link to={`/places/${place.id}`} className={`place-row card ${mine.visit_count > 0 ? 'visited' : ''}`}>
        {seq !== undefined && (
          <span className={`seq-badge ${mine.visit_count > 0 || mine.stamp_count > 0 ? 'done' : ''}`}>{seq ?? '·'}</span>
        )}
        <KindBadge kind={place.kind} />
        <span className="grow">
          <strong>{placeName(place, locale)}</strong> {sub && <span className="ja">{sub}</span>}
          <br />
          <span className="muted small">
            {t(`kind.${place.kind}`)}
            {pref && ` · ${localName(pref, locale)}`}
            {mine.visit_count > 0 &&
              ` · ${t(mine.visit_count === 1 ? 'place.visited_1' : 'place.visited_n', { n: String(mine.visit_count) })}, ${formatWithRelative(mine.last_visit, mine.last_visit_precision ?? 'unknown', locale, t)}`}
          </span>
        </span>
        <span className="badges">
          {mine.favorite && <span title={t('place.favorite')}>★</span>}
          {mine.wishlist && <span className="heart" title={t('place.wishlist')}>♥</span>}
          {mine.visit_count > 0 && <span className="mini-seal">{mine.stamp_count > 0 ? `印 ${mine.stamp_count}` : '参拝'}</span>}
        </span>
      </Link>
    </li>
  )
}
