"""Verified file-operation execution and content-free JSONL audit records."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from core.tools.file_permissions import (
    FileAuthorization,
    FileOperationPlan,
    FilePermissionError,
    FilePermissionPolicy,
)


class FileAuditLogger:
    SENSITIVE_KEYS = {"content", "text", "secret", "token", "password", "api_key", "key"}

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
            content = str(params.get("content", ""))
            plan = self.policy.build_plan(
                operation, source=source, destination=destination, content=content,
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
                    return {"action": operation, "denied": True,
                            "error": "user confirmation required", "error_code": "user_cancelled",
                            "plan": plan.preview()}
            authorization = FileAuthorization.issue(plan, now=self.clock())
            authorization.validate(plan, now=self.clock())
            self.policy.revalidate(plan, content=content)
            verification = self._perform(plan, content=content, params=params)
            self.audit.record(
                operation=operation, result="success", plan=plan, verification=verification,
                duration_ms=(time.monotonic() - started) * 1000,
            )
            return {"action": operation, "plan_id": plan.plan_id,
                    "risk": plan.risk, "verification": verification}
        except Exception as exc:
            code = exc.code if isinstance(exc, FilePermissionError) else self._error_code(exc)
            self.audit.record(
                operation=operation, result="failed", plan=plan, error_code=code,
                duration_ms=(time.monotonic() - started) * 1000,
            )
            return {"action": operation, "error": str(exc), "error_code": code,
                    "plan": plan.preview() if plan else None}

    @staticmethod
    def _optional(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

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
        if plan.operation == "read_text_file":
            return self._read_text_file(source, str(params.get("encoding", "utf-8")))
        if plan.operation == "create_text_file":
            return self._create_text_file(destination, content, plan.overwrite)
        if plan.operation == "copy_file":
            return self._copy_file(source, destination, plan.overwrite)
        if plan.operation in {"move_file", "rename_file"}:
            return self._move_file(source, destination, plan.overwrite)
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

    @staticmethod
    def _read_text_file(source: Path | None, encoding: str) -> dict[str, Any]:
        assert source is not None
        size = source.stat().st_size
        if size > 2_000_000:
            raise FilePermissionError("file_too_large", "file exceeds 2 MB read limit")
        data = source.read_bytes()
        if b"\x00" in data[:8192]:
            raise FilePermissionError("binary_file", "binary files cannot be read as text")
        return {"path": str(source), "content": data.decode(encoding, errors="replace"),
                "size": size, "sha256": FilePermissionPolicy.sha256(source)}

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
