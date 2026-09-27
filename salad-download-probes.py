#!/opt/venv/bin/python

import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


INTERVAL_SECONDS = 5.0
LOCAL_TIMEOUT_SECONDS = 2
GATEWAY_TIMEOUT_SECONDS = 3


def gateway_health_url() -> str:
    raw_url = os.environ.get("SALAD_GATEWAY_URL", "").strip()
    parsed = urlsplit(raw_url)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise SystemExit("Set SALAD_GATEWAY_URL to the public https:// Gateway base URL, without a path or credentials.")
    return urlunsplit((parsed.scheme, parsed.netloc, "/v1/health", "", ""))


def probe(url: str, timeout_seconds: int, ipv6: bool) -> dict[str, object]:
    command = ["curl", "--silent", "--show-error", "--location", "--output", os.devnull]
    if ipv6:
        command.extend(["--ipv6", "--globoff"])
    command.extend(
        [
            "--connect-timeout",
            str(timeout_seconds),
            "--max-time",
            str(timeout_seconds),
            "--write-out",
            "%{http_code} %{time_total}",
            url,
        ]
    )
    started = time.perf_counter()
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds + 1, check=False)
    except subprocess.TimeoutExpired:
        return {
            "status": None,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "error": "probe process timed out",
            "timeout": True,
            "ok": False,
        }

    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    match = re.search(r"(\d{3})\s+([0-9.]+)\s*$", result.stdout)
    status = int(match.group(1)) if match else None
    reported_seconds = float(match.group(2)) if match else None
    error = result.stderr.strip().replace("\n", " ")[:180] if result.returncode else None
    timed_out = result.returncode == 28 or bool(error and "timed out" in error.lower())
    ok = result.returncode == 0 and status == 200
    return {
        "status": status,
        "latency_ms": round(reported_seconds * 1000, 1) if reported_seconds is not None else latency_ms,
        "error": error,
        "timeout": timed_out,
        "ok": ok,
    }


def staged_bytes(root: Path) -> int:
    if not root.is_dir():
        return 0
    total = 0
    for current, directories, _files in os.walk(root):
        staged = [name for name in directories if name.endswith(".part")]
        for dirname in staged:
            for partial_root, _partial_dirs, filenames in os.walk(Path(current) / dirname):
                for filename in filenames:
                    try:
                        total += (Path(partial_root) / filename).stat().st_size
                    except OSError:
                        pass
        directories[:] = [name for name in directories if not name.endswith(".part")]
    return total


def main() -> None:
    if not shutil.which("curl"):
        raise SystemExit("curl is required; it is included in the base image for the upstream healthcheck.")
    gateway_url = gateway_health_url()
    port = os.environ.get("INLINE_PORT", "8848")
    local_url = f"http://[::1]:{port}/v1/health"
    models_root = Path(os.environ.get("INLINE_MODELS_DIR", "/workspace/models"))
    failures = {"local": 0, "gateway": 0}
    previous_bytes = staged_bytes(models_root)
    previous_time = time.perf_counter()
    print("Probing local IPv6 and Salad Gateway health in parallel; stop with Ctrl+C.", flush=True)
    print("staged_mbps is the observed growth of Inline Studio .part staging files, not wire-level throughput.", flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        try:
            while True:
                sample_started = time.perf_counter()
                local_future = executor.submit(probe, local_url, LOCAL_TIMEOUT_SECONDS, True)
                gateway_future = executor.submit(probe, gateway_url, GATEWAY_TIMEOUT_SECONDS, False)
                local = local_future.result()
                gateway = gateway_future.result()
                failures["local"] = failures["local"] + 1 if not local["ok"] else 0
                failures["gateway"] = failures["gateway"] + 1 if not gateway["ok"] else 0

                sampled_at = time.perf_counter()
                current_bytes = staged_bytes(models_root)
                elapsed = max(sampled_at - previous_time, 0.001)
                delta_bytes = max(current_bytes - previous_bytes, 0)
                record = {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                    "local_ipv6": {**local, "consecutive_failures": failures["local"]},
                    "gateway": {**gateway, "consecutive_failures": failures["gateway"]},
                    "download": {
                        "staged_bytes": current_bytes,
                        "staged_mbps": round(delta_bytes * 8 / elapsed / 1_000_000, 2),
                    },
                }
                print(json.dumps(record, separators=(",", ":")), flush=True)
                previous_bytes = current_bytes
                previous_time = sampled_at
                time.sleep(max(0.0, INTERVAL_SECONDS - (time.perf_counter() - sample_started)))
        except KeyboardInterrupt:
            print("Probe stopped by user.", flush=True)


if __name__ == "__main__":
    main()
