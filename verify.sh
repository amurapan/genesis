#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONDONTWRITEBYTECODE=1
if [[ $# -gt 1 || ( $# -eq 1 && "$1" != "--offline" ) ]]; then
  echo 'Usage: bash verify.sh [--offline]' >&2
  exit 2
fi
agent_source_hash="$(python3 -m sled.build_meta)"
core_source_hash="$(python3 -c 'from sled.metadata import source_fingerprint; print(source_fingerprint())')"
if [[ "${1:-}" == "--offline" ]]; then
  image_agent_hash="$(docker image inspect --format '{{index .Config.Labels "org.sled.agent-source"}}' sled-agent:1.0.0)"
  image_core_hash="$(docker image inspect --format '{{index .Config.Labels "org.sled.core-source"}}' sled-core:1.0.0)"
  if [[ "$image_agent_hash" != "$agent_source_hash" || "$image_core_hash" != "$core_source_hash" ]]; then
    echo 'Images differ from source. Run bash verify.sh to rebuild.' >&2
    exit 1
  fi
else
  docker build --network=none --pull=false --build-arg "AGENT_SOURCE_HASH=$agent_source_hash" -f containers/agent.Dockerfile -t sled-agent:1.0.0 .
  docker build --network=none --pull=false --build-arg "CORE_SOURCE_HASH=$core_source_hash" -f containers/core.Dockerfile -t sled-core:1.0.0 .
fi
export SLED_DOCKER_TESTS=1
python3 -m sled.testing --output artifacts/unit-tests.json
python3 -m sled evaluate --output artifacts/release
