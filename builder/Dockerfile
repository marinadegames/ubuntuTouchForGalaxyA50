FROM debian:trixie-slim@sha256:f6b08b09a05725f9431502d3b5714f5c4576e82c1a84fa1debe0c24a7e0c3ec4
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ca-certificates curl git python3 gcc libc6-dev libext2fs-dev libarchive-dev \
    e2fsprogs util-linux mount xz-utils zstd patch dpkg-dev file \
    && rm -rf /var/lib/apt/lists/*
ENV LC_ALL=C.UTF-8 LANG=C.UTF-8 TZ=UTC HOME=/tmp/a50-builder-home \
    SOURCE_DATE_EPOCH=1793318400 PYTHONDONTWRITEBYTECODE=1
WORKDIR /repo
ENTRYPOINT ["python3", "/repo/scripts/build_release.py", "--inside"]
