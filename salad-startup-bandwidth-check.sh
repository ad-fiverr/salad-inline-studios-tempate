#!/usr/bin/env bash

set -euo pipefail
export LC_ALL=C

log() { printf '[salad-bandwidth] %s\n' "$*"; }

MIN_MBPS="${MIN_MBPS:-60}"
if [[ ! "$MIN_MBPS" =~ ^[0-9]+([.][0-9]+)?$ ]] || \
   ! awk -v value="$MIN_MBPS" 'BEGIN { exit !(value > 0) }'; then
    log "WARNING: invalid MIN_MBPS=${MIN_MBPS}; using 60."
    MIN_MBPS=60
fi

INLINE_PORT="${INLINE_PORT:-8848}"
if [[ ! "$INLINE_PORT" =~ ^[0-9]+$ ]]; then
    log "WARNING: invalid INLINE_PORT; using 8848 for the local readiness probe."
    INLINE_PORT=8848
fi

if ! command -v curl >/dev/null 2>&1; then
    log "WARNING: curl is unavailable; skipping bandwidth qualification without reallocation."
    exit 0
fi

health_url="http://[::1]:${INLINE_PORT}/v1/health"
server_ready=0
for ((health_attempt = 1; health_attempt <= 90; health_attempt++)); do
    if curl --ipv6 --globoff --silent --show-error --fail \
        --connect-timeout 1 --max-time 2 --output /dev/null "$health_url" \
        >/dev/null 2>&1; then
        server_ready=1
        break
    fi
    sleep 2
done

if ((server_ready == 0)); then
    log "HTTP server did not become ready on IPv6; bandwidth qualification was not run and no reallocation was requested."
    exit 0
fi

log "HTTP server is ready; running one startup-only download bandwidth qualification (minimum ${MIN_MBPS} Mbps)."

SPEED_TEST_BYTES=25000000
SPEED_TEST_ATTEMPTS=3
SPEED_TEST_BACKOFF_SECONDS=10
SPEED_TEST_URL="https://speed.cloudflare.com/__down?bytes=${SPEED_TEST_BYTES}"
best_mbps="0.00"

for ((attempt = 1; attempt <= SPEED_TEST_ATTEMPTS; attempt++)); do
    metrics=""
    if metrics="$(curl --location --fail --silent --show-error \
        --connect-timeout 5 --max-time 30 --output /dev/null \
        --write-out '%{speed_download} %{time_total} %{http_code}' \
        "$SPEED_TEST_URL")"; then
        read -r speed_bps elapsed http_status <<< "$metrics"
        mbps="$(awk -v speed="$speed_bps" 'BEGIN { printf "%.2f", speed * 8 / 1000000 }')"
        best_mbps="$(awk -v best="$best_mbps" -v current="$mbps" \
            'BEGIN { printf "%.2f", (current > best ? current : best) }')"

        if awk -v current="$mbps" -v minimum="$MIN_MBPS" \
            'BEGIN { exit !(current >= minimum) }'; then
            log "attempt=${attempt}/${SPEED_TEST_ATTEMPTS} measured_mbps=${mbps} elapsed_s=${elapsed} http_status=${http_status} result=PASS"
            log "Startup bandwidth qualification passed; no further checks or reallocations will run."
            exit 0
        fi
        log "attempt=${attempt}/${SPEED_TEST_ATTEMPTS} measured_mbps=${mbps} elapsed_s=${elapsed} http_status=${http_status} result=FAIL below_minimum=${MIN_MBPS}"
    else
        curl_exit=$?
        if [[ "$metrics" =~ ^([0-9.]+)[[:space:]]+([0-9.]+)[[:space:]]+([0-9]{3})$ ]]; then
            elapsed="${BASH_REMATCH[2]}"
            http_status="${BASH_REMATCH[3]}"
        else
            elapsed="unknown"
            http_status="unknown"
        fi
        log "attempt=${attempt}/${SPEED_TEST_ATTEMPTS} result=ERROR curl_exit=${curl_exit} elapsed_s=${elapsed} http_status=${http_status}; curl error details are logged separately."
    fi

    if ((attempt < SPEED_TEST_ATTEMPTS)); then
        sleep "$SPEED_TEST_BACKOFF_SECONDS"
    fi
done

reason="Startup download bandwidth below ${MIN_MBPS} Mbps; best measured ${best_mbps} Mbps after ${SPEED_TEST_ATTEMPTS} attempts."
payload="$(printf '{\"reason\":\"%s\"}' "$reason")"
log "All startup attempts failed; sending one Salad IMDS reallocation request."

if http_status="$(curl --silent --show-error --output /dev/null \
    --connect-timeout 3 --max-time 10 --request POST \
    --header 'Content-Type: application/json' \
    --header 'Metadata: true' \
    --data "$payload" \
    --write-out '%{http_code}' \
    'http://169.254.169.254/v1/reallocate')"; then
    log "IMDS reallocation request completed; http_status=${http_status}. Response body was not logged."
else
    curl_exit=$?
    log "IMDS reallocation request failed; curl_exit=${curl_exit} http_status=${http_status:-unknown}. Response body was not logged."
fi

log "Startup qualification is finished; no later bandwidth checks or reallocation requests will run."
