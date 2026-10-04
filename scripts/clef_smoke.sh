#!/usr/bin/env bash
# Minimal live check of Clef / Clef-flash on Workers AI. Replaced by `debugassist decide` in P1.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
: "${CLOUDFLARE_ACCOUNT_ID:?missing}" "${CLOUDFLARE_API_KEY:?missing}"
for model in clef clef-flash; do
  curl -sS -m 60 -o /dev/null -w "$model: HTTP %{http_code} in %{time_total}s\n" \
    -X POST "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/ai/run/@cf/cloudflare/${model}" \
    -H "Authorization: Bearer ${CLOUDFLARE_API_KEY}" -H 'Content-Type: application/json' \
    -d "{\"model\":\"${model}\",\"state\":\"App crashed on launch.\",\"questions\":{\"is_crash\":{\"type\":\"noul\",\"instructions\":\"Is this a crash?\"}}}"
done
