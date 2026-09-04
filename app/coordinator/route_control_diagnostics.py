from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from secrets import token_hex

from app.api.errors import BridgeError, ErrorCode


class RouteControlTraceStore:
    def __init__(self, state_dir: Path, raw_ttl_seconds: int = 86400) -> None:
        self.state_dir = Path(state_dir).expanduser()
        self.raw_ttl_seconds = raw_ttl_seconds

    def _trace_path(self, diagnostic_id: str) -> Path:
        return self.state_dir / f"{diagnostic_id}.json"

    def _create_raw(self, trace_data: dict) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        diag_id = trace_data["diagnostic_id"]
        target = self._trace_path(diag_id)
        tmp = self.state_dir / f"{diag_id}.{token_hex(8)}.tmp"

        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.fchmod(fd, 0o600)
            with open(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps(trace_data, ensure_ascii=False, indent=2) + "\n")
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise

        mode = tmp.stat().st_mode & 0o777
        if mode != 0o600:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise BridgeError(ErrorCode.INTERNAL_ERROR, f"trace file permissions {oct(mode)} are not 0600")

        try:
            os.link(tmp, target)
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    def _save_raw(self, trace_data: dict) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        diag_id = trace_data["diagnostic_id"]
        target = self._trace_path(diag_id)
        tmp = self.state_dir / f"{diag_id}.{token_hex(8)}.tmp"

        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.fchmod(fd, 0o600)
            with open(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps(trace_data, ensure_ascii=False, indent=2) + "\n")
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise

        mode = tmp.stat().st_mode & 0o777
        if mode != 0o600:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise BridgeError(ErrorCode.INTERNAL_ERROR, f"trace file permissions {oct(mode)} are not 0600")

        os.replace(tmp, target)

    def _load_raw(self, diagnostic_id: str) -> dict | None:
        path = self._trace_path(diagnostic_id)
        try:
            stat = path.stat()
            if time.time() - stat.st_mtime > self.raw_ttl_seconds:
                try:
                    path.unlink()
                except OSError:
                    pass
                return None
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return None

    def start(
        self,
        operation_type: str,
        route_id: str | None = None,
        diagnostic_id: str | None = None,
        operation_id: str | None = None,
    ) -> str:
        now = datetime.now(UTC).isoformat()
        if diagnostic_id:
            diag_id = diagnostic_id
            trace_data = {
                "diagnostic_id": diag_id,
                "operation_type": str(operation_type),
                "operation_id": operation_id,
                "route_id": route_id,
                "status": "in_progress",
                "created_at": now,
                "updated_at": now,
                "finished_at": None,
                "error_code": None,
                "stages": [],
            }
            try:
                self._create_raw(trace_data)
            except FileExistsError:
                raise BridgeError(ErrorCode.POLICY_VIOLATION, f"diagnostic trace {diag_id} already exists")
            return diag_id

        for _ in range(10):
            candidate_id = f"bind-{token_hex(12)}"
            trace_data = {
                "diagnostic_id": candidate_id,
                "operation_type": str(operation_type),
                "operation_id": operation_id,
                "route_id": route_id,
                "status": "in_progress",
                "created_at": now,
                "updated_at": now,
                "finished_at": None,
                "error_code": None,
                "stages": [],
            }
            try:
                self._create_raw(trace_data)
                return candidate_id
            except FileExistsError:
                continue

        raise BridgeError(ErrorCode.INTERNAL_ERROR, "failed to generate unique diagnostic id")

    def stage(
        self,
        diagnostic_id: str,
        stage_name: str,
        status: str,
        *,
        error_code: str | None = None,
        details: dict | None = None,
        duration_ms: float | None = None,
    ) -> None:
        trace = self._load_raw(diagnostic_id)
        if trace is None:
            return
        if trace.get("finished_at") is not None or trace.get("status") in ("ok", "failed"):
            return
        now = datetime.now(UTC).isoformat()
        stage_record = {
            "name": str(stage_name),
            "status": str(status),
            "timestamp": now,
        }
        if duration_ms is not None:
            stage_record["duration_ms"] = round(float(duration_ms), 2)
        if error_code is not None:
            stage_record["error_code"] = str(error_code)
        if details is not None:
            stage_record["details"] = details

        trace["stages"].append(stage_record)
        trace["updated_at"] = now
        self._save_raw(trace)

    def finish(
        self,
        diagnostic_id: str,
        *,
        status: str,
        error_code: str | None = None,
    ) -> dict | None:
        trace = self._load_raw(diagnostic_id)
        if trace is None:
            return None
        if trace.get("finished_at") is not None or trace.get("status") in ("ok", "failed"):
            return self.sanitized(diagnostic_id)
        now = datetime.now(UTC).isoformat()
        trace["status"] = str(status)
        trace["finished_at"] = now
        trace["updated_at"] = now
        if error_code is not None:
            trace["error_code"] = str(error_code)
        self._save_raw(trace)
        return self.sanitized(diagnostic_id)

    def sanitized(self, diagnostic_id: str) -> dict | None:
        trace = self._load_raw(diagnostic_id)
        if trace is None:
            return None
        sanitized_stages = []
        for stage in trace.get("stages", []):
            st = {
                "name": stage["name"],
                "status": stage["status"],
                "timestamp": stage.get("timestamp"),
            }
            if "duration_ms" in stage:
                st["duration_ms"] = stage["duration_ms"]
            if "error_code" in stage:
                st["error_code"] = stage["error_code"]
            sanitized_stages.append(st)

        return {
            "diagnostic_id": trace["diagnostic_id"],
            "operation_type": trace["operation_type"],
            "route_id": trace.get("route_id"),
            "status": trace["status"],
            "created_at": trace.get("created_at"),
            "finished_at": trace.get("finished_at"),
            "error_code": trace.get("error_code"),
            "stages": sanitized_stages,
        }

    def find_by_operation_id(self, operation_id: str) -> str | None:
        if not self.state_dir.exists():
            return None
        now = time.time()
        for path in self.state_dir.glob("*.json"):
            try:
                if now - path.stat().st_mtime > self.raw_ttl_seconds:
                    try:
                        path.unlink()
                    except OSError:
                        pass
                    continue
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("operation_id") == operation_id:
                    return str(data.get("diagnostic_id"))
            except (OSError, json.JSONDecodeError):
                continue
        return None

    def latest_diagnostic_id_for_route(self, route_id: str) -> str | None:
        if not self.state_dir.exists():
            return None
        now = time.time()
        latest_time = None
        latest_diag = None
        for path in self.state_dir.glob("*.json"):
            try:
                if now - path.stat().st_mtime > self.raw_ttl_seconds:
                    try:
                        path.unlink()
                    except OSError:
                        pass
                    continue
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("route_id") == route_id:
                    created_at = data.get("created_at") or ""
                    if latest_time is None or created_at > latest_time:
                        latest_time = created_at
                        latest_diag = str(data.get("diagnostic_id"))
            except (OSError, json.JSONDecodeError):
                continue
        return latest_diag

    def get_return_target(self, diagnostic_id: str) -> str | None:
        raw = self._load_raw(diagnostic_id)
        if raw is None:
            return None
        for stage in raw.get("stages", []):
            if stage.get("name") == "return_received" and stage.get("status") == "ok":
                details = stage.get("details")
                if isinstance(details, dict) and details.get("raw_redirect_url"):
                    return str(details["raw_redirect_url"])
        return None

    def purge_expired(self) -> int:
        if not self.state_dir.exists():
            return 0
        now = time.time()
        deleted = 0
        for path in self.state_dir.glob("*.json"):
            try:
                mtime = path.stat().st_mtime
                if now - mtime > self.raw_ttl_seconds:
                    path.unlink()
                    deleted += 1
            except OSError:
                continue
        return deleted
