# The Linux build environment, pinned so a rebuild bundles the same system
# libraries byte for byte. PyInstaller copies OpenSSL, X11/xcb, glib and the
# like from the build machine into the runtime layer; on a GitHub runner they
# moved with every image update and changed the runtime id with no change of
# ours (libssl.so.3, v0.2.2 -> v0.2.3), costing every Linux user a 1.7 GB
# full update. Three pins:
#   * the base image digest
#   * the apt archive: snapshot.ubuntu.com at SNAPSHOT
#   * Python: the exact actions/setup-python 3.12.10 build, checked by SHA-256
# Moving any of them is a planned runtime change (docs/RELEASING.md).
# Used by .github/workflows/release.yml and packaging/ci/local-build.sh.
FROM ubuntu:22.04@sha256:5ec03bb3441e8b0bf3b4f9cd4629a1ae763010dc3035bb8da3ae6cf026486401

ARG SNAPSHOT=20261005T000000Z
ARG PYTHON_URL=https://github.com/actions/python-versions/releases/download/3.12.10-14343898437/python-3.12.10-linux-22.04-x64.tar.gz
ARG PYTHON_SHA256=f8e0109b3eeb6cb0a246725d16595793f5f3c882df77bd4acf195fbab64819ac
ENV DEBIAN_FRONTEND=noninteractive

# The snapshot service is https-only; the base image has no CA bundle yet.
# ca-certificates is only used to reach it -- nothing of it is bundled.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN printf '%s\n' \
      "deb https://snapshot.ubuntu.com/ubuntu/${SNAPSHOT} jammy main universe" \
      "deb https://snapshot.ubuntu.com/ubuntu/${SNAPSHOT} jammy-updates main universe" \
      "deb https://snapshot.ubuntu.com/ubuntu/${SNAPSHOT} jammy-security main universe" \
      > /etc/apt/sources.list \
    && apt-get -o Acquire::Check-Valid-Until=false update \
    && apt-get install -y --no-install-recommends \
         build-essential git curl xvfb xauth dpkg-dev \
         libssl3 libsqlite3-0 libbz2-1.0 liblzma5 libffi8 libreadline8 libncursesw6 \
         libuuid1 libexpat1 zlib1g libgdbm6 libgdbm-compat4 \
         libfontconfig1 libxcomposite1 \
    && rm -rf /var/lib/apt/lists/*

# Same layout and path setup-python uses, so nothing about the interpreter
# differs from the runner builds before this image.
ENV PYTHON_ROOT=/opt/hostedtoolcache/Python/3.12.10/x64
RUN curl -fsSL "$PYTHON_URL" -o /tmp/python.tgz \
    && echo "${PYTHON_SHA256}  /tmp/python.tgz" | sha256sum -c - \
    && mkdir -p "$PYTHON_ROOT" && tar xzf /tmp/python.tgz -C "$PYTHON_ROOT" \
    && rm /tmp/python.tgz
ENV PATH=/opt/hostedtoolcache/Python/3.12.10/x64/bin:$PATH \
    LD_LIBRARY_PATH=/opt/hostedtoolcache/Python/3.12.10/x64/lib

# Qt's xcb plugin chain: the deb's Depends plus the libraries it bundles.
# (libfontconfig1 / libxcomposite1 above are Qt plugin dependencies the
# GitHub runner happened to carry; without them PyInstaller cannot resolve
# them and Qt aborts at startup -- found by diffing this image's bundle
# against the v0.2.3 runner build's runtime manifest.)
COPY packaging/deb.py packaging/layers.py /tmp/pkg/
RUN deps="$(python3.12 -c "import sys; sys.path.insert(0, '/tmp/pkg'); import deb; print(', '.join(deb.RUNTIME_DEPENDS + deb.BUNDLED_LIBS))")" \
    && apt-get -o Acquire::Check-Valid-Until=false update \
    && apt-get satisfy -y --no-install-recommends "$deps" \
    && rm -rf /var/lib/apt/lists/* /tmp/pkg
