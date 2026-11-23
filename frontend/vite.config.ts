import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

const backend = process.env.BACKEND_URL ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'apple-touch-icon.png'],
      manifest: {
        name: 'Goshuinchō',
        short_name: 'Goshuinchō',
        description: 'Registro de goshuin, sellos y visitas en Japón',
        lang: 'es',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        background_color: '#f5eedf',
        theme_color: '#e03a1e',
        icons: [
          { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//, /^\/admin/, /^\/static\//, /^\/media\//, /^\/tiles\//],
        runtimeCaching: [
          {
            urlPattern: /\/assets\/.*\.woff2?$/,
            handler: 'CacheFirst',
            options: { cacheName: 'fonts', expiration: { maxEntries: 300 } },
          },
          {
            // fotos ya procesadas: inmutables por id
            urlPattern: /\/api\/media\/[^/]+\/(thumb|medium)/,
            handler: 'CacheFirst',
            options: { cacheName: 'media', expiration: { maxEntries: 500, maxAgeSeconds: 60 * 60 * 24 * 60 } },
          },
          {
            // lecturas de la API para consultar sin conexión; siempre se prefiere la red
            urlPattern: ({ url, request }) =>
              request.method === 'GET' &&
              url.pathname.startsWith('/api/') &&
              !/^\/api\/(auth|export|import|media)\b/.test(url.pathname),
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api',
              networkTimeoutSeconds: 4,
              expiration: { maxEntries: 300, maxAgeSeconds: 60 * 60 * 24 * 30 },
              cacheableResponse: { statuses: [200] },
            },
          },
          {
            urlPattern: /\/map\/fonts\//,
            handler: 'CacheFirst',
            options: { cacheName: 'map-glyphs', expiration: { maxEntries: 100 } },
          },
        ],
      },
    }),
  ],
  build: {
    // fonts are split by unicode-range; inlining them would bloat the CSS
    assetsInlineLimit: (file) => (/\.woff2?$/.test(file) ? false : undefined),
  },
  server: {
    proxy: {
      '/api': backend,
      '/admin': backend,
      '/static': backend,
      '/tiles': backend,
    },
  },
})
