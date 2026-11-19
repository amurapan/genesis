"""Trusted Docker launcher. Agent stdout is only ever interpreted as actions."""

import subprocess
import time
import uuid
from pathlib import Path

from .environment import AuditEnv
from .oracle import oracle_submission
from .protocol import ProtocolError, Wire
from .validation import verify_episode

AGENT_IMAGE = "sled-agent:1.0.0"


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
        self.cgroup = None
        self.peak_memory_bytes = 0

    def sample_memory(self):
        try:
            if self.cgroup is None:
                pid=int(subprocess.check_output(['docker','inspect','--format','{{.State.Pid}}',self.name],stderr=subprocess.DEVNULL,text=True,timeout=2).strip())
                entries=Path(f'/proc/{pid}/cgroup').read_text().splitlines()
                suffix=next(x.split('::',1)[1] for x in entries if x.startswith('0::'))
                self.cgroup=Path('/sys/fs/cgroup')/suffix.lstrip('/')
            self.peak_memory_bytes=max(self.peak_memory_bytes,int((self.cgroup/'memory.peak').read_text()))
        except (OSError,ValueError,StopIteration,subprocess.SubprocessError):
            pass

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


def run_episode(episode, policy="reconciler", mode="evaluation", image=AGENT_IMAGE, timeout_seconds=60, policy_command=None):
    validation = verify_episode(episode)
    started = time.monotonic()
    with AuditEnv(mode=mode, episode_factory=lambda seed, config: episode, timeout_seconds=timeout_seconds) as env:
        observation, info = env.reset(0)
        agent = None
        try:
            if policy == "oracle":
                env.step({"action": "submit", "findings": oracle_submission(episode["truth"])})
            else:
                agent = DockerPolicy(policy, image, command=policy_command) if policy_command else DockerPolicy(policy, image)
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
                        agent.sample_memory()
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
            def peak(pid):
                try:
                    for line in Path(f'/proc/{pid}/status').read_text().splitlines():
                        if line.startswith('VmHWM:'): return int(line.split()[1])*1024
                except OSError: pass
                return 0
            import os
            if agent is not None: agent.sample_memory()
            resources=dict(harness_peak_rss_bytes=peak(os.getpid()),evaluator_peak_rss_bytes=peak(env.evaluator.process.pid),
                           agent_cgroup_peak_bytes=agent.peak_memory_bytes if agent else 0,
                           agent_memory_limit_bytes=256*1024*1024,agent_cpu_limit=1,
                           method='Linux VmHWM plus agent cgroup v2 memory.peak; shared Docker daemon excluded')
            resources['observed_peak_upper_bound_bytes']=sum(resources[k] for k in ['harness_peak_rss_bytes','evaluator_peak_rss_bytes','agent_cgroup_peak_bytes'])
            if agent is not None:
                agent.close()
        return {"episode_id": episode["public"]["manifest"]["episode_id"], "policy": policy,
                "mode": mode, "validation": validation, "evaluation": env.evaluation_result,
                'resources':resources,
                "submission": env.final_submission, "steps": env.steps,
                "elapsed_seconds": round(time.monotonic()-started, 6),
                "terminated": env.terminated, "truncated": env.truncated,
                "trajectories": env.trajectories}
