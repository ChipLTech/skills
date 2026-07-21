import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "engineering" / "dlc-env-setup" / "scripts" / "runtime-smoke.sh"


class RuntimeSmokeTests(unittest.TestCase):
    def run_script(self, *arguments: str, environment=None):
        env = os.environ.copy()
        if environment:
            env.update(environment)
        return subprocess.run(
            [str(SCRIPT), *arguments],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )

    def test_help_documents_execution_and_import_gates(self):
        result = self.run_script("--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--require-device-execution", result.stdout)
        self.assertIn("--require-vllm", result.stdout)
        self.assertIn("--require-vllm-dlc", result.stdout)
        self.assertIn("--skip-vllm-dlc", result.stdout)
        self.assertIn("DLC_PACKAGE_SMOKE_TIMEOUT", result.stdout)
        self.assertIn("DLC_RUNTIME_SMOKE_TIMEOUT", result.stdout)

    def test_rejects_invalid_arguments_before_running_python(self):
        for arguments in (
            ("--unknown",),
            ("--device-index",),
            ("--device-index", "invalid"),
            ("/tmp", "/tmp"),
            ("--require-vllm-dlc", "--skip-vllm-dlc"),
        ):
            with self.subTest(arguments=arguments):
                result = self.run_script(*arguments)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_layered_execution_branch_runs_in_a_second_python_process(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            root = Path(directory)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            calls = root / "calls"
            self.write_fake_runtime(root)
            env = {
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "PYTHONPATH": str(root),
                "MOCK_CALLS": str(calls),
            }

            result = self.run_script(
                str(root),
                "--require-vllm",
                "--skip-vllm-dlc",
                "--require-device-execution",
                "--device-index",
                "3",
                environment=env,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("runtime_execution_device_index 3", result.stdout)
            self.assertIn("LAYERED_RUNTIME_EXECUTION_PASS", result.stdout)
            self.assertEqual(
                calls.read_text(encoding="utf-8").splitlines(),
                [
                    "device_count",
                    "device_properties:3",
                    "set_device:3",
                    "mem_get_info:3",
                    "empty:dlc:3",
                    "to:dlc:3",
                    "add:dlc:3",
                    "synchronize:3",
                    "cpu:dlc:3",
                ],
            )

    def test_execution_timeout_is_enforced(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            root = Path(directory)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            self.write_fake_runtime(root)
            result = self.run_script(
                str(root),
                "--skip-vllm-dlc",
                "--require-device-execution",
                environment={
                    "PATH": f"{fake_bin}:{os.environ['PATH']}",
                    "PYTHONPATH": str(root),
                    "MOCK_CALLS": str(root / "calls"),
                    "MOCK_DEVICE_COUNT_SLEEP": "5",
                    "DLC_RUNTIME_SMOKE_TIMEOUT": "1",
                },
            )

        self.assertEqual(result.returncode, 124, result.stdout + result.stderr)

    def test_package_timeout_is_enforced(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            fake_bin = Path(directory) / "bin"
            fake_bin.mkdir()
            python = fake_bin / "python3"
            python.write_text(
                "#!/usr/bin/env bash\nsleep 5\n",
                encoding="utf-8",
            )
            python.chmod(0o755)
            result = self.run_script(
                directory,
                environment={
                    "PATH": f"{fake_bin}:{os.environ['PATH']}",
                    "DLC_PACKAGE_SMOKE_TIMEOUT": "1",
                },
            )

        self.assertEqual(result.returncode, 124, result.stdout + result.stderr)

    def test_rejects_invalid_execution_timeout(self):
        with tempfile.TemporaryDirectory(dir="/tmp/kilo") as directory:
            fake_bin = Path(directory) / "bin"
            fake_bin.mkdir()
            python = fake_bin / "python3"
            python.write_text("#!/usr/bin/env bash\ncat >/dev/null\n", encoding="utf-8")
            python.chmod(0o755)
            result = self.run_script(
                directory,
                "--require-device-execution",
                environment={
                    "PATH": f"{fake_bin}:{os.environ['PATH']}",
                    "DLC_RUNTIME_SMOKE_TIMEOUT": "0",
                },
            )

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("must be a positive integer", result.stderr)

    @staticmethod
    def write_fake_runtime(root: Path):
        fake_bin = root / "bin"
        python = fake_bin / "python3"
        python.write_text(
            "#!/usr/bin/env bash\nexec /usr/bin/python3 \"$@\"\n",
            encoding="utf-8",
        )
        python.chmod(0o755)

        (root / "numpy.py").write_text("__version__ = '1.26.4'\n", encoding="utf-8")
        (root / "vllm.py").write_text("__version__ = 'test'\n", encoding="utf-8")
        dist_info = root / "vllm-1.0.dist-info"
        dist_info.mkdir()
        (dist_info / "METADATA").write_text(
            "Metadata-Version: 2.1\nName: vllm\nVersion: 1.0\n",
            encoding="utf-8",
        )
        (dist_info / "RECORD").write_text("", encoding="utf-8")

        (root / "torch.py").write_text(
            textwrap.dedent(
                """
                import os
                import time

                __version__ = "2.5.0"
                float32 = "float32"


                def log(value):
                    with open(os.environ["MOCK_CALLS"], "a", encoding="utf-8") as stream:
                        stream.write(value + "\\n")


                class Tensor:
                    def __init__(self, value, device="cpu"):
                        self.value = value
                        self.device = device
                        self.shape = (1,)
                        self.dtype = float32

                    def numpy(self):
                        return [self.value]

                    def to(self, device):
                        log(f"to:{device}")
                        return Tensor(self.value, device)

                    def __add__(self, value):
                        log(f"add:{self.device}")
                        return Tensor(self.value + value, self.device)

                    def cpu(self):
                        log(f"cpu:{self.device}")
                        return Tensor(self.value)

                    def item(self):
                        return self.value


                class Backend:
                    @staticmethod
                    def is_available():
                        return True


                class Backends:
                    dlc = Backend()


                class Dlc:
                    current_device = 0

                    @staticmethod
                    def device_count():
                        log("device_count")
                        time.sleep(float(os.environ.get("MOCK_DEVICE_COUNT_SLEEP", "0")))
                        return 4

                    @staticmethod
                    def get_device_properties(index):
                        log(f"device_properties:{index}")
                        return object()

                    @classmethod
                    def set_device(cls, index):
                        cls.current_device = index
                        log(f"set_device:{index}")

                    @classmethod
                    def mem_get_info(cls):
                        log(f"mem_get_info:{cls.current_device}")
                        return (1, 1)

                    @classmethod
                    def synchronize(cls):
                        log(f"synchronize:{cls.current_device}")


                backends = Backends()
                dlc = Dlc()


                def tensor(values, dtype=None):
                    return Tensor(values[0])


                def empty(size, device):
                    log(f"empty:{device}")
                    return Tensor(0, device)


                def ones(size, dtype=None):
                    return Tensor(1)
                """
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
