FROM inlineresearch/inline-studio:1.3.26

ENV INLINE_HOST=:: \
    INLINE_PORT=8848 \
    ENABLE_JUPYTER=0 \
    ENABLE_FILEBROWSER=0 \
    MIN_MBPS=60 \
    HF_XET_HIGH_PERFORMANCE=0 \
    HF_XET_FIXED_DOWNLOAD_CONCURRENCY=2 \
    HF_XET_DATA_MAX_CONCURRENT_FILE_DOWNLOADS=1 \
    INLINE_HF_SNAPSHOT_MAX_WORKERS=2

COPY salad-entrypoint.sh /opt/salad-entrypoint.sh
COPY salad-startup-bandwidth-check.sh /opt/salad-startup-bandwidth-check.sh
COPY salad-download-probes.py /usr/local/bin/salad-download-probes
COPY salad-patch-inline-models.py /tmp/salad-patch-inline-models.py

RUN chmod 0755 \
        /opt/salad-entrypoint.sh \
        /opt/salad-startup-bandwidth-check.sh \
        /usr/local/bin/salad-download-probes \
    && /opt/venv/bin/python /tmp/salad-patch-inline-models.py \
    && cd /opt/inline-studio/core \
    && uv pip install --python /opt/venv/bin/python --no-sources --no-deps --reinstall . \
    && /opt/venv/bin/python -c "from inline_core.studio.models import _snapshot_download_max_workers; assert _snapshot_download_max_workers() == 2"

ENTRYPOINT ["/usr/bin/tini", "-g", "--", "/opt/salad-entrypoint.sh"]
