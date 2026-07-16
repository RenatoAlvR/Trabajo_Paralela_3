# Cruz Morada — Servicio ReST de Resumen Estadístico de Ventas

Servicio REST que procesa el archivo CSV consolidado de ventas de Cruz Morada
(cadena de farmacias) y expone un resumen estadístico integral —suma, conteo,
promedio, mínimo, máximo, mediana y desviación estándar— sobre el
`MONTO APLICADO`, con filtros dinámicos por género, edad, canal, producto,
cliente, local y rango de fechas.

## Tecnologías

| Componente | Tecnología | Rol |
|---|---|---|
| Framework web | [FastAPI](https://fastapi.tiangolo.com/) | Endpoints REST, validación y documentación Swagger automática |
| Servidor ASGI | [Uvicorn](https://www.uvicorn.org/) | Servidor de aplicación |
| Procesamiento de datos | [Polars](https://pola.rs/) | Lectura y agregación paralela del CSV |
| Pruebas | pytest + httpx (`TestClient`) | Suite de pruebas automatizadas |

Todas las herramientas son open source e instalables de forma nativa en
GNU/Linux mediante `pip`.

## Decisiones de diseño

- **Carga desatendida**: el CSV se procesa automáticamente al iniciar la
  aplicación (evento *lifespan* de FastAPI). No se requiere intervención
  manual; los datos quedan disponibles para GET y POST desde el arranque.
  También existe una alternativa por CLI: `python scripts/load_data.py`.
- **Procesamiento paralelo y streaming**: Polars ejecuta la lectura del CSV y
  las agregaciones en paralelo sobre todos los núcleos disponibles. La carga
  usa *lazy evaluation* (`scan_csv` + plan de ejecución diferido) con el motor
  **streaming**, que procesa el archivo por *chunks* sin materializar todo el
  volumen de una sola vez, manteniendo bajo el consumo de memoria durante la
  ingesta.
- **Almacenamiento en memoria**: tras el tipado (fechas, cálculo de edad,
  etiquetado de género), el DataFrame queda residente en memoria para
  responder consultas en milisegundos. Cada
  consulta se ejecuta como un plan lazy de Polars (filtros + 7 agregaciones en
  una sola pasada paralela).
- **Autodetección de formato**: se detectan automáticamente el separador
  (`,`, `;`, tab, `|`) y la compresión gzip. Las cabeceras se normalizan
  (BOM, espacios, mayúsculas y tildes), por lo que se aceptan `GENERO` y
  `GÉNERO` indistintamente.
- **Tolerancia a datos corruptos**: el CSV se lee sin inferencia de tipos
  (todo como texto) y cada columna se convierte con *casts* tolerantes: una
  celda ilegible se vuelve `null` en lugar de abortar la carga completa. **No se
  descarta ninguna fila**: las métricas globales se calculan sobre TODAS las
  filas del archivo; la edad solo se usa cuando se aplica el filtro `EDAD`. Las
  líneas con campos de más se truncan. Los UUID de cliente se normalizan a
  minúsculas (son case-insensitive), y los filtros validan rangos numéricos
  antes de tocar los datos.
- **Métricas precomputadas**: el resumen global (sin filtros) se calcula una
  sola vez al arranque; un `GET` sin filtros lo devuelve al instante, mientras
  que `GET` con filtros y `POST` calculan dinámicamente.
- **Errores estandarizados**: todas las respuestas de error (400, 404, 405,
  406, 413, 415, 500, 503) siguen el formato exacto del enunciado (estilo
  RFC 7807 extendido con `errorCode`, `errorLabel`, `timestamp` y `method`).

## Docker (reproducibilidad)

La imagen se construye sobre **Ubuntu 24.04 LTS** (Python 3.12). El CSV **no** se
copia a la imagen: se monta como volumen desde `./data`.

```bash
# Coloca el CSV en ./data/ventas_completas.csv y luego:
docker compose up --build
```

El servicio queda en `http://localhost:8000` (Swagger en `/docs`). La carga del
CSV ocurre de forma desatendida al iniciar el contenedor. Alternativa sin
compose:

```bash
docker build -t cruzmorada-rest .
docker run --rm -p 8000:8000 -v "$(pwd)/data:/app/data:ro" cruzmorada-rest
```

## Estructura del proyecto

```
app/
  main.py       # Endpoints GET/POST y manejadores de error
  loader.py     # Carga desatendida y paralela del CSV (Polars)
  filters.py    # Validación de filtros -> predicados de Polars
  stats.py      # Cálculo de las 7 métricas
  errors.py     # Formato estándar de errores (400 VF / 500 IE)
  schemas.py    # Modelos Pydantic (documentados en Swagger)
  config.py     # Configuración por variables de entorno
scripts/
  load_data.py        # Carga por CLI (alternativa al arranque)
tests/
  conftest.py   # Oráculo independiente sobre el CSV real + TestClient
  test_api.py   # Suite de pruebas de la API (contra datos reales)
  test_loader.py # Defensas del cargador frente a CSVs corruptos
datos.json      # Datos de prueba: payloads y respuestas de ejemplo
run.sh          # Arranque desatendido del servidor
```

## Requisitos

- GNU/Linux (probado también en Windows/macOS).
- Python ≥ 3.10 con `venv` y `pip`.

## Instalación (GNU/Linux)

```bash
# 1. Clonar / entrar al proyecto
cd Trabajo_Paralela_3

# 2. Crear y activar el entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt
```

## Datos de entrada

El servicio trabaja exclusivamente con el CSV real del enunciado (carpeta
Drive del curso). Descárguelo y déjelo dentro de `data/`:

```bash
# https://drive.google.com/file/d/15jLBlJ9eMQSoHsoCMnFWBGopr98FIHlK/view?usp=sharing
mv ~/Descargas/ventas_completas.csv.gz data/
```

Se acepta el archivo comprimido (`.gz`) directamente, pero para archivos de
este volumen (~3,2 millones de filas) se recomienda descomprimirlo: así la
carga usa el motor streaming de Polars, con un consumo de memoria muy
inferior:

```bash
python -c "import gzip, shutil; shutil.copyfileobj(gzip.open('data/ventas_completas.csv.gz','rb'), open('data/ventas_completas.csv','wb'))"
```

La ruta es configurable con la variable de entorno `CSV_PATH`; si la ruta
configurada no existe, el servicio busca automáticamente el CSV de mayor
tamaño dentro de `data/`. El separador, la compresión y las cabeceras (con o
sin tilde) se autodetectan.

## Ejecución

Arranque desatendido (carga el CSV automáticamente al iniciar):

```bash
./run.sh
# o con una ruta específica:
CSV_PATH=data/ventas.csv ./run.sh
```

El servidor queda disponible en `http://localhost:8000`:

- **Swagger UI**: <http://localhost:8000/docs>
- **OpenAPI**: <http://localhost:8000/openapi.json>

Configuración opcional por variables de entorno: `CSV_PATH`, `METRIC_COLUMN`
(por defecto `monto_aplicado`), `USE_STREAMING` (`1`/`0`), `STD_DDOF`
(`0` = poblacional), `ROUND_DECIMALS` (por defecto `2`).

## Uso de la API

Ruta base: `GET|POST /v1/estadisticas/ventas`

### Filtros soportados

| Filtro | Valores |
|---|---|
| `GENERO` | `No especificado`, `Masculino`, `Femenino`, `Otro` |
| `EDAD` | Entero (edad exacta del cliente) |
| `CANAL` | `POS`, `WEB`, `APP`, `CCT`, `APR`, `WPR` |
| `CODIGO_PRODUCTO` | Entero (SKU) |
| `ID_PERSONA` | UUID del cliente |
| `LOCAL` | Entero (número de local) |
| `FECHA_DESDE` / `FECHA_HASTA` | Fecha ISO-8601 (inclusive) |

Las consultas pueden hacerse sin filtros o con cualquier combinación de ellos.

### GET — filtros por query params

```bash
# Estadísticas generales (sin filtros)
curl -s http://localhost:8000/v1/estadisticas/ventas

# Ventas POS de clientes de 31 años
curl -s "http://localhost:8000/v1/estadisticas/ventas?CANAL=POS&EDAD=31"

# Rango de fechas
curl -s "http://localhost:8000/v1/estadisticas/ventas?FECHA_DESDE=2026-01-01T00:00:00&FECHA_HASTA=2026-06-30T23:59:59"
```

### POST — filtros en el body JSON

```bash
curl -s -X POST http://localhost:8000/v1/estadisticas/ventas \
  -H "Content-Type: application/json" \
  -d '{
    "consultas": [
      {"consulta": "GENERO", "valor": "Femenino"},
      {"consulta": "EDAD", "valor": "31"},
      {"consulta": "CANAL", "valor": "POS"}
    ]
  }'
```

### Respuesta exitosa (200)

```json
{
  "suma": 1500.5,
  "conteo": 42,
  "promedio": 35.73,
  "minimo": 10.0,
  "maximo": 100.0,
  "mediana": 30.0,
  "desviacion_estandar": 25.4
}
```

Si ningún registro coincide con los filtros, se responde `conteo = 0`,
`suma = 0.0` y el resto de las métricas en `null`.

### Respuesta de error (400 / 500)

```bash
# Provocar una validación fallida (LOCAL no numérico)
curl -s -X POST http://localhost:8000/v1/estadisticas/ventas \
  -H "Content-Type: application/json" \
  -d '{"consultas": [{"consulta": "LOCAL", "valor": "qwerqwer"}]}'
```

```json
{
  "detail": "El valor 'qwerqwer' no es un número entero válido para LOCAL",
  "instance": "/v1/estadisticas/ventas",
  "status": 400,
  "title": "Bad Request",
  "type": "https://developer.mozilla.org/es/docs/Web/HTTP/Reference/Status/400",
  "timestamp": "2026-06-30T20:44:49.201437Z",
  "errorCode": "VF",
  "errorLabel": "Validación Fallida",
  "method": "POST"
}
```

Los errores internos usan el mismo formato con `status: 500`,
`errorCode: "IE"` y `errorLabel: "Error Interno"`. En `datos.json` hay más
ejemplos de payloads y respuestas.

## Verificación con el dataset real

El servicio fue verificado contra el CSV real de producción (3.242.878
registros, ~1,5 GB descomprimido):

- Carga desatendida al arranque: **3.240.068 filas válidas** procesadas; las
  2.810 filas con fecha de nacimiento corrupta (0,09 %) se descartaron y
  contabilizaron automáticamente, sin abortar la carga.
- La cabecera real `GÉNERO` (con tilde) se normalizó correctamente.
- Consultas GET/POST sobre los 3,2 millones de filas —incluida la mediana,
  la agregación más costosa— responden en menos de 1 segundo gracias al
  cómputo paralelo de Polars.

**Resultado obtenido sobre el universo total de ventas reales (GET `/v1/estadisticas/ventas`):**
```json
{
  "suma": 32985462184.0,
  "conteo": 3240068,
  "promedio": 10180.48,
  "minimo": 15.0,
  "maximo": 226476.0,
  "mediana": 7662.0,
  "desviacion_estandar": 14451.28
}
```


## Pruebas automatizadas

La suite se ejecuta **contra el CSV real de producción** (requiere el archivo
en `data/`; si falta, las pruebas de API se omiten con un mensaje indicando
cómo obtenerlo). Para validar los resultados, un *oráculo* independiente
implementado con la librería estándar de Python (csv + math, sin Polars)
recorre el mismo archivo, replica las reglas de limpieza y calcula las 7
métricas por su cuenta: dos implementaciones independientes deben coincidir
sobre los ~3,2 millones de registros.

Cubre: éxito GET/POST, los 8 filtros y combinaciones (con valores tomados del
propio CSV real), validaciones 400 con la estructura exacta de error, casos
límite (0 coincidencias) y las defensas del cargador frente a CSVs corruptos.

```bash
source .venv/bin/activate
pytest -v   # ~1-2 min: incluye la pasada del oráculo sobre el archivo completo
```
