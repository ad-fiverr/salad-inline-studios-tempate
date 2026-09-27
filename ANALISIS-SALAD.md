# Análisis de Inline Studio 1.3.26 en SaladCloud

**Fecha de auditoría:** 2026-09-26  
**Alcance:** imagen pública `inlineresearch/inline-studio:1.3.26`; ejecución efímera con Salad Container Engine y Container Gateway en el puerto 8848.  
**Límite:** inspección de solo lectura. En este equipo no están disponibles Docker ni `nvidia-smi`; no se construyó ni arrancó la imagen y no se hicieron pruebas en Salad.

## Dictamen

Inline Studio es el proceso principal de la aplicación bajo `tini`; el entrypoint de fábrica también puede iniciar Jupyter y File Browser salvo que se desactiven con `ENABLE_JUPYTER=0` y `ENABLE_FILEBROWSER=0`. La imagen sirve interfaz y API en el puerto 8848, y ya incluye `/v1/health`, `tini` y un `HEALTHCHECK`. El hallazgo concreto para Salad es que la configuración exacta de la imagen fija `INLINE_HOST=0.0.0.0`, mientras que el Container Gateway requiere que la aplicación acepte IPv6. La corrección mínima a probar es sobrescribir `INLINE_HOST=::`, conservar `INLINE_PORT=8848` y el entrypoint original, y establecer `ENABLE_JUPYTER=0` y `ENABLE_FILEBROWSER=0`.

No se encontró motivo para reconstruir PyTorch, sustituir el entrypoint, añadir un wrapper o incorporar persistencia. La compatibilidad real de IPv6, CUDA, Gateway y WebSockets queda pendiente de una ejecución en Salad.

## Clases de evidencia

- **VERIFIED:** comprobado directamente en el manifiesto/capas de la imagen, mediante comparación de bytes con el commit fuente, o en una referencia primaria aplicable.
- **STATIC:** la configuración o el código lo demuestran; no se ejecutó bajo Salad.
- **NEEDS SALAD:** depende de la asignación de GPU/driver, del Gateway, de las sondas o del ciclo de vida real de Salad.

## Identidad exacta de la imagen

| Campo | Evidencia observada |
|---|---|
| Referencia | `inlineresearch/inline-studio:1.3.26` |
| Digest OCI del manifiesto | `sha256:9424463b243bd15802d0f67ae22efb760f4292b001d5b2fd4fd80c8b9cc84482` |
| Digest OCI de configuración | `sha256:fade7a1ece68614bf5c5bbac8666538bfd713848e965479105d49cc51891b163` |
| Plataforma | `linux/amd64` |
| Creación declarada en OCI | `2026-09-25T10:43:25.071901722Z` |
| `org.opencontainers.image.source` | `https://github.com/inlineresearch/Inline-Studio` |
| `org.opencontainers.image.version` | `24.04` — coincide con Ubuntu base; no es una etiqueta inequívoca de la versión de la aplicación. |

El tag upstream `v1.3.26` resolvió al commit `fcac353928ede74b28819274a9287783fdee6151`. La rama `main` resolvió al mismo commit durante esta auditoría; no se asumió esa equivalencia. Además, comparé SHA-256 de los archivos extraídos de las capas de la imagen con los archivos de ese commit: `core/main.py`, `core/src/inline_core/server/app.py`, `core/src/inline_core/studio/models.py`, `core/src/inline_core/models/minimaxh3/requirements.py` y `docker/entrypoint.sh` coincidieron byte por byte. Por tanto, esos archivos fuente sí están respaldados por la imagen; el manifiesto no contiene una etiqueta OCI de revisión.

Referencias: [tag de Docker Hub](https://hub.docker.com/r/inlineresearch/inline-studio/tags?name=1.3.26), [commit `v1.3.26`](https://github.com/omnichar/OmniChar/commit/fcac353928ede74b28819274a9287783fdee6151), [Dockerfile de ese commit](https://github.com/omnichar/OmniChar/blob/fcac353928ede74b28819274a9287783fdee6151/Dockerfile).

## Evidencia y resultado por área

| Área | Clasificación | Evidencia | Hallazgo y delta mínimo |
|---|---|---|---|
| Identidad/tag/digest | **VERIFIED** | Manifiesto y configuración OCI descargados directamente; digest arriba. Tag de código y rama `main` comprobados en GitHub el 2026-09-26. | Usar el tag solicitado; para builds reproducibles se puede fijar también el digest. No inferir una revisión OCI que la imagen no declara. |
| Contrato del contenedor | **STATIC** | Config OCI y Dockerfile del commit que coincide con los archivos extraídos. | `Entrypoint=["/usr/bin/tini","-g","--","/opt/entrypoint.sh"]`; `Cmd` vacío; `WorkingDir=/workspace`; usuario por omisión (root); plataformas/puertos declarados en la sección siguiente. Conservar entrypoint y no pasar `--listen`. |
| Proceso/PID 1 y señales | **STATIC** | `tini -g` ejecuta `/opt/entrypoint.sh`; este termina con `exec /opt/venv/bin/inline-studio "$@"`. El entrypoint puede iniciar Jupyter y File Browser antes del `exec` salvo que se deshabiliten. | `tini` permanece como PID 1 y el servidor es su proceso hijo directo al final del entrypoint. Para Salad, desactivar ambos servicios auxiliares. La propagación de SIGTERM/SIGINT y los códigos de salida no se ejecutaron aquí; verificación final en Salad o Docker. No se justifica un wrapper. |
| Jupyter y File Browser | **STATIC** | El entrypoint inicia Jupyter en 8888 y File Browser en 8080 salvo que sus variables valgan `0`. Ambos están activos por omisión. | Para el servicio efímero de Studio, poner `ENABLE_JUPYTER=0` y `ENABLE_FILEBROWSER=0`. No hace falta eliminar paquetes ni reescribir el entrypoint. |
| IPv6 de entrada | **STATIC** | La imagen fija `INLINE_HOST=0.0.0.0`; el `main.py` lee `INLINE_HOST` y lo pasa a Uvicorn. `--listen` fuerza `0.0.0.0`. Salad documenta `::` para Uvicorn y exige IPv6 para Container Gateway. | Hay un desajuste demostrable. Sobrescribir `INLINE_HOST=::`; no agregar el argumento `--listen`. El listener real en `:::8848` y el acceso por Gateway son **NEEDS SALAD**. ([IPv6 de Salad](https://docs.salad.com/container-engine/how-to-guides/gateway/enabling-ipv6), [requisitos de Gateway](https://docs.salad.com/container-engine/explanation/infrastructure-platform/networking)) |
| Puerto, UI y rutas HTTP | **STATIC** | La configuración expone 8848 y `INLINE_PORT=8848`. FastAPI sirve la SPA y sus assets en el mismo puerto. Rutas presentes: `/api` (referencia Scalar), `/openapi.json`, `POST /rpc` (canales del editor), `/v1/*` REST, `GET /v1/health`. | Configurar Container Gateway en HTTP port 8848. `/api` es documentación interactiva, no el endpoint REST; usar `/v1/*` o `POST /rpc` para la aplicación. La respuesta externa real sigue **NEEDS SALAD**. |
| Healthcheck de la imagen | **STATIC** | Healthcheck Docker existente: `curl -fsS http://127.0.0.1:8848/v1/health`, cada 30 s, timeout 5 s, inicio 180 s, 3 reintentos. | El endpoint existe y devuelve JSON `ok: true` más datos de dispositivo. No confirma que se descargó o cargó un modelo. Dejar el healthcheck upstream durante el primer intento; probar `curl -g -6 -fsS 'http://[::1]:8848/v1/health'` dentro del contenedor. Sobrescribir el healthcheck de Docker con esa prueba IPv6 solo si el test muestra que hace falta. |
| Gateway HTTPS y proxy | **NEEDS SALAD** | La imagen establece `FORWARDED_ALLOW_IPS=*`; el Dockerfile upstream explica que lo usa para conservar `X-Forwarded-Proto` tras un proxy TLS. La SPA forma sus llamadas desde el origen del navegador. Salad termina la entrada pública en HTTPS. | Probar carga en `https://…`, assets, respuestas/redirecciones y que el navegador negocie WebSocket seguro (`wss://`). La variable del contenedor no demuestra qué encabezados envía Salad. |
| WebSockets | **NEEDS SALAD** | La SPA abre `/events`; el servidor también ofrece `/v1/runs/{run_id}/events`. El socket `/events` queda esperando eventos y no tiene heartbeat de aplicación. Salad documenta cierre tras 100 s inactivo; el cliente de la SPA vuelve a conectar, pero no se probó la recuperación de eventos frente al Gateway. | Probar ambos WebSockets, incluidos más de 100 s inactivos y reanudación de una descarga/generación. La documentación de Salad dice que, al usar WebSockets, se deshabilite la autenticación del Container Gateway porque el navegador no puede enviar sus encabezados de autenticación en la negociación. El servidor de esta imagen no ofrece autenticación de aplicación para la interfaz/API; considerar el URL de Gateway accesible por quien lo conozca. ([WebSockets de Salad](https://docs.salad.com/container-engine/explanation/gateway/websockets)) |
| Startup/readiness/liveness | **NEEDS SALAD** | `/v1/health` puede contestar sin que se haya pedido un checkpoint; los pesos se descargan después, por acción del usuario. Salad permite HTTP/1.X en probes y mantiene fuera del Gateway instancias no listas. | Usar una startup probe o readiness HTTP sobre puerto 8848 y `/v1/health` para esperar al servidor, no a la descarga de modelos. Omitir liveness agresiva inicialmente: Salad reubica la instancia si falla esa sonda y se perdería la sesión efímera. Confirmar tiempos y comportamiento con una instancia real. ([startup](https://docs.salad.com/container-engine/explanation/infrastructure-platform/startup-probes), [readiness](https://docs.salad.com/container-engine/explanation/infrastructure-platform/readiness-probes), [liveness](https://docs.salad.com/container-engine/explanation/infrastructure-platform/liveness-probes)) |
| CUDA/Torch/driver | **STATIC** | La imagen contiene CUDA 13.0.3 y PyTorch 2.13.0/torchvision 0.28.0 de `cu130`. `NVIDIA_REQUIRE_CUDA` permite desde driver 575, pero el entrypoint advierte que CUDA 13 necesita R580 y, si no, solo avisa: no cancela el arranque. NVIDIA lista R580 como mínimo de compatibilidad minor-version para CUDA 13.x; el Toolkit 13.0 Update 3 lista `580.126.20` como versión empaquetada. | Usar como requisito operativo conservador driver `580.126.20+`; verificar `nvidia-smi`, `torch.cuda.is_available()`, versión CUDA de Torch y una inferencia mínima. No reconstruir Torch por hipótesis. ([release notes CUDA 13.0](https://docs.nvidia.com/cuda/archive/13.0.3/cuda-toolkit-release-notes/index.html), [soporte de arquitecturas R580](https://docs.nvidia.com/datacenter/tesla/tesla-release-notes-580-126-20/index.html)) |
| RTX 3090 | **NEEDS SALAD** | Ampere; arquitectura cubierta por CUDA 13/R580. | No hay prueba de esta imagen/Torch en una RTX 3090 asignada por Salad. Comprobar device visible y una inferencia. |
| A40 | **NEEDS SALAD** | Ampere; arquitectura cubierta por CUDA 13/R580. | No hay prueba de esta imagen/Torch en una A40 asignada por Salad. Comprobar device visible y una inferencia. |
| RTX 4090 | **NEEDS SALAD** | Ada; arquitectura cubierta por CUDA 13/R580. | No hay prueba de esta imagen/Torch en una RTX 4090 asignada por Salad. Comprobar device visible y una inferencia. |
| L40 | **NEEDS SALAD** | Ada; arquitectura cubierta por CUDA 13/R580. | No hay prueba de esta imagen/Torch en una L40 asignada por Salad. Comprobar device visible y una inferencia. |
| L40S | **NEEDS SALAD** | Ada; arquitectura cubierta por CUDA 13/R580. | No hay prueba de esta imagen/Torch en una L40S asignada por Salad. Comprobar device visible y una inferencia. |
| RTX 5090 | **NEEDS SALAD** | Blackwell; arquitectura cubierta por CUDA 13/R580. La coincidencia de arquitectura no demuestra que kernels/modelos concretos funcionen en esta imagen y nodo. | Probar el arranque de Torch y un caso H3 pequeño en una 5090 de Salad antes de darla por compatible. |
| Descarga de modelos y caché | **STATIC** | `studio/models.py` declara ser el único lugar del motor que descarga modelos; el runner usa `local_files_only=True`. La descarga se pide desde la interfaz, corre en un hilo de fondo y deja `.part` para staging/reanudación. Modelos: `/workspace/models`; datos/caché incluyen `/workspace/.inline` y `/workspace/huggingface`. | No hay prefetch de checkpoints en startup. En modo efímero se pierde todo lo descargado al destruir o reasignar la instancia y se baja otra vez en la siguiente sesión; aceptado por el alcance. |
| MiniMax H3 y archivos >50 GB | **STATIC** | Los requisitos versionados indican repos `Comfy-Org/MiniMax-H3` y `MiniMaxAI/MiniMax-H3`. La combinación de generación por omisión suma aproximadamente 40 GB: transformer int8 21.0 GB, encoder NVFP4 15.7 GB, VAE de video int8 2.8 GB, VAE de audio 0.6 GB y processor 12 MB. Alternativas de entrenamiento BF16 incluyen transformer 66.3 GB y encoder de archivo único 51.5 GB. El código reintenta con Xet ante el rechazo de HTTP para archivos mayores a 50 GB. La imagen fija `HF_HUB_DISABLE_XET=0`; el servidor usa `setdefault(..., "1")`, así que no sustituye ese valor. | El H3 predeterminado no se baja al arrancar y sus archivos individuales son menores de 50 GB. Para archivos BF16 mayores a 50 GB entra en juego Xet. Si una descarga de ~40 GB tardara, el tiempo no bloquea la interfaz al arrancar: sería al pedir ese modelo. ([requisitos en el commit](https://github.com/omnichar/OmniChar/blob/fcac353928ede74b28819274a9287783fdee6151/core/src/inline_core/models/minimaxh3/requirements.py), [gestor de descargas](https://github.com/omnichar/OmniChar/blob/fcac353928ede74b28819274a9287783fdee6151/core/src/inline_core/studio/models.py), [variables Xet de Hugging Face](https://huggingface.co/docs/huggingface_hub/main/package_reference/environment_variables#hf_hub_disable_xet)) |
| Guardia de ancho de banda / objetivo solicitado de 60 Mbps | **STATIC** — únicamente constata ausencia de implementación en las fuentes inspeccionadas | Los archivos `Dockerfile` y `setup_models.sh` de la referencia actual `ad-fiverr/comfyui-minimax-runpod` no contienen `MIN_MBPS` ni la llamada IMDS de reallocation. El script sí comprueba CUDA, descarga modelos y luego ejecuta ComfyUI con `--listen 0.0.0.0 --port 8188`; es otro flujo. Esta clasificación no verifica el valor efectivo. | Objetivo solicitado: **60 Mbps**. Valor efectivo en una instancia Salad: **NOT VERIFIED / NEEDS EVIDENCE**. En la configuración/código de la imagen y en los archivos de referencia inspeccionados no se encontró una implementación de guardia ni una definición de `MIN_MBPS`. No presentar 60 Mbps como configuración observada ni añadir el guardia por suposición. Inline Studio no descarga pesos al iniciar; no se justifica rechazar/reasignar un nodo solo por ancho de banda de inicio. Salad recomienda la comprobación únicamente si la velocidad mínima es requisito funcional; una reallocation excluye el nodo de la bolsa de asignación durante 48 h y un límite alto puede ciclar réplicas. Los cálculos a 60 Mbps son solo sensibilidad/ejemplo basado en el objetivo solicitado: 40 GB requieren ~89 min y 66.3 GB ~2 h 28 min, antes de overhead; la velocidad real hacia Hugging Face no está garantizada. ([Dockerfile de referencia](https://github.com/ad-fiverr/comfyui-minimax-runpod/blob/main/Dockerfile), [setup_models.sh de referencia](https://github.com/ad-fiverr/comfyui-minimax-runpod/blob/main/setup_models.sh), [guía de ancho de banda de Salad](https://docs.salad.com/container-engine/tutorials/performance/network-bandwidth-checks)) |
| Persistencia y `/workspace` | **STATIC** | El entrypoint solo avisa si `/workspace` no es volumen montado; crea directorios y continúa. La imagen guarda allí modelos, proyectos, LoRAs y cachés. | El aviso es esperado y no requiere cambio. No añadir S3, R2, volúmenes, sincronización ni prefetch. |

## Referencia de ComfyUI: uso limitado a comparación

En el estado de `main` consultado, el Dockerfile de referencia usa CUDA 12.8/cu128, ejecuta `setup_models.sh`, expone 8188 y el script pasa `0.0.0.0` a ComfyUI. Descarga una colección extensa de modelos antes de la orden final de inicio. No contiene `MIN_MBPS=60`, configuración IPv6 ni las llamadas Salad IMDS buscadas. Sirve para comparar el patrón de descargas y las decisiones históricas, no como arquitectura para OmniChar. No copiar sus dependencias, descarga en startup, puertos ni comandos.

`core/webui.sh` del commit 1.3.26 es el instalador/launcher para instalación local: crea el entorno Python, puede instalar dependencias y selecciona un índice de PyTorch según GPU/driver. La imagen inspeccionada no lo ejecuta; arranca el `inline-studio` ya instalado. Por ello, su lógica no cambia la versión CUDA/Torch medida en la imagen ni prueba las GPU de Salad. [Fuente versionada](https://github.com/omnichar/OmniChar/blob/fcac353928ede74b28819274a9287783fdee6151/core/webui.sh).

**Nota de seguridad:** el `setup_models.sh` público contiene valores con formato de token dentro de URLs de descarga. No copio esos valores en este informe. Revócalos o rótalos si siguen activos.

## Configuración mínima candidata

La siguiente capa describe el delta a evaluar en el microtask de implementación; **no se creó ni se construyó aquí**:

```dockerfile
FROM inlineresearch/inline-studio:1.3.26

ENV INLINE_HOST=:: \
    INLINE_PORT=8848 \
    ENABLE_JUPYTER=0 \
    ENABLE_FILEBROWSER=0
```

Conservar `ENTRYPOINT`, `tini` y el healthcheck upstream inicialmente. Solo cambiar el healthcheck de Docker a loopback IPv6 si la prueba `curl -g -6 http://[::1]:8848/v1/health` demuestra que el actual no acompaña la nueva dirección. En la consola de Salad, usar Container Gateway en 8848 y una sonda HTTP sobre `/v1/health`; no declarar la instancia lista según los modelos, porque el usuario los pide durante la sesión.

## Pruebas aún necesarias en Salad

| Prueba | Estado |
|---|---|
| Construir la capa mínima | No ejecutada: Docker no está instalado en este equipo. |
| Arrancar la imagen efímera sin volumen | No ejecutada; comprobar que el warning de `/workspace` no bloquea el proceso. |
| GPU visible, driver R580, `torch.cuda.is_available()` | No ejecutada: no hay `nvidia-smi` ni GPU local accesible. |
| UI, assets, `/api`, `/v1/health`, `/v1/models`, `POST /rpc` por Gateway | No ejecutadas. |
| Listener `:::8848` y `curl -g -6 http://[::1]:8848/v1/health` | No ejecutadas. |
| WebSockets `/events` y `/v1/runs/{id}/events`, incluido cierre por inactividad | No ejecutadas. |
| Sonda readiness, `SIGTERM`/`SIGINT` y códigos de salida | No ejecutadas. |
| Smoke test CUDA/inferencia en RTX 3090, 4090, 5090, A40, L40 y L40S | No ejecutado en ninguno de los seis modelos. |

El alcance de este informe cubrió estáticamente todos los puntos pedidos. No se atribuye a la imagen ningún resultado de ejecución que no se haya observado.

## Referencias

- [OmniChar, sitio oficial](https://www.omnichar.org/) — nombre vigente del producto y motor en un proceso.
- [OmniChar, commit fuente que elevó la versión a 1.3.26](https://github.com/omnichar/OmniChar/commit/fcac353928ede74b28819274a9287783fdee6151).
- [Salad: requisitos del Container Gateway y HTTPS/IPv6](https://docs.salad.com/container-engine/explanation/infrastructure-platform/networking).
- [Salad: configurar IPv6 con Uvicorn](https://docs.salad.com/container-engine/how-to-guides/gateway/enabling-ipv6).
- [Salad: WebSockets](https://docs.salad.com/container-engine/explanation/gateway/websockets).
- [Salad: bandwidth checks y reallocation](https://docs.salad.com/container-engine/tutorials/performance/network-bandwidth-checks).
- [NVIDIA: CUDA Toolkit 13.0 Update 3 release notes](https://docs.nvidia.com/cuda/archive/13.0.3/cuda-toolkit-release-notes/index.html).
