from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.tools import SystemTool


class FileOperationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.base = Path(self._temporary.name)
        self.workspace = self.base / "workspace"
        self.outside = self.base / "outside"
        self.workspace.mkdir()
        self.outside.mkdir()
        self.audit_path = self.base / "audit.jsonl"
        self.requests: list[tuple[str, dict]] = []

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def _tool(self, answer=True, callback=None) -> SystemTool:
        def confirm(action, params):
            self.requests.append((action, params))
            return answer

        return SystemTool(
            workspace={"root": str(self.workspace)},
            confirmation_callback=callback or confirm,
            audit_path=self.audit_path,
        )

    def _audit(self) -> list[dict]:
        if not self.audit_path.exists():
            return []
        return [json.loads(line) for line in self.audit_path.read_text(encoding="utf-8").splitlines()]

    def test_create_new_file_confirms_and_verifies_size_and_hash(self) -> None:
        destination = self.workspace / "created.txt"
        result = self._tool().execute("create_text_file", {
            "destination": str(destination), "content": "hello",
        })

        self.assertEqual(destination.read_text(encoding="utf-8"), "hello")
        self.assertEqual(result["raw"]["verification"]["size"], 5)
        self.assertEqual(
            result["raw"]["verification"]["sha256"],
            hashlib.sha256(b"hello").hexdigest(),
        )
        preview = self.requests[0][1]["file_plan"]
        self.assertEqual(preview["operation"], "create_text_file")
        self.assertEqual(preview["estimated_items"], 1)
        self.assertFalse(preview["destination_exists"])
        self.assertIn("fingerprint", preview)

    def test_list_stat_search_and_read_execute_without_confirmation(self) -> None:
        source = self.workspace / "notes.txt"
        source.write_text("hello", encoding="utf-8")
        tool = self._tool(answer=False)

        listed = tool.execute("list_directory", {"source": str(self.workspace)})
        stated = tool.execute("stat_file", {"source": str(source)})
        searched = tool.execute("search_files", {"source": str(self.workspace), "pattern": "*.txt"})
        read = tool.execute("read_text_file", {"source": str(source)})

        self.assertEqual(listed["raw"]["verification"]["count"], 1)
        self.assertEqual(stated["raw"]["verification"]["type"], "file")
        self.assertEqual(searched["raw"]["verification"]["matches"], [str(source)])
        self.assertEqual(read["raw"]["verification"]["content"], "hello")
        self.assertEqual(self.requests, [])

    @unittest.skipUnless(__import__("os").name == "nt", "overwrite uses Windows recycle bin")
    def test_approved_overwrite_uses_a_new_high_risk_plan(self) -> None:
        destination = self.workspace / "existing.txt"
        destination.write_text("old", encoding="utf-8")

        result = self._tool(answer=True).execute("create_text_file", {
            "destination": str(destination), "content": "new",
        })

        self.assertEqual(destination.read_text(encoding="utf-8"), "new")
        preview = self.requests[0][1]["file_plan"]
        self.assertEqual(preview["risk"], "high")
        self.assertTrue(preview["overwrite"])
        self.assertNotIn("error", result["raw"])

    def test_existing_destination_is_not_overwritten_when_confirmation_is_rejected(self) -> None:
        destination = self.workspace / "existing.txt"
        destination.write_text("old", encoding="utf-8")

        result = self._tool(answer=False).execute("create_text_file", {
            "destination": str(destination), "content": "new",
        })

        self.assertTrue(result["raw"]["denied"])
        self.assertEqual(destination.read_text(encoding="utf-8"), "old")
        self.assertTrue(self.requests[0][1]["file_plan"]["overwrite"])

    def test_copy_file_verifies_source_and_destination(self) -> None:
        source = self.workspace / "source.txt"
        destination = self.workspace / "copy.txt"
        source.write_text("copy me", encoding="utf-8")

        result = self._tool().execute("copy_file", {
            "source": str(source), "destination": str(destination),
        })

        self.assertEqual(destination.read_bytes(), source.read_bytes())
        self.assertTrue(result["raw"]["verification"]["sha256_match"])

    def test_move_file_verifies_source_missing_and_destination_present(self) -> None:
        source = self.workspace / "move-source.txt"
        destination = self.workspace / "move-destination.txt"
        source.write_text("move me", encoding="utf-8")

        result = self._tool().execute("move_file", {
            "source": str(source), "destination": str(destination),
        })

        self.assertFalse(source.exists())
        self.assertTrue(destination.exists())
        self.assertTrue(result["raw"]["verification"]["source_missing"])
        self.assertTrue(result["raw"]["verification"]["destination_exists"])

    def test_cross_volume_move_copies_verifies_then_recycles_source(self) -> None:
        source = self.workspace / "cross-source.txt"
        destination = self.workspace / "cross-destination.txt"
        source.write_text("cross volume", encoding="utf-8")
        tool = self._tool()
        real_replace = __import__("os").replace

        def exdev_once(src, dst):
            if Path(src) == source and Path(dst) == destination:
                error = OSError("cross device")
                error.errno = 18
                raise error
            return real_replace(src, dst)

        with patch("core.tools.file_operations.os.replace", side_effect=exdev_once), \
                patch.object(tool.file_operations, "_recycle_path", side_effect=lambda path: path.unlink()):
            result = tool.execute("move_file", {
                "source": str(source), "destination": str(destination),
            })

        self.assertFalse(source.exists())
        self.assertEqual(destination.read_text(encoding="utf-8"), "cross volume")
        self.assertTrue(result["raw"]["verification"]["source_missing"])

    def test_rename_conflict_is_cancelled_without_overwrite(self) -> None:
        source = self.workspace / "old.txt"
        destination = self.workspace / "new.txt"
        source.write_text("source", encoding="utf-8")
        destination.write_text("destination", encoding="utf-8")

        result = self._tool(answer=False).execute("rename_file", {
            "source": str(source), "destination": str(destination),
        })

        self.assertTrue(result["raw"]["denied"])
        self.assertEqual(source.read_text(encoding="utf-8"), "source")
        self.assertEqual(destination.read_text(encoding="utf-8"), "destination")

    def test_outside_workspace_operation_executes_only_after_high_risk_confirmation(self) -> None:
        destination = self.outside / "approved.txt"
        result = self._tool().execute("create_text_file", {
            "destination": str(destination), "content": "approved",
        })

        self.assertTrue(destination.exists())
        self.assertEqual(self.requests[0][1]["file_plan"]["risk"], "high")
        self.assertTrue(result["raw"]["verification"]["exists"])

    def test_file_state_change_after_confirmation_invalidates_authorization(self) -> None:
        source = self.workspace / "source.txt"
        destination = self.workspace / "destination.txt"
        source.write_text("before", encoding="utf-8")

        def mutate_then_confirm(action, params):
            source.write_text("after", encoding="utf-8")
            return True

        result = self._tool(callback=mutate_then_confirm).execute("copy_file", {
            "source": str(source), "destination": str(destination),
        })

        self.assertEqual(result["raw"]["error_code"], "file_state_changed")
        self.assertFalse(destination.exists())

    def test_ui_cancel_does_not_execute_and_is_audited(self) -> None:
        destination = self.workspace / "cancelled.txt"
        result = self._tool(answer=False).execute("create_text_file", {
            "destination": str(destination), "content": "do not write",
        })

        self.assertTrue(result["raw"]["denied"])
        self.assertFalse(destination.exists())
        self.assertEqual(self._audit()[-1]["result"], "cancelled")

    def test_audit_records_success_failure_and_never_file_content_or_secret(self) -> None:
        secret = "PRIVATE-KEY-CONTENT"
        success = self._tool().execute("create_text_file", {
            "destination": str(self.workspace / "safe.txt"), "content": secret,
        })
        failure = self._tool().execute("copy_file", {
            "source": str(self.workspace / "missing.txt"),
            "destination": str(self.workspace / "copy.txt"),
        })
        read_secret = self.workspace / "read-secret.txt"
        read_secret.write_text("READ-BACK-SECRET", encoding="utf-8")
        self._tool().execute("read_text_file", {"source": str(read_secret)})

        self.assertNotIn("error", success["raw"])
        self.assertIn("error", failure["raw"])
        records = self._audit()
        self.assertIn("success", [record["result"] for record in records])
        self.assertIn("failed", [record["result"] for record in records])
        self.assertNotIn(secret, self.audit_path.read_text(encoding="utf-8"))
        self.assertNotIn("READ-BACK-SECRET", self.audit_path.read_text(encoding="utf-8"))
        self.assertTrue(all("content" not in json.dumps(record) for record in records))


if __name__ == "__main__":
    unittest.main()
