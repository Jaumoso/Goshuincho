import type { ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth'
import { I18nProvider, useI18n } from './i18n'
import Home from './pages/Home'
import Login from './pages/Login'

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
      <span className="brand">Goshuinchō</span>
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

export default function App() {
  return (
    <I18nProvider>
      <AuthProvider>
        <BrowserRouter>
          <Header />
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route
              path="/"
              element={
                <RequireAuth>
                  <Home />
                </RequireAuth>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </I18nProvider>
  )
}
