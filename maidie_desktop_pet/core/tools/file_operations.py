"""Verified file-operation execution and content-free JSONL audit records."""

from __future__ import annotations

import ctypes
import difflib
import errno
import hashlib
import json
import mimetypes
import os
import shutil
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4
from xml.etree import ElementTree

from core.tools.file_permissions import (
    FileAuthorization,
    FileOperationPlan,
    FilePermissionError,
    FilePermissionPolicy,
)


class FileAuditLogger:
    SENSITIVE_KEYS = {
        "content", "content_match", "text", "diff", "secret", "token", "password",
        "api_key", "key",
    }

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or (Path.cwd() / "logs" / "file_operations.jsonl"))
        self._lock = threading.Lock()

    def record(self, *, operation: str, result: str, plan: FileOperationPlan | None = None,
               error_code: str | None = None, verification: dict[str, Any] | None = None,
               duration_ms: float = 0.0) -> None:
        record = {
            "schema_version": 1,
            "timestamp": time.time(),
            "operation_id": uuid4().hex,
            "plan_id": plan.plan_id if plan else None,
            "operation": operation,
            "workspace": list(plan.workspace_names) if plan else [],
            "source": plan.resolved_source if plan else None,
            "destination": plan.resolved_destination if plan else None,
            "risk": plan.risk if plan else None,
            "risk_reasons": list(plan.risk_reasons) if plan else [],
            "plan_fingerprint": plan.fingerprint if plan else None,
            "confirmation_required": plan.requires_confirmation if plan else None,
            "result": result,
            "error_code": error_code,
            "verification": self._sanitize(verification or {}),
            "duration_ms": round(duration_ms, 3),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line)

    @classmethod
    def _sanitize(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: cls._sanitize(item)
                for key, item in value.items()
                if str(key).lower() not in cls.SENSITIVE_KEYS
            }
        if isinstance(value, list):
            return [cls._sanitize(item) for item in value]
        return value


class FileOperationService:
    def __init__(self, policy: FilePermissionPolicy,
                 confirmation_callback: Callable[[str, dict[str, Any]], bool] | None = None,
                 audit_path: str | Path | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        self.policy = policy
        self.confirmation_callback = confirmation_callback
        self.audit = FileAuditLogger(audit_path)
        self.clock = clock

    def execute(self, operation: str, params: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        plan: FileOperationPlan | None = None
        try:
            source = self._optional(params.get("source"))
            destination = self._optional(params.get("destination"))
            content = self._binding_content(operation, params)
            plan = self.policy.build_plan(
                operation, source=source, destination=destination, content=content,
            )
            if operation in {"append_file", "replace_exact"}:
                plan = self.policy.with_diff(plan, self._text_change_diff(plan, params))
            if operation in {
                "list_directory", "stat_file", "search_files", "read_text_file", "read_file",
            } and plan.requires_confirmation:
                self.audit.record(
                    operation=operation, result="failed", plan=plan,
                    error_code="permission_denied",
                    duration_ms=(time.monotonic() - started) * 1000,
                )
                return self._failure(
                    operation, "permission_denied",
                    "path is outside configured readable workspaces", plan,
                )
            if plan.requires_confirmation:
                approved = bool(self.confirmation_callback and self.confirmation_callback(
                    operation, {"file_plan": plan.preview()},
                ))
                if not approved:
                    self.audit.record(
                        operation=operation, result="cancelled", plan=plan,
                        error_code="user_cancelled",
                        duration_ms=(time.monotonic() - started) * 1000,
                    )
                    return self._failure(
                        operation, "user_cancelled", "用户取消了文件操作", plan, denied=True,
                    )
                if operation == "delete_file":
                    approved_again = bool(
                        self.confirmation_callback
                        and self.confirmation_callback(operation, {
                            "file_plan": {**plan.preview(), "confirmation_stage": 2},
                        })
                    )
                    if not approved_again:
                        self.audit.record(
                            operation=operation, result="cancelled", plan=plan,
                            error_code="user_cancelled",
                            duration_ms=(time.monotonic() - started) * 1000,
                        )
                        return self._failure(
                            operation, "user_cancelled", "用户取消了第二次删除确认",
                            plan, denied=True,
                        )
            authorization = FileAuthorization.issue(plan, now=self.clock())
            authorization.validate(plan, now=self.clock())
            self.policy.revalidate(plan, content=content)
            verification = self._perform(plan, content=content, params=params)
            self.audit.record(
                operation=operation, result="success", plan=plan, verification=verification,
                duration_ms=(time.monotonic() - started) * 1000,
            )
            return self._success(operation, plan, verification)
        except Exception as exc:
            code = exc.code if isinstance(exc, FilePermissionError) else self._error_code(exc)
            self.audit.record(
                operation=operation, result="failed", plan=plan, error_code=code,
                duration_ms=(time.monotonic() - started) * 1000,
            )
            return self._failure(operation, code, str(exc), plan)

    @staticmethod
    def _optional(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _binding_content(operation: str, params: dict[str, Any]) -> str:
        if operation in {"create_text_file", "append_file"}:
            return str(params.get("content", ""))
        if operation == "replace_exact":
            return json.dumps({
                "old_text": str(params.get("old_text", "")),
                "new_text": str(params.get("new_text", "")),
            }, ensure_ascii=False, sort_keys=True)
        return ""

    def _perform(self, plan: FileOperationPlan, *, content: str,
                 params: dict[str, Any]) -> dict[str, Any]:
        source = Path(plan.resolved_source) if plan.resolved_source else None
        destination = Path(plan.resolved_destination) if plan.resolved_destination else None
        if plan.operation == "list_directory":
            return self._list_directory(source)
        if plan.operation == "stat_file":
            return self._stat_file(source)
        if plan.operation == "search_files":
            return self._search_files(source, str(params.get("pattern", "*")),
                                      int(params.get("limit", 50)))
        if plan.operation in {"read_text_file", "read_file"}:
            return self._read_file(source, str(params.get("encoding", "utf-8")))
        if plan.operation == "create_text_file":
            return self._create_text_file(destination, content, plan.overwrite)
        if plan.operation == "copy_file":
            return self._copy_file(source, destination, plan.overwrite)
        if plan.operation in {"move_file", "rename_file"}:
            return self._move_file(source, destination, plan.overwrite)
        if plan.operation in {"append_file", "replace_exact"}:
            return self._modify_text_file(plan, params)
        if plan.operation == "delete_file":
            return self._delete_file(source)
        raise FilePermissionError("unsupported_operation", plan.operation)

    def _list_directory(self, source: Path | None) -> dict[str, Any]:
        assert source is not None
        entries = []
        for child in sorted(source.iterdir(), key=lambda item: item.name.lower())[:200]:
            if self.policy._is_reparse_point(child):
                continue
            try:
                self.policy._assert_safe_real_path(child.resolve(strict=True))
            except FilePermissionError:
                continue
            entries.append({"name": child.name, "path": str(child),
                            "type": "directory" if child.is_dir() else "file"})
        return {"path": str(source), "entries": entries, "count": len(entries),
                "truncated": len(entries) >= 200}

    def _stat_file(self, source: Path | None) -> dict[str, Any]:
        assert source is not None
        state = self.policy.capture_state(source)
        return {"path": str(source), "exists": state.exists, "type": state.kind,
                "size": state.size, "mtime_ns": state.mtime_ns, "sha256": state.sha256}

    def _search_files(self, source: Path | None, pattern: str, limit: int) -> dict[str, Any]:
        assert source is not None
        limit = max(1, min(200, limit))
        matches: list[str] = []
        for root, dirs, files in os.walk(source, followlinks=False):
            root_path = Path(root)
            safe_dirs = []
            for name in dirs:
                candidate = root_path / name
                try:
                    if self.policy._is_reparse_point(candidate):
                        continue
                    self.policy._assert_safe_real_path(candidate.resolve(strict=True))
                    safe_dirs.append(name)
                except (FilePermissionError, OSError):
                    continue
            dirs[:] = safe_dirs
            for name in files:
                candidate = root_path / name
                if candidate.match(pattern):
                    matches.append(str(candidate))
                    if len(matches) >= limit:
                        return {"root": str(source), "matches": matches, "truncated": True}
        return {"root": str(source), "matches": matches, "truncated": False}

    def _read_file(self, source: Path | None, encoding: str) -> dict[str, Any]:
        assert source is not None
        size = source.stat().st_size
        if size > 2_000_000:
            raise FilePermissionError("file_too_large", "file exceeds 2 MB read limit")
        file_type, extension, mime = self._detect_file_type(source)
        if file_type == "docx":
            return self._read_docx(source, extension, mime)
        if file_type == "pdf":
            return self._read_pdf(source, extension, mime)
        data = source.read_bytes()
        if b"\x00" in data[:8192]:
            raise FilePermissionError("binary_file", "binary files cannot be read as text")
        try:
            content = data.decode(encoding)
        except UnicodeDecodeError as exc:
            raise FilePermissionError("binary_file", "file is not valid text") from exc
        metadata = {
            "size": size, "extension": extension, "mime": mime,
            "sha256": FilePermissionPolicy.sha256(source),
        }
        return {
            "path": str(source), "file_type": file_type, "content": content,
            "metadata": metadata, "size": size, "sha256": metadata["sha256"],
        }

    @staticmethod
    def _detect_file_type(source: Path) -> tuple[str, str, str]:
        extension = source.suffix.lower().lstrip(".")
        guessed_mime = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        header = source.read_bytes()[:8192]
        if header.startswith(b"%PDF-"):
            return "pdf", extension, "application/pdf"
        if header.startswith(b"PK"):
            try:
                with zipfile.ZipFile(source) as archive:
                    names = set(archive.namelist())
                    if "word/document.xml" in names and "[Content_Types].xml" in names:
                        return "docx", extension, (
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        )
            except (OSError, zipfile.BadZipFile):
                pass
        if b"\x00" in header:
            return "binary", extension, guessed_mime
        if extension in {"md", "markdown"}:
            return "markdown", extension, "text/markdown"
        if extension == "json":
            return "json", extension, "application/json"
        if extension in {"yaml", "yml"}:
            return "yaml", extension, "application/yaml"
        if extension in {
            "py", "pyi", "js", "ts", "tsx", "jsx", "java", "c", "h", "cpp", "hpp",
            "cs", "go", "rs", "rb", "php", "sh", "ps1", "html", "css", "xml", "toml",
        }:
            return "code", extension, guessed_mime
        return "text", extension, guessed_mime if guessed_mime.startswith("text/") else "text/plain"

    @staticmethod
    def _read_docx(source: Path, extension: str, mime: str) -> dict[str, Any]:
        namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        try:
            with zipfile.ZipFile(source) as archive:
                total_uncompressed = sum(item.file_size for item in archive.infolist())
                if total_uncompressed > 20_000_000:
                    raise FilePermissionError("document_too_large", "DOCX expanded content is too large")
                root = ElementTree.fromstring(archive.read("word/document.xml"))
        except (KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
            raise FilePermissionError("invalid_docx", "DOCX structure is invalid") from exc
        blocks: list[dict[str, Any]] = []
        rendered: list[str] = []
        for paragraph in root.findall(".//w:body/w:p", namespace):
            text = "".join(node.text or "" for node in paragraph.findall(".//w:t", namespace)).strip()
            if not text:
                continue
            style_node = paragraph.find("./w:pPr/w:pStyle", namespace)
            style = style_node.get(f"{{{namespace['w']}}}val", "") if style_node is not None else ""
            level = None
            if style.lower().startswith("heading"):
                suffix = style[len("Heading"):]
                level = int(suffix) if suffix.isdigit() else 1
                level = max(1, min(6, level))
            blocks.append({"type": "heading" if level else "paragraph", "level": level, "text": text})
            rendered.append(f"{'#' * level} {text}" if level else text)
        metadata = {
            "size": source.stat().st_size, "extension": extension, "mime": mime,
            "paragraphs": len(blocks), "sha256": FilePermissionPolicy.sha256(source),
        }
        return {"path": str(source), "file_type": "docx", "content": "\n\n".join(rendered),
                "blocks": blocks, "metadata": metadata}

    @staticmethod
    def _read_pdf(source: Path, extension: str, mime: str) -> dict[str, Any]:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise FilePermissionError("pdf_reader_unavailable", "PDF reader dependency is unavailable") from exc
        try:
            reader = PdfReader(str(source))
            if reader.is_encrypted:
                raise FilePermissionError("encrypted_pdf", "encrypted PDF files are not supported")
            pages = []
            for index, page in enumerate(reader.pages, 1):
                pages.append({"page": index, "text": str(page.extract_text() or "").strip()})
        except FilePermissionError:
            raise
        except Exception as exc:
            raise FilePermissionError("invalid_pdf", "PDF structure could not be read") from exc
        content = "\n\n".join(
            f"[Page {page['page']}]\n{page['text']}" for page in pages if page["text"]
        )
        if not content.strip():
            raise FilePermissionError(
                "scanned_pdf_no_text", "扫描型 PDF 没有可提取文本，当前未启用 OCR",
            )
        metadata = {
            "size": source.stat().st_size, "extension": extension, "mime": mime,
            "pages": len(pages), "sha256": FilePermissionPolicy.sha256(source),
        }
        return {"path": str(source), "file_type": "pdf", "content": content,
                "pages": pages, "metadata": metadata}

    def _text_change_diff(self, plan: FileOperationPlan, params: dict[str, Any]) -> str:
        source = Path(str(plan.resolved_source))
        old_content, new_content = self._build_text_change(source, plan.operation, params)
        lines = difflib.unified_diff(
            old_content.splitlines(), new_content.splitlines(),
            fromfile=str(source), tofile=str(source), lineterm="",
        )
        return "\n".join(lines)

    def _modify_text_file(self, plan: FileOperationPlan, params: dict[str, Any]) -> dict[str, Any]:
        source = Path(str(plan.resolved_source))
        _old_content, new_content = self._build_text_change(source, plan.operation, params)
        data = new_content.encode("utf-8")
        if len(data) > 2_000_000:
            raise FilePermissionError("content_too_large", "content exceeds 2 MB write limit")
        self._atomic_replace_bytes(source, data)
        digest = FilePermissionPolicy.sha256(source)
        expected = hashlib.sha256(data).hexdigest()
        if not source.exists() or source.stat().st_size != len(data) or digest != expected:
            raise FilePermissionError("verification_failed", "modified file verification failed")
        return {"path": str(source), "exists": True, "size": len(data), "sha256": digest,
                "content_match": True, "diff": plan.diff}

    @staticmethod
    def _build_text_change(source: Path, operation: str,
                           params: dict[str, Any]) -> tuple[str, str]:
        data = source.read_bytes()
        if len(data) > 2_000_000:
            raise FilePermissionError("file_too_large", "file exceeds 2 MB modification limit")
        if b"\x00" in data[:8192]:
            raise FilePermissionError("binary_file", "binary files cannot be modified as text")
        try:
            old_content = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FilePermissionError("binary_file", "file is not valid UTF-8 text") from exc
        if operation == "append_file":
            addition = str(params.get("content", ""))
            if not addition:
                raise FilePermissionError("content_required", "append content is required")
            return old_content, old_content + addition
        old_text = str(params.get("old_text", ""))
        new_text = str(params.get("new_text", ""))
        if not old_text:
            raise FilePermissionError("old_text_required", "old_text is required")
        matches = old_content.count(old_text)
        if matches == 0:
            raise FilePermissionError("match_not_found", "exact text was not found")
        if matches > 1:
            raise FilePermissionError("multiple_matches", "exact text matched more than once")
        return old_content, old_content.replace(old_text, new_text, 1)

    def _delete_file(self, source: Path | None) -> dict[str, Any]:
        assert source is not None
        self._recycle_path(source)
        if source.exists():
            raise FilePermissionError("verification_failed", "deleted file still exists")
        return {"path": str(source), "deleted": True, "exists": False,
                "recycle_bin": True, "source_missing": True}

    def _create_text_file(self, destination: Path | None, content: str,
                          overwrite: bool) -> dict[str, Any]:
        assert destination is not None
        data = content.encode("utf-8")
        if len(data) > 2_000_000:
            raise FilePermissionError("content_too_large", "content exceeds 2 MB write limit")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if overwrite:
            self._atomic_replace_bytes(destination, data)
        else:
            temporary = self._write_temp(destination.parent, data)
            self._commit_new_temp(temporary, destination)
        state = self.policy.capture_state(destination)
        digest = FilePermissionPolicy.sha256(destination)
        if state.size != len(data) or digest != hashlib.sha256(data).hexdigest():
            raise FilePermissionError("verification_failed", "created file verification failed")
        return {"path": str(destination), "exists": True, "size": state.size, "sha256": digest}

    def _copy_file(self, source: Path | None, destination: Path | None,
                   overwrite: bool) -> dict[str, Any]:
        assert source is not None and destination is not None
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_hash = FilePermissionPolicy.sha256(source)
        if overwrite:
            self._atomic_copy(source, destination)
        else:
            temporary = self._copy_to_temp(source, destination.parent)
            self._commit_new_temp(temporary, destination)
            try:
                shutil.copystat(source, destination)
            except OSError:
                pass
        destination_hash = FilePermissionPolicy.sha256(destination)
        if source_hash != destination_hash or source.stat().st_size != destination.stat().st_size:
            raise FilePermissionError("verification_failed", "copied file verification failed")
        return {"source": str(source), "destination": str(destination),
                "source_sha256": source_hash, "destination_sha256": destination_hash,
                "sha256_match": True}

    def _move_file(self, source: Path | None, destination: Path | None,
                   overwrite: bool) -> dict[str, Any]:
        assert source is not None and destination is not None
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_hash = FilePermissionPolicy.sha256(source)
        backup = self._backup_existing(destination) if overwrite else None
        cross_volume = source.drive.lower() != destination.drive.lower()
        if cross_volume:
            return self._move_cross_volume(source, destination, source_hash, backup)
        try:
            try:
                os.replace(source, destination)
            except OSError as exc:
                if exc.errno != errno.EXDEV:
                    raise
                return self._move_cross_volume(source, destination, source_hash, backup)
            destination_hash = FilePermissionPolicy.sha256(destination)
            if source.exists() or not destination.exists() or destination_hash != source_hash:
                raise FilePermissionError("verification_failed", "moved file verification failed")
            if backup:
                self._recycle_path(backup)
            return {"source": str(source), "destination": str(destination),
                    "source_missing": True, "destination_exists": True,
                    "sha256": destination_hash}
        except Exception:
            if destination.exists() and not source.exists():
                os.replace(destination, source)
            if backup and backup.exists() and not destination.exists():
                os.replace(backup, destination)
            raise

    def _move_cross_volume(self, source: Path, destination: Path, source_hash: str,
                           backup: Path | None) -> dict[str, Any]:
        self._copy_file(source, destination, False)
        try:
            self._recycle_path(source)
        except Exception as recycle_error:
            try:
                self._recycle_path(destination)
                if backup and backup.exists():
                    os.replace(backup, destination)
            except Exception as rollback_error:
                raise FilePermissionError(
                    "partial_completion",
                    f"cross-volume rollback failed: {rollback_error}",
                ) from recycle_error
            raise
        destination_hash = FilePermissionPolicy.sha256(destination)
        if source.exists() or destination_hash != source_hash:
            raise FilePermissionError("verification_failed", "moved file verification failed")
        verification = {
            "source": str(source), "destination": str(destination),
            "source_missing": True, "destination_exists": True,
            "sha256": destination_hash, "cross_volume": True,
        }
        if backup:
            try:
                self._recycle_path(backup)
            except Exception:
                # The requested move is complete and verified.  Retaining the old
                # destination is safer than permanently deleting it or claiming rollback.
                verification["backup_retained"] = str(backup)
        return verification

    def _atomic_replace_bytes(self, destination: Path, data: bytes) -> None:
        temporary = self._write_temp(destination.parent, data)
        backup = self._backup_existing(destination)
        try:
            os.replace(temporary, destination)
            if backup:
                self._recycle_path(backup)
        except Exception:
            if temporary.exists():
                temporary.unlink(missing_ok=True)
            if backup and backup.exists() and not destination.exists():
                os.replace(backup, destination)
            raise

    def _atomic_copy(self, source: Path, destination: Path) -> None:
        temporary = self._copy_to_temp(source, destination.parent)
        backup = self._backup_existing(destination)
        try:
            os.replace(temporary, destination)
            try:
                shutil.copystat(source, destination)
            except OSError:
                pass
            if backup:
                self._recycle_path(backup)
        except Exception:
            temporary.unlink(missing_ok=True)
            if backup and backup.exists() and not destination.exists():
                os.replace(backup, destination)
            raise

    @staticmethod
    def _write_temp(parent: Path, data: bytes) -> Path:
        handle = tempfile.NamedTemporaryFile(prefix=".maidie-", suffix=".tmp", dir=parent,
                                             delete=False)
        path = Path(handle.name)
        try:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            handle.close()
        return path

    @staticmethod
    def _copy_to_temp(source: Path, parent: Path) -> Path:
        handle = tempfile.NamedTemporaryFile(prefix=".maidie-", suffix=".tmp", dir=parent,
                                             delete=False)
        path = Path(handle.name)
        try:
            with source.open("rb") as reader:
                shutil.copyfileobj(reader, handle, length=1024 * 1024)
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            handle.close()
        return path

    @staticmethod
    def _commit_new_temp(temporary: Path, destination: Path) -> None:
        try:
            # On Windows os.rename is atomic and refuses an existing destination,
            # preserving the no-silent-overwrite precondition.
            os.rename(temporary, destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    @staticmethod
    def _backup_existing(destination: Path) -> Path | None:
        if not destination.exists():
            return None
        backup = destination.with_name(f".{destination.name}.maidie-backup-{uuid4().hex}")
        os.replace(destination, backup)
        return backup

    @staticmethod
    def _recycle_path(path: Path) -> None:
        if os.name != "nt":
            raise FilePermissionError("recycle_unavailable", "permanent deletion is forbidden")

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", ctypes.c_void_p), ("wFunc", ctypes.c_uint),
                ("pFrom", ctypes.c_wchar_p), ("pTo", ctypes.c_wchar_p),
                ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", ctypes.c_bool),
                ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", ctypes.c_wchar_p),
            ]

        operation = SHFILEOPSTRUCTW()
        operation.wFunc = 3  # FO_DELETE
        operation.pFrom = str(path) + "\0\0"
        operation.fFlags = 0x0040 | 0x0010 | 0x0400  # ALLOWUNDO | NOCONFIRMATION | NOERRORUI
        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
        if result != 0 or operation.fAnyOperationsAborted:
            raise FilePermissionError("recycle_failed", "failed to move path to recycle bin")

    @staticmethod
    def _error_code(exc: Exception) -> str:
        if isinstance(exc, FileExistsError):
            return "destination_exists"
        if isinstance(exc, FileNotFoundError):
            return "path_not_found"
        return "file_operation_failed"

    @staticmethod
    def _success(operation: str, plan: FileOperationPlan,
                 verification: dict[str, Any]) -> dict[str, Any]:
        workspace = plan.workspace_names[0] if plan.workspace_names else None
        resolved_path = plan.resolved_source or plan.resolved_destination
        payload: dict[str, Any] = {
            "ok": True,
            "operation": operation,
            "action": operation,
            "plan_id": plan.plan_id,
            "risk": plan.risk,
            "resolved_path": resolved_path,
            "path": resolved_path,
            "workspace_id": workspace,
            "verification": verification,
            "result": verification,
            "error_code": None,
            "message": "",
        }
        if operation == "list_directory":
            items = list(verification.get("entries", []))
            payload.update({
                "items": items,
                "result_count": int(verification.get("count", len(items))),
                "truncated": bool(verification.get("truncated", False)),
                "data": {"items": items},
            })
        elif operation == "search_files":
            items = [
                {"name": Path(str(match)).name, "path": str(match), "type": "file"}
                for match in verification.get("matches", [])
            ]
            payload.update({
                "items": items,
                "result_count": len(items),
                "truncated": bool(verification.get("truncated", False)),
                "data": {"items": items},
            })
        else:
            payload.update({"result_count": None, "items": None, "data": verification})
        for key in ("file_type", "content", "metadata", "pages", "blocks", "diff"):
            if key in verification:
                payload[key] = verification[key]
        return payload

    @staticmethod
    def _failure(operation: str, code: str, message: str,
                 plan: FileOperationPlan | None, *, denied: bool = False) -> dict[str, Any]:
        error_code = code if code.isupper() else code
        resolved_path = (
            (plan.resolved_source or plan.resolved_destination) if plan else None
        )
        return {
            "ok": False,
            "operation": operation,
            "action": operation,
            "error": message,
            "error_code": error_code,
            "message": message,
            "data": None,
            "result": None,
            "resolved_path": resolved_path,
            "path": resolved_path,
            "workspace_id": plan.workspace_names[0] if plan and plan.workspace_names else None,
            "result_count": None,
            "items": None,
            "plan": plan.preview() if plan else None,
            "denied": denied,
        }
