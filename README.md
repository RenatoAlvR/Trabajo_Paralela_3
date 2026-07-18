# Trabajo #3 - Computación Paralela y Distribuida
## API Rest para Cruz Morada
### Integrantes: 
- Renato Álvarez Ramos
- Cristopher Retamales Pedreros

# Resumen del proyecto
- Servicio Rest que procesa el archivo CSV ventas_completas.csv y permite realizar consultas sobre esta aplicando distintos filtros, además de calcular y mostrar las estadísticas globales de este.

# Tecnologías
- FastAPI: Para la creación de la API y endpoints, además de la documentación Swagger
- Uvicorn: Servidor de la aplicación
- Polars: Lectura y procesamiento paralelo de los datos, permite manejar las (aprox) 3,24 millones de filas que contiene el csv.
- Docker: Para el despliegue y ejecución del servicio, asegurando reproducibilidad, en este caso se utiliza un entorno de Ubuntu 24.04 LTS.
- Todas las dependencias son Open-Source, descargables mediante pip (Python Package Index) y listadas en requirements.txt

# Ejecución

```bash
docker compose up --build
```
- De esta manera se construye la imagen Docker y se inicia el servicio, dejando expuesto el puerto 8000.
- La API por ende queda accesible mediante http://localhost:8000
- El servicio carga los datos de manera desatendida al iniciar, sólo requiere que el archivo ventas_completas.csv se encuentre en la carpeta data.
- Mientras esté funcionando permite realizar consultas sobre los datos. Ya sean métricas globales (pre-computadas para respuesta en O(1)) o filtradas según el parámetro elegido.
- Los cálculos se realizan en base a la columna MONTO APLICADO.
- Para ejecutar en local (sin Docker) puedes ejecutar el siguiente comando en la terminal (asegurarse de tener las dependencias instaladas): 
```bash 
pip install -r requirements.txt
./run.sh
```
- El servicio se detiene manualmente con CTRL + C en la terminal donde se ejecuta

# Documentación API
- La documentación Swagger se encuentra disponible en http://localhost:8000/docs

# Endpoints
- `GET /v1/estadisticas/ventas`: Consultas mediante parámetros
- `POST /v1/estadisticas/ventas`: Filtra en un cuerpo JSON
- `GET /`: Redirige a /docs

# Otras mecánicas
- Destacar que los resultados se redondean a 2 decimales por comodidad
- El programa se asegura de que los datos sean correctos, si el csv no contiene la columna MONTO APLICADO, no se generarán estadísticas y el programa termina con un error
- Los datos aceptados son datos parseables mediante polars, en caso contrario, se lanzará un error
- En caso de que el monto sea negativo (<0) se considerará corrupto
- También se limita el tamaño del cuerpo de la consulta a máximo 1 mb, esto para evitar ataques DoS sin autenticación (enviar un cuerpo demasiado grande que agote los recursos)

# Configuración
- Mediante el archivo config.py se pueden configurar distintos parámetros, como:
- Ruta del CSV
- Columna sobre la cual se cálculan las estadísticas
- Uso de desviación estándar poblacional o muestral
- Número de consultas máximas
- Tamaño del cuerpo de consulta máximo
- Ruta base de la API
- Entre otras

# Loader
- Polars utiliza evaluación perezosa con el motor streaming, leyendo por chunks, de manera paralela y utilizando todos los núcleos disponibles.
- Separa los campos usando ;,|, tab o coma como separador
- Se normalizan las cabeceras
- Esto es automático, sin intervención del usuario
- Se considera MONTO APLICADO como corrupto si el valor es negativo o no es parseable, SÓLO en ese caso se excluyen de las métricas (no ocurre en este csv, pero en caso de que se pruebe con otros datos, está ahí)
- En caso de que otras columnas estén corruptas, no se excluyen de las métricas globales, sólo quedan excluidas de las filtradas (ya que no cumplen los parámetros), por ejemplo la edad tiene aprox. 2800 filas con edades fuera de rango, estas se consideran en las métricas globales, pero se excluiran de las filtradas, a menos que las busques especificamente
- Luego de generar las edades y la genero_label (genero en terminos númericos), se retienen sólo 8 columnas (fecha, canal, sku, monto_aplicado, local, codigo_cliente, genero_label, edad) y se descarta el resto, ahorrando un 40% (aprox) de memoria y evitando guardar información personal.
- Si falta alguna columna esencial, se aborta el arranque. Si el archivo está vacío pero válido (sólo los headers) se envía un error correspondiente.
- Si el CSV_PATH no está definido o no existe, se carga el csv más grande de la carpeta /data

# Cálculo de métricas
- Se realiza aplicando los filtros seleccionados combinandolos con AND
- Excluye las filas que tengan valor NULL en la columna MONTO APLICADO (ninguna en este caso)
- Calcula las metrica globales apenas carga el archivo, dejando los resultados precomputados

# Filtros
- Genero (GENERO): No especificado, Masculino, Femenino u Otro
- Edad (EDAD): de tipo integer
- Canal (CANAL): Puede ser POS, WEB, APP, CCT, APR o WPR
- Codigo de Producto (CODIGO_PRODUCTO): Integer
- ID (ID_PERSONA): UUID del cliente
- Local (LOCAL): Integer
- Fecha desde y hasta (FECHA_DESDE y FECHA_HASTA): ISO 8601
- Sin filtros: métricas globales
- Los valores de los filtros si son case sensitive

# Manejo de errores
- Todos los errores devuelven un problem detail (RFC 9457) con 9 campos y media type application/problem+json
- Campos: detail, instance, status, title, type, timestamp, errorCode, errorLabel y method
- Errores que maneja junto a su errorCode:
    - 400: VF
    - 404: RNE
    - 405: MNP
    - 413: CDG
    - 500: IE
    - 406: NA
    - 415: TNS
    - 503: SND

- Notar que en la practica los errores 406, 415 y 503 estan programados, pero nunca los utiliza al API, el comportamiento actual del programa enruta esos casos a errores 400

# Testeo
- Se creó un oráculo de python puro encargado de computar las mismas métricas con los mismos criterios del programa principal, para validar que el cálculo sea correcto.
- Esto se reparte en los archivos conftest.py, test_api.py y test_loader.py
- Calcula en base a los 7 parametros y politicas del programa principal, simula GET/POST y la carga del archivo inicial.

# Ejemplos
- Query: curl "http://localhost:8000/v1/estadisticas/ventas?CANAL=POS&EDAD=31"
- Respuesta: {"suma":453653010.0,"conteo":52620,"promedio":8621.3,"minimo":20.0,"maximo":226475.0,"mediana":7016.0,"desviacion_estandar":12525.06}
- Query: curl -X POST http://localhost:8000/v1/estadisticas/ventas \
  -H "Content-Type: application/json" \
  -d '{"consultas":[{"consulta":"GENERO","valor":"Femenino"},{"consulta":"CANAL","valor":"POS"}]}'
- Respuesta: {"suma":20649356290.0,"conteo":2086258,"promedio":9897.8,"minimo":15.0,"maximo":226475.0,"mediana":7476.0,"desviacion_estandar":14565.87}
