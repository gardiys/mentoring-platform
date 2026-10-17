import json
import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path


class InterviewMediaDeploymentTests(unittest.TestCase):
    def test_transcription_worker_shares_disk_and_limits_with_backend(self):
        if not shutil.which("docker"):
            self.skipTest("Docker Compose is required to render deployment configuration")
        root = Path(__file__).resolve().parents[1]
        directory = "/var/lib/mentoring/interview-legacy-transcode"
        overrides = {
            "INTERVIEW_LEGACY_TRANSCODE_MAX_CONCURRENCY": "2",
            "INTERVIEW_LEGACY_TRANSCODE_MIN_FREE_BYTES": "3221225472",
            "INTERVIEW_LEGACY_TRANSCODE_MAX_RESERVED_BYTES": "4294967296",
            "INTERVIEW_LEGACY_TRANSCODE_CLEANUP_AGE_SECONDS": "43200",
            "INTERVIEW_LEGACY_TRANSCODE_TIMEOUT_SECONDS": "1200",
        }
        for filename in ("docker-compose.yml", "docker-compose.prod.yml"):
            config_path = root / "infra" / filename
            # Supply placeholders for required settings without loading local secrets.
            env = {"PATH": os.environ["PATH"]}
            env.update(
                (name, "test-value")
                for name in re.findall(r"\$\{([A-Z_0-9]+):\?", config_path.read_text())
            )
            for custom_limits in (False, True):
                with self.subTest(compose=filename, custom_limits=custom_limits):
                    result = subprocess.run(
                        [
                            "docker",
                            "compose",
                            "--env-file",
                            os.devnull,
                            "-f",
                            str(config_path),
                            "config",
                            "--format",
                            "json",
                        ],
                        env=env | (overrides if custom_limits else {}),
                        capture_output=True,
                        text=True,
                        timeout=20,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    config = json.loads(result.stdout)
                    services = config["services"]
                    legacy_settings = {
                        key: value
                        for key, value in services["backend"]["environment"].items()
                        if key.startswith("INTERVIEW_LEGACY_TRANSCODE_")
                    }
                    self.assertEqual(
                        legacy_settings["INTERVIEW_LEGACY_TRANSCODE_DIRECTORY"], directory
                    )
                    if custom_limits:
                        for key, value in overrides.items():
                            self.assertEqual(legacy_settings[key], value)
                    for name in ("backend", "intelligence-worker"):
                        service = services[name]
                        for key, value in legacy_settings.items():
                            self.assertEqual(service["environment"][key], value)
                        mounts = [
                            mount for mount in service["volumes"] if mount["target"] == directory
                        ]
                        self.assertEqual(len(mounts), 1)
                        self.assertEqual(mounts[0]["source"], "interview_legacy_transcode")
                        self.assertEqual(mounts[0]["type"], "volume")
                        self.assertFalse(mounts[0].get("read_only", False))
                    for name in ("intelligence-ai-worker", "intelligence-maintenance-worker"):
                        self.assertFalse(
                            any(
                                mount.get("source") == "interview_legacy_transcode"
                                for mount in services[name].get("volumes", [])
                            )
                        )


if __name__ == "__main__":
    unittest.main()
