from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FileEntry:
    path: str
    type: str
    size: int | None = None

    def as_dict(self) -> dict[str, str | int]:
        result: dict[str, str | int] = {"path": self.path, "type": self.type}
        if self.size is not None:
            result["size"] = self.size
        return result


@dataclass(frozen=True, slots=True)
class FileMatch:
    path: str
    line: int
    text: str

    def as_dict(self) -> dict[str, str | int]:
        return {"path": self.path, "line": self.line, "text": self.text}
