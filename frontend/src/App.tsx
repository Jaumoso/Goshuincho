import type { ReactNode } from 'react'
import { BrowserRouter, Navigate, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth'
import { I18nProvider, useI18n } from './i18n'
import Books from './pages/Books'
import Collection from './pages/Collection'
import Home from './pages/Home'
import Login from './pages/Login'
import NewPlace from './pages/NewPlace'
import PlaceDetail from './pages/PlaceDetail'
import Places from './pages/Places'

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  const { t } = useI18n()
  const location = useLocation()
  if (loading) return <p className="page muted">{t('common.loading')}</p>
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return children
}

function Header() {
  const { user, logout, setLocale } = useAuth()
  const { t, locale } = useI18n()
  if (!user) return null
  return (
    <header className="topbar">
      <NavLink to="/" className="brand">Goshuinchō</NavLink>
      <select aria-label={t('nav.language')} value={locale} onChange={(e) => setLocale(e.target.value as 'es' | 'en')}>
        <option value="es">ES</option>
        <option value="en">EN</option>
      </select>
      <button className="link" onClick={() => logout()}>
        {t('nav.logout')}
      </button>
    </header>
  )
}

function TabBar() {
  const { user } = useAuth()
  const { t } = useI18n()
  if (!user) return null
  const tabs = [
    { to: '/', icon: '🏠', label: t('nav.home') },
    { to: '/places', icon: '⛩️', label: t('nav.places') },
    { to: '/collection', icon: '印', label: t('nav.collection') },
    { to: '/books', icon: '📕', label: t('nav.books') },
  ]
  return (
    <nav className="tabbar">
      {tabs.map((tab) => (
        <NavLink key={tab.to} to={tab.to} end={tab.to === '/' || tab.to === '/places'}>
          <span aria-hidden>{tab.icon}</span>
          {tab.label}
        </NavLink>
      ))}
    </nav>
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
            <Route path="/collection" element={authed(<Collection />)} />
            <Route path="/books" element={authed(<Books />)} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          <TabBar />
        </BrowserRouter>
      </AuthProvider>
    </I18nProvider>
  )
}
