import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TauriShellTests(unittest.TestCase):
    def test_tauri_config_loads_local_server_and_resizable_window(self):
        config = json.loads((ROOT / "src-tauri/tauri.conf.json").read_text())
        self.assertEqual(config["build"]["frontendDist"], "../app/static")
        self.assertEqual(config["app"]["windows"], [])
        self.assertIn("backend/", config["bundle"]["resources"].values())

    def test_rust_shell_owns_only_spawned_python_process(self):
        source = (ROOT / "src-tauri/src/main.rs").read_text()
        self.assertIn("pagetide-server", source)
        self.assertIn("struct PythonProcess", source)
        self.assertIn("child.kill()", source)
        self.assertIn("recv_timeout", source)

    def test_shell_does_not_add_remote_frontend_or_provider_permissions(self):
        config = json.loads((ROOT / "src-tauri/tauri.conf.json").read_text())
        self.assertIsNone(config["app"]["security"]["csp"])
        self.assertNotIn("devUrl", config["build"])


if __name__ == "__main__":
    unittest.main()
