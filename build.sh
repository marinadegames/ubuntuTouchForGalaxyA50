#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
VERSION=0.0.1
CHECK=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --version) [ "$#" -ge 2 ] || { echo 'Missing version.' >&2; exit 2; }; VERSION=$2; shift 2 ;;
        --check) CHECK=1; shift ;;
        -h|--help) echo 'Usage: ./build.sh [--version 0.0.1] [--check]'; echo 'Requires Docker with Linux ARM64 support. Output: release/ubuntu-touch-a50-VERSION.zip'; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done
export PYTHONDONTWRITEBYTECODE=1
python3 "$ROOT/scripts/build_release.py" --check --version "$VERSION"
[ "$CHECK" = 0 ] || exit 0
python3 "$ROOT/scripts/public_sources.py"
command -v docker >/dev/null 2>&1 || { echo 'Install Docker and start its Linux engine first.' >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo 'Docker is not running. Start Docker Desktop or Colima.' >&2; exit 1; }
mkdir -p "$ROOT/release"
[ ! -e "$ROOT/release/ubuntu-touch-a50-$VERSION.zip" ] || { echo 'This version already exists in release/. Move it aside before rebuilding.' >&2; exit 1; }
docker build --platform linux/arm64 -t linuxgalaxya50-builder:0.0.1 - < "$ROOT/builder/Dockerfile"
VOLUME=$(docker volume create)
cleanup() { docker volume rm "$VOLUME" >/dev/null 2>&1 || true; }
trap cleanup EXIT HUP INT TERM
docker run --rm --privileged --platform linux/arm64 \
    --mount "type=volume,source=$VOLUME,target=/build" \
    --mount "type=bind,source=$ROOT/scripts,target=/repo/scripts,readonly" \
    --mount "type=bind,source=$ROOT/patches,target=/repo/patches,readonly" \
    --mount "type=bind,source=$ROOT/installer,target=/repo/installer,readonly" \
    --mount "type=bind,source=$ROOT/release,target=/output" \
    --env "OUTPUT_UID=$(id -u)" --env "OUTPUT_GID=$(id -g)" \
    linuxgalaxya50-builder:0.0.1 --version "$VERSION"
printf 'Ready: %s/release/ubuntu-touch-a50-%s.zip\n' "$ROOT" "$VERSION"
