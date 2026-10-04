#!/usr/bin/env bash
#
# Build the app images (issue 452) the way a release publishes them: <registry>/javv-backend:<version>
# and <registry>/javv-frontend:<version>, the version from .release-please-manifest.json. Each image
# carries the OCI version, revision and source labels, so `docker image inspect` tells which release
# and commit it is under any tag. Builds only: the release workflow smokes the images before it
# pushes them, and CI builds them with this same script.
#
#   development/scripts/build-app-images.sh
#
# Env: REGISTRY (default ghcr.io/danube-labs, the registry deploy/compose/compose.yaml names)
#      SOURCE   (default https://github.com/Danube-Labs/javv-poc)
# Prints the two image references, backend first. Requires: docker, jq, git.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
registry=${REGISTRY:-ghcr.io/danube-labs}
source_url=${SOURCE:-https://github.com/Danube-Labs/javv-poc}
version=$(jq -r '."."' .release-please-manifest.json)
revision=$(git rev-parse HEAD)
[[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
  echo "build-app-images: no release version in .release-please-manifest.json: '$version'" >&2
  exit 1
}

for app in backend frontend; do
  ref="$registry/javv-$app:$version"
  docker build -f "$app/Dockerfile" -t "$ref" \
    --label "org.opencontainers.image.version=$version" \
    --label "org.opencontainers.image.revision=$revision" \
    --label "org.opencontainers.image.source=$source_url" \
    . >&2
  echo "$ref"
done
