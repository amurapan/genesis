"""Trusted Docker launcher. Agent stdout is only ever interpreted as actions."""

import subprocess
import time
import uuid

from .environment import AuditEnv
from .oracle import oracle_submission
from .protocol import ProtocolError, Wire
from .validation import verify_episode

AGENT_IMAGE = "sled-agent:0.1.0"


def docker_command(name, image=AGENT_IMAGE):
    return ["docker", "run", "--rm", "--name", name, "-i", "--network=none", "--read-only",
            "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit=64",
            "--memory=256m", "--cpus=1", "--user=65532:65532",
            "--tmpfs=/tmp:rw,noexec,nosuid,size=16m", image]


class DockerPolicy:
    def __init__(self, policy, image=AGENT_IMAGE, command=None):
        self.name = "sled-agent-" + uuid.uuid4().hex
        program = command or ["python", "-m", "sled.agent", "--policy", policy]
        self.process = subprocess.Popen(docker_command(self.name, image) + program,
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.wire = Wire(self.process.stdout, self.process.stdin)

    def close(self):
        # Killing just the Docker client can leave the container alive.
        subprocess.run(["docker", "rm", "-f", self.name], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=10, check=False)
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        self.process.stdin.close()
        self.process.stdout.close()


def run_episode(episode, policy="reconciler", mode="evaluation", image=AGENT_IMAGE, timeout_seconds=60):
    validation = verify_episode(episode)
    started = time.monotonic()
    with AuditEnv(mode=mode, episode_factory=lambda seed, config: episode, timeout_seconds=timeout_seconds) as env:
        observation, info = env.reset(0)
        agent = None
        try:
            if policy == "oracle":
                env.step({"action": "submit", "findings": oracle_submission(episode["truth"])})
            else:
                agent = DockerPolicy(policy, image)
                message = {"observation": observation, "reward": 0.0, "terminated": False, "truncated": False, "info": info}
                while True:
                    remaining = env.deadline - time.monotonic()
                    if remaining <= 0:
                        env.truncate()
                        break
                    try:
                        agent.wire.send(message, timeout=remaining)
                        if message["terminated"] or message["truncated"]:
                            break
                        action = agent.wire.receive(timeout=max(0.001, env.deadline-time.monotonic()))
                    except ProtocolError:
                        action = None
                    except TimeoutError:
                        env.truncate()
                        break
                    except (EOFError, BrokenPipeError):
                        if not (env.terminated or env.truncated):
                            env.truncate("AGENT_EXIT")
                        break
                    obs, reward, terminated, truncated, info = env.step(action)
                    message = {"observation": obs, "reward": reward, "terminated": terminated, "truncated": truncated, "info": info}
        finally:
            if agent is not None:
                agent.close()
        return {"episode_id": episode["public"]["manifest"]["episode_id"], "policy": policy,
                "mode": mode, "validation": validation, "evaluation": env.evaluation_result,
                "submission": env.final_submission, "steps": env.steps,
                "elapsed_seconds": round(time.monotonic()-started, 6),
                "terminated": env.terminated, "truncated": env.truncated,
                "trajectories": env.trajectories}
