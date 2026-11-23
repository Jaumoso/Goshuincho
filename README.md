# Goshuinchō

Aplicación selfhosted (PWA) para registrar visitas a santuarios, templos y estaciones de Japón, y los goshuin y sellos conseguidos. La especificación completa está en [`docs/especificacion.md`](docs/especificacion.md).

## Instalación con Docker

```sh
cp .env.example .env   # rellena PUBLIC_URL, SECRET_KEY, DB_PASSWORD, ADMIN_EMAIL y ADMIN_PASSWORD
mkdir -p tiles
docker compose up -d --build
```

La app escucha en `127.0.0.1:8000`; ponla detrás de tu proxy inverso (ejemplos de Caddy y nginx en la especificación, sección 6). El servicio `migrate` aplica las migraciones, carga regiones, prefecturas y zonas, y crea el administrador; después arrancan `app` y `worker`.

- PWA: `/`
- Administración: `/admin/`
- API y documentación OpenAPI: `/api/docs`
- Salud: `/api/health`

> La imagen `postgis/postgis` solo se publica para amd64. En ARM (Apple Silicon, Raspberry Pi) funciona emulada, o puedes indicar otra imagen compatible con `POSTGIS_IMAGE` en el `.env`.

## Lugares

Hasta que llegue el importador de OpenStreetMap (fase 2b), los lugares se cargan desde CSV:

```sh
docker compose exec app python manage.py seed --if-empty           # categorías (peregrinaciones, deidades…)
docker compose exec app python manage.py import_places_csv --sample # 36 lugares de ejemplo
docker compose exec app python manage.py import_places_csv /ruta/lugares.csv
```

Columnas del CSV: `kind,name_ja,name_romaji,name_en,prefecture,lat,lon,categories`. `kind` es `shrine`, `temple`, `station` o `site`; `prefecture` admite código ISO, id o nombre (si va vacía se deduce de las coordenadas); `categories` son slugs separados por `;`, con orden opcional (`saigoku-kannon:16`). Reimportar actualiza los lugares existentes.

Pantallas de la PWA: inicio con estadísticas y últimas visitas, búsqueda de lugares con filtros, ficha del lugar con historial y alta rápida de visita + goshuin con foto, colección de sellos, libretas (goshuinchō) y alta de lugares privados.

## Desarrollo

Estructura:

- `backend/`: Django + django-ninja + GeoDjango, gestionado con [uv](https://docs.astral.sh/uv/).
- `frontend/`: React + Vite + TypeScript (PWA).

GeoDjango necesita GDAL, GEOS y PROJ; si no los tienes instalados, usa los contenedores.

```sh
# Tests del backend (PostGIS incluido)
docker compose -f docker-compose.test.yml run --rm --build tests

# Migraciones nuevas
docker compose -f docker-compose.test.yml run --rm tests python manage.py makemigrations

# Frontend con recarga en caliente, contra el backend en localhost:8000
cd frontend && npm install && npm run dev
```

## Datos y atribuciones

- Contornos de prefecturas: [Natural Earth](https://www.naturalearthdata.com/) (dominio público).
- Lugares (fases siguientes): © colaboradores de [OpenStreetMap](https://www.openstreetmap.org/copyright), licencia ODbL.
