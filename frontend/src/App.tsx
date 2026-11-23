import { lazy, Suspense, type ReactNode } from 'react'
import { BrowserRouter, Navigate, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth'
import { Book, Lantern, MapIcon, Seal, Torii } from './components/Icons'
import { I18nProvider, useI18n } from './i18n'
import { useOutbox } from './outbox'
import Books from './pages/Books'
import Collection from './pages/Collection'
import Home from './pages/Home'
import Login from './pages/Login'
import NewPlace from './pages/NewPlace'
import PlaceDetail from './pages/PlaceDetail'
import Places from './pages/Places'
import RouteDetail from './pages/RouteDetail'
import Settings from './pages/Settings'
import StatsPage from './pages/Stats'

// maplibre pesa ~800 kB: solo se descarga al abrir el mapa.
const MapPage = lazy(() => import('./pages/MapPage'))

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  const { t } = useI18n()
  const location = useLocation()
  if (loading) return <p className="page muted">{t('common.loading')}</p>
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return children
}

function Header() {
  const { user, setLocale } = useAuth()
  const { t, locale } = useI18n()
  const pending = useOutbox().length
  if (!user) return null
  return (
    <header className="topbar">
      <NavLink to="/" className="brand">
        <span className="hanko vertical logo" aria-hidden>朱印</span>
        <b>Goshuinchō</b>
      </NavLink>
      <select aria-label={t('nav.language')} value={locale} onChange={(e) => setLocale(e.target.value as 'es' | 'en')}>
        <option value="es">ES</option>
        <option value="en">EN</option>
      </select>
      <NavLink to="/settings" className="topbar-link">
        <span className="ja" aria-hidden>設定</span> {t('nav.settings')}
        {pending > 0 && (
          <span className="outbox-badge" title={t('offline.pending_title')} aria-label={t('offline.pending_title')}>
            {pending}
          </span>
        )}
      </NavLink>
    </header>
  )
}

function TabBar() {
  const { user } = useAuth()
  const { t } = useI18n()
  if (!user) return null
  const tabs = [
    { to: '/', icon: <Lantern />, label: t('nav.home') },
    { to: '/places', icon: <Torii />, label: t('nav.places') },
    { to: '/map', icon: <MapIcon />, label: t('nav.map') },
    { to: '/collection', icon: <Seal />, label: t('nav.collection') },
    { to: '/books', icon: <Book />, label: t('nav.books') },
  ]
  return (
    <nav className="tabbar">
      {tabs.map((tab) => (
        <NavLink key={tab.to} to={tab.to} end={tab.to === '/' || tab.to === '/places'}>
          <span className="tab-icon">{tab.icon}</span>
          {tab.label}
        </NavLink>
      ))}
    </nav>
  )
}

function MapRoute() {
  const { t } = useI18n()
  return (
    <Suspense fallback={<p className="page muted">{t('common.loading')}</p>}>
      <MapPage />
    </Suspense>
  )
}

const authed = (element: ReactNode) => <RequireAuth>{element}</RequireAuth>

export default function App() {
  return (
    <I18nProvider>
      <AuthProvider>
        <BrowserRouter>
          <Header />
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/" element={authed(<Home />)} />
            <Route path="/places" element={authed(<Places />)} />
            <Route path="/places/new" element={authed(<NewPlace />)} />
            <Route path="/places/:id" element={authed(<PlaceDetail />)} />
            <Route path="/map" element={authed(<MapRoute />)} />
            <Route path="/collection" element={authed(<Collection />)} />
            <Route path="/books" element={authed(<Books />)} />
            <Route path="/routes/:slug" element={authed(<RouteDetail />)} />
            <Route path="/stats" element={authed(<StatsPage />)} />
            <Route path="/settings" element={authed(<Settings />)} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          <TabBar />
        </BrowserRouter>
      </AuthProvider>
    </I18nProvider>
  )
}
