from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from core.tools.file_permissions import (
    FileAuthorization,
    FilePermissionError,
    FilePermissionPolicy,
)


class FilePermissionPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.base = Path(self._temporary.name)
        self.primary = self.base / "primary"
        self.secondary = self.base / "secondary"
        self.outside = self.base / "outside"
        for path in (self.primary, self.secondary, self.outside):
            path.mkdir()
        self.policy = FilePermissionPolicy({
            "root": str(self.primary),
            "workspaces": [
                {"id": "secondary", "name": "Secondary", "path": str(self.secondary)},
            ],
            "allow_home_read_only": True,
        })

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def test_paths_inside_multiple_workspaces_are_allowed(self) -> None:
        first = self.primary / "one.txt"
        second = self.secondary / "two.txt"
        first.write_text("one", encoding="utf-8")
        second.write_text("two", encoding="utf-8")

        first_plan = self.policy.build_plan("read_text_file", source=str(first))
        second_plan = self.policy.build_plan("read_text_file", source=str(second))

        self.assertEqual(first_plan.risk, "low")
        self.assertEqual(second_plan.risk, "low")
        self.assertFalse(first_plan.requires_confirmation)
        self.assertEqual(second_plan.workspace_names, ("Secondary",))

    def test_relative_paths_always_use_primary_workspace_root(self) -> None:
        plan = self.policy.build_plan(
            "create_text_file", destination="relative.txt", content="data",
        )

        self.assertEqual(Path(plan.resolved_destination), self.primary / "relative.txt")

    def test_relative_parent_escape_is_rejected(self) -> None:
        with self.assertRaisesRegex(FilePermissionError, "path_escape"):
            self.policy.build_plan("read_text_file", source="../outside/file.txt")

    def test_outside_workspace_write_requires_high_risk_single_authorization(self) -> None:
        plan = self.policy.build_plan(
            "create_text_file",
            destination=str(self.outside / "created.txt"),
            content="safe",
        )

        self.assertEqual(plan.risk, "high")
        self.assertTrue(plan.requires_confirmation)
        self.assertIn("outside_configured_workspace", plan.risk_reasons)

    def test_home_read_only_access_is_low_risk_but_write_still_needs_high_risk(self) -> None:
        source = self.outside / "readable.txt"
        source.write_text("home data", encoding="utf-8")

        read_plan = self.policy.build_plan("read_text_file", source=str(source))
        write_plan = self.policy.build_plan(
            "create_text_file", destination=str(self.outside / "write.txt"), content="x",
        )

        self.assertEqual(read_plan.risk, "low")
        self.assertFalse(read_plan.requires_confirmation)
        self.assertEqual(write_plan.risk, "high")

    def test_system_appdata_maidie_state_ssh_and_drive_root_are_forbidden(self) -> None:
        blocked = [
            str(Path(os.environ.get("WINDIR", r"C:\Windows"))),
            str(Path.home() / "AppData"),
            str(Path.cwd() / "memory"),
            str(Path.home() / ".ssh" / "new.txt"),
            str(Path(Path.cwd().anchor)),
        ]
        for path in blocked:
            with self.subTest(path=path):
                operation = "create_text_file" if path.endswith("new.txt") else "stat_file"
                arguments = {"destination": path, "content": "x"} if operation.startswith("create") else {"source": path}
                with self.assertRaises(FilePermissionError):
                    self.policy.build_plan(operation, **arguments)

    def test_delete_rejects_system_and_maidie_protected_paths(self) -> None:
        app_root = self.base / "maidie-app"
        protected_file = app_root / "config" / "config.json"
        protected_file.parent.mkdir(parents=True)
        protected_file.write_text("{}", encoding="utf-8")
        policy = FilePermissionPolicy(
            {"root": str(self.base), "allow_home_read_only": False},
            app_root=app_root,
        )

        with self.assertRaisesRegex(FilePermissionError, "protected_path"):
            policy.build_plan("delete_file", source=str(protected_file))
        with self.assertRaisesRegex(FilePermissionError, "protected_path"):
            policy.build_plan("delete_file", source=os.environ.get("WINDIR", r"C:\Windows"))

    def test_text_mutation_still_rejects_reparse_points(self) -> None:
        source = self.primary / "notes.txt"
        source.write_text("before", encoding="utf-8")

        with patch.object(self.policy, "_is_reparse_point", side_effect=lambda path: path == source):
            with self.assertRaisesRegex(FilePermissionError, "reparse_point"):
                self.policy.build_plan("append_file", source=str(source), content="after")

    def test_symlink_or_reparse_component_is_rejected(self) -> None:
        source = self.primary / "source.txt"
        source.write_text("data", encoding="utf-8")
        with patch.object(self.policy, "_is_reparse_point", side_effect=lambda path: path == source):
            with self.assertRaisesRegex(FilePermissionError, "reparse_point"):
                self.policy.build_plan("read_text_file", source=str(source))

    def test_real_symlink_escape_is_rejected_when_supported(self) -> None:
        target = self.outside / "secret.txt"
        target.write_text("secret", encoding="utf-8")
        link = self.primary / "link.txt"
        try:
            os.symlink(target, link)
        except OSError as exc:
            self.skipTest(f"symlink unavailable: {exc}")
        with self.assertRaisesRegex(FilePermissionError, "reparse_point"):
            self.policy.build_plan("read_text_file", source=str(link))

    @unittest.skipUnless(os.name == "nt", "junctions are Windows-specific")
    def test_real_junction_escape_is_rejected(self) -> None:
        target = self.outside / "junction-target"
        target.mkdir()
        (target / "secret.txt").write_text("secret", encoding="utf-8")
        junction = self.primary / "junction"
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(junction), str(target)],
            capture_output=True, text=True, shell=False,
        )
        if completed.returncode != 0:
            self.skipTest(f"junction unavailable: {completed.stderr.strip()}")
        try:
            with self.assertRaisesRegex(FilePermissionError, "reparse_point"):
                self.policy.build_plan("read_text_file", source=str(junction / "secret.txt"))
        finally:
            os.rmdir(junction)

    def test_device_unc_ads_and_reserved_names_are_rejected(self) -> None:
        invalid = [
            r"\\.\PhysicalDrive0",
            r"\\server\share\file.txt",
            str(self.primary / "file.txt") + ":secret",
            str(self.primary / "CON.txt"),
        ]
        for path in invalid:
            with self.subTest(path=path):
                with self.assertRaises(FilePermissionError):
                    self.policy.build_plan("stat_file", source=path)

    def test_authorization_is_bound_to_fingerprint(self) -> None:
        destination = self.primary / "new.txt"
        plan = self.policy.build_plan(
            "create_text_file", destination=str(destination), content="hello",
        )
        authorization = FileAuthorization.issue(plan, now=10.0, ttl_seconds=30.0)
        tampered = replace(plan, fingerprint="different")

        with self.assertRaisesRegex(FilePermissionError, "authorization_mismatch"):
            authorization.validate(tampered, now=11.0)

    def test_authorization_expires(self) -> None:
        plan = self.policy.build_plan(
            "create_text_file", destination=str(self.primary / "new.txt"), content="hello",
        )
        authorization = FileAuthorization.issue(plan, now=10.0, ttl_seconds=1.0)

        with self.assertRaisesRegex(FilePermissionError, "authorization_expired"):
            authorization.validate(plan, now=11.1)

    @unittest.skipUnless(os.name == "nt", "real Known Folder lookup is Windows-specific")
    def test_desktop_alias_resolves_to_current_windows_desktop(self) -> None:
        desktop = self.policy.resolve_system_directory("desktop")

        self.assertIsNotNone(desktop)
        self.assertTrue(desktop.is_absolute())

    def test_system_directory_aliases_resolve_from_configured_resolver(self) -> None:
        desktop = self.base / "OneDrive" / "Desktop"
        downloads = self.base / "Downloads"
        documents = self.base / "Documents"
        for path in (desktop, downloads, documents):
            path.mkdir(parents=True)
        policy = FilePermissionPolicy({
            "root": str(self.primary),
            "workspaces": [{"id": "desktop", "name": "Desktop", "path": str(desktop)}],
            "allow_home_read_only": False,
            "system_directory_resolver": {
                "desktop": desktop,
                "downloads": downloads,
                "documents": documents,
            }.get,
        })

        desktop_plan = policy.build_plan("list_directory", source="桌面")
        download_plan = policy.build_plan("list_directory", source="downloads")
        document_plan = policy.build_plan("list_directory", source="文档")

        self.assertEqual(Path(desktop_plan.resolved_source), desktop)
        self.assertEqual(Path(download_plan.resolved_source), downloads)
        self.assertEqual(Path(document_plan.resolved_source), documents)

    def test_system_directory_alias_resolution_still_uses_permission_policy(self) -> None:
        downloads = self.base / "Downloads"
        downloads.mkdir()
        policy = FilePermissionPolicy({
            "root": str(self.primary),
            "allow_home_read_only": False,
            "system_directory_resolver": {"downloads": downloads}.get,
        })

        plan = policy.build_plan("list_directory", source="下载")

        self.assertTrue(plan.requires_confirmation)
        self.assertIn("outside_configured_workspace", plan.risk_reasons)


if __name__ == "__main__":
    unittest.main()
