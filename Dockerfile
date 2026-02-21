FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml VERSION ./
COPY rein/ rein/
COPY models/ models/
COPY schemas/ schemas/

RUN pip install --no-cache-dir ".[all,daemon]"

ENTRYPOINT ["rein"]
