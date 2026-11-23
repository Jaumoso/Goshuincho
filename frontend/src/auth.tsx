import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, ApiError, type Locale, type Me } from './api'
import { useI18n } from './i18n'

interface Auth {
  user: Me | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  setLocale: (locale: Locale) => Promise<void>
  update: (me: Me) => void
  forget: () => void
}

const AuthContext = createContext<Auth | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const { setLocale: setUiLocale } = useI18n()
  const [user, setUser] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)

  const adopt = useCallback(
    (me: Me) => {
      setUser(me)
      setUiLocale(me.locale)
    },
    [setUiLocale],
  )

  useEffect(() => {
    api<Me>('/me')
      .then(adopt)
      .catch((err) => {
        if (!(err instanceof ApiError && err.status === 401)) console.error(err)
      })
      .finally(() => setLoading(false))
  }, [adopt])

  const value = useMemo<Auth>(
    () => ({
      user,
      loading,
      login: async (email, password) => adopt(await api<Me>('/auth/login', { method: 'POST', json: { email, password } })),
      logout: async () => {
        await api('/auth/logout', { method: 'POST' })
        setUser(null)
      },
      setLocale: async (locale) => {
        setUiLocale(locale)
        if (user) setUser(await api<Me>('/me', { method: 'PATCH', json: { locale } }))
      },
      update: setUser,
      forget: () => setUser(null),
    }),
    [user, loading, adopt, setUiLocale],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// oxlint-disable-next-line react/only-export-components
export function useAuth(): Auth {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth fuera de AuthProvider')
  return ctx
}
