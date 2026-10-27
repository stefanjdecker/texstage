# SPDX-FileCopyrightText: 2026 Stefan Decker
# SPDX-License-Identifier: Apache-2.0
# The texstage server as a container (docs/architecture/design.md, section 8). Built from the repository
# root by docker-compose.yml next to this file; on its own:
#
#   docker build -f deploy/Dockerfile -t texstage .
#   docker run -p 8470:8470 -v texstage-data:/data texstage
#
# Bundles arrive with `texstage publish` and live in the volume (/data/bundles), with the
# games' database and the presenter key (/data/presenter-key).
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
# what the package is built from (pyproject.toml): the server needs none of the LaTeX files,
# but the package includes them
COPY pyproject.toml README.md LICENSE NOTICE ./
COPY latex/texstage.sty latex/texquiz.sty latex/texvideo.sty latex/texactivity.sty ./latex/
COPY src ./src
COPY requirements ./requirements
RUN pip install --require-hashes --only-binary=:all: -r requirements/runtime.txt -r requirements/build.txt \
 && pip install --no-deps --no-build-isolation . \
 && useradd --system --home-dir /data texstage \
 && mkdir -p /data/bundles && chown -R texstage /data

USER texstage
VOLUME /data
EXPOSE 8470
HEALTHCHECK --interval=30s --timeout=5s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8470/api/status', timeout=3)"
CMD ["texstage", "serve", "/data/bundles", "--data", "/data", "--host", "0.0.0.0", "--port", "8470"]
