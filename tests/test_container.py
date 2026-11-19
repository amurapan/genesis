import json
import os
import subprocess
import unittest
import uuid
from unittest.mock import patch

from sled.generation import generate
from sled.runner import DockerPolicy, docker_command, run_episode
from support import fixture


@unittest.skipUnless(os.environ.get("SLED_DOCKER_TESTS") == "1", "Run ./verify.sh for required Docker checks")
class ContainerTests(unittest.TestCase):
    def test_agent_sandbox(self):
        command = docker_command("sled-probe-" + uuid.uuid4().hex) + ["python", "-m", "sled.probe"]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=20, check=True)
        checks = json.loads(completed.stdout)
        self.assertTrue(all(checks.values()), checks)

    def test_manual_clean_and_errors_through_agent(self):
        for clean, expected in [(False, 2), (True, 0)]:
            with self.subTest(clean=clean):
                result = run_episode(fixture(clean))
                self.assertTrue(result["terminated"])
                self.assertFalse(result["truncated"])
                self.assertEqual(result["evaluation"]["tp"], expected)
                self.assertEqual(result["evaluation"]["fp"], 0)
                self.assertEqual(result["evaluation"]["f1"], 1)
                self.assertEqual(result["steps"], 5)
                self.assertTrue(all(t["reward"] == 0 for t in result["trajectories"]))

    def test_generated_episode_paginates(self):
        result = run_episode(generate(901))
        self.assertEqual(result["evaluation"]["f1"], 1)
        self.assertGreater(result["steps"], 5)
        self.assertLess(result["steps"], 100)

    def test_control_policies(self):
        episode = fixture()
        for policy in ["random", "flag_all", "oracle"]:
            result = run_episode(episode, policy)
            self.assertFalse(result["truncated"])
            self.assertEqual(result["evaluation"]["reward"], 1 if policy == "oracle" else -1)

    def test_hung_container_is_stopped(self):
        agents = []

        def sleeper(policy, image):
            agent = DockerPolicy(policy, image, command=["python", "-c", "import time; time.sleep(60)"])
            agents.append(agent)
            return agent

        with patch("sled.runner.DockerPolicy", side_effect=sleeper):
            result = run_episode(fixture(True), timeout_seconds=.5)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["submission"]["findings"], [])
        self.assertEqual(result["evaluation"]["reward"], 1)
        self.assertLess(result["elapsed_seconds"], 10)
        completed = subprocess.run(["docker", "inspect", agents[0].name], capture_output=True)
        self.assertNotEqual(completed.returncode, 0)
