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

### Mapa base (opcional, recomendado)

El mapa usa un único archivo [PMTiles](https://docs.protomaps.com/pmtiles/) servido por la propia app: no hay servidor de teselas ni peticiones a terceros. Extrae Japón del build diario de Protomaps (elige una fecha de [builds.json](https://build-metadata.protomaps.dev/builds.json)):

```sh
docker run --rm -v ./tiles:/tiles protomaps/go-pmtiles extract \
  https://build.protomaps.com/20261123.pmtiles /tiles/japan.pmtiles \
  --bbox=122.9,24.0,146.0,45.6 --maxzoom=14
```

| `--maxzoom` | Tamaño aprox. | Detalle |
|---|---|---|
| 12 | 400 MB | ciudades y carreteras |
| 13 | 860 MB | calles principales |
| 14 | 1,7 GB | calles y edificios (recomendado) |
| 15 | 3,7 GB | máximo |

Sin el archivo, el mapa funciona igualmente pero sin fondo (solo los puntos) y avisa de que falta.

> La imagen `postgis/postgis` solo se publica para amd64. En ARM (Apple Silicon, Raspberry Pi) funciona emulada, o puedes indicar otra imagen compatible con `POSTGIS_IMAGE` en el `.env`.

## Lugares

Los templos, santuarios y estaciones se importan de OpenStreetMap por región, desde los extractos de [Geofabrik](https://download.geofabrik.de/asia/japan.html) (de 90 MB para Shikoku a ~1 GB para Kantō), filtrados localmente: solo elementos con nombre de `amenity=place_of_worship` sintoístas o budistas y `railway=station`. Desde la administración, en *Geo › Regiones*, selecciona las regiones y lanza «Importar de OpenStreetMap»; el worker las descarga e importa en segundo plano y el progreso queda en *Lugares › Importaciones de OpenStreetMap*. También por línea de comandos:

```sh
docker compose exec app python manage.py seed --if-empty           # categorías (peregrinaciones, deidades…)
docker compose exec app python manage.py import_osm kansai shikoku  # o «all»; --file para un .osm.pbf ya descargado
```

Reimportar actualiza los lugares por su id de OSM sin tocar los editados a mano (`locally_modified`); los que desaparecen de OSM se marcan como `osm_missing` y nunca se borran. Los lugares que ya existían por CSV o alta manual se enlazan con su elemento de OSM si coinciden tipo y nombre japonés a menos de ~1 km. El romaji que falta en OSM se genera con pykakasi y se marca como generado.

Además, o antes de importar de OSM, los lugares se pueden cargar desde CSV:

```sh
docker compose exec app python manage.py import_places_csv --sample # 36 lugares de ejemplo
docker compose exec app python manage.py import_places_csv /ruta/lugares.csv
```

Columnas del CSV: `kind,name_ja,name_romaji,name_en,prefecture,lat,lon,categories`. `kind` es `shrine`, `temple`, `station` o `site`; `prefecture` admite código ISO, id o nombre (si va vacía se deduce de las coordenadas); `categories` son slugs separados por `;`, con orden opcional (`saigoku-kannon:16`). Reimportar actualiza los lugares existentes.

Pantallas de la PWA: inicio con estadísticas y últimas visitas, búsqueda de lugares con filtros, mapa con agrupación por zonas (visitados en 朱, deseados en 金, el resto al acercarse), ficha del lugar con historial y alta rápida de visita + goshuin con foto, colección de sellos, libretas (goshuinchō), rutas de peregrinaje con progreso (p. ej. 3/33 del Saigoku), estadísticas (rachas por meses, calendario de visitas, mapa de prefecturas, goshuin por año), alta de lugares privados y ajustes (perfil, contraseña, copia personal y borrado de cuenta).

### Revisión de lugares propuestos

Los lugares que crean los usuarios quedan pendientes y solo los ve quien los creó. En *Lugares › Lugares pendientes de revisión* el administrador los aprueba, los rechaza o los fusiona con un duplicado ya aprobado: la lista sugiere candidatos cercanos con nombre parecido y la fusión mueve visitas, goshuin, listas de deseos y categorías al lugar de destino. El lugar fusionado no se borra (queda como `merged`), así que los enlaces antiguos siguen funcionando.

### Propuestas de corrección

En la ficha de un lugar aprobado, **Proponer corrección** abre un formulario con los datos actuales (tipo, nombres, dirección, web, goshuin, coordenadas) y un comentario. Solo se envía lo que cambia. En *Lugares › Propuestas de corrección* el administrador ve una tabla «actual → propuesto» y la aplica o rechaza (desde la ficha o en bloque). Al aplicarla, si cambian las coordenadas se recalcula la prefectura, y el lugar queda marcado como modificado localmente para que una reimportación de OSM no deshaga la corrección.

## Copia personal y migración entre instancias

En *Ajustes › Copia de tus datos* cada usuario descarga un ZIP con `data.json` (visitas, goshuin y sellos, libretas, lista de deseos y notas, lugares propios) y las fotos originales, y puede importarlo en esta u otra instancia (`POST /api/export`, `POST /api/import`). Al importar, cada lugar se busca por id, después por su id de OSM y por último por nombre a menos de 300 m; si no aparece se crea como lugar privado pendiente. La importación conserva los ids y es idempotente: repetirla no duplica nada.

## Compartir la colección

En **Ajustes → Compartir colección** se crean enlaces de solo lectura (`/s/<token>`) a toda la colección o a una libreta. Quien tenga el enlace ve fotos, lugares, fechas y títulos de los goshuin, pero nunca notas, donativos ni el email; las páginas llevan `noindex`. Cada enlace muestra cuántas veces se ha abierto y se puede revocar en cualquier momento.

## Uso sin conexión

La app guarda las consultas recientes (lugares, visitas, colección y miniaturas) para poder verlas sin cobertura. Las visitas y goshuin que se registran sin conexión, con su foto, quedan en una cola del dispositivo y se envían solos al recuperar la conexión. El número pendiente aparece junto a **Ajustes**, donde se puede forzar el envío, reintentar o descartar lo que el servidor haya rechazado. Al cerrar sesión se borra la caché local.

## Copias de seguridad

La copia personal no sustituye a la del servidor. Haz una copia de la base de datos y del volumen de medios, por ejemplo con [restic](https://restic.net/) desde el host:

```sh
export RESTIC_REPOSITORY=sftp:copias@nas:/goshuincho RESTIC_PASSWORD_FILE=~/.restic-pass
docker compose exec -T db pg_dump -U goshuin -Fc goshuin > goshuin.dump
restic backup goshuin.dump "$(docker volume inspect -f '{{ .Mountpoint }}' goshuincho_media)"
restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 12 --prune
```

Para restaurar: `restic restore latest --target /tmp/r`, copia los medios al volumen y carga la base con `docker compose exec -T db pg_restore -U goshuin -d goshuin --clean --if-exists < goshuin.dump`. Prueba la restauración al menos una vez. Las teselas (`tiles/`) y los lugares de OSM se pueden regenerar, pero entran en el volcado igualmente.

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
- Lugares y mapa base: © colaboradores de [OpenStreetMap](https://www.openstreetmap.org/copyright), licencia ODbL; teselas de [Protomaps](https://protomaps.com).
- Tipografía del mapa: Noto Sans (SIL Open Font License, `frontend/public/map/fonts/OFL.txt`).
