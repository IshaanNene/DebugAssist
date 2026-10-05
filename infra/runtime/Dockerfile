# DebugAssist runtime image for one agent type: Python + git + the docker CLI (the pipeline drives sandbox
# containers through the host's Docker socket) + the agent type's PEX. Configs, marketplace, targets and
# .data come from the checkout mounted at the same path as on the host (DEBUGASSIST_ROOT).
FROM python:3.13-slim
ARG AGENT_TYPE
ARG PEX
ARG DOCKER_CLI_VERSION=28.5.1
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates curl \
 && curl -fsSL "https://download.docker.com/linux/static/stable/$(uname -m)/docker-${DOCKER_CLI_VERSION}.tgz" \
    | tar -xz -C /usr/local/bin --strip-components=1 docker/docker \
 && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/* \
 && git config --system --add safe.directory '*'
COPY ${PEX} /opt/debugassist.pex
ENV DA_AGENT_TYPE=${AGENT_TYPE} PEX_ROOT=/tmp/.pex
LABEL org.opencontainers.image.title="debugassist-runtime-${AGENT_TYPE}"
ENTRYPOINT ["python3", "/opt/debugassist.pex"]
