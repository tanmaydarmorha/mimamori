#!/usr/bin/env bash
# Reset the deployed prototype to the seed, like `scripts/dev.sh down --wipe && up` does locally:
# delete the cases and everything demo runs wrote to case-db, reseed it, and restart the backends (their in-memory state:
# the bank mock's freezes, call state, SSE fan-out). Synthetic data only.
#
#   scripts/cloud-reset.sh                       # project from `gcloud config get project`
#   PROJECT=<id> REGION=asia-south1 scripts/cloud-reset.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT="${PROJECT:-$(gcloud config get project 2>/dev/null)}"
REGION="${REGION:-asia-south1}"
[[ -n "$PROJECT" ]] || { echo "set PROJECT" >&2; exit 2; }

echo "resetting $PROJECT: case-db"
# What demo runs write. Seeded or derived collections (wishes, baselines) are kept; wishes are reseeded.
gcloud firestore bulk-delete --project "$PROJECT" --database case-db --quiet \
  --collection-ids audit,cards,case_state,cases,events,freeze_requests,scores >/dev/null
env -u FIRESTORE_EMULATOR_HOST MIMAMORI_ENV=cloud MIMAMORI_STORE=firestore MIMAMORI_PROJECT_ID="$PROJECT" \
  GOOGLE_CLOUD_PROJECT="$PROJECT" .venv/bin/python seed/load.py --db case

echo "restarting the backends"
stamp="$(date +%s)"
for svc in core-bank-mock scoring case-svc conversation-svc; do
  gcloud run services update "$svc" --project "$PROJECT" --region "$REGION" --update-labels "reset=$stamp" --quiet >/dev/null 2>&1 &
done
wait
echo "reset done"
