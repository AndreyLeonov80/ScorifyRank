from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "preflight_docker_daemon.py"


def load_preflight_module():
    spec = importlib.util.spec_from_file_location("preflight_docker_daemon", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class DockerPreflightRuntimeTest(unittest.TestCase):
    def test_local_runtime_checks_validate_ports_data_dirs_and_old_containers(self) -> None:
        preflight = load_preflight_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            data_root = Path(tmpdir)
            for name in preflight.DEFAULT_DATA_SUBDIRS:
                (data_root / name).mkdir(parents=True)
            args = SimpleNamespace(
                check_local_runtime=True,
                local_bind="127.0.0.1",
                local_ports="65530",
                data_root=str(data_root),
            )
            docker_ps = preflight.CheckResult(
                "docker_ps",
                ["docker", "ps"],
                True,
                0,
                False,
                "x-files-backfront-new-back\timage\tUp",
            )

            checks = preflight.run_local_runtime_checks(args, docker_ps=docker_ps)

        by_name = {check.name: check for check in checks}
        self.assertTrue(by_name["local_ports_free"].ok)
        self.assertTrue(by_name["client_data_dirs_exist"].ok)
        self.assertTrue(by_name["old_container_names_absent"].ok)

    def test_local_runtime_checks_report_missing_dirs_and_old_containers(self) -> None:
        preflight = load_preflight_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            args = SimpleNamespace(
                check_local_runtime=True,
                local_bind="127.0.0.1",
                local_ports="65530",
                data_root=tmpdir,
            )
            docker_ps = preflight.CheckResult(
                "docker_ps",
                ["docker", "ps"],
                True,
                0,
                False,
                "x-files-client-backfront\told\tExited\nx-files-root-web\told\tExited",
            )

            checks = preflight.run_local_runtime_checks(args, docker_ps=docker_ps)

        by_name = {check.name: check for check in checks}
        self.assertFalse(by_name["client_data_dirs_exist"].ok)
        self.assertIn("state", by_name["client_data_dirs_exist"].output)
        self.assertFalse(by_name["old_container_names_absent"].ok)
        self.assertIn("x-files-root-web", by_name["old_container_names_absent"].output)


if __name__ == "__main__":
    unittest.main()
