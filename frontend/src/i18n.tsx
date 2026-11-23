import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import type { Locale } from './api'

const messages = {
  es: {
    'app.tagline': 'Tu libro de goshuin, sellos y visitas',
    'login.title': 'Iniciar sesión',
    'login.email': 'Email',
    'login.password': 'Contraseña',
    'login.submit': 'Entrar',
    'login.invalid': 'Email o contraseña incorrectos.',
    'login.locked': 'Demasiados intentos. Vuelve a probar en unos minutos.',
    'login.error': 'No se ha podido iniciar sesión. Inténtalo de nuevo.',
    'home.welcome': 'Hola, {name}',
    'home.soon': 'Aquí aparecerán tus visitas, goshuin y el mapa.',
    'home.regions': 'Regiones y prefecturas',
    'home.admin': 'Panel de administración',
    'nav.logout': 'Cerrar sesión',
    'nav.language': 'Idioma',
    'common.loading': 'Cargando…',
  },
  en: {
    'app.tagline': 'Your book of goshuin, stamps and visits',
    'login.title': 'Sign in',
    'login.email': 'Email',
    'login.password': 'Password',
    'login.submit': 'Sign in',
    'login.invalid': 'Wrong email or password.',
    'login.locked': 'Too many attempts. Try again in a few minutes.',
    'login.error': 'Could not sign in. Please try again.',
    'home.welcome': 'Hi, {name}',
    'home.soon': 'Your visits, goshuin and map will show up here.',
    'home.regions': 'Regions and prefectures',
    'home.admin': 'Admin panel',
    'nav.logout': 'Sign out',
    'nav.language': 'Language',
    'common.loading': 'Loading…',
  },
} satisfies Record<Locale, Record<string, string>>

export type MessageKey = keyof (typeof messages)['es']

interface I18n {
  locale: Locale
  setLocale: (locale: Locale) => void
  t: (key: MessageKey, vars?: Record<string, string>) => string
}

const I18nContext = createContext<I18n | null>(null)

function initialLocale(): Locale {
  const saved = localStorage.getItem('locale')
  if (saved === 'es' || saved === 'en') return saved
  return navigator.language.startsWith('es') ? 'es' : 'en'
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale)

  const setLocale = useCallback((next: Locale) => {
    localStorage.setItem('locale', next)
    document.documentElement.lang = next
    setLocaleState(next)
  }, [])

  const value = useMemo<I18n>(
    () => ({
      locale,
      setLocale,
      t: (key, vars) =>
        messages[locale][key].replace(/\{(\w+)\}/g, (_, name: string) => vars?.[name] ?? `{${name}}`),
    }),
    [locale, setLocale],
  )

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

// oxlint-disable-next-line react/only-export-components
export function useI18n(): I18n {
  const ctx = useContext(I18nContext)
  if (!ctx) throw new Error('useI18n fuera de I18nProvider')
  return ctx
}
