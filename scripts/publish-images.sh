#!/bin/sh
set -eu

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 BACKEND_IMAGE FRONTEND_IMAGE" >&2
    exit 1
fi

backend_image=$1
frontend_image=$2

docker build --pull --tag "$backend_image" backend
docker push "$backend_image"
docker build --pull --tag "$frontend_image" frontend
docker push "$frontend_image"
