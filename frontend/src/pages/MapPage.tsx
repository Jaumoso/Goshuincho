import { layers, namedFlavor, type Flavor } from '@protomaps/basemaps'
import * as maplibregl from 'maplibre-gl'
import type { GeoJSONSource, LngLatBoundsLike, MapLayerMouseEvent, StyleSpecification } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import { Protocol } from 'pmtiles'
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, type PlaceKind, type PlaceNames } from '../api'
import { useCategories } from '../data'
import { localName, placeName, placeSubName } from '../format'
import { useI18n } from '../i18n'

interface MapPoint extends PlaceNames {
  id: string
  kind: PlaceKind
  lon: number
  lat: number
  state: 'visited' | 'wishlist' | 'unvisited'
}

const JAPAN: LngLatBoundsLike = [[122.9, 24.0], [146.0, 45.6]]
const TILES = '/tiles/japan.pmtiles'
/** Desde este zoom se piden también los lugares no visitados de la zona visible. */
const DETAIL_ZOOM = 9

// 和色: papel washi, agua añil y verdes de musgo en lugar de los grises por defecto.
const WASHI: Partial<Flavor> = {
  background: '#efe6d2', earth: '#f5eedf', water: '#a8c3d4', park_a: '#dfe3c3', park_b: '#d6ddb6',
  wood_a: '#dce3c0', wood_b: '#d2dbb2', scrub_a: '#e2e3c6', scrub_b: '#dadcbb', buildings: '#e7dcc6',
  boundaries: '#b39b7d', railway: '#9c8f80', ocean_label: '#4d6b86', city_label: '#3b2f25',
  state_label: '#8a7560', country_label: '#8a7560',
}
const YORU: Partial<Flavor> = {
  background: '#0e1016', earth: '#171a23', water: '#0b1422', park_a: '#1b241d', park_b: '#1d2820',
  wood_a: '#1b241d', wood_b: '#1d2820', buildings: '#232736', boundaries: '#4a4f63',
}

let protocolAdded = false

function mapStyle(dark: boolean, lang: string, hasTiles: boolean): StyleSpecification {
  const base = namedFlavor(dark ? 'dark' : 'light')
  const flavor: Flavor = { ...base, ...(dark ? YORU : WASHI), pois: undefined }
  return {
    version: 8,
    glyphs: `${location.origin}/map/fonts/{fontstack}/{range}.pbf`,
    sources: hasTiles
      ? {
          protomaps: {
            type: 'vector',
            url: `pmtiles://${location.origin}${TILES}`,
            attribution:
              '<a href="https://protomaps.com">Protomaps</a> © <a href="https://openstreetmap.org/copyright">OpenStreetMap</a>',
          },
        }
      : {},
    layers: hasTiles
      ? // Sin sprites: los escudos de carretera no tendrían icono.
        layers('protomaps', flavor, { lang }).filter((l) => l.id !== 'roads_shields')
      : [{ id: 'background', type: 'background', paint: { 'background-color': flavor.background } }],
  }
}

function pointCoords(feature: { geometry: unknown }): [number, number] {
  return (feature.geometry as { coordinates: [number, number] }).coordinates
}

function cssVar(name: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

export default function MapPage() {
  const { t, locale } = useI18n()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const categories = useCategories()
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const loadRef = useRef<() => void>(() => {})
  const [zoom, setZoom] = useState(0)
  const [truncated, setTruncated] = useState(false)
  const [noTiles, setNoTiles] = useState(false)
  const kind = params.get('kind') ?? ''
  const category = params.get('category') ?? ''

  useEffect(() => {
    if (!container.current) return
    if (!protocolAdded) {
      maplibregl.setWorkerUrl(new URL(workerUrl, location.origin).href)
      maplibregl.addProtocol('pmtiles', new Protocol().tile)
      protocolAdded = true
    }
    const dark = matchMedia('(prefers-color-scheme: dark)').matches
    const lat = Number(params.get('lat'))
    const lon = Number(params.get('lon'))
    const focus = params.get('place')
    const map = new maplibregl.Map({
      container: container.current,
      style: mapStyle(dark, locale, false),
      ...(lat && lon ? { center: [lon, lat] as [number, number], zoom: 15 } : { bounds: JAPAN }),
      maxBounds: [[110, 18], [160, 52]],
      attributionControl: false,
      localIdeographFontFamily: "'Hiragino Sans', 'Hiragino Kaku Gothic ProN', 'Noto Sans JP', 'Yu Gothic', sans-serif",
    })
    mapRef.current = map
    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right')
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    map.addControl(
      new maplibregl.GeolocateControl({ positionOptions: { enableHighAccuracy: true }, trackUserLocation: false }),
      'top-right',
    )

    fetch(TILES, { method: 'HEAD' })
      .then((r) => {
        if (r.ok) map.setStyle(mapStyle(dark, locale, true), { diff: false })
        else setNoTiles(true)
      })
      .catch(() => setNoTiles(true))

    const shu = cssVar('--shu')
    const kin = cssVar('--kin')
    const ai = dark ? '#8fa6c9' : cssVar('--ai')
    const ring = dark ? '#12141b' : '#fffaf0'
    const stateColor = ['match', ['get', 'state'], 'visited', shu, 'wishlist', kin, ai] as const

    const addPlaces = () => {
      if (map.getSource('places')) return
      map.addSource('places', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
        cluster: true,
        clusterMaxZoom: 12,
        clusterRadius: 44,
        clusterProperties: {
          visited: ['+', ['case', ['==', ['get', 'state'], 'visited'], 1, 0]],
          wishlist: ['+', ['case', ['==', ['get', 'state'], 'wishlist'], 1, 0]],
        },
      })
      map.addLayer({
        id: 'clusters',
        type: 'circle',
        source: 'places',
        filter: ['has', 'point_count'],
        paint: {
          'circle-color': ['case', ['>', ['get', 'visited'], 0], shu, ['>', ['get', 'wishlist'], 0], kin, ai],
          'circle-radius': ['step', ['get', 'point_count'], 15, 10, 19, 100, 24, 1000, 30],
          'circle-stroke-width': 3,
          'circle-stroke-color': ring,
          'circle-opacity': 0.92,
        },
      })
      map.addLayer({
        id: 'cluster-count',
        type: 'symbol',
        source: 'places',
        filter: ['has', 'point_count'],
        layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-font': ['Noto Sans Medium'], 'text-size': 12 },
        paint: { 'text-color': '#fff' },
      })
      map.addLayer({
        id: 'points',
        type: 'circle',
        source: 'places',
        filter: ['!', ['has', 'point_count']],
        layout: { 'circle-sort-key': ['match', ['get', 'state'], 'visited', 2, 'wishlist', 1, 0] },
        paint: {
          'circle-color': stateColor as never,
          'circle-radius': ['match', ['get', 'state'], 'unvisited', 6, 8.5],
          'circle-stroke-width': 2.5,
          'circle-stroke-color': ring,
        },
      })
      map.addLayer({
        id: 'point-labels',
        type: 'symbol',
        source: 'places',
        minzoom: 13,
        filter: ['!', ['has', 'point_count']],
        layout: {
          'text-field': ['coalesce', ['get', 'name_ja'], ['get', 'name_romaji'], ['get', 'name_en']],
          'text-font': ['Noto Sans Medium'],
          'text-size': 12,
          'text-offset': [0, 1.1],
          'text-anchor': 'top',
          'text-optional': true,
          // Los visitados y deseados ganan la colisión de etiquetas.
          'symbol-sort-key': ['match', ['get', 'state'], 'visited', 0, 'wishlist', 1, 2],
        },
        paint: { 'text-color': dark ? '#f1e8d6' : '#231d18', 'text-halo-color': ring, 'text-halo-width': 1.5 },
      })
      loadRef.current()
    }
    // setStyle borra fuentes y capas propias; se vuelven a añadir al cargar el estilo nuevo.
    map.on('style.load', addPlaces)

    map.on('click', 'clusters', async (e: MapLayerMouseEvent) => {
      const feature = e.features?.[0]
      if (!feature) return
      const source = map.getSource('places') as GeoJSONSource
      const z = await source.getClusterExpansionZoom(feature.properties.cluster_id as number)
      map.easeTo({ center: pointCoords(feature), zoom: z + 0.5 })
    })

    const popup = new maplibregl.Popup({ closeButton: false, offset: 12, maxWidth: '260px' })
    const openPopup = (p: MapPoint) => {
      const el = document.createElement('a')
      el.className = 'map-popup'
      el.href = `/places/${p.id}`
      const sub = placeSubName(p)
      el.innerHTML = `<small></small><strong></strong>${sub ? '<span class="ja"></span>' : ''}<em></em>`
      el.querySelector('small')!.textContent = t(`kind.${p.kind}`)
      el.querySelector('strong')!.textContent = placeName(p, locale)
      if (sub) el.querySelector('.ja')!.textContent = sub
      el.querySelector('em')!.textContent = p.state === 'unvisited' ? t('map.open') : t(`map.state.${p.state}`)
      el.dataset.state = p.state
      el.addEventListener('click', (ev) => {
        ev.preventDefault()
        navigate(`/places/${p.id}`)
      })
      popup.setLngLat([p.lon, p.lat]).setDOMContent(el).addTo(map)
    }
    map.on('click', 'points', (e: MapLayerMouseEvent) => {
      const f = e.features?.[0]
      if (!f) return
      const [lon, lat] = pointCoords(f)
      openPopup({ ...(f.properties as MapPoint), lon, lat })
    })
    for (const layer of ['clusters', 'points']) {
      map.on('mouseenter', layer, () => (map.getCanvas().style.cursor = 'pointer'))
      map.on('mouseleave', layer, () => (map.getCanvas().style.cursor = ''))
    }

    let controller: AbortController | null = null
    let lastKey = ''
    let focused = false
    const load = (force = false) => {
      const z = map.getZoom()
      setZoom(z)
      const search = new URLSearchParams()
      const sp = new URLSearchParams(location.search)
      for (const key of ['kind', 'category']) if (sp.get(key)) search.set(key, sp.get(key)!)
      if (z >= DETAIL_ZOOM) {
        const b = map.getBounds()
        search.set('bbox', [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map((v) => v.toFixed(3)).join(','))
      }
      const key = search.toString()
      if (key === lastKey && !force) return
      lastKey = key
      controller?.abort()
      controller = new AbortController()
      api<{ items: MapPoint[]; truncated: boolean }>(`/places/map?${key}`, { signal: controller.signal })
        .then((data) => {
          setTruncated(data.truncated)
          const source = map.getSource('places') as GeoJSONSource | undefined
          source?.setData({
            type: 'FeatureCollection',
            features: data.items.map(({ lon, lat, ...props }) => ({
              type: 'Feature',
              geometry: { type: 'Point', coordinates: [lon, lat] },
              properties: props,
            })),
          })
          const target = focus && !focused && data.items.find((p) => p.id === focus)
          if (target) {
            focused = true
            openPopup(target)
          }
        })
        .catch(() => {})
    }
    let timer: ReturnType<typeof setTimeout>
    map.on('moveend', () => {
      clearTimeout(timer)
      timer = setTimeout(() => load(), 200)
    })
    loadRef.current = () => load(true)

    return () => {
      controller?.abort()
      clearTimeout(timer)
      map.remove()
      mapRef.current = null
    }
    // El mapa se crea una vez; idioma y filtros se aplican sin recrearlo.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    loadRef.current()
  }, [kind, category])

  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    next.delete('place')
    setParams(next, { replace: true })
  }

  return (
    <div className="map-page">
      <div ref={container} className="map-canvas" />
      <div className="map-overlay">
        <div className="filters">
          <select aria-label={t('places.all_kinds')} value={kind} onChange={(e) => update('kind', e.target.value)}>
            <option value="">{t('places.all_kinds')}</option>
            {(['shrine', 'temple', 'station', 'site'] as const).map((k) => (
              <option key={k} value={k}>{t(`kind.${k}`)}</option>
            ))}
          </select>
          <select aria-label={t('places.all_categories')} value={category} onChange={(e) => update('category', e.target.value)}>
            <option value="">{t('places.all_categories')}</option>
            {categories.map((c) => (
              <option key={c.slug} value={c.slug}>{localName(c, locale)}</option>
            ))}
          </select>
        </div>
        <ul className="map-legend" aria-label={t('map.legend')}>
          <li data-state="visited">{t('map.state.visited')}</li>
          <li data-state="wishlist">{t('map.state.wishlist')}</li>
          {zoom >= DETAIL_ZOOM && <li data-state="unvisited">{t('map.state.unvisited')}</li>}
        </ul>
        {noTiles && <p className="map-note">{t('map.no_tiles')}</p>}
        {!noTiles && zoom > 0 && zoom < DETAIL_ZOOM && <p className="map-note">{t('map.zoom_hint')}</p>}
        {truncated && <p className="map-note">{t('map.truncated')}</p>}
      </div>
    </div>
  )
}
