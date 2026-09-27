#!/usr/bin/env bash

echo "=== Salad GPU / Torch startup diagnostics ==="

if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi || echo "WARNING: nvidia-smi failed; continuing with upstream startup." >&2
else
    echo "WARNING: nvidia-smi is unavailable; continuing with upstream startup." >&2
fi

if [ -x /opt/venv/bin/python ]; then
    if /opt/venv/bin/python - <<'PY'
try:
    import torch

    print(f"torch.__version__={torch.__version__}")
    print(f"torch.version.cuda={torch.version.cuda}")
    cuda_available = torch.cuda.is_available()
    print(f"torch.cuda.is_available()={cuda_available}")
    if cuda_available:
        print(f"torch.cuda.device_count()={torch.cuda.device_count()}")
        for index in range(torch.cuda.device_count()):
            properties = torch.cuda.get_device_properties(index)
            total_vram_gib = properties.total_memory / (1024 ** 3)
            print(f"torch.cuda.get_device_name({index})={torch.cuda.get_device_name(index)}")
            print(f"torch.cuda.total_vram_gib({index})={total_vram_gib:.2f}")
    else:
        print("torch.cuda.get_device_name(0)=UNAVAILABLE")
except Exception as error:
    print(f"WARNING: Torch diagnostics failed: {type(error).__name__}: {error}")
PY
    then
        :
    else
        echo "WARNING: the Torch diagnostic command failed; continuing with upstream startup." >&2
    fi
else
    echo "WARNING: /opt/venv/bin/python is unavailable; continuing with upstream startup." >&2
fi

echo "=== Starting the upstream Inline Studio entrypoint ==="
/opt/salad-startup-bandwidth-check.sh &
exec /opt/entrypoint.sh "$@"
