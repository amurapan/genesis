FROM python:3.11-slim@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce
ARG AGENT_SOURCE_HASH
LABEL org.sled.agent-source=$AGENT_SOURCE_HASH
ENV PYTHONPATH=/app/src PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY src/sled/__init__.py src/sled/agent.py src/sled/policies.py src/sled/policy_v2.py src/sled/protocol.py src/sled/probe.py /app/src/sled/
USER 65532:65532
CMD ["python", "-m", "sled.agent"]
