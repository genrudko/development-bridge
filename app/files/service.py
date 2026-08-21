from __future__ import annotations

from pathlib import Path, PurePosixPath

from app.api.errors import BridgeError, ErrorCode
from app.capabilities import Capability, CapabilityPolicy
from app.projects import Repository

from .models import FileEntry, FileMatch


class FileService:
    MAX_FILE_BYTES = 1024 * 1024
    MAX_LIST_ENTRIES = 1000
    MAX_SEARCH_FILES = 10_000
    MAX_SEARCH_RESULTS = 100
    MAX_MATCH_TEXT = 1000

    def __init__(self, policy: CapabilityPolicy) -> None:
        self._policy = policy

    def list(
        self, repository: Repository, path: str = "", *, recursive: bool = False
    ) -> tuple[FileEntry, ...]:
        target = self._resolve(repository, path, expect_directory=True)
        entries: list[FileEntry] = []
        iterator = target.rglob("*") if recursive else target.iterdir()
        for candidate in iterator:
            relative = candidate.relative_to(repository.root)
            if self._is_internal(relative) or self._has_symlink_component(repository.root, relative):
                continue
            stat = candidate.stat()
            entry_type = "directory" if candidate.is_dir() else "file"
            entries.append(
                FileEntry(
                    relative.as_posix(),
                    entry_type,
                    stat.st_size if entry_type == "file" else None,
                )
            )
            if len(entries) > self.MAX_LIST_ENTRIES:
                raise self._boundary_error(
                    "File listing exceeds the entry limit", limit=self.MAX_LIST_ENTRIES
                )
        return tuple(sorted(entries, key=lambda entry: entry.path))

    def read(self, repository: Repository, path: str) -> str:
        target = self._resolve(repository, path, expect_file=True)
        size = target.stat().st_size
        if size > self.MAX_FILE_BYTES:
            raise self._boundary_error(
                "File exceeds the read size limit", limit=self.MAX_FILE_BYTES, size=size
            )
        data = target.read_bytes()
        if b"\0" in data:
            raise self._boundary_error("Binary files cannot be read")
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise self._boundary_error("File is not valid UTF-8 text") from exc

    def search(
        self,
        repository: Repository,
        query: str,
        path: str = "",
        *,
        max_results: int = MAX_SEARCH_RESULTS,
        case_sensitive: bool = True,
    ) -> tuple[FileMatch, ...]:
        if not query:
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Search query must not be empty")
        if not 1 <= max_results <= self.MAX_SEARCH_RESULTS:
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "max_results is outside the allowed range",
                details={"minimum": 1, "maximum": self.MAX_SEARCH_RESULTS},
            )
        target = self._resolve(repository, path)
        candidates = (target,) if target.is_file() else target.rglob("*")
        needle = query if case_sensitive else query.casefold()
        matches: list[FileMatch] = []
        examined = 0
        for candidate in candidates:
            relative = candidate.relative_to(repository.root)
            if (
                self._is_internal(relative)
                or self._has_symlink_component(repository.root, relative)
                or not candidate.is_file()
            ):
                continue
            examined += 1
            if examined > self.MAX_SEARCH_FILES:
                raise self._boundary_error(
                    "File search exceeds the traversal limit", limit=self.MAX_SEARCH_FILES
                )
            if candidate.stat().st_size > self.MAX_FILE_BYTES:
                continue
            try:
                with candidate.open("r", encoding="utf-8") as source:
                    for line_number, line in enumerate(source, start=1):
                        comparable = line if case_sensitive else line.casefold()
                        if needle in comparable:
                            matches.append(
                                FileMatch(
                                    relative.as_posix(),
                                    line_number,
                                    line.rstrip("\r\n")[: self.MAX_MATCH_TEXT],
                                )
                            )
                            if len(matches) >= max_results:
                                return tuple(matches)
            except (UnicodeDecodeError, OSError):
                continue
        return tuple(matches)

    def _resolve(
        self,
        repository: Repository,
        path: str,
        *,
        expect_file: bool = False,
        expect_directory: bool = False,
    ) -> Path:
        self._policy.require(
            repository.capabilities,
            Capability.READ,
            project_id=repository.project_id,
            repository_id=repository.id,
        )
        if not isinstance(path, str):
            raise BridgeError(ErrorCode.INVALID_ARGUMENT, "Path must be a string")
        normalized = PurePosixPath(path or ".")
        if normalized.is_absolute() or ".." in normalized.parts or self._is_internal(normalized):
            raise self._boundary_error(
                "Path is outside the repository file boundary", path=path
            )
        candidate = repository.root.joinpath(*normalized.parts)
        if self._has_symlink_component(repository.root, normalized):
            raise self._boundary_error("Symbolic links cannot be followed", path=path)
        try:
            candidate.relative_to(repository.root)
        except ValueError as exc:
            raise self._boundary_error(
                "Path is outside the repository file boundary", path=path
            ) from exc
        if not candidate.exists():
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT, "Path does not exist", details={"path": path}
            )
        if expect_file and not candidate.is_file():
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT, "Path is not a file", details={"path": path}
            )
        if expect_directory and not candidate.is_dir():
            raise BridgeError(
                ErrorCode.INVALID_ARGUMENT,
                "Path is not a directory",
                details={"path": path},
            )
        return candidate

    @staticmethod
    def _is_internal(path: PurePosixPath | Path) -> bool:
        return bool(path.parts) and path.parts[0] == ".git"

    @staticmethod
    def _has_symlink_component(root: Path, relative: PurePosixPath | Path) -> bool:
        current = root
        for part in relative.parts:
            if part in ("", "."):
                continue
            current = current / part
            if current.is_symlink():
                return True
        return False

    @staticmethod
    def _boundary_error(message: str, **details: int | str) -> BridgeError:
        return BridgeError(ErrorCode.POLICY_VIOLATION, message, details=details)
