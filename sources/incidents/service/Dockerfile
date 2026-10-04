FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN uv pip install --system --no-cache .
ENV INCIDENTS_STATE_FILE=/data/incidents.json
EXPOSE 8300
CMD ["uvicorn", "incidents_service.app:app", "--host", "0.0.0.0", "--port", "8300"]
