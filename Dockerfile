
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV UV_LINK_MODE=copy

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       git nodejs npm ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY . .

# Install the Python project and its locked dependencies.
RUN uv sync --frozen --extra web

# Fetch the Pokémon data files used to build the database.
RUN git clone --filter=blob:none --no-checkout \
    https://github.com/projectpokemon/champout.git /app/champout \
    && cd /app/champout \
    && git sparse-checkout init --cone \
    && git sparse-checkout set parse \
    && git checkout main

# Install the pinned calculator package.
RUN npm ci --omit=dev

# Generate the DuckDB database from the Pokémon data.
RUN uv run teambuilder build-db

EXPOSE 10000

CMD ["sh", "-c", "uv run gunicorn --workers 2 --threads 4 --timeout 120 --bind 0.0.0.0:${PORT:-10000} teambuilder.web_server:app"]
