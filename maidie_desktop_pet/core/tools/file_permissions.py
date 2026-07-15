"""Authoritative file-operation plans and path permission policy.

Planner fields are treated as untrusted input.  This module resolves paths,
assigns risk, snapshots preconditions, and produces a fingerprint that can be
bound to a short-lived UI authorization.
"""

from __future__ import annotations

import hashlib
import json
import ntpath
import os
import stat
import time
import ctypes
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PureWindowsPath
from typing import Any, Callable
from uuid import uuid4


READ_OPERATIONS = {
    "list_directory", "stat_file", "search_files", "read_text_file", "read_file",
}
WRITE_OPERATIONS = {
    "create_text_file", "copy_file", "move_file", "rename_file",
    "append_file", "replace_exact", "delete_file",
}
FILE_OPERATIONS = READ_OPERATIONS | WRITE_OPERATIONS
TEXT_MUTATION_OPERATIONS = {"append_file", "replace_exact"}


SYSTEM_DIRECTORY_ALIASES = {
    "desktop": ("desktop", "Desktop"),
    "桌面": ("desktop", "Desktop"),
    "documents": ("documents", "Documents"),
    "document": ("documents", "Documents"),
    "文档": ("documents", "Documents"),
    "downloads": ("downloads", "Downloads"),
    "download": ("downloads", "Downloads"),
    "下载": ("downloads", "Downloads"),
    "pictures": ("pictures", "Pictures"),
    "picture": ("pictures", "Pictures"),
    "图片": ("pictures", "Pictures"),
    "music": ("music", "Music"),
    "音乐": ("music", "Music"),
    "videos": ("videos", "Videos"),
    "video": ("videos", "Videos"),
    "视频": ("videos", "Videos"),
    "home": ("home", "Home"),
    "用户目录": ("home", "Home"),
    "主目录": ("home", "Home"),
}

KNOWN_FOLDER_IDS = {
    "desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
    "documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
    "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
    "pictures": "{33E28130-4E1E-4676-835A-98395C3BC3BB}",
    "music": "{4BD8D571-6D19-48D3-BE97-422220080E43}",
    "videos": "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}",
}


class FilePermissionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class WorkspaceRule:
    id: str
    name: str
    root: Path
    mode: str = "read_write"
    explicit: bool = True


@dataclass(frozen=True)
class FileState:
    exists: bool
    kind: str | None = None
    size: int | None = None
    mtime_ns: int | None = None
    sha256: str | None = None


@dataclass(frozen=True)
class FileOperationPlan:
    version: int
    plan_id: str
    operation: str
    requested_source: str | None
    requested_destination: str | None
    resolved_source: str | None
    resolved_destination: str | None
    source_state: FileState | None
    destination_state: FileState | None
    content_size: int
    content_sha256: str | None
    workspace_names: tuple[str, ...]
    risk: str
    risk_reasons: tuple[str, ...]
    requires_confirmation: bool
    overwrite: bool
    estimated_items: int
    diff: str
    impact_scope: str
    recycle_bin: bool
    file_details: dict[str, Any] | None
    created_at: float
    fingerprint: str

    def preview(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "plan_id": self.plan_id,
            "operation": self.operation,
            "workspace": ", ".join(self.workspace_names) or "工作区外单次授权",
            "source": self.resolved_source,
            "destination": self.resolved_destination,
            "destination_exists": bool(self.destination_state and self.destination_state.exists),
            "overwrite": self.overwrite,
            "risk": self.risk,
            "risk_reasons": list(self.risk_reasons),
            "estimated_items": self.estimated_items,
            "diff": self.diff,
            "impact_scope": self.impact_scope,
            "recycle_bin": self.recycle_bin,
            "file_details": dict(self.file_details or {}),
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True)
class FileAuthorization:
    plan_id: str
    fingerprint: str
    issued_at: float
    expires_at: float

    @classmethod
    def issue(cls, plan: FileOperationPlan, *, now: float | None = None,
              ttl_seconds: float = 30.0) -> "FileAuthorization":
        current = time.time() if now is None else float(now)
        return cls(plan.plan_id, plan.fingerprint, current, current + max(0.1, ttl_seconds))

    def validate(self, plan: FileOperationPlan, *, now: float | None = None) -> None:
        current = time.time() if now is None else float(now)
        if current > self.expires_at:
            raise FilePermissionError("authorization_expired", "file authorization has expired")
        if self.plan_id != plan.plan_id or self.fingerprint != plan.fingerprint:
            raise FilePermissionError(
                "authorization_mismatch", "authorization is not bound to this file plan",
            )


class FilePermissionPolicy:
    """Resolve file paths against configured workspaces and immutable deny rules."""

    RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                      *(f"LPT{i}" for i in range(1, 10))}

    def __init__(self, workspace: dict[str, Any] | None = None, *,
                 home: Path | None = None, app_root: Path | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        self.options = dict(workspace or {})
        self.home = (home or Path.home()).expanduser().resolve()
        self.app_root = (app_root or Path(__file__).resolve().parents[2]).resolve()
        self.clock = clock
        self.workspaces = self._load_workspaces()
        self.primary = next((item for item in self.workspaces if item.id == "primary"), None)
        self._blocked_roots = self._build_blocked_roots()

    def _load_workspaces(self) -> tuple[WorkspaceRule, ...]:
        rules: list[WorkspaceRule] = []
        primary = str(self.options.get("root") or "").strip()
        if primary:
            try:
                root = Path(primary).expanduser().resolve(strict=True)
            except (OSError, RuntimeError):
                root = None
            if root is not None and root.is_dir():
                rules.append(WorkspaceRule("primary", "Primary", root))
        configured = self.options.get("workspaces", self.options.get("roots", []))
        if isinstance(configured, list):
            for index, item in enumerate(configured):
                data = item if isinstance(item, dict) else {"path": item}
                raw_path = str(data.get("path") or data.get("root") or "").strip()
                if not raw_path:
                    continue
                try:
                    root = Path(raw_path).expanduser().resolve(strict=True)
                except (OSError, RuntimeError):
                    continue
                if not root.is_dir():
                    continue
                if any(rule.root == root for rule in rules):
                    continue
                rules.append(WorkspaceRule(
                    str(data.get("id") or f"workspace-{index + 1}"),
                    str(data.get("name") or root.name or root),
                    root,
                    "read_only" if str(data.get("mode", "read_write")) == "read_only" else "read_write",
                ))
        if bool(self.options.get("allow_home_read_only", True)):
            rules.append(WorkspaceRule("home-readonly", "用户主目录（只读）", self.home,
                                       "read_only", False))
        return tuple(sorted(rules, key=lambda item: len(str(item.root)), reverse=True))

    def _build_blocked_roots(self) -> tuple[Path, ...]:
        candidates = [
            os.environ.get("WINDIR", r"C:\Windows"),
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            os.environ.get("ProgramData", r"C:\ProgramData"),
            os.environ.get("APPDATA", str(self.home / "AppData" / "Roaming")),
            os.environ.get("LOCALAPPDATA", str(self.home / "AppData" / "Local")),
            str(self.home / "AppData"),
            str(self.app_root / "memory"),
            str(self.app_root / "logs"),
            str(self.app_root / "config"),
        ]
        roots: list[Path] = []
        for value in candidates:
            if value:
                roots.append(Path(value).expanduser().resolve(strict=False))
        return tuple(roots)

    def build_plan(self, operation: str, *, source: str | None = None,
                   destination: str | None = None, content: str = "") -> FileOperationPlan:
        operation = str(operation)
        if operation not in FILE_OPERATIONS:
            raise FilePermissionError("unsupported_operation", f"unsupported file operation: {operation}")
        self._validate_required_fields(operation, source, destination)
        resolved_source = self._normalize(source, destination=False) if source else None
        resolved_destination = self._normalize(destination, destination=True) if destination else None
        self._validate_operation_types(operation, resolved_source, resolved_destination)

        source_state = self.capture_state(resolved_source) if resolved_source else None
        destination_state = self.capture_state(resolved_destination) if resolved_destination else None
        content_bytes = str(content).encode("utf-8")
        content_bound = operation in {"create_text_file", *TEXT_MUTATION_OPERATIONS}
        content_hash = hashlib.sha256(content_bytes).hexdigest() if content_bound else None

        relevant = [path for path in (resolved_source, resolved_destination) if path is not None]
        matches = [self._workspace_for(path) for path in relevant]
        is_write = operation in WRITE_OPERATIONS
        if operation in TEXT_MUTATION_OPERATIONS | {"delete_file"}:
            if any(match is None or match.mode != "read_write" for match in matches):
                raise FilePermissionError(
                    "permission_denied",
                    "modification and deletion require an explicitly writable workspace",
                )
        outside = any(match is None or (is_write and match.mode == "read_only") for match in matches)
        overwrite = bool(destination_state and destination_state.exists) or (
            operation in TEXT_MUTATION_OPERATIONS
        )
        reasons: list[str] = []
        if is_write:
            reasons.append(operation)
        if outside:
            reasons.append("outside_configured_workspace")
        if overwrite:
            reasons.append("overwrite_existing_file")
        risk = "high" if operation == "delete_file" or outside or overwrite else (
            "medium" if is_write else "low"
        )
        requires_confirmation = is_write or outside
        names = tuple(dict.fromkeys(
            match.name for match in matches if match is not None and not (is_write and match.mode == "read_only")
        ))
        plan = FileOperationPlan(
            version=1,
            plan_id=uuid4().hex,
            operation=operation,
            requested_source=str(source) if source is not None else None,
            requested_destination=str(destination) if destination is not None else None,
            resolved_source=str(resolved_source) if resolved_source else None,
            resolved_destination=str(resolved_destination) if resolved_destination else None,
            source_state=source_state,
            destination_state=destination_state,
            content_size=len(content_bytes) if content_bound else 0,
            content_sha256=content_hash,
            workspace_names=names,
            risk=risk,
            risk_reasons=tuple(reasons),
            requires_confirmation=requires_confirmation,
            overwrite=overwrite,
            estimated_items=1,
            diff="",
            impact_scope="single_file",
            recycle_bin=operation == "delete_file",
            file_details=self._file_details(resolved_source) if operation == "delete_file" else None,
            created_at=self.clock(),
            fingerprint="",
        )
        return replace(plan, fingerprint=self._fingerprint(plan))

    def with_diff(self, plan: FileOperationPlan, diff: str) -> FileOperationPlan:
        updated = replace(plan, diff=str(diff), fingerprint="")
        return replace(updated, fingerprint=self._fingerprint(updated))

    def describe_access(self) -> dict[str, Any]:
        rules = [
            {
                "workspace_id": rule.id,
                "name": rule.name,
                "root": str(rule.root),
                "mode": rule.mode,
                "readable": True,
                "writable": rule.mode == "read_write",
                "explicit": rule.explicit,
            }
            for rule in self.workspaces
        ]
        aliases = []
        for alias_id, label in (
            ("desktop", "Desktop"),
            ("documents", "Documents"),
            ("downloads", "Downloads"),
        ):
            path = self.resolve_system_directory(alias_id)
            match = self._workspace_for(path) if path else None
            aliases.append({
                "id": alias_id,
                "name": label,
                "path": str(path) if path else None,
                "accessible": match is not None,
                "mode": match.mode if match else None,
                "workspace_id": match.id if match else None,
            })
        result = {
            "workspaces": rules,
            "system_directories": aliases,
            "primary_workspace_id": self.primary.id if self.primary else None,
        }
        return {
            "ok": True,
            "operation": "describe_file_access",
            "path": None,
            "result": result,
            "error_code": None,
            "message": "",
            **result,
        }

    def revalidate(self, plan: FileOperationPlan, *, content: str = "") -> None:
        source = self._normalize(plan.requested_source, destination=False) if plan.requested_source else None
        destination = self._normalize(plan.requested_destination, destination=True) if plan.requested_destination else None
        if ((str(source) if source else None) != plan.resolved_source
                or (str(destination) if destination else None) != plan.resolved_destination):
            raise FilePermissionError("file_state_changed", "resolved path changed after confirmation")
        if source and self.capture_state(source) != plan.source_state:
            raise FilePermissionError("file_state_changed", "source changed after confirmation")
        if destination and self.capture_state(destination) != plan.destination_state:
            raise FilePermissionError("file_state_changed", "destination changed after confirmation")
        if plan.operation in {"create_text_file", *TEXT_MUTATION_OPERATIONS}:
            content_bytes = str(content).encode("utf-8")
            if (len(content_bytes) != plan.content_size
                    or hashlib.sha256(content_bytes).hexdigest() != plan.content_sha256):
                raise FilePermissionError("file_state_changed", "content changed after confirmation")

    def _normalize(self, raw: str | None, *, destination: bool) -> Path:
        text = str(raw or "").strip()
        self._validate_raw_path(text)
        alias_path = self._resolve_alias_path(text)
        expanded = alias_path if alias_path is not None else Path(text).expanduser()
        if not expanded.is_absolute():
            if self.primary is None:
                raise FilePermissionError("workspace_not_configured", "relative paths need a primary workspace")
            candidate = self.primary.root / expanded
            resolved_candidate = candidate.resolve(strict=False)
            if not self._is_within(resolved_candidate, self.primary.root):
                raise FilePermissionError("path_escape", "relative path escapes the primary workspace")
        else:
            candidate = expanded
        self._assert_no_reparse(candidate)
        try:
            resolved = candidate.resolve(strict=not destination)
        except FileNotFoundError as exc:
            raise FilePermissionError("path_not_found", f"path does not exist: {candidate}") from exc
        self._assert_safe_real_path(resolved)
        return resolved

    def _resolve_alias_path(self, text: str) -> Path | None:
        normalized = text.strip().replace("\\", "/")
        if not normalized or normalized.startswith((".", "~", "/")):
            return None
        parts = [part for part in normalized.split("/") if part]
        if not parts:
            return None
        alias = SYSTEM_DIRECTORY_ALIASES.get(parts[0].lower()) or SYSTEM_DIRECTORY_ALIASES.get(parts[0])
        if alias is None:
            return None
        alias_id, _label = alias
        root = self.resolve_system_directory(alias_id)
        if root is None:
            raise FilePermissionError("PATH_NOT_RESOLVED", f"system directory is not available: {parts[0]}")
        candidate = root
        for part in parts[1:]:
            candidate /= part
        return candidate

    def resolve_system_directory(self, alias_id: str) -> Path | None:
        alias_id = str(alias_id).lower()
        if alias_id == "home":
            return self.home
        resolver = self.options.get("system_directory_resolver")
        if callable(resolver):
            value = resolver(alias_id)
            return Path(value).expanduser().resolve(strict=False) if value else None
        if os.name == "nt":
            return self._windows_known_folder(alias_id) or self._windows_user_shell_folder(alias_id)
        fallback_names = {
            "desktop": "Desktop",
            "documents": "Documents",
            "downloads": "Downloads",
            "pictures": "Pictures",
            "music": "Music",
            "videos": "Videos",
        }
        name = fallback_names.get(alias_id)
        return (self.home / name).resolve(strict=False) if name else None

    @staticmethod
    def _windows_known_folder(alias_id: str) -> Path | None:
        folder_id = KNOWN_FOLDER_IDS.get(alias_id)
        if not folder_id:
            return None
        try:
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [
                    ("Data1", ctypes.c_ulong),
                    ("Data2", ctypes.c_ushort),
                    ("Data3", ctypes.c_ushort),
                    ("Data4", ctypes.c_ubyte * 8),
                ]

            guid = GUID()
            ctypes.windll.ole32.CLSIDFromString(folder_id, ctypes.byref(guid))
            path_ptr = ctypes.c_wchar_p()
            result = ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(guid), 0, None, ctypes.byref(path_ptr),
            )
            if result != 0 or not path_ptr.value:
                return None
            value = path_ptr.value
            ctypes.windll.ole32.CoTaskMemFree(path_ptr)
            return Path(value).expanduser().resolve(strict=False)
        except Exception:
            return None

    @staticmethod
    def _windows_user_shell_folder(alias_id: str) -> Path | None:
        names = {
            "desktop": "Desktop",
            "documents": "Personal",
            "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
            "pictures": "My Pictures",
            "music": "My Music",
            "videos": "My Video",
        }
        name = names.get(alias_id)
        if not name:
            return None
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
            ) as key:
                value, _kind = winreg.QueryValueEx(key, name)
            expanded = os.path.expandvars(str(value))
            return Path(expanded).expanduser().resolve(strict=False)
        except Exception:
            return None

    def _validate_raw_path(self, text: str) -> None:
        if not text:
            raise FilePermissionError("path_required", "path is required")
        lowered = text.replace("/", "\\").lower()
        if "\x00" in text:
            raise FilePermissionError("invalid_path", "NUL is not allowed in paths")
        if lowered.startswith(("\\\\.\\", "\\\\?\\", "\\??\\")):
            raise FilePermissionError("device_path", "Windows device paths are forbidden")
        if lowered.startswith("\\\\") or text.startswith("//"):
            raise FilePermissionError("unc_path", "UNC paths are forbidden")
        _drive, tail = ntpath.splitdrive(text)
        if ":" in tail:
            raise FilePermissionError("ntfs_ads", "NTFS alternate data streams are forbidden")
        for part in PureWindowsPath(text).parts:
            if part in {".", ".."}:
                continue
            clean = part.rstrip(" .")
            stem = clean.split(".", 1)[0].upper()
            if stem in self.RESERVED_NAMES:
                raise FilePermissionError("reserved_name", f"reserved Windows name: {stem}")
            if clean != part and part not in {"\\", "/"}:
                raise FilePermissionError("invalid_path", "trailing dots or spaces are forbidden")

    def _assert_safe_real_path(self, path: Path) -> None:
        if path == Path(path.anchor):
            raise FilePermissionError("drive_root", "operations on a drive root are forbidden")
        lowered_parts = [part.lower() for part in path.parts]
        if ".ssh" in lowered_parts:
            raise FilePermissionError("protected_path", ".ssh is forbidden")
        lowered = str(path).replace("/", "\\").lower()
        browser_markers = (
            "\\google\\chrome\\user data", "\\microsoft\\edge\\user data",
            "\\mozilla\\firefox\\profiles",
        )
        if any(marker in lowered for marker in browser_markers):
            raise FilePermissionError("protected_path", "browser credential directories are forbidden")
        for root in self._blocked_roots:
            if self._is_within(path, root):
                raise FilePermissionError("protected_path", f"protected Maidie or system path: {root}")

    def _assert_no_reparse(self, path: Path) -> None:
        absolute = path.absolute()
        current = Path(absolute.anchor)
        for part in absolute.parts[1:]:
            current /= part
            if not os.path.lexists(current):
                break
            if self._is_reparse_point(current):
                raise FilePermissionError("reparse_point", f"symlink/junction is forbidden: {current}")

    @staticmethod
    def _is_reparse_point(path: Path) -> bool:
        try:
            info = path.lstat()
        except OSError:
            return False
        attributes = int(getattr(info, "st_file_attributes", 0))
        return stat.S_ISLNK(info.st_mode) or bool(attributes & 0x400)

    def _workspace_for(self, path: Path) -> WorkspaceRule | None:
        return next((rule for rule in self.workspaces if self._is_within(path, rule.root)), None)

    @staticmethod
    def _is_within(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    @staticmethod
    def _validate_required_fields(operation: str, source: str | None,
                                  destination: str | None) -> None:
        if operation in {
            "list_directory", "stat_file", "search_files", "read_text_file", "read_file",
            "append_file", "replace_exact", "delete_file",
        } and not source:
            raise FilePermissionError("source_required", "source path is required")
        if operation == "create_text_file" and not destination:
            raise FilePermissionError("destination_required", "destination path is required")
        if operation in {"copy_file", "move_file", "rename_file"} and (not source or not destination):
            raise FilePermissionError("paths_required", "source and destination are required")

    def _validate_operation_types(self, operation: str, source: Path | None,
                                  destination: Path | None) -> None:
        if operation == "delete_file" and source is not None:
            if any(source == rule.root for rule in self.workspaces):
                raise FilePermissionError("workspace_root_forbidden", "workspace roots cannot be deleted")
        if operation in {
            "read_text_file", "read_file", "copy_file", "move_file", "rename_file",
            "append_file", "replace_exact", "delete_file",
        }:
            if source is None or not source.is_file():
                raise FilePermissionError("source_not_file", "source must be an existing file")
        if operation in {"list_directory", "search_files"}:
            if source is None or not source.is_dir():
                raise FilePermissionError("source_not_directory", "source must be an existing directory")
        if operation == "rename_file" and source and destination and source.parent != destination.parent:
            raise FilePermissionError("rename_cross_directory", "rename_file must stay in the same directory")
        if destination and destination.exists() and destination.is_dir():
            raise FilePermissionError("destination_is_directory", "destination cannot be a directory")

    @staticmethod
    def capture_state(path: Path) -> FileState:
        if not path.exists():
            return FileState(False)
        info = path.stat()
        kind = "directory" if path.is_dir() else "file" if path.is_file() else "other"
        digest = None
        if kind == "file":
            digest = FilePermissionPolicy.sha256(path)
        return FileState(True, kind, int(info.st_size), int(info.st_mtime_ns), digest)

    @staticmethod
    def _file_details(path: Path | None) -> dict[str, Any] | None:
        if path is None or not path.is_file():
            return None
        info = path.stat()
        return {
            "path": str(path),
            "size": int(info.st_size),
            "created_time": float(info.st_ctime),
            "modified_time": float(info.st_mtime),
            "type": "file",
        }

    @staticmethod
    def sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _fingerprint(plan: FileOperationPlan) -> str:
        payload = asdict(plan)
        payload.pop("fingerprint", None)
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
