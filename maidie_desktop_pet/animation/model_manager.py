from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class AnimationModel:
    id: str
    name: str
    backend: str
    model3_json: str
    source: str
    imported_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AnimationModelRegistry:
    """In-memory registry for external animation models; never copies assets."""

    def __init__(self, models: Iterable[AnimationModel | dict[str, Any]] | None = None,
                 current_model_id: str = "") -> None:
        self._models: dict[str, AnimationModel] = {}
        self.current_model_id = str(current_model_id or "")
        for model in models or ():
            try:
                self.register_model(self._coerce(model))
            except (TypeError, ValueError):
                continue

    def scan_model_root(self, path: str | Path) -> list[AnimationModel]:
        root = Path(path).expanduser()
        if not root.is_dir():
            return []
        found: list[AnimationModel] = []
        for model_path in sorted(root.rglob("*.model3.json"), key=lambda item: str(item).lower()):
            try:
                found.append(self.import_model3_json(model_path, root=root))
            except (FileNotFoundError, ValueError, OSError):
                continue
        return found

    def scan_model_folder(self, path: str | Path) -> list[AnimationModel]:
        folder = Path(path).expanduser()
        if not folder.is_dir():
            return []
        found: list[AnimationModel] = []
        for model_path in sorted(folder.glob("*.model3.json"), key=lambda item: item.name.lower()):
            try:
                found.append(self.import_model3_json(model_path, root=folder))
            except (FileNotFoundError, ValueError, OSError):
                continue
        return found

    def import_model3_json(self, path: str | Path, *, root: str | Path | None = None) -> AnimationModel:
        model_path = Path(path).expanduser().resolve()
        if not model_path.is_file():
            raise FileNotFoundError(f"Live2D model3_json 不存在：{model_path}")
        if not model_path.name.lower().endswith(".model3.json"):
            raise ValueError("Live2D 模型入口必须是 *.model3.json")
        root_path = Path(root).expanduser().resolve() if root else model_path.parent
        try:
            identity = model_path.relative_to(root_path).as_posix()
        except ValueError:
            identity = str(model_path)
        stem = model_path.name[:-len(".model3.json")]
        model_id = f"live2d-{self._slug(stem)}-{hashlib.sha1(identity.encode('utf-8')).hexdigest()[:8]}"
        model = AnimationModel(
            id=model_id,
            name=stem.replace("_", " ").replace("-", " ").strip().title(),
            backend="live2d_web",
            model3_json=str(model_path),
            source="local_scan",
            imported_at=datetime.now(timezone.utc).isoformat(),
            metadata={"relative_path": identity},
        )
        self.register_model(model)
        return model

    def register_model(self, model: AnimationModel) -> AnimationModel:
        if model.backend != "live2d_web":
            raise ValueError("AnimationModelRegistry only accepts live2d_web models")
        if not model.id:
            raise ValueError("animation model id is required")
        self._models[model.id] = model
        return model

    def list_models(self) -> list[AnimationModel]:
        return sorted(self._models.values(), key=lambda item: (item.name.lower(), item.id))

    def set_current_model(self, model_id: str) -> AnimationModel:
        model = self._models.get(str(model_id or ""))
        if model is None:
            raise KeyError(f"未知 Live2D 模型：{model_id}")
        if not Path(model.model3_json).is_file():
            raise FileNotFoundError(f"Live2D model3_json 不存在：{model.model3_json}")
        self.current_model_id = model.id
        return model

    def resolve_current_model(self) -> AnimationModel | None:
        model = self._models.get(self.current_model_id)
        if model is None or not Path(model.model3_json).is_file():
            return None
        return model

    @staticmethod
    def _coerce(value: AnimationModel | dict[str, Any]) -> AnimationModel:
        if isinstance(value, AnimationModel):
            return value
        if not isinstance(value, dict):
            raise TypeError("model must be AnimationModel or dict")
        return AnimationModel(
            id=str(value.get("id", "")),
            name=str(value.get("name", "")),
            backend=str(value.get("backend", "live2d_web")),
            model3_json=str(value.get("model3_json", "")),
            source=str(value.get("source", "config")),
            imported_at=str(value.get("imported_at", "")),
            metadata=dict(value.get("metadata", {})) if isinstance(value.get("metadata"), dict) else {},
        )

    @staticmethod
    def _slug(value: str) -> str:
        slug = "".join(char.lower() if char.isalnum() else "-" for char in value)
        return "-".join(part for part in slug.split("-") if part) or "model"
