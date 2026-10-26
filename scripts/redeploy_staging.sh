#!/usr/bin/env bash
# Build, push and roll out changed images to Google staging by digest.
# Usage: scripts/redeploy_staging.sh [backend] [frontend]   (default: both)
set -euo pipefail
cd "$(dirname "$0")/.."
REG=asia-south1-docker.pkg.dev/caseproof-511713/caseproof
VARS=infra/google/runtime/staging.tfvars
TAG=$(git rev-parse --short HEAD)-$(date +%H%M%S)
targets=${*:-backend frontend}

push() { # name dockerfile context [build args...]
  local name=$1 file=$2 ctx=$3; shift 3
  docker build -q -f "$file" -t "$REG/$name:$TAG" "$@" "$ctx" >/dev/null
  docker push -q "$REG/$name:$TAG" >/dev/null
  local digest
  digest=$(gcloud artifacts docker images describe "$REG/$name:$TAG" --format='value(image_summary.digest)')
  echo "$name -> $digest"
  local var=$([ "$name" = backend ] && echo application_image || echo "${name}_image")
  sed -i -E "s#^($var *= *\").*\"#\1$REG/$name@$digest\"#" "$VARS"
}
for t in $targets; do
  case $t in
    backend) push backend Dockerfile.cloud . ;;
    frontend) push frontend frontend/Dockerfile frontend \
      --build-arg FRONTEND_PROFILE=cloud --build-arg STAFF_ACCESS=practice ;;
  esac
done
TF="$PWD/var/tools/terraform/terraform.exe"; cd infra/google/runtime
plan=$("$TF" plan -input=false -no-color -var-file=staging.tfvars -out=staging.plan)
echo "$plan" | grep -E "^Plan:|No changes" || true
if ! echo "$plan" | grep -qE "No changes| 0 to destroy"; then
  echo "Refusing to apply: the plan destroys resources." >&2; exit 1
fi
"$TF" apply -input=false staging.plan | tail -2
