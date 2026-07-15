# Explicación completa — Trabajo 3 (tu repo) y el ejemplo del profesor

Guía desde cero: qué hace cada archivo, sus funciones y el flujo completo.

---

# PARTE 1 — Tu repositorio (`Trabajo_Paralela_3`)

## La idea en una frase
Es un **servicio web (API REST)** hecho en **Python con FastAPI**. Al arrancar, lee el CSV
gigante de ventas (3,2M filas) con **Polars** (motor paralelo), lo deja limpio y en memoria, y
queda escuchando peticiones HTTP. Cuando alguien pide `GET` o `POST` a
`/v1/estadisticas/ventas`, responde con 7 estadísticas (suma, conteo, promedio, mínimo, máximo,
mediana, desviación estándar) del `MONTO APLICADO`, aplicando los filtros que le pidan.

## El ciclo de vida (workflow)
1. Ejecutas `./run.sh` → arranca Uvicorn (el servidor) con la app FastAPI.
2. **Al iniciar** (evento *lifespan*), la app llama a `store.load(CSV)`: lee, limpia y guarda el
   DataFrame en memoria **una sola vez**. Esto es la "carga desatendida" que pide el enunciado.
3. La app queda viva. Cada petición:
   `main.py` recibe → arma la lista de filtros → `filters.py` los valida y traduce a predicados
   Polars → `stats.py` filtra el DataFrame y calcula las 7 métricas → responde JSON.
   Si algo falla, `errors.py` produce el JSON de error con el formato exacto del enunciado.

## Archivos raíz

### `run.sh`
Script de arranque. Fija `CSV_PATH` (por defecto `data/ventas_completas.csv`) y lanza el
servidor: `uvicorn app.main:app --host 0.0.0.0 --port 8000`. Es tu "operación CLI de arranque".

### `requirements.txt`
Dependencias: `fastapi`, `uvicorn` (servidor), `polars` (procesamiento paralelo), y para pruebas
`httpx` + `pytest`. Todas open source, instalables en Linux con `pip`.

### `datos.json`
Entregable obligatorio: archivo de datos de prueba. Documenta en JSON los filtros soportados y
da ejemplos de solicitudes GET/POST, respuestas exitosas y respuestas de error. No es código; es
documentación de ejemplo para quien consuma la API.

### `README.md`
Documentación del proyecto: tecnologías, decisiones de diseño (carga desatendida, streaming,
almacenamiento en memoria, autodetección de formato), instrucciones de instalación y ejecución,
y ejemplos de uso.

### `.gitignore`
Lista de lo que Git NO debe subir: la carpeta `data/` (CSV pesado), cachés de Python, entornos
virtuales, archivos de sistema, y ahora también `utem-weather-app/` (el ejemplo del profesor).

## El paquete `app/` (el corazón del servicio)

### `app/config.py` — Configuración central
Define constantes leídas de variables de entorno (para poder cambiarlas sin tocar código):
- `CSV_PATH`: ruta del CSV a cargar.
- `METRIC_COLUMN = "monto_aplicado"`: **la columna sobre la que se calculan las estadísticas.**
- `USE_STREAMING`: activa el motor por chunks de Polars.
- `STD_DDOF = 0`: desviación estándar **poblacional** (dividir por N). Con `1` sería muestral.
- `MIN_AGE`/`MAX_AGE` (0–120): rango de edad válido; fuera de eso la fila se descarta.
- `ROUND_DECIMALS = 2`: decimales en la respuesta.
- `API_BASE = "/v1/estadisticas/ventas"`: la ruta base.

### `app/loader.py` — Carga y limpieza (el archivo más complejo)
Contiene la clase **`DataStore`** y la instancia global **`store`** que guarda el DataFrame.
Qué hace `store.load(path)`, paso a paso:
1. **`_resolve_path`**: si la ruta exacta no existe, busca el CSV más grande dentro de `data/`.
2. **`_is_gzip` / `_detect_separator`**: autodetecta compresión gzip y el separador (`;`, `,`,
   tab, `|`) leyendo la primera línea.
3. **Lectura sin inferencia de tipos**: lee todo como texto (`scan_csv` perezoso para .csv, o
   `read_csv` para .gz). Leer como texto evita que una celda corrupta aborte la carga completa.
4. **`_rename_map` + `_canon`**: normaliza las cabeceras (quita BOM, tildes, espacios, mayúsculas)
   y las renombra a nombres canónicos (`"MONTO APLICADO"` → `monto_aplicado`, `"GÉNERO"` →
   `genero`, etc.). Así acepta cabeceras "sucias".
5. **Verifica columnas requeridas**: si falta alguna esencial, aborta con mensaje claro.
6. **Casts tolerantes** (`strict=False`): convierte fechas, enteros y floats; lo que no se puede
   convertir queda `null` en vez de romper.
7. **`GENERO_LABEL`**: traduce el entero de género a texto (1→Masculino, 2→Femenino, 3→Otro,
   resto→"No especificado"), para poder filtrar por el texto que pide el enunciado.
8. **`_edad_expr`**: calcula la **edad exacta a la fecha de hoy** desde `fecha_nacimiento`.
9. **Descarte de filas corruptas**: elimina filas sin fecha, sin monto, sin nacimiento, o con
   edad fuera de [0,120]. Cuenta cuántas descartó (`rows_dropped`).
10. Guarda el DataFrame limpio en `store.df` y marca `store.loaded = True`.
> Polars ejecuta lectura y agregaciones en paralelo sobre todos los núcleos; el motor streaming
> procesa por chunks para no cargar todo el volumen de golpe.

### `app/schemas.py` — Modelos de datos (Pydantic)
Define la forma de las peticiones y respuestas (y las documenta en Swagger):
- `Consulta`: un filtro `{consulta, valor}`.
- `PostBody`: el body del POST `{consultas: [...]}`.
- `Resumen`: la respuesta con las 7 métricas.

### `app/filters.py` — Validación y traducción de filtros
Define los conjuntos permitidos (`ALLOWED_GENERO`, `ALLOWED_CANAL`, `ALLOWED_FILTERS`) y la
función clave **`build_predicate(consulta, valor)`**: recibe un filtro y devuelve un *predicado
de Polars* (ej. `pl.col("canal") == "POS"`), o lanza un error si el nombre o el valor es inválido.
Maneja cada filtro: GENERO/CANAL (valida contra lista), EDAD/LOCAL/CODIGO_PRODUCTO (enteros),
ID_PERSONA (UUID), FECHA_DESDE/HASTA (fechas ISO). Excepciones `FilterError` y `UnknownFilter`
se traducen luego a error 400.

### `app/stats.py` — Cálculo estadístico
Función **`compute_stats(df, metric_col, predicates)`**: aplica los filtros (combinados con AND),
y en **una sola pasada lazy y paralela** calcula suma, conteo, promedio, mín, máx, mediana y
desviación estándar. Si el filtro no deja filas (`conteo = 0`), devuelve suma 0.0 y el resto
`null`. Redondea a 2 decimales.

### `app/errors.py` — Formato de error estándar
Define la excepción `ApiError` y **`error_body(...)`**, que construye el JSON de error EXACTO del
enunciado: `detail, instance, status, title, type, timestamp, errorCode, errorLabel, method`.
Dos atajos: `validation_error(...)` → 400 con código **VF** ("Validación Fallida");
`internal_error(...)` → 500 con código **IE** ("Error Interno"). El timestamp se formatea con 9
dígitos fraccionarios + `Z`, como el ejemplo del enunciado.

### `app/main.py` — La aplicación y los endpoints
El archivo que une todo:
- **`lifespan`**: al arrancar, carga el CSV (`store.load`).
- **Manejadores de error** (`@app.exception_handler`): capturan `ApiError`, errores de validación
  del body y cualquier excepción no prevista, y devuelven el JSON de error estándar.
- **`GET /`**: redirige a `/docs` (Swagger UI).
- **`GET /v1/estadisticas/ventas`**: recibe filtros por *query params*, los arma y responde.
- **`POST /v1/estadisticas/ventas`**: recibe filtros en el *body*; si `consultas` está vacío o
  nulo → error 400.
- Funciones internas `_make_predicates` (valida cada filtro) y `_run` (verifica que los datos
  estén cargados y llama a `compute_stats`).

### `scripts/load_data.py` — Carga por CLI (alternativa)
Permite cargar y verificar el CSV desde la terminal sin levantar el servidor:
`python scripts/load_data.py [ruta]`. Imprime filas válidas, descartadas y columnas.

## La carpeta `tests/`

### `tests/conftest.py` — Configuración de pruebas y el "oráculo"
Lo más ingenioso del proyecto. Define un **oráculo independiente**: recorre el MISMO CSV real con
Python puro (módulos `csv` + `math`, sin Polars), replica exactamente las reglas de limpieza, y
calcula las 7 métricas por su cuenta (usa `math.fsum` para sumar exacto, y **desviación
poblacional**). Así se validan dos implementaciones independientes entre sí: si Polars (paralelo)
y el oráculo (secuencial) coinciden sobre 3,2M filas, casi seguro ambas están bien. Provee los
*fixtures* `client` (la app cargando el CSV real) y `oracle` (los montos esperados por subconjunto).

### `tests/test_api.py` — Pruebas de la API
Verifica: GET/POST devuelven las 7 métricas correctas (contra el oráculo); todos los filtros y
combinaciones; que los errores 400 tengan la estructura EXACTA del enunciado; y casos límite
(conteo 0 → métricas null). Toma los valores de filtro de la primera fila válida del CSV real.

### `tests/test_loader.py` — Pruebas de las defensas del cargador
Fabrica CSVs corruptos a propósito (en carpeta temporal) para probar que: se descartan solo las
filas malas sin abortar; se autodetectan BOM/tilde/`;`; los UUID se normalizan a minúsculas; y si
faltan columnas requeridas, aborta con mensaje claro.

## La carpeta `data/`
Contiene `ventas_completas.csv` (real, ~665 MB, ignorado por Git), un `sample.csv.gz` y un
`README.md` con instrucciones para descargar el CSV. El CSV nunca se sube al repo.

---

# PARTE 2 — El ejemplo del profesor (`utem-weather-app`)

## Qué es
Es un **proyecto de referencia completo** de otra asignatura (Computación Móvil), sobre clima y
farmacias de turno. NO es de tu trabajo; el profesor lo subió como ejemplo de "cómo se hace bien
un sistema distribuido". Tiene **tres componentes** (arquitectura distribuida):

1. **`mobile/`** — App móvil en **Flutter** (Dart): login con Google, GPS, mapa, consulta el
   servicio REST. Es el "cliente".
2. **`ReST/`** — El **servicio REST en Spring Boot (Java 21)**. Es la parte que te interesa como
   referencia.
3. **`scheduler/`** — Un **servicio programado** (tareas periódicas) que baja datos de clima
   (`MeteoTask`) y de farmacias del MINSAL (`MinsalTask`) y los guarda en la base de datos.
4. **`db/01-model.sql`** — El esquema PostgreSQL (con PostGIS para geolocalización).

## El servicio REST (`ReST/`), por capas
Está organizado en capas limpias — un patrón que vale la pena imitar:

- **`WeatherApplication.java`**: el punto de entrada (`main`) que arranca Spring Boot. Equivale a
  tu `app/main.py` + `run.sh`.
- **`api/v1/` (controladores)**: `PharmaRest.java` y `WeatherRest.java` definen los endpoints
  (`/v1/farmacias/...`, `/v1/clima/...`). Equivalen a tus funciones `@app.get`/`@app.post`. Cada
  método lleva anotaciones `@Operation` y `@ApiResponses` que documentan el endpoint en Swagger.
- **`api/ApiExceptionHandler.java`**: el **manejador global de errores** (`@RestControllerAdvice`).
  Es el archivo más valioso como referencia: convierte muchas excepciones distintas en un cuerpo
  de error estándar (`ProblemDetail`, RFC 9457) con `type`, `title`, `status`, `detail`,
  `instance`, `timestamp`, `errorCode`, `method`. Equivale a tu `app/errors.py` +
  los `exception_handler` de tu `main.py`, **pero cubre muchos más casos**: 401, 403, 404, 405
  (método no permitido), 415 (media type), parámetros faltantes, tipo inválido, JSON malformado,
  validación de campos, y un fallback 500.
- **`exception/` (excepciones de dominio)**: `UtemException` (base), `ValidationException`,
  `NoDataException`, `AuthException`, `ForbiddenException`, `LimitException`, `BadDataException`.
  Cada una mapea a un código HTTP. Es como tener tu `ApiError` pero dividido en tipos con
  significado de negocio.
- **`manager/` (lógica de negocio)**: `PharmaManager`, `MeteoManager` — la lógica entre el
  controlador y los datos. Tú no tienes una capa separada porque tu `stats.py` cumple ese rol.
- **`domain/` (modelo de datos)**: `model/` = entidades JPA (`Pharmacy`, `Station`,
  `Observation`) mapeadas a tablas; `repository/` = interfaces para consultar la BD;
  `data/` = objetos de respuesta (DTOs); `enums/` = enumeraciones.
- **`conf/OpenApiConfig.java`**: configura Swagger/OpenAPI (título, versión, seguridad JWT,
  servidores). En tu caso FastAPI genera todo esto automáticamente en `/docs`.
- **`utils/`**: utilidades (`CoordinatesUtils` para distancias, `GoogleAuthUtils` para validar
  tokens).
- **`application.properties`**: configuración (conexión a PostgreSQL, encoding, context-path).
  Equivale a tu `config.py`.
- **`src/test/`**: pruebas unitarias por capa (managers, utils).

## Qué SÍ tomar del ejemplo (patrones que el profesor valora)
1. **Manejador de errores centralizado y amplio**: tu punto más mejorable. Él cubre 405/415/JSON
   malformado/tipo inválido con códigos propios; tú hoy cubres 400 (VF) y 500 (IE).
2. **Arquitectura por capas** con responsabilidades separadas (ya la tienes en buena medida).
3. **Documentación Swagger rica** con ejemplos por endpoint (tú la tienes automática; podrías
   enriquecer descripciones).
4. **Pruebas por capa** (ya las tienes).

## Qué NO copiar
- **No copies los campos de error de él**: su cuerpo NO tiene `errorLabel` y añade `query`/`errors`
  porque es otro proyecto. **Tu enunciado exige `errorLabel`** → sigue tu enunciado (ya lo haces).
- No necesitas base de datos, JWT, ni las 3 capas de Spring: tu solución en memoria con Polars es
  válida y más simple. Es una referencia de estilo, no una plantilla a clonar.

---

# PARTE 3 — Cambio realizado
Se agregó `utem-weather-app/` al `.gitignore` para que el repo de ejemplo del profesor no se suba
por accidente a tu repositorio.
