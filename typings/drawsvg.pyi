from types import ModuleType
from typing import Any

class Image:
    def __init__(self, *args: object, **kwargs: object) -> None: ...
    def add_key_frame(self, time: float, *, opacity: float) -> None: ...

class Drawing:
    def __init__(self, *args: object, **kwargs: object) -> None: ...
    def append(self, element: Image, *, z: int | None = None) -> None: ...
    def save_svg(
        self,
        fname: str,
        encoding: str = "utf-8",
        context: dict[str, Any] | None = None,
    ) -> None: ...

class SyncedAnimationConfig:
    def __init__(
        self,
        *,
        duration: float,
        show_playback_progress: bool,
        show_playback_controls: bool,
    ) -> None: ...

class TypesSubmodule(ModuleType):
    SyncedAnimationConfig: type[SyncedAnimationConfig]

types: TypesSubmodule
