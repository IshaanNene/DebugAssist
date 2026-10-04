# Built from the DebugAssist repo root (needs packages/core for redaction).
FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY packages/core /src/packages/core
COPY sources/bugdrop/service /src/sources/bugdrop/service
RUN uv pip install --system --no-cache --no-sources /src/packages/core /src/sources/bugdrop/service
EXPOSE 8200
CMD ["uvicorn", "bugdrop_service.app:app", "--host", "0.0.0.0", "--port", "8200"]
