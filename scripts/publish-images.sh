#!/bin/sh
set -eu

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 BACKEND_IMAGE FRONTEND_IMAGE" >&2
    exit 1
fi

backend_image=$1
frontend_image=$2
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

backend_image_name=${backend_image##*/}
frontend_image_name=${frontend_image##*/}

case "$backend_image_name" in
    *:*) ;;
    *)
        echo "BACKEND_IMAGE must include an explicit tag." >&2
        exit 1
        ;;
esac

case "$frontend_image_name" in
    *:*) ;;
    *)
        echo "FRONTEND_IMAGE must include an explicit tag." >&2
        exit 1
        ;;
esac

backend_latest_image="${backend_image%:*}:latest"
frontend_latest_image="${frontend_image%:*}:latest"

docker build --pull --tag "$backend_image" --tag "$backend_latest_image" backend
docker push "$backend_image"
docker push "$backend_latest_image"
docker build --pull --tag "$frontend_image" --tag "$frontend_latest_image" frontend
docker push "$frontend_image"
docker push "$frontend_latest_image"

if [ -n "${PORTAINER_URL:-}${PORTAINER_API_TOKEN:-}" ]; then
    : "${PORTAINER_URL:?Set PORTAINER_URL to redeploy through Portainer.}"
    : "${PORTAINER_API_TOKEN:?Set PORTAINER_API_TOKEN to redeploy through Portainer.}"
    PORTAINER_STACK_NAME=${PORTAINER_STACK_NAME:-som_comparativa_factures}
    export PORTAINER_STACK_NAME
    python3 "$script_dir/redeploy-portainer.py"
fi
