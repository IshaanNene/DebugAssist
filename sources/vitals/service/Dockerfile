FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml ./
COPY src ./src
RUN uv pip install --system --no-cache .
EXPOSE 8100
CMD ["uvicorn", "vitals_service.app:app", "--host", "0.0.0.0", "--port", "8100"]
