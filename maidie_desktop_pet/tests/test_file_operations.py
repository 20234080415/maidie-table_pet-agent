from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import zipfile
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

    @staticmethod
    def _write_docx(path: Path) -> None:
        content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
        document = """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Release Notes</w:t></w:r></w:p>
    <w:p><w:r><w:t>Document body.</w:t></w:r></w:p>
  </w:body>
</w:document>"""
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("[Content_Types].xml", content_types)
            archive.writestr("word/document.xml", document)

    @staticmethod
    def _write_pdf(path: Path, text: str | None = "Hello PDF") -> None:
        stream = b"" if text is None else f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        ]
        payload = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for index, obj in enumerate(objects, 1):
            offsets.append(len(payload))
            payload.extend(f"{index} 0 obj\n".encode("ascii") + obj + b"\nendobj\n")
        xref = len(payload)
        payload.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
        payload.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            payload.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
        payload.extend(
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
        )
        path.write_bytes(payload)

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

    def test_read_file_detects_txt_and_markdown_from_content_and_extension(self) -> None:
        text = self.workspace / "notes.txt"
        markdown = self.workspace / "README.md"
        text.write_text("plain text", encoding="utf-8")
        markdown.write_text("# Heading", encoding="utf-8")

        text_result = self._tool().execute("read_file", {"source": str(text)})["raw"]
        markdown_result = self._tool().execute("read_file", {"source": str(markdown)})["raw"]

        self.assertEqual(text_result["file_type"], "text")
        self.assertEqual(text_result["content"], "plain text")
        self.assertEqual(markdown_result["file_type"], "markdown")
        self.assertEqual(markdown_result["content"], "# Heading")
        self.assertEqual(text_result["result"]["metadata"]["size"], len(b"plain text"))

    def test_read_docx_extracts_heading_and_structured_paragraphs(self) -> None:
        source = self.workspace / "renamed.bin"
        self._write_docx(source)

        result = self._tool().execute("read_file", {"source": str(source)})["raw"]

        self.assertTrue(result["ok"])
        self.assertEqual(result["file_type"], "docx")
        self.assertIn("# Release Notes", result["content"])
        self.assertIn("Document body.", result["content"])
        self.assertEqual(result["result"]["blocks"][0]["level"], 1)

    def test_read_pdf_extracts_text_and_page_numbers(self) -> None:
        source = self.workspace / "document.data"
        self._write_pdf(source)

        result = self._tool().execute("read_file", {"source": str(source)})["raw"]

        self.assertTrue(result["ok"])
        self.assertEqual(result["file_type"], "pdf")
        self.assertIn("Hello PDF", result["content"])
        self.assertEqual(result["result"]["metadata"]["pages"], 1)
        self.assertEqual(result["result"]["pages"][0]["page"], 1)

    def test_scanned_pdf_without_text_returns_explicit_failure(self) -> None:
        source = self.workspace / "scan.pdf"
        self._write_pdf(source, None)

        result = self._tool().execute("read_file", {"source": str(source)})["raw"]

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "scanned_pdf_no_text")
        self.assertIn("扫描", result["message"])

    def test_read_file_rejects_binary_and_oversized_files(self) -> None:
        binary = self.workspace / "fake.txt"
        oversized = self.workspace / "large.md"
        binary.write_bytes(b"text\x00binary")
        oversized.write_bytes(b"a" * 2_000_001)

        binary_result = self._tool().execute("read_file", {"source": str(binary)})["raw"]
        oversized_result = self._tool().execute("read_file", {"source": str(oversized)})["raw"]

        self.assertEqual(binary_result["error_code"], "binary_file")
        self.assertEqual(oversized_result["error_code"], "file_too_large")

    def test_append_shows_diff_confirms_and_verifies_new_content(self) -> None:
        source = self.workspace / "README.md"
        source.write_text("# Project\n", encoding="utf-8")

        result = self._tool().execute("append_file", {
            "source": str(source), "content": "\n## Install\nRun setup.",
        })["raw"]

        self.assertTrue(result["ok"])
        self.assertEqual(source.read_text(encoding="utf-8"), "# Project\n\n## Install\nRun setup.")
        preview = self.requests[0][1]["file_plan"]
        self.assertIn("+## Install", preview["diff"])
        self.assertEqual(preview["impact_scope"], "single_file")
        self.assertTrue(result["verification"]["content_match"])

    def test_replace_exact_requires_one_match_and_displays_diff(self) -> None:
        source = self.workspace / "config.txt"
        source.write_text("timeout=30\n", encoding="utf-8")

        result = self._tool().execute("replace_exact", {
            "source": str(source), "old_text": "timeout=30", "new_text": "timeout=60",
        })["raw"]

        self.assertTrue(result["ok"])
        self.assertEqual(source.read_text(encoding="utf-8"), "timeout=60\n")
        preview = self.requests[0][1]["file_plan"]
        self.assertIn("-timeout=30", preview["diff"])
        self.assertIn("+timeout=60", preview["diff"])

    def test_replace_exact_rejects_multiple_matches_without_confirmation(self) -> None:
        source = self.workspace / "config.txt"
        source.write_text("timeout=30\ntimeout=30\n", encoding="utf-8")

        result = self._tool().execute("replace_exact", {
            "source": str(source), "old_text": "timeout=30", "new_text": "timeout=60",
        })["raw"]

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "multiple_matches")
        self.assertEqual(self.requests, [])
        self.assertEqual(source.read_text(encoding="utf-8"), "timeout=30\ntimeout=30\n")

    def test_cancelled_text_change_does_not_modify_file(self) -> None:
        source = self.workspace / "notes.txt"
        source.write_text("before", encoding="utf-8")

        result = self._tool(answer=False).execute("append_file", {
            "source": str(source), "content": " after",
        })["raw"]

        self.assertFalse(result["ok"])
        self.assertTrue(result["denied"])
        self.assertEqual(source.read_text(encoding="utf-8"), "before")

    def test_delete_file_requires_two_confirmations_recycles_and_audits(self) -> None:
        source = self.workspace / "obsolete.txt"
        source.write_text("remove me", encoding="utf-8")
        tool = self._tool(answer=True)

        with patch.object(tool.file_operations, "_recycle_path", side_effect=lambda path: path.unlink()):
            result = tool.execute("delete_file", {"source": str(source)})["raw"]

        self.assertTrue(result["ok"])
        self.assertFalse(source.exists())
        self.assertEqual(len(self.requests), 2)
        preview = self.requests[0][1]["file_plan"]
        self.assertEqual(preview["risk"], "high")
        self.assertEqual(preview["file_details"]["size"], len(b"remove me"))
        self.assertTrue(preview["recycle_bin"])
        self.assertEqual(result["verification"]["deleted"], True)
        self.assertEqual(self._audit()[-1]["operation"], "delete_file")
        self.assertEqual(self._audit()[-1]["result"], "success")

    def test_delete_cancel_and_workspace_root_rejection_leave_paths_untouched(self) -> None:
        source = self.workspace / "keep.txt"
        source.write_text("keep", encoding="utf-8")

        cancelled = self._tool(answer=False).execute("delete_file", {"source": str(source)})["raw"]
        root_result = self._tool().execute("delete_file", {"source": str(self.workspace)})["raw"]

        self.assertFalse(cancelled["ok"])
        self.assertTrue(source.exists())
        self.assertFalse(root_result["ok"])
        self.assertEqual(root_result["error_code"], "workspace_root_forbidden")

    def test_directory_alias_list_returns_structured_items(self) -> None:
        desktop = self.base / "OneDrive" / "Desktop"
        desktop.mkdir(parents=True)
        (desktop / "notes.md").write_text("# hello", encoding="utf-8")
        tool = SystemTool(
            workspace={
                "root": str(self.workspace),
                "workspaces": [{"id": "desktop", "name": "Desktop", "path": str(desktop)}],
                "allow_home_read_only": False,
                "system_directory_resolver": {"desktop": desktop}.get,
            },
            audit_path=self.audit_path,
        )

        result = tool.execute("list_directory", {"source": "桌面"})

        self.assertTrue(result["raw"]["ok"])
        self.assertEqual(result["raw"]["operation"], "list_directory")
        self.assertEqual(result["raw"]["resolved_path"], str(desktop))
        self.assertEqual(result["raw"]["workspace_id"], "Desktop")
        self.assertEqual(result["raw"]["result_count"], 1)
        self.assertEqual(result["raw"]["items"][0]["name"], "notes.md")

    def test_search_md_uses_only_tool_items_and_distinguishes_empty_success(self) -> None:
        desktop = self.base / "Desktop"
        desktop.mkdir()
        note = desktop / "real.md"
        note.write_text("# real", encoding="utf-8")
        tool = SystemTool(
            workspace={
                "root": str(self.workspace),
                "workspaces": [{"id": "desktop", "name": "Desktop", "path": str(desktop)}],
                "allow_home_read_only": False,
                "system_directory_resolver": {"desktop": desktop}.get,
            },
            audit_path=self.audit_path,
        )

        found = tool.execute("search_files", {"source": "desktop", "pattern": "*.md"})
        empty = tool.execute("search_files", {"source": "desktop", "pattern": "*.pdf"})

        self.assertTrue(found["raw"]["ok"])
        self.assertEqual(found["raw"]["result_count"], 1)
        self.assertEqual(found["raw"]["items"], [{"name": "real.md", "path": str(note), "type": "file"}])
        self.assertTrue(empty["raw"]["ok"])
        self.assertEqual(empty["raw"]["result_count"], 0)
        self.assertEqual(empty["raw"]["items"], [])

    def test_unauthorized_desktop_returns_permission_error_not_success(self) -> None:
        desktop = self.base / "Desktop"
        desktop.mkdir()
        tool = SystemTool(
            workspace={
                "root": str(self.workspace),
                "allow_home_read_only": False,
                "system_directory_resolver": {"desktop": desktop}.get,
            },
            audit_path=self.audit_path,
        )

        result = tool.execute("list_directory", {"source": "桌面"})

        self.assertFalse(result["raw"]["ok"])
        self.assertEqual(result["raw"]["operation"], "list_directory")
        self.assertEqual(result["raw"]["error_code"], "permission_denied")
        self.assertIsNone(result["raw"]["data"])

    def test_file_access_description_reports_real_policy_rules(self) -> None:
        desktop = self.base / "Desktop"
        documents = self.base / "Documents"
        downloads = self.base / "Downloads"
        for path in (desktop, documents, downloads):
            path.mkdir()
        tool = SystemTool(
            workspace={
                "root": str(self.workspace),
                "workspaces": [
                    {"id": "extra", "name": "Extra", "path": str(self.outside), "mode": "read_only"},
                    {"id": "desktop", "name": "Desktop", "path": str(desktop), "mode": "read_only"},
                ],
                "allow_home_read_only": True,
                "system_directory_resolver": {
                    "desktop": desktop,
                    "documents": documents,
                    "downloads": downloads,
                }.get,
            },
            audit_path=self.audit_path,
        )

        result = tool.execute("describe_file_access", {})

        self.assertTrue(result["raw"]["ok"])
        modes = {item["id"]: item for item in result["raw"]["system_directories"]}
        self.assertTrue(modes["desktop"]["accessible"])
        self.assertEqual(modes["desktop"]["mode"], "read_only")
        self.assertTrue(modes["documents"]["accessible"])
        self.assertEqual(modes["documents"]["mode"], "read_only")
        self.assertTrue(modes["downloads"]["accessible"])
        self.assertEqual(modes["downloads"]["mode"], "read_only")
        self.assertIn("home-readonly", [item["workspace_id"] for item in result["raw"]["workspaces"]])

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
        modified = self.workspace / "modified.txt"
        modified.write_text("AUDIT-DIFF-OLD", encoding="utf-8")
        self._tool().execute("replace_exact", {
            "source": str(modified), "old_text": "AUDIT-DIFF-OLD",
            "new_text": "AUDIT-DIFF-NEW",
        })

        self.assertNotIn("error", success["raw"])
        self.assertIn("error", failure["raw"])
        records = self._audit()
        self.assertIn("success", [record["result"] for record in records])
        self.assertIn("failed", [record["result"] for record in records])
        self.assertNotIn(secret, self.audit_path.read_text(encoding="utf-8"))
        self.assertNotIn("READ-BACK-SECRET", self.audit_path.read_text(encoding="utf-8"))
        self.assertNotIn("AUDIT-DIFF-OLD", self.audit_path.read_text(encoding="utf-8"))
        self.assertNotIn("AUDIT-DIFF-NEW", self.audit_path.read_text(encoding="utf-8"))
        self.assertTrue(all("content" not in json.dumps(record) for record in records))


if __name__ == "__main__":
    unittest.main()
