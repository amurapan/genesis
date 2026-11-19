#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONDONTWRITEBYTECODE=1
agent_source_hash="$(python3 -m sled.build_meta)"
if [[ "${1:-}" == "--offline" ]]; then
  image_source_hash="$(docker image inspect --format '{{index .Config.Labels "org.sled.agent-source"}}' sled-agent:0.1.0)"
  if [[ "$image_source_hash" != "$agent_source_hash" ]]; then
    echo "Agent image differs from source. Run ./verify.sh to rebuild it." >&2
    exit 1
  fi
else
  docker build --network=none --pull=false --build-arg "AGENT_SOURCE_HASH=$agent_source_hash" -f containers/agent.Dockerfile -t sled-agent:0.1.0 .
fi
export SLED_DOCKER_TESTS=1
python3 -m unittest discover -s tests -v
python3 -m sled demo --fixture fixtures/manual_errors.json --output artifacts/manual-errors
python3 -m sled demo --fixture fixtures/manual_clean.json --output artifacts/manual-clean
python3 -m sled demo --seed 19 --output artifacts/generated
