# The Habitat in one container: Django web server + reverie.py, on Python 3.9.
# Build and run with `docker compose up --build` (see the "Docker" section of the README).

# ---- build stage: compile and install the pinned dependencies ----------------
FROM python:3.9-slim AS build

# build-essential: some pinned packages (e.g. gensim 3.8.0) have no Python 3.9
# wheel and are compiled from source.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY environment/frontend_server/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# ---- runtime stage ------------------------------------------------------------
FROM python:3.9-slim

# libgomp1: OpenMP runtime used by the compiled numeric packages.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /opt/venv /opt/venv

# start.sh reads these. The venv is already built, so VENV points at it.
ENV VENV=/opt/venv \
    WEB_HOST=0.0.0.0 \
    WEB_PORT=8000 \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 1000 habitat
WORKDIR /app
COPY --chown=habitat:habitat . /app
# start.sh writes logs and PIDs here. Named volumes copy the ownership of the
# folder they cover from the image the first time they are created.
RUN mkdir -p /app/.habitat-run && chown habitat:habitat /app/.habitat-run
USER habitat

EXPOSE 8000

# start.sh starts the web server and reverie.py together and stops both on SIGTERM/Ctrl+C.
ENTRYPOINT ["./start.sh"]
CMD ["start"]
