FROM python:3.11-slim@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce
ARG CORE_SOURCE_HASH
LABEL org.sled.core-source=$CORE_SOURCE_HASH
ENV PYTHONPATH=/app/src PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY src /app/src
COPY fixtures /app/fixtures
COPY tests /app/tests
COPY schemas /app/schemas
COPY configs /app/configs
COPY planning /app/planning
USER 65532:65532
CMD ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]
