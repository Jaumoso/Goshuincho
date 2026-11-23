import { useEffect, useState } from 'react'
import { api, type Prefecture, type Region } from '../api'
import { useAuth } from '../auth'
import { useI18n } from '../i18n'

export default function Home() {
  const { user } = useAuth()
  const { t, locale } = useI18n()
  const [regions, setRegions] = useState<Region[]>([])
  const [prefectures, setPrefectures] = useState<Prefecture[]>([])

  useEffect(() => {
    Promise.all([api<Region[]>('/regions'), api<Prefecture[]>('/prefectures')])
      .then(([r, p]) => {
        setRegions(r)
        setPrefectures(p)
      })
      .catch(console.error)
  }, [])

  const name = (item: { name_es: string; name_en: string }) => (locale === 'es' ? item.name_es : item.name_en)

  return (
    <main className="page">
      <h1>{t('home.welcome', { name: user?.display_name ?? '' })}</h1>
      <p className="muted">{t('home.soon')}</p>
      {user?.role === 'admin' && (
        <p>
          <a href="/admin/">{t('home.admin')}</a>
        </p>
      )}
      <h2>{t('home.regions')}</h2>
      <div className="regions">
        {regions.map((region) => (
          <section key={region.id} className="card">
            <h3>
              {name(region)} <span className="ja">{region.name_ja}</span>
            </h3>
            <ul>
              {prefectures
                .filter((p) => p.region_id === region.id)
                .map((p) => (
                  <li key={p.id}>
                    {name(p)} <span className="ja">{p.name_ja}</span>
                  </li>
                ))}
            </ul>
          </section>
        ))}
      </div>
    </main>
  )
}
