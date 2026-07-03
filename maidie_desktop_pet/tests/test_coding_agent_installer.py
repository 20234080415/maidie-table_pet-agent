from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core.tools.coding_agent_installer import CodingAgentInstaller


class CodingAgentInstallerTests(unittest.TestCase):
    @staticmethod
    def which(mapping):
        return lambda name: mapping.get(name)

    @patch("core.tools.coding_agent_installer.shutil.which", return_value=None)
    def test_no_package_manager_returns_no_methods(self, _which):
        self.assertEqual(CodingAgentInstaller().detect_install_methods(), {})

    def test_npm_builds_fixed_command(self):
        with patch("core.tools.coding_agent_installer.shutil.which",
                   side_effect=self.which({"npm.cmd": "C:/node/npm.cmd"})):
            command = CodingAgentInstaller().build_install_command("npm")
        self.assertEqual(command, ["C:/node/npm.cmd", "install", "-g", "opencode-ai"])

    def test_scoop_builds_fixed_command(self):
        with patch("core.tools.coding_agent_installer.shutil.which",
                   side_effect=self.which({"scoop.cmd": "C:/scoop/scoop.cmd"})):
            command = CodingAgentInstaller().build_install_command("scoop")
        self.assertEqual(command, ["C:/scoop/scoop.cmd", "install", "opencode"])

    def test_choco_builds_fixed_command(self):
        with patch("core.tools.coding_agent_installer.shutil.which",
                   side_effect=self.which({"choco.exe": "C:/choco/choco.exe"})):
            command = CodingAgentInstaller().build_install_command("choco")
        self.assertEqual(command, ["C:/choco/choco.exe", "install", "opencode", "-y"])

    @patch("core.tools.coding_agent_installer.subprocess.run")
    def test_install_uses_argument_list_without_shell_and_redetects(self, run):
        installer = CodingAgentInstaller()
        installer.detect_install_methods = Mock(return_value={"npm": "npm.cmd"})
        installer.detect_opencode = Mock(return_value="C:/bin/opencode.exe")
        run.return_value = Mock(returncode=0, stdout="installed", stderr="")

        result = installer.install_opencode("npm")

        self.assertTrue(result["success"])
        self.assertEqual(run.call_args.args[0], ["npm.cmd", "install", "-g", "opencode-ai"])
        self.assertIs(run.call_args.kwargs["shell"], False)
        self.assertEqual(run.call_args.kwargs["timeout"], 300)
        installer.detect_opencode.assert_called_once_with()

    @patch("core.tools.coding_agent_installer.subprocess.run")
    def test_installer_does_not_access_workspace_files(self, run):
        installer = CodingAgentInstaller()
        installer.detect_install_methods = Mock(return_value={"npm": "npm.cmd"})
        installer.detect_opencode = Mock(return_value="C:/bin/opencode.exe")
        run.return_value = Mock(returncode=0, stdout="", stderr="")
        with tempfile.TemporaryDirectory() as root:
            marker = Path(root) / "project.py"
            marker.write_text("unchanged", encoding="utf-8")
            installer.install_opencode("npm")
            self.assertEqual(marker.read_text(encoding="utf-8"), "unchanged")
            self.assertNotIn(str(Path(root)), repr(run.call_args))

    def test_agents_md_setup_status(self):
        installer = CodingAgentInstaller()
        installer.detect_opencode = Mock(return_value="opencode")
        with tempfile.TemporaryDirectory() as root:
            self.assertFalse(installer.detect_setup_status(root)["agents_md"])
            (Path(root) / "AGENTS.md").write_text("rules", encoding="utf-8")
            self.assertTrue(installer.detect_setup_status(root)["agents_md"])

    @patch("core.tools.coding_agent_installer.subprocess.Popen")
    def test_visible_terminal_uses_workspace_and_shell_false(self, popen):
        popen.return_value = Mock(pid=1)
        installer = CodingAgentInstaller(); installer.detect_opencode = Mock(return_value="opencode")
        with tempfile.TemporaryDirectory() as root:
            result = installer.open_visible_terminal(root)
        self.assertTrue(result["ok"])
        self.assertIs(popen.call_args.kwargs["shell"], False)
        self.assertEqual(Path(popen.call_args.kwargs["cwd"]), Path(root).resolve())


if __name__ == "__main__":
    unittest.main()
