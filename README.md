# Inline Studio 1.3.26 en SaladCloud — plantilla independiente

Este directorio es el root de un proyecto independiente para construir una imagen efímera de `inlineresearch/inline-studio:1.3.26` en SaladCloud. Está pensado para el flujo de generación/entrenamiento LoRA y no depende de `voice_agent_llm`.

La capa solicita bind IPv6 para Salad y desactiva los servicios opcionales. Añade una calificación de ancho de banda de una sola ejecución después de que el servidor esté listo, límites conservadores para las descargas a demanda y una herramienta manual para medir salud local frente al Container Gateway.

## Construir la imagen

Desde la raíz de este repositorio:

```sh
docker build -t inline-studio-salad:1.3.26 .
```

El build aplica un ajuste acotado a las dos llamadas `snapshot_download` del selector de modelos de Inline Studio y reinstala el paquete desde el árbol que ya trae la imagen, sin actualizar dependencias. No publica la imagen ni despliega un Container Group.

## Publicar en Docker Hub con GitHub Actions

El workflow `.github/workflows/build.yml` construye y publica para `linux/amd64` cuando hay un push a `main` o cuando se ejecuta manualmente con `workflow_dispatch`. Usa el directorio de este repositorio como contexto y `./Dockerfile`; no descarga modelos ni despliega nada en Salad.

En GitHub configura estos dos valores en **Settings → Secrets and variables → Actions → Repository secrets**:

| Secret | Valor |
|---|---|
| `DOCKERHUB_USERNAME` | Tu usuario de Docker Hub. |
| `DOCKERHUB_TOKEN` | Un access token de Docker Hub. No uses la contraseña de tu cuenta. |

El destino es `<DOCKERHUB_USERNAME>/inline-studio-salad`. Cada ejecución publica `1.3.26`, `latest` y `sha-<short_sha>` (por ejemplo, `sha-abcdef0`). GitHub Actions no necesita `HF_TOKEN`, credenciales/API keys de Salad, `SALAD_GATEWAY_URL` ni `MIN_MBPS`; esas opciones pertenecen al runtime o al diagnóstico manual.

## Variables runtime para Salad

Estos son los valores por defecto del Dockerfile. Puedes copiarlos explícitamente al Container Group para dejar registrada la configuración de la primera prueba y sobrescribirlos allí cuando lo necesites:

```ini
INLINE_HOST=::
INLINE_PORT=8848
ENABLE_JUPYTER=0
ENABLE_FILEBROWSER=0
MIN_MBPS=60
HF_XET_HIGH_PERFORMANCE=0
HF_XET_FIXED_DOWNLOAD_CONCURRENCY=2
HF_XET_DATA_MAX_CONCURRENT_FILE_DOWNLOADS=1
INLINE_HF_SNAPSHOT_MAX_WORKERS=2
```

`HF_TOKEN` es opcional y solo hace falta si el modelo Hugging Face solicitado es gated o privado. Configúralo como **Secret de Salad**, nunca en GitHub Actions ni en un archivo versionado. `SALAD_GATEWAY_URL` también es opcional: solo la lee la herramienta manual `salad-download-probes`; Inline Studio no la necesita para arrancar.

`MIN_MBPS` es el ajuste principal del test de ancho de banda de inicio. Los parámetros internos del test (25 MB, tres intentos, pausa de 10 segundos, timeout de conexión de 5 s y máximo de 30 s) se conservan fijos para mantener el comportamiento implementado; no son variables configurables. El test corre solo durante el inicio, una vez que el servidor responde, y no vigila ni reasigna la instancia después.

## Health y descarga de diagnóstico

La aplicación sirve en el puerto **8848** y el endpoint `GET /v1/health` indica que el servidor está listo; no indica que un modelo se haya descargado o cargado. Configura el Container Gateway como HTTP en el puerto de contenedor 8848 y usa `/v1/health` para startup/readiness.

Durante una descarga de modelo, puedes ejecutar manualmente dentro del contenedor:

```sh
SALAD_GATEWAY_URL='https://xxxxx.salad.cloud' salad-download-probes
```

La herramienta consulta en paralelo `http://[::1]:8848/v1/health` por IPv6 local y `https://xxxxx.salad.cloud/v1/health` por el Gateway público. Registra estado HTTP, latencia, errores/timeouts y crecimiento aproximado de archivos `.part`; ese crecimiento no es una medida exacta del throughput de red. Presiona Ctrl+C para detenerla. Esta comparación y la prueba de descarga real siguen **NEEDS SALAD**.

## Configuración de Salad

- Container Gateway: puerto de contenedor **8848**, protocolo **HTTP**. No configurar 8080 ni 8888.
- Startup probe y readiness probe: HTTP GET en `:8848/v1/health`. El endpoint indica que el servidor responde; **no** confirma que un modelo se haya descargado o cargado.
- No configures una liveness probe agresiva durante la primera validación.
- Salad termina HTTPS en el Gateway. Valida la página, assets, API y WebSockets desde la URL HTTPS pública.

La imagen conserva el `HEALTHCHECK` upstream sobre `127.0.0.1` (intervalo 30 s, timeout 5 s, inicio 180 s y 3 reintentos). No se ha comprobado si funciona con el bind IPv6. Compáralo dentro del contenedor con:

```sh
curl -g -6 -fsS 'http://[::1]:8848/v1/health'
```

El listener `:::8848`, el healthcheck IPv6 y el acceso por Gateway siguen **NEEDS SALAD**. Conserva el healthcheck upstream salvo que una prueba real demuestre que hay que cambiarlo.

## Variables y servicios

| Variable | Valor inicial | Motivo |
|---|---:|---|
| `INLINE_HOST` | `::` | Solicitar el bind IPv6 que requiere Container Gateway. |
| `INLINE_PORT` | `8848` | Puerto de la aplicación. |
| `ENABLE_JUPYTER` | `0` | No iniciar Jupyter en 8888. |
| `ENABLE_FILEBROWSER` | `0` | No iniciar File Browser en 8080. |
| `MIN_MBPS` | `60` | Umbral configurable de calificación al inicio. |
| `HF_XET_HIGH_PERFORMANCE` | `0` | Mantener desactivado el modo que aumenta concurrencia y uso de red/CPU. |
| `HF_XET_FIXED_DOWNLOAD_CONCURRENCY` | `2` | Dos flujos Xet por archivo como valor inicial. |
| `HF_XET_DATA_MAX_CONCURRENT_FILE_DOWNLOADS` | `1` | Un archivo Xet simultáneo como valor inicial. |
| `INLINE_HF_SNAPSHOT_MAX_WORKERS` | `2` | Limitar a dos archivos simultáneos los `snapshot_download` del selector de modelos. |

Los cuatro primeros cambios son los overrides de Salad. `MIN_MBPS` y los límites de descarga se pueden cambiar como variables del Container Group para una prueba controlada.

## Orden de inicio y calificación de red

`salad-entrypoint.sh` conserva los diagnósticos GPU/Torch y lanza el helper de red en segundo plano antes de delegar a `/opt/entrypoint.sh`. `tini` sigue como PID 1. El helper espera hasta tres minutos a que responda `http://[::1]:8848/v1/health`; esa espera no retrasa el arranque del servidor ni modifica la respuesta del health endpoint.

Cuando el servidor ya responde, el helper ejecuta **una sola calificación** contra el endpoint de prueba de descarga de Cloudflare: hasta 3 intentos, 25 MB por intento, timeout total de 30 s, timeout de conexión de 5 s y pausa de 10 s entre fallos. Registra intento, Mbps, duración, estado HTTP y resultado. Un intento que alcance `MIN_MBPS` termina el helper permanentemente. No descarga modelos.

Solo si los tres intentos fallan, el helper envía una petición `POST` a Salad IMDS en `http://169.254.169.254/v1/reallocate`, con `Metadata: true` y una razón breve. Registra el estado HTTP, descarta el cuerpo de respuesta y no vuelve a medir ni a solicitar reallocation durante esa sesión. Si el servidor nunca llega a estar listo, no hace una petición IMDS: ese caso no demuestra que el ancho de banda sea bajo.

Espera el mensaje de calificación en los logs antes de iniciar una descarga de modelo en la primera sesión. El resultado Cloudflare solo mide ese destino; no demuestra conectividad o rendimiento hacia Hugging Face ni hacia Container Gateway. Salad advierte que una reallocation excluye temporalmente el nodo rechazado durante 48 horas, así que el umbral debe reflejar una necesidad real del workload ([guía de comprobación de ancho de banda](https://docs.salad.com/container-engine/tutorials/performance/network-bandwidth-checks), [referencia de reallocation IMDS](https://docs.salad.com/reference/imds/reallocate)).

## Descargas a demanda y límites Hugging Face/Xet

La auditoría estática del digest `sha256:9424463b243bd15802d0f67ae22efb760f4292b001d5b2fd4fd80c8b9cc84482` de la imagen 1.3.26 encontró `huggingface_hub==1.33.0` y `hf_xet==1.6.0`. En `inline_core/studio/models.py`, el usuario inicia cada descarga desde Studio y el trabajo bloqueante corre fuera del event loop. El downloader del registro sí mantiene una cola de un modelo activo; otras solicitudes del popup pueden usar llamadas en segundo plano separadas. El flujo existente `.part`, la reanudación, las rutas y la descarga bajo demanda se mantienen.

El código llama `snapshot_download` en dos casos sin pasar `max_workers`; la versión exacta de Hugging Face usa 8 por omisión. `huggingface_hub` 1.33.0 no ofrece una variable de entorno para ese argumento. El ajuste Salad pasa `max_workers` explícitamente en esas dos llamadas, con `INLINE_HF_SNAPSHOT_MAX_WORKERS=2` de inicio. Acepta enteros de 1 a 8; un valor inválido vuelve a 2. El tope se aplica a cada llamada a `snapshot_download`, no como semáforo global entre solicitudes concurrentes. No parchea globalmente Hugging Face ni cambia otros usos de la biblioteca.

La imagen exacta trae `HF_HUB_DISABLE_XET=0`, pero el downloader intenta primero HTTP y activa Xet como fallback para archivos que el camino HTTP rechaza por superar 50 GB. Los límites Xet son compatibles con el `hf_xet` incluido: dos flujos por archivo, un archivo Xet simultáneo y high-performance apagado. No se activa ninguna descarga automática al arrancar. El límite `max_workers` cubre el selector de modelos; la importación de datasets por `studio/training.py` y los modelos de captioning que Transformers pueda descargar con `from_pretrained` son rutas distintas que no se modificaron. Los valores son candidatos iniciales **NEEDS SALAD**, no resultados óptimos; las guías oficiales explican las variables y `max_workers` ([Xet](https://huggingface.co/docs/hub/xet/using-xet-storage), [`snapshot_download` 1.33.0](https://huggingface.co/docs/huggingface_hub/v1.33.0/package_reference/file_download)).

La cola y el trabajo en segundo plano evitan bloquear el event loop de Studio; no prueban que el enlace del nodo o el Gateway sigan respondiendo durante una transferencia. Los incidentes anteriores de gateway intermitente, caídas a 0 Mbps y errores DNS son **USER-REPORTED**, no reproducidos en esta revisión.

## Medición local y externa durante una descarga

Después de que la calificación inicial pase, inicia una descarga grande desde la interfaz y, desde una terminal del contenedor, ejecuta:

```sh
SALAD_GATEWAY_URL='https://<URL-publica-del-Gateway>' /usr/local/bin/salad-download-probes
```

Ejecuta la herramienta en el contenedor, por ejemplo mediante el terminal de ejecución de Salad. Consulta en paralelo cada cinco segundos:

- local: `http://[::1]:8848/v1/health` sobre IPv6;
- externo: `https://<URL-publica-del-Gateway>/v1/health`.

Imprime una línea JSON por muestra con hora UTC, estado HTTP, latencia, error/timeouts y contador de fallos consecutivos en cada ruta. La consulta Gateway usa su URL pública pero se origina en el contenedor; no equivale a medir desde el equipo del usuario. `download.staged_bytes` y `download.staged_mbps` calculan el crecimiento observado de archivos dentro de directorios `.part`; es una **aproximación del progreso local**, no el throughput de red en el cable. Correlaciónala con el progreso/nombre del archivo visible en Studio. Detén la herramienta con Ctrl+C. No inicia ni cancela descargas y no ejecuta reallocation.

Interpretación para investigar, no como conclusión automática:

- Local OK y Gateway lento/fallido: apunta a la ruta del Gateway o red externa.
- Ambos lentos/fallidos: apunta a agotamiento de recursos o bloqueo dentro del proceso/instancia.
- Ambos OK con poco crecimiento `.part`: la transferencia puede estar limitada sin degradar la salud del servidor.

La medición real, la UI y los WebSockets durante una descarga siguen **UNRUN / NEEDS SALAD**.

### Matriz para una validación futura

Usa la misma descarga de modelo y cambia una dimensión cada vez. Mantén las otras dos en sus valores iniciales; no ejecutes un factorial 4×4×4.

| Dimensión | Variable | Valores a comparar | Mantener fijo |
|---|---|---|---|
| Flujos Xet por archivo | `HF_XET_FIXED_DOWNLOAD_CONCURRENCY` | 1, 2, 4, 8 | Archivos Xet=1; `snapshot_download`=2 |
| Archivos Xet simultáneos | `HF_XET_DATA_MAX_CONCURRENT_FILE_DOWNLOADS` | 1, 2, 4, 8 | Flujos/archivo=2; `snapshot_download`=2 |
| Archivos Hub simultáneos | `INLINE_HF_SNAPSHOT_MAX_WORKERS` | 1, 2, 4, 8 | Flujos/archivo=2; archivos Xet=1 |

Por ejecución anota el modelo y la fase observada, las tres variables, duración/throughput de la descarga, latencia p50/p95/máxima local y externa cuando haya muestras suficientes, errores/timeouts, respuesta visible de UI/API/WebSocket y CPU/RAM/GPU/VRAM si están disponibles. No marques un valor como óptimo sin datos de Salad.

## Diagnóstico GPU/Torch al inicio

Los logs del wrapper deben mostrar `nvidia-smi`, GPU, driver y memoria, además de `torch.__version__`, `torch.version.cuda`, `torch.cuda.is_available()`, nombre de cada dispositivo visible y VRAM que Torch reporta. Si falla el diagnóstico, el wrapper avisa y continúa con el entrypoint upstream. Imprimir estos valores no demuestra compatibilidad ni una inferencia correcta.

La auditoría estática de la imagen encontró CUDA 13.0.3 y PyTorch 2.13.0/torchvision 0.28.0 (`cu130`). El requisito conservador documentado para el driver es NVIDIA R580.126.20 o posterior. No se reconstruye PyTorch ni se cambia CUDA.

| GPU | Estado |
|---|---|
| RTX 3090 | NEEDS SALAD |
| RTX 4090 | NEEDS SALAD |
| RTX 5090 | NEEDS SALAD |
| A40 | NEEDS SALAD |
| L40 | NEEDS SALAD |
| L40S | NEEDS SALAD |

## WebSockets, acceso y almacenamiento efímero

Comprueba `GET /events` y `/v1/runs/{id}/events` por `wss://`, incluyendo inactividad, reconexión y reanudación. Según la auditoría, el Gateway necesita autenticación desactivada para transportar WebSockets del navegador, que no puede añadir los encabezados requeridos al handshake. La imagen no proporciona autenticación propia para UI/API; evalúa esa exposición antes de publicar o compartir la URL.

Modelos, outputs, proyectos, LoRAs y cachés guardados bajo `/workspace` se pierden al destruir o reasignar la instancia; es intencional. El warning upstream de que `/workspace` no es un volumen no bloquea el arranque. No se añaden volúmenes, S3/R2, sincronización, restauración ni prefetch.

## Verificación

La verificación estática local cubre sintaxis de scripts, digest/base previsto, variables soportadas, dos llamadas acotadas a `snapshot_download`, delegación al entrypoint original, health sin cambio, reintentos finitos, una sola ruta posible de POST IMDS y ausencia de checks posteriores. No hay Docker instalado en el equipo de auditoría, por lo que el build tampoco se ha ejecutado.

Deja estos puntos como **UNRUN / NEEDS SALAD** hasta validarlos en una instancia real:

- medición inicial de 60 Mbps y resultado de reallocation IMDS;
- listener `:::8848`, health IPv6, Gateway y healthcheck Docker heredado;
- throughput y Gateway/UI/API/WebSockets durante descargas, en los tres ejes de concurrencia;
- diagnóstico CUDA/Torch en Salad e inferencia mínima después de pedir un modelo;
- apagado graceful y no inicio de Jupyter 8888/File Browser 8080.

No se ha desplegado, incurrido en cargos de Salad ni afirmado éxito en runtime.

## Referencias de esta adaptación

- [Análisis de la imagen 1.3.26](ANALISIS-SALAD.md)
- [Salad: comprobación de ancho de banda e IMDS](https://docs.salad.com/container-engine/tutorials/performance/network-bandwidth-checks)
- [Salad: endpoint de reallocation IMDS](https://docs.salad.com/reference/imds/reallocate)
- [Hugging Face: controles de Xet](https://huggingface.co/docs/hub/xet/using-xet-storage)
- [Hugging Face Hub 1.33.0: descarga de archivos y `max_workers`](https://huggingface.co/docs/huggingface_hub/v1.33.0/package_reference/file_download)
