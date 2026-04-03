FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY pyproject.toml ./
RUN pip install --no-cache-dir ".[all,daemon,mcp]" 2>/dev/null || \
    echo "Dependencies will install with source"

# Copy source
COPY rein/ rein/
COPY models/ models/
COPY schemas/ schemas/

# Reinstall with source present (picks up the package itself)
RUN pip install --no-cache-dir ".[all,daemon,mcp]"

# Run as non-root user
RUN useradd -r -u 1001 -m rein && chown -R rein:rein /app
USER rein

ENTRYPOINT ["rein"]
