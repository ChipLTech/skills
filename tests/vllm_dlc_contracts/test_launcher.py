import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "scripts" / "launch-vllm-dlc-server.py"


def load_launcher():
    spec = importlib.util.spec_from_file_location("vllm_dlc_launcher", LAUNCHER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LauncherTests(unittest.TestCase):
    def test_child_environment_propagates_only_allowlisted_dlc_controls(self) -> None:
        launcher = load_launcher()
        captured = {}

        class Child:
            returncode = 0

            def poll(self):
                return 0

        def popen(command, env):
            captured["command"] = command
            captured["env"] = env
            return Child()

        def find_spec(module):
            root = "/work/vllm-dlc" if module.startswith("vllm_dlc") else "/work/vllm"
            return mock.Mock(origin=f"{root}/package/module.py")

        with tempfile.TemporaryDirectory() as directory:
            argv = [
                str(LAUNCHER),
                "--ready-file", str(Path(directory) / "ready"),
                "--host", "127.0.0.1",
                "--port", "18080",
                "--model", "/model",
                "--tokenizer", "/tokenizer",
                "--served-model-name", "model",
                "--tensor-parallel-size", "2",
                "--pipeline-parallel-size", "1",
                "--dtype", "bfloat16",
                "--quantization", "none",
                "--max-model-len", "8192",
                "--max-num-batched-tokens", "1024",
                "--enforce-eager",
                "--expected-vllm-root", "/work/vllm",
                "--expected-vllm-dlc-root", "/work/vllm-dlc",
            ]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(launcher.importlib.util, "find_spec", find_spec),
                mock.patch.object(launcher.subprocess, "Popen", popen),
                mock.patch.dict(
                    os.environ,
                    {
                        "DLC_VISIBLE_DEVICES": "2,3",
                        "DLC_SYN_COPY_ASYNC": "O2",
                        "CHIPLTECH_VISIBLE_DEVICES": "4,5",
                        "UNRELATED_SECRET": "secret",
                    },
                    clear=True,
                ),
            ):
                self.assertEqual(launcher.main(), 0)

        self.assertEqual(
            captured["env"],
            {
                "PATH": "/usr/bin:/bin",
                "PYTHONDONTWRITEBYTECODE": "1",
                "DLC_VISIBLE_DEVICES": "2,3",
                "DLC_SYN_COPY_ASYNC": "O2",
            },
        )


if __name__ == "__main__":
    unittest.main()
