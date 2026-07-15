# Carpeta de Datos (data/)

Esta carpeta contiene los archivos de datos utilizados por el servicio REST de Cruz Morada. 

Debido a que los archivos CSV originales superan el límite de tamaño permitido por GitHub, estos se encuentran excluidos del control de versiones (definido en `.gitignore`).

## Instrucciones de Carga de Datos

Para que el servidor funcione de forma correcta, debes descargar el archivo de datos real y ubicarlo en este directorio.

1. **Descarga el archivo real** desde el siguiente enlace de Google Drive:
   * [Archivo CSV de Ventas - Google Drive](https://drive.google.com/file/d/15jLBlJ9eMQSoHsoCMnFWBGopr98FIHlK/view?usp=sharing)
2. **Guarda el archivo** en este directorio `data/` con uno de los siguientes nombres:
   * `ventas_completas.csv` (descomprimido, recomendado para activar el motor de streaming)
   * `ventas.csv`
   * `ventas_completas.csv.gz` (comprimido en gzip)

El cargador de datos (`app/loader.py`) autodetectará de forma automática el archivo de mayor tamaño en esta carpeta para iniciar el servicio en el arranque.
