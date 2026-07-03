from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PackagingConfigurationTests(unittest.TestCase):
    def test_default_package_config_contains_no_keys(self):
        config = json.loads(
            (ROOT / "packaging" / "config.json").read_text(encoding="utf-8")
        )
        self.assertEqual(config["ai"]["api_key"], "")
        self.assertEqual(config["network"]["search_api_key"], "")
        self.assertIn("fence", config)
        self.assertIn("vision", config)

    def test_spec_collects_extensible_data_directories(self):
        spec = (ROOT / "maidie.spec").read_text(encoding="utf-8")
        self.assertIn('project_root / "assets"', spec)
        self.assertIn('project_root / "docs"', spec)
        self.assertIn('collect_submodules("core.plugins")', spec)
        self.assertIn('contents_directory="."', spec)

    def test_build_script_uses_active_python_and_spec(self):
        script = (ROOT / "build_exe.bat").read_text(encoding="utf-8")
        spec = (ROOT / "maidie.spec").read_text(encoding="utf-8")
        self.assertIn("python -m PyInstaller", script)
        self.assertIn("maidie.spec", script)
        self.assertNotIn(".venv\\Scripts\\python", script)
        self.assertTrue((ROOT / "packaging" / "maidie.ico").is_file())
        self.assertIn('icon=str(project_root / "packaging" / "maidie.ico")', spec)

    def test_installer_preserves_user_config_and_packages_full_build(self):
        script = (ROOT / "build_installer.bat").read_text(encoding="utf-8")
        installer = (ROOT / "packaging" / "maidie.iss").read_text(encoding="utf-8")
        self.assertIn("INNO_SETUP_COMPILER", script)
        self.assertIn("call build_exe.bat", script)
        self.assertNotIn('if not exist "dist\\Maidie\\Maidie.exe"', script)
        self.assertIn('DefaultDirName={localappdata}\\Programs\\Maidie', installer)
        self.assertIn("SetupIconFile=maidie.ico", installer)
        self.assertIn("recursesubdirs", installer)
        self.assertIn('Excludes: "config\\config.json,logs\\*,memory\\*"', installer)
        self.assertIn("onlyifdoesntexist uninsneveruninstall", installer)
        self.assertIn("PrivilegesRequired=lowest", installer)


if __name__ == "__main__":
    unittest.main()
