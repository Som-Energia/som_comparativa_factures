#!/bin/sh
set -eu

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 BACKEND_IMAGE_REPOSITORY FRONTEND_IMAGE_REPOSITORY" >&2
    exit 1
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
version=$(tr -d '\r\n' < "$project_dir/VERSION")
backend_repository=$1
frontend_repository=$2
git_tag="v$version"

if [ -z "$version" ]; then
    echo "VERSION must define an application version." >&2
    exit 1
fi

if [ -n "$(git -C "$project_dir" status --porcelain)" ]; then
    echo "Refusing to publish from a working tree with uncommitted changes." >&2
    exit 1
fi

if git -C "$project_dir" rev-parse --verify --quiet "refs/tags/$git_tag" >/dev/null; then
    echo "Git tag $git_tag already exists locally." >&2
    exit 1
fi

remote_tag=$(git -C "$project_dir" ls-remote --tags origin "refs/tags/$git_tag") || {
    echo "Could not check whether Git tag $git_tag exists on origin." >&2
    exit 1
}
if [ -n "$remote_tag" ]; then
    echo "Git tag $git_tag already exists on origin." >&2
    exit 1
fi

backend_image_name=${backend_repository##*/}
frontend_image_name=${frontend_repository##*/}

case "$backend_image_name" in
    *:*)
        echo "BACKEND_IMAGE_REPOSITORY must not include a tag." >&2
        exit 1
        ;;
esac

case "$frontend_image_name" in
    *:*)
        echo "FRONTEND_IMAGE_REPOSITORY must not include a tag." >&2
        exit 1
        ;;
esac

backend_image="$backend_repository:$version"
frontend_image="$frontend_repository:$version"
backend_latest_image="$backend_repository:latest"
frontend_latest_image="$frontend_repository:latest"

docker build --pull --file "$project_dir/backend/Dockerfile" --tag "$backend_image" --tag "$backend_latest_image" "$project_dir"
docker push "$backend_image"
docker push "$backend_latest_image"
docker build --pull --build-arg APP_VERSION="$version" --tag "$frontend_image" --tag "$frontend_latest_image" "$project_dir/frontend"
docker push "$frontend_image"
docker push "$frontend_latest_image"

git -C "$project_dir" tag --annotate "$git_tag" --message "Release $git_tag"
git -C "$project_dir" push origin "$git_tag"

if [ -n "${PORTAINER_URL:-}${PORTAINER_API_TOKEN:-}" ]; then
    : "${PORTAINER_URL:?Set PORTAINER_URL to redeploy through Portainer.}"
    : "${PORTAINER_API_TOKEN:?Set PORTAINER_API_TOKEN to redeploy through Portainer.}"
    PORTAINER_STACK_NAME=${PORTAINER_STACK_NAME:-som_comparativa_factures}
    export PORTAINER_STACK_NAME
    python3 "$script_dir/redeploy-portainer.py"
fi
