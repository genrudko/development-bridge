from __future__ import annotations

import base64
import gzip
import hashlib
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.06.153"
CONSOLE_SOURCE_B64 = "__CONSOLE_SOURCE_B64__"
PORTABLE_KIT_TEMPLATE_B64 = "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"
TOPOLOGY_HELPER_SOURCE_B64 = "H4sIAAAAAAAC/71a7XPaOBP/zl+h+sPFnlDnpXfP3JQmN2mS9phpm0wgvXZ6+SBsAXoqLGrJCVyO//1ZyRbYxjImpA8fGLBXu6t9+e1q7UTQaIR6cyHJpNNKcv/8c84YCSTlkfDfk4jENChRvGd8gBn9Byui0r3uVenCTRJJOiF+N5Ik5tMeie9pQESJqk9msnxpHBMcwoVOqxXhCRFTHBB0CQqN+Ac+okGfTznjo/kNEZLHpPXYQvChSk6EGRIEMxKigGEh0GU4Ivp2SqQ+02TAaKDoUY8ncUC6Yad8U8hYaXQZhVMOhJ2qxX0cj4isWKxu3vCH9PqiVdJOgvWCTLvrmI9iPCkrGNN7LIkhzXS5IAEPiZv9u8csId5yyWqx+sREJnEE2sMKIPZv++9+B5fKnl7rnvPonsTSfxfzyVssyH9+zW6kTL3VhjLlK5QacM7QOx5PEoZvyJDEJALnpiZxC8pkCg9T2nbhXjgHBwM3qdcV7ykrxvyhXcUMz6iwbT5vIHRi5KI//kCO06miBCEqCoEWfvl9bqyUMLAi6UZDDjF8j2OKI5ld9KoYfbtDIhkO6YwI4BWRB7hQVE19nBdg/sjkmYP2l/L3kaP/q821G6xTdKvlhQWLon4fqJBvUiVPITiGmX6F625pT4rMPwtD1+mNCZFaogmcPoekfnXspm7zuxdtVGuthkYtaSDjeeH/ui0zByqQgB2ttMuEZep9gtsbFKyKDh2DQ+S+SLn5XfEpYewq/mtMJekpTHKVYM9bmUr/L3JZFP4FWAZj9Fi6utVGbzfs9PbnbfW2vNfbhpstXIaEJBhuGCRLdQcMgYzX7L0NxigzSJNOrTbp562tWeeSM2tIY8grsOtKlf2MV6du3Y+ESyg0J8jZU9mRX51eqeOh7K0xClwUktnV0E3VaKPUCed8MgXPCR75VzGgOGbdUQQ7PwfA9tDpCTpE//5byVl9ipxTRZtz9qx8s8oi44Ssb2tREwzZwiFmgjSuL13xHrZxzmNlGNcUiykeQT6rwo4IfNnqwOasMgyF7gLAj4qz3xvjKRF+F1oRVSC7F66S4ptWwetY+aQBsIGP6Roq+GRhNfuU4pkmNx0IOoEwG5ARjRwECfxW/frioNfIAYovjpXZvCmzr4bZVzuzWVbwqyAoNaJ/ThgTt67eg+dn9E/FJLOHxmLnTxK7JvfgAJ2pFKIhOnp5gVQQokkiJBrQKERvr/p/ooBznTsSir3kSI4hcpWlg2WRruKqre+j/hgqd0gYHZAYOLA5pMd/YZVAn/sXewKNMRu+1FJVNhD0MIb+Cn1BVFQxjZKJ6tXRIJHoK6ygjCk1JKYRdJhnN+71p77r+77n+S1LPtsaOePwtunQ0jiC5raNnC+Oh375xQYVNpbzOpZfnUYVpQAmORo7nNxz8KWy6FkUfgZrDefbwslzgMVzAIUpelqCCvud0aJQh3McnXzD+UXVM+OppzXJhUwt6u/5yjd9bhqZjKioUrk/1B1LsUSkvtRuXK9hcgytsu57laaQ3FdTlX6wvctZQKbqh1sZzVlXpAIXS9daG+ts0bauci5n2ckwNcHywHKvwpQGWkEIdQpn2tcm+h4PF+jxaNExkfR4vDh4fLVw7GIKYbmBzETRBjIToBvIIF4qCdYd1OjgqaL7I0Cbuzx0gRqbDoMxEeCHayzHENeK3v9AohH8O0VHkCDqyrejO5UfzrZnEBWFeY4vTtBxdf/UJP6cWwEh/Do/7fBL444/CYN1PpkR9GbKcHSK3qTbO1XgaauhijK3/2+Hd9ZyG/IAKkokDQzYC7NKtxoqfbxUwHqqI6Fw6tSX3SqFy+19jB9Ub/8OEsC/ITg8Y+wDjYhwzZbaxUGH17T7V56zH3hALBx3VB2lUVWzWzj3Qz8t1fZgkd+bMirdvb/lnmfv/PUCEzIA1sdQSVMu4BmN3hdX5469Dy/5KJsNpQyO7iyCCZTLhtKvz95f1ojPOX5H0b+tib68sIp+rEWa7FwKEaaLuZ1YY3oGhbADPcvwr3EsVtvY0Dm2a3mvqnC2s+O7+gUGSSuVebWbMgC/lWx/3cTWynVh8fGi4kDY2i7p8mHtwfkW2UlNCHo7gK1BVo2O0F2jCRUiD4EHSgqiIfykcu7UnP3wdApm/ggGhuZdzVrPoHG6J1cD1de7zmcqKPfPpoANaUWv42WkK7yEbXeqIBK5KsCoOuAD2VEn+/nmRN/wQB3/ImMj/HOeRDIj2d9vio9GnQBHIQ1VCT5BRb6qZXU11xqoy1x4+SOBdt1dO8AtuTeZ07ULwNdooLEtkuSMv1StY6UeQK363jwdquyzEpi6e4d4hmsR0qG22kbEJcRLEkHzqFr4QoZVVN/8qWiH+DNiAHIUMD9fAJYYb4zADSPiraLPNqZoMqEtCrrdQdJ6TkVadQOIzcZ8NbPDdea3W3LfNueyYPv/5FsqbOdcS9NMMyul2LIyVaSXfqhFppjGenB82KmkSI9+miJtbNL8qaQNGMHRjZIu7AzjmvvQ4gqZKfYjUYqdF1j+XrdkgmdLwuNa5lBp2UfKGBXQMGYLfjus7v+Ru1QYkCX7DdCylGYuNseSvOHV+E3zSQ1SSb88hSwHQ+oQor2xbXSXz5DNVj1lwtGcs/oUx2E5xp2NS40l9/eb0y6tvmnRorX9nXQy6C7zU2/kMo557D3R9k+eFtknR08bENmHRZlpdx8O2QdFpYFQafCzHPB4m3mvHNLZ0r+L6gw9OEBp6OrhewD1iBFoEchsCnkC2ClNc4+HYDOEGcvsJVQmy3HFMD1jq7HFNxPsl9rGhWlcblq/mtX7PxtHdkGDnxDNjaLpOUN+6dCKyWjm5NTBPyUTmi/ZPD59wii18Vi1fsRqGbc2SDcVfRUFtPZpca43sYG+Ggw1WV9TqpVmecrTk6pOxtvUU9rQoA/oMtYzVxQnkUA8kYgP0TTmARECPYwh/jQE4TB8CbkdANIMcPAdkMGKMJipV9zm2YMsAmDTY4RM1QlCP+oDte+JSI9yewLddg8U1ExAHh4RG1PG+RQNY0LUA0mjXkgYnkN+xOQhpuph5YAoSNIKR+qto2BMgu/V2JW+iOdr1dxy/+Z1mo578r5509w1O0FWBWrA0UJ36kLiAWX0H/I6ja8T6NmbRGDDh141zJwD/brXugGegbXpiE/SN8q24NqyYMPadT2B/0tF0Rlj6pWzavOvnrVUo5lzfdbr/S1tVjcY09gmyLEzMwepZ2EWb+erOlbbh1W1LQsPPloNAD57cn64+Sl7vpeebXolq+qIY3/oUvOa2Sp4ahqa9UDMxRyk/s3N1Y22PWi+Mq9Xfk7UaTAwqH5hL2fJI5slF9nbv4vW/wDkuOPZcy0AAA=="


def install(namespace: dict) -> None:
    """Register managed Visio tools into the already-hardened live launcher."""
    mcp = namespace["mcp"]
    visio = namespace["visio"]
    parse_page = namespace["_parse_page"]
    ok = namespace["_ok"]
    err = namespace["_err"]
    workspace = Path(namespace["WORKSPACE"]).resolve()
    root = Path(namespace["ROOT"]).resolve()
    chat_root = root / "operator-chat"
    pending_dir = chat_root / "pending"
    acked_dir = chat_root / "acked"
    replies_dir = chat_root / "replies"
    for _directory in (pending_dir, acked_dir, replies_dir):
        _directory.mkdir(parents=True, exist_ok=True)

    payload_dir = workspace / "managed_payloads"
    payload_dir.mkdir(parents=True, exist_ok=True)

    @mcp.tool()
    def stage_energologic_payload_chunk(
        payload_name: str,
        offset: int,
        content_b64: str,
        total_size: int,
        sha256: str,
        final: bool = False,
    ) -> str:
        """Stage one bounded chunk of a server-pinned EnergoLogic payload."""
        try:
            allowed = {"EnergoLogicVisioEditorAddin.cs"}
            name = str(payload_name)
            if name not in allowed:
                raise ValueError("unsupported EnergoLogic payload")
            expected_size = int(total_size)
            if expected_size < 1 or expected_size > 2 * 1024 * 1024:
                raise ValueError("payload total_size is out of bounds")
            expected_sha = str(sha256).lower()
            if len(expected_sha) != 64 or any(c not in "0123456789abcdef" for c in expected_sha):
                raise ValueError("invalid payload sha256")

            chunk = base64.b64decode(str(content_b64), validate=True)
            if not chunk or len(chunk) > 24 * 1024:
                raise ValueError("payload chunk must contain 1..24576 bytes")

            target = payload_dir / name
            partial = payload_dir / (name + ".part")
            position = int(offset)
            if position < 0 or position > expected_size:
                raise ValueError("invalid payload offset")
            if position == 0:
                partial.unlink(missing_ok=True)
            current = partial.stat().st_size if partial.exists() else 0
            if current != position:
                raise RuntimeError(
                    f"payload offset mismatch: expected {current}, got {position}"
                )
            with partial.open("ab") as handle:
                handle.write(chunk)

            received = partial.stat().st_size
            if received > expected_size:
                raise RuntimeError("payload exceeds declared total_size")

            ready = False
            if bool(final):
                if received != expected_size:
                    raise RuntimeError(
                        f"final payload size mismatch: {received} != {expected_size}"
                    )
                actual_sha = hashlib.sha256(partial.read_bytes()).hexdigest()
                if actual_sha != expected_sha:
                    raise RuntimeError(
                        f"payload sha256 mismatch: {actual_sha} != {expected_sha}"
                    )
                partial.replace(target)
                ready = True

            return ok({
                "payload_name": name,
                "received": received,
                "total_size": expected_size,
                "sha256": expected_sha,
                "ready": ready,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def build_energologic_portable_kit(
        include_personal_stencils: bool = True,
    ) -> str:
        """Build an offline EnergoLogic Visio Editor ZIP on the local desktop."""
        try:
            import io
            import json
            import os
            import shutil
            import zipfile
            from datetime import datetime, timezone

            version = "0.3.49"
            kit_name = "EnergoLogic-Visio-Editor-Kit-" + version
            staged_editor_source = (
                payload_dir / "EnergoLogicVisioEditorAddin.cs"
            )
            if not staged_editor_source.is_file():
                raise FileNotFoundError(
                    "EnergoLogic editor payload is not staged; "
                    "run visio_managed_update first"
                )

            home = Path.home()
            desktop_candidates = [
                home / "Desktop",
                home / "Рабочий стол",
            ]
            for env_name in (
                "OneDrive",
                "OneDriveConsumer",
                "OneDriveCommercial",
            ):
                value = os.environ.get(env_name, "")
                if value:
                    desktop_candidates.extend([
                        Path(value) / "Desktop",
                        Path(value) / "Рабочий стол",
                    ])

            export_root = next(
                (item for item in desktop_candidates if item.is_dir()),
                workspace / "exports",
            )
            export_root.mkdir(parents=True, exist_ok=True)

            kit_dir = export_root / kit_name
            zip_path = export_root / (kit_name + ".zip")
            if kit_dir.exists():
                shutil.rmtree(kit_dir)
            if zip_path.exists():
                zip_path.unlink()
            kit_dir.mkdir(parents=True, exist_ok=True)

            # The embedded template contains only repo-maintained scripts/docs.
            template_raw = gzip.decompress(
                base64.b64decode(PORTABLE_KIT_TEMPLATE_B64)
            )
            with zipfile.ZipFile(io.BytesIO(template_raw), "r") as archive:
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    relative = Path(info.filename)
                    if (
                        relative.is_absolute()
                        or ".." in relative.parts
                        or len(relative.parts) != 1
                    ):
                        raise RuntimeError(
                            "Portable kit template contains unsafe path"
                        )
                    target = kit_dir / relative.name
                    target.write_bytes(archive.read(info))

            payload = kit_dir / "payload"
            payload.mkdir(parents=True, exist_ok=True)
            shutil.copy2(
                staged_editor_source,
                payload / "EnergoLogicVisioEditorAddin.cs",
            )
            (payload / "EnergoLogicTopologyRestoreHelper.cs").write_bytes(
                gzip.decompress(
                    base64.b64decode(TOPOLOGY_HELPER_SOURCE_B64)
                )
            )

            stencils_dir = kit_dir / "stencils"
            stencils_dir.mkdir(parents=True, exist_ok=True)
            copied_stencils = []
            searched_roots = []
            if bool(include_personal_stencils):
                stencil_roots = []
                for env_name in (
                    "OneDrive",
                    "OneDriveConsumer",
                    "OneDriveCommercial",
                ):
                    value = os.environ.get(env_name, "")
                    if value:
                        stencil_roots.append(
                            Path(value)
                            / "Documents"
                            / "Мои фигуры"
                            / "ГОСТ"
                        )
                stencil_roots.extend([
                    home / "OneDrive" / "Documents" / "Мои фигуры" / "ГОСТ",
                    home / "Documents" / "Мои фигуры" / "ГОСТ",
                ])
                try:
                    stencil_roots.extend(
                        home.glob(
                            "OneDrive*/Documents/Мои фигуры/ГОСТ"
                        )
                    )
                except Exception:
                    pass

                seen_roots = set()
                seen_names = set()
                for stencil_root in stencil_roots:
                    try:
                        resolved = stencil_root.resolve()
                    except Exception:
                        resolved = stencil_root
                    key = str(resolved).lower()
                    if key in seen_roots or not stencil_root.is_dir():
                        continue
                    seen_roots.add(key)
                    searched_roots.append(str(stencil_root))

                    for source in sorted(stencil_root.iterdir()):
                        if not source.is_file():
                            continue
                        if source.suffix.lower() not in {
                            ".vss",
                            ".vssx",
                            ".vssm",
                        }:
                            continue
                        source_lower = str(source).lower().replace("/", "\\")
                        if "\\programdata\\" in source_lower:
                            continue
                        if "\\vtd\\" in source_lower:
                            continue
                        name_key = source.name.lower()
                        if name_key in seen_names:
                            continue
                        target = stencils_dir / source.name
                        shutil.copy2(source, target)
                        seen_names.add(name_key)
                        copied_stencils.append({
                            "name": source.name,
                            "source": str(source),
                            "size": target.stat().st_size,
                            "sha256": hashlib.sha256(
                                target.read_bytes()
                            ).hexdigest(),
                        })

            manifest_files = []
            for item in sorted(kit_dir.rglob("*")):
                if not item.is_file() or item.name == "MANIFEST.json":
                    continue
                raw = item.read_bytes()
                manifest_files.append({
                    "path": item.relative_to(kit_dir).as_posix(),
                    "size": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                })

            manifest = {
                "schema": 1,
                "product": "EnergoLogic Visio Editor Kit",
                "version": version,
                "editor_api_version": "0.3.49",
                "managed_extension_version": MANAGED_EXTENSION_VERSION,
                "built_utc": datetime.now(timezone.utc).isoformat(),
                "personal_stencils_included": len(copied_stencils),
                "files": manifest_files,
            }
            (kit_dir / "MANIFEST.json").write_text(
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            # Validate the exact portable payload with the target-side
            # installer before publishing the ZIP. CompileOnly does not touch COM
            # registration and is safe while Visio is running.
            import subprocess
            install_script = kit_dir / "Install-EnergoLogic.ps1"
            validation = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(install_script),
                    "-CompileOnly",
                    "-NoShortcut",
                ],
                cwd=str(kit_dir),
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if validation.returncode != 0:
                raise RuntimeError(
                    "Portable kit CompileOnly validation failed: "
                    + (validation.stdout + "\n" + validation.stderr)[-6000:]
                )

            with zipfile.ZipFile(
                zip_path,
                "w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            ) as archive:
                for item in sorted(kit_dir.rglob("*")):
                    if item.is_file():
                        archive.write(
                            item,
                            arcname=(
                                kit_name
                                + "/"
                                + item.relative_to(kit_dir).as_posix()
                            ),
                        )

            zip_raw = zip_path.read_bytes()
            return ok({
                "kit_name": kit_name,
                "kit_directory": str(kit_dir),
                "zip_path": str(zip_path),
                "zip_size": len(zip_raw),
                "zip_sha256": hashlib.sha256(zip_raw).hexdigest(),
                "personal_stencils_included": len(copied_stencils),
                "stencils": copied_stencils,
                "stencil_roots": searched_roots,
                "manifest_files": len(manifest_files),
                "portable_compile_validation": "PASS",
                "portable_compile_stdout_tail": validation.stdout[-2000:],
                "third_party_vtd_included": False,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def render_page_png(page: str = "", doc_name: str = "") -> types.ImageContent:
        """Render an existing Visio page to PNG and return the actual image bytes.

        This is read-only with respect to the Visio document. A short-lived PNG is
        created only inside the approved Visio workspace and deleted immediately
        after the bytes are read.
        """
        output = workspace / f".visio-snapshot-{uuid.uuid4().hex}.png"
        try:
            page_obj = visio._resolve_page(doc_name, parse_page(page))
            page_obj.Export(str(output))
            raw = output.read_bytes()
            if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
                raise RuntimeError("Visio page export did not produce a PNG")
            if len(raw) > 32 * 1024 * 1024:
                raise RuntimeError("Visio page PNG exceeds the 32 MiB visual limit")
            return types.ImageContent(
                type="image",
                data=base64.b64encode(raw).decode("ascii"),
                mimeType="image/png",
            )
        finally:
            try:
                output.unlink(missing_ok=True)
            except OSError:
                pass

    @mcp.tool()
    def read_connection_points(
        shape_id: int,
        page: str = "",
        doc_name: str = "",
    ) -> str:
        """Read existing connection points from one Visio shape."""
        try:
            page_obj = visio._resolve_page(doc_name, parse_page(page))
            shape = page_obj.Shapes.ItemFromID(int(shape_id))
            section = 7  # visSectionConnectionPts
            points = []
            try:
                count = int(shape.RowCount(section))
            except Exception:
                count = 0
            for row_index in range(count):
                try:
                    row = shape.Section(section).Row(row_index)
                    x_iu = float(row.Cell(0).ResultIU)
                    y_iu = float(row.Cell(1).ResultIU)
                    page_x_iu = None
                    page_y_iu = None
                    transform_error = None
                    try:
                        transformed = shape.XYToPage(x_iu, y_iu)
                        if isinstance(transformed, (tuple, list)) and len(transformed) >= 2:
                            page_x_iu = float(transformed[0])
                            page_y_iu = float(transformed[1])
                        else:
                            transform_error = (
                                "XYToPage returned unsupported result "
                                f"{transformed!r}"
                            )
                    except Exception as transform_exc:
                        transform_error = str(transform_exc)
                    points.append({
                        "row": row_index,
                        "connection_row": row_index + 1,
                        "x_formula_u": str(row.Cell(0).FormulaU),
                        "y_formula_u": str(row.Cell(1).FormulaU),
                        "x_result_iu": x_iu,
                        "y_result_iu": y_iu,
                        "page_x_iu": page_x_iu,
                        "page_y_iu": page_y_iu,
                        "page_x_mm": None if page_x_iu is None else page_x_iu * 25.4,
                        "page_y_mm": None if page_y_iu is None else page_y_iu * 25.4,
                        "page_transform_error": transform_error,
                    })
                except Exception:
                    continue
            return ok({
                "shape_id": int(shape.ID),
                "shape_name": str(shape.Name),
                "points": points,
            })
        except Exception as exc:
            return err(exc)


    @mcp.tool()
    def set_1d_shape_endpoints(
        shape_id: int,
        begin_x_mm: float,
        begin_y_mm: float,
        end_x_mm: float,
        end_y_mm: float,
        page: str = "",
        doc_name: str = "",
    ) -> str:
        """Set endpoints of one existing 1-D shape using bounded page coordinates in mm."""
        try:
            values = [float(begin_x_mm), float(begin_y_mm), float(end_x_mm), float(end_y_mm)]
            if any(v < -1000.0 or v > 6000.0 for v in values):
                raise ValueError("1-D endpoint coordinates must be between -1000 and 6000 mm")
            page_obj = visio._resolve_page(doc_name, parse_page(page))
            shape = page_obj.Shapes.ItemFromID(int(shape_id))
            before = {
                "BeginX": str(shape.CellsU("BeginX").FormulaU),
                "BeginY": str(shape.CellsU("BeginY").FormulaU),
                "EndX": str(shape.CellsU("EndX").FormulaU),
                "EndY": str(shape.CellsU("EndY").FormulaU),
            }
            shape.CellsU("BeginX").FormulaU = f"{values[0]} mm"
            shape.CellsU("BeginY").FormulaU = f"{values[1]} mm"
            shape.CellsU("EndX").FormulaU = f"{values[2]} mm"
            shape.CellsU("EndY").FormulaU = f"{values[3]} mm"
            after = {
                "BeginX": str(shape.CellsU("BeginX").FormulaU),
                "BeginY": str(shape.CellsU("BeginY").FormulaU),
                "EndX": str(shape.CellsU("EndX").FormulaU),
                "EndY": str(shape.CellsU("EndY").FormulaU),
            }
            return ok({
                "shape_id": int(shape.ID),
                "shape_name": str(shape.Name),
                "before": before,
                "after": after,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def set_text_control_position(
        shape_id: int,
        x_mm: float,
        y_mm: float,
        page: str = "",
        doc_name: str = "",
    ) -> str:
        """Move an existing shape's native text control point (Controls.Row_2) in local mm."""
        try:
            x = float(x_mm)
            y = float(y_mm)
            if not (-500.0 <= x <= 500.0 and -500.0 <= y <= 500.0):
                raise ValueError("Text control coordinates must be between -500 and 500 mm")
            page_obj = visio._resolve_page(doc_name, parse_page(page))
            shape = page_obj.Shapes.ItemFromID(int(shape_id))
            section = 9  # visSectionControls
            if int(shape.RowCount(section)) < 2:
                raise KeyError("Shape has no Controls.Row_2 text control")
            row = shape.Section(section).Row(1)
            before = {
                "x_formula_u": str(row.Cell(0).FormulaU),
                "y_formula_u": str(row.Cell(1).FormulaU),
                "x_result_iu": float(row.Cell(0).ResultIU),
                "y_result_iu": float(row.Cell(1).ResultIU),
            }
            row.Cell(0).FormulaU = f"{x} mm"
            row.Cell(1).FormulaU = f"{y} mm"
            after = {
                "x_formula_u": str(row.Cell(0).FormulaU),
                "y_formula_u": str(row.Cell(1).FormulaU),
                "x_result_iu": float(row.Cell(0).ResultIU),
                "y_result_iu": float(row.Cell(1).ResultIU),
            }
            return ok({
                "shape_id": int(shape.ID),
                "shape_name": str(shape.Name),
                "before": before,
                "after": after,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def batch_set_1d_shape_endpoints(
        items_json: str,
        page: str = "",
        doc_name: str = "",
    ) -> str:
        """Batch-set endpoints of existing 1-D shapes using bounded mm coordinates."""
        try:
            import json
            items = json.loads(items_json)
            if not isinstance(items, list) or not items or len(items) > 300:
                raise ValueError("items_json must be a JSON array with 1..300 items")
            page_obj = visio._resolve_page(doc_name, parse_page(page))
            results = []
            for item in items:
                sid = int(item["shape_id"])
                vals = [float(item[k]) for k in ("begin_x_mm","begin_y_mm","end_x_mm","end_y_mm")]
                if any(v < -1000.0 or v > 6000.0 for v in vals):
                    raise ValueError(f"1-D endpoint coordinate out of bounds for shape {sid}")
                shape = page_obj.Shapes.ItemFromID(sid)
                shape.CellsU("BeginX").FormulaU = f"{vals[0]} mm"
                shape.CellsU("BeginY").FormulaU = f"{vals[1]} mm"
                shape.CellsU("EndX").FormulaU = f"{vals[2]} mm"
                shape.CellsU("EndY").FormulaU = f"{vals[3]} mm"
                results.append({"shape_id": sid, "shape_name": str(shape.Name)})
            return ok({"count": len(results), "results": results})
        except Exception as exc:
            return err(exc)


    @mcp.tool()
    def batch_set_shape_text(
        items_json: str,
        page: str = "",
        doc_name: str = "",
    ) -> str:
        """Batch-set text on existing shapes."""
        try:
            import json
            items = json.loads(items_json)
            if not isinstance(items, list) or not items or len(items) > 300:
                raise ValueError("items_json must be a JSON array with 1..300 items")
            page_obj = visio._resolve_page(doc_name, parse_page(page))
            results = []
            for item in items:
                sid = int(item["shape_id"])
                text_value = str(item.get("text", ""))
                if len(text_value) > 2000:
                    raise ValueError(f"Text too long for shape {sid}")
                shape = page_obj.Shapes.ItemFromID(sid)
                shape.Text = text_value
                results.append({"shape_id": sid, "shape_name": str(shape.Name), "text": text_value})
            return ok({"count": len(results), "results": results})
        except Exception as exc:
            return err(exc)


    @mcp.tool()
    def batch_set_text_control_positions(
        items_json: str,
        page: str = "",
        doc_name: str = "",
    ) -> str:
        """Batch-move native Controls.Row_2 text anchors in local mm."""
        try:
            import json
            items = json.loads(items_json)
            if not isinstance(items, list) or not items or len(items) > 300:
                raise ValueError("items_json must be a JSON array with 1..300 items")
            page_obj = visio._resolve_page(doc_name, parse_page(page))
            results = []
            for item in items:
                sid = int(item["shape_id"])
                x = float(item["x_mm"]); y = float(item["y_mm"])
                if not (-500.0 <= x <= 500.0 and -500.0 <= y <= 500.0):
                    raise ValueError(f"Text control coordinate out of bounds for shape {sid}")
                shape = page_obj.Shapes.ItemFromID(sid)
                section = 9
                if int(shape.RowCount(section)) < 2:
                    raise KeyError(f"Shape {sid} has no Controls.Row_2 text control")
                row = shape.Section(section).Row(1)
                row.Cell(0).FormulaU = f"{x} mm"
                row.Cell(1).FormulaU = f"{y} mm"
                results.append({"shape_id": sid, "shape_name": str(shape.Name)})
            return ok({"count": len(results), "results": results})
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def batch_read_shape_cells(
        items_json: str,
        page: str = "",
        doc_name: str = "",
    ) -> str:
        """Batch-read existing ShapeSheet cells from up to 300 shapes."""
        try:
            import json
            items = json.loads(items_json)
            if not isinstance(items, list) or not items or len(items) > 300:
                raise ValueError("items_json must be a JSON array with 1..300 items")
            page_obj = visio._resolve_page(doc_name, parse_page(page))
            results = []
            for item in items:
                sid = int(item["shape_id"])
                names = item.get("cell_names")
                if not isinstance(names, list) or not names or len(names) > 100:
                    raise ValueError(f"cell_names invalid for shape {sid}")
                shape = page_obj.Shapes.ItemFromID(sid)
                cells = {}
                missing = []
                for raw_name in names:
                    name = str(raw_name)
                    try:
                        exists = bool(shape.CellExistsU(name, 0))
                    except Exception:
                        exists = False
                    if not exists:
                        missing.append(name)
                        continue
                    cell = shape.CellsU(name)
                    value = {"formula_u": str(cell.FormulaU)}
                    try: value["result_str_u"] = str(cell.ResultStrU(0))
                    except Exception: value["result_str_u"] = None
                    try: value["result_iu"] = float(cell.ResultIU)
                    except Exception: value["result_iu"] = None
                    cells[name] = value
                results.append({
                    "shape_id": sid,
                    "shape_name": str(shape.Name),
                    "cells": cells,
                    "missing": missing,
                })
            return ok({"count": len(results), "results": results})
        except Exception as exc:
            return err(exc)







    @mcp.tool()
    def duplicate_page(
        page: str,
        new_page_name: str,
        doc_name: str = "",
    ) -> str:
        """Duplicate one existing Visio page natively and assign a bounded new name."""
        try:
            name = str(new_page_name).strip()
            if not name or len(name) > 80:
                raise ValueError("new_page_name must contain 1..80 characters")
            source = visio._resolve_page(doc_name, parse_page(page))
            document = source.Document
            for index in range(1, int(document.Pages.Count) + 1):
                if str(document.Pages.Item(index).Name) == name:
                    raise ValueError(f"Page already exists: {name}")
            duplicated = source.Duplicate()
            duplicated.Name = name
            return ok({
                "source_page": str(source.Name),
                "new_page": str(duplicated.Name),
                "index": int(duplicated.Index),
                "shape_count": int(duplicated.Shapes.Count),
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def move_shapes_exact(
        shape_ids_json: str,
        dx_mm: float,
        dy_mm: float,
        page: str = "",
        doc_name: str = "",
        select_result: bool = True,
        detach_items_json: str = "[]",
        glue_items_json: str = "[]",
    ) -> str:
        """Move explicit top-level shapes by an exact engineering offset.

        Optional detach items break only an explicitly expected native Glue endpoint
        by replacing its current absolute page coordinates with literal mm formulas.
        Optional glue items then attach the moved endpoint to an explicitly selected
        native connection point. The compound mutation rolls back on any failure.
        """
        try:
            import json
            import math

            raw_ids = json.loads(shape_ids_json)
            if not isinstance(raw_ids, list) or not raw_ids or len(raw_ids) > 100:
                raise ValueError("shape_ids_json must be a JSON array with 1..100 items")
            shape_ids = [int(value) for value in raw_ids]
            if len(set(shape_ids)) != len(shape_ids):
                raise ValueError("shape_ids_json must not contain duplicate shape IDs")
            if any(value <= 0 for value in shape_ids):
                raise ValueError("shape IDs must be positive integers")

            dx = float(dx_mm)
            dy = float(dy_mm)
            if not math.isfinite(dx) or not math.isfinite(dy):
                raise ValueError("dx_mm and dy_mm must be finite")
            if abs(dx) > 2000.0 or abs(dy) > 2000.0:
                raise ValueError("dx_mm and dy_mm must be within +/-2000 mm")
            if abs(dx) < 1e-12 and abs(dy) < 1e-12:
                raise ValueError("move offset must not be zero")

            page_obj = visio._resolve_page(doc_name, parse_page(page))
            document = page_obj.Document
            app = page_obj.Application
            window = app.ActiveWindow
            try:
                window.Page = page_obj
            except Exception:
                try:
                    page_obj.Activate()
                except Exception:
                    pass

            def shape_snapshot(shape):
                try:
                    master = shape.Master
                    master_name = str(master.NameU) if master is not None else None
                except Exception:
                    master_name = None
                try:
                    text_value = str(shape.Text)
                except Exception:
                    text_value = ""
                try:
                    pin_x_mm = float(shape.CellsU("PinX").ResultIU) * 25.4
                    pin_y_mm = float(shape.CellsU("PinY").ResultIU) * 25.4
                except Exception:
                    pin_x_mm = None
                    pin_y_mm = None
                return {
                    "shape_id": int(shape.ID),
                    "shape_name": str(shape.Name),
                    "master_name": master_name,
                    "text": text_value,
                    "pin_x_mm": pin_x_mm,
                    "pin_y_mm": pin_y_mm,
                }

            def endpoint_cells(shape, endpoint):
                if endpoint == "begin":
                    return shape.CellsU("BeginX"), shape.CellsU("BeginY"), "BeginX", "BeginY"
                if endpoint == "end":
                    return shape.CellsU("EndX"), shape.CellsU("EndY"), "EndX", "EndY"
                raise ValueError("endpoint must be begin/end")

            def connection_formula_matches(formula_u, target_name, row_number):
                value = str(formula_u).casefold()
                return (
                    str(target_name).casefold() in value
                    and (
                        f"connections.{row_number}.x" in value
                        or f"connections.x{row_number}" in value
                    )
                )

            source_shapes = [page_obj.Shapes.ItemFromID(sid) for sid in shape_ids]
            source_snapshot = [shape_snapshot(shape) for shape in source_shapes]
            if any(row["pin_x_mm"] is None or row["pin_y_mm"] is None for row in source_snapshot):
                raise RuntimeError("Cannot determine PinX/PinY for all selected shapes")

            raw_detach_items = json.loads(detach_items_json)
            if not isinstance(raw_detach_items, list) or len(raw_detach_items) > 32:
                raise ValueError("detach_items_json must be a JSON array with at most 32 items")
            detach_items = []
            seen_detach = set()
            for raw in raw_detach_items:
                if not isinstance(raw, dict):
                    raise ValueError("each detach item must be an object")
                sid = int(raw["shape_id"])
                if sid not in shape_ids:
                    raise ValueError(f"detach shape_id {sid} is not in moved shape IDs")
                endpoint = str(raw["endpoint"]).strip().lower()
                if endpoint not in {"begin", "end"}:
                    raise ValueError(f"detach endpoint must be begin/end for shape {sid}")
                target_sid = int(raw["expected_target_shape_id"])
                row_number = int(raw["expected_target_connection_row"])
                if target_sid <= 0:
                    raise ValueError("expected_target_shape_id must be positive")
                if row_number < 1 or row_number > 256:
                    raise ValueError("expected_target_connection_row must be within 1..256")
                key = (sid, endpoint)
                if key in seen_detach:
                    raise ValueError(f"duplicate detach endpoint for shape {sid}: {endpoint}")
                seen_detach.add(key)
                target = page_obj.Shapes.ItemFromID(target_sid)
                source_shape = page_obj.Shapes.ItemFromID(sid)
                source_x, source_y, source_x_name, source_y_name = endpoint_cells(
                    source_shape, endpoint
                )
                before_formula = str(source_x.FormulaU)
                if not connection_formula_matches(before_formula, str(target.Name), row_number):
                    raise ValueError(
                        f"shape {sid} {source_x_name} is not glued to expected target "
                        f"{target_sid} Connections.{row_number}.X: {before_formula}"
                    )
                detach_items.append({
                    "shape_id": sid,
                    "endpoint": endpoint,
                    "expected_target_shape_id": target_sid,
                    "expected_target_connection_row": row_number,
                    "source_x_name": source_x_name,
                    "source_y_name": source_y_name,
                })

            raw_glue_items = json.loads(glue_items_json)
            if not isinstance(raw_glue_items, list) or len(raw_glue_items) > 32:
                raise ValueError("glue_items_json must be a JSON array with at most 32 items")
            glue_items = []
            seen_glue = set()
            for raw in raw_glue_items:
                if not isinstance(raw, dict):
                    raise ValueError("each glue item must be an object")
                sid = int(raw["shape_id"])
                if sid not in shape_ids:
                    raise ValueError(f"glue shape_id {sid} is not in moved shape IDs")
                endpoint = str(raw["endpoint"]).strip().lower()
                if endpoint not in {"begin", "end"}:
                    raise ValueError(f"glue endpoint must be begin/end for shape {sid}")
                target_sid = int(raw["target_shape_id"])
                row_number = int(raw["target_connection_row"])
                if target_sid <= 0:
                    raise ValueError("glue target_shape_id must be positive")
                if row_number < 1 or row_number > 256:
                    raise ValueError("glue target_connection_row must be within 1..256")
                key = (sid, endpoint)
                if key in seen_glue:
                    raise ValueError(f"duplicate glue endpoint for shape {sid}: {endpoint}")
                seen_glue.add(key)
                target = page_obj.Shapes.ItemFromID(target_sid)
                target_cell_name = f"Connections.X{row_number}"
                if not bool(target.CellExistsU(target_cell_name, 0)):
                    raise KeyError(f"Target shape {target_sid} has no {target_cell_name}")
                glue_items.append({
                    "shape_id": sid,
                    "endpoint": endpoint,
                    "target_shape_id": target_sid,
                    "target_connection_row": row_number,
                })

            previous_ids = []
            try:
                previous = window.Selection
                for index in range(1, int(previous.Count) + 1):
                    previous_ids.append(int(previous.Item(index).ID))
            except Exception:
                previous_ids = []

            def select_ids(ids):
                window.DeselectAll()
                for sid in ids:
                    window.Select(page_obj.Shapes.ItemFromID(int(sid)), 2)  # visSelect

            select_ids(shape_ids)
            selected = window.Selection
            if int(selected.Count) != len(shape_ids):
                raise RuntimeError(
                    f"Visio selected {int(selected.Count)} shapes, expected {len(shape_ids)}"
                )

            scope_id = int(document.BeginUndoScope("EnergoLogic: Move Shapes Exact"))
            committed = False
            try:
                detach_results = []
                detach_tolerance_mm = 0.01
                for item in detach_items:
                    shape = page_obj.Shapes.ItemFromID(item["shape_id"])
                    x_cell, y_cell, x_name, y_name = endpoint_cells(shape, item["endpoint"])
                    before_x_formula = str(x_cell.FormulaU)
                    before_y_formula = str(y_cell.FormulaU)
                    before_x_mm = float(x_cell.ResultIU) * 25.4
                    before_y_mm = float(y_cell.ResultIU) * 25.4
                    x_cell.FormulaU = f"{before_x_mm:.12g} mm"
                    y_cell.FormulaU = f"{before_y_mm:.12g} mm"
                    after_x_formula = str(x_cell.FormulaU)
                    after_y_formula = str(y_cell.FormulaU)
                    after_x_mm = float(x_cell.ResultIU) * 25.4
                    after_y_mm = float(y_cell.ResultIU) * 25.4
                    if (
                        abs(after_x_mm - before_x_mm) > detach_tolerance_mm
                        or abs(after_y_mm - before_y_mm) > detach_tolerance_mm
                    ):
                        raise RuntimeError(
                            f"Detach changed endpoint coordinates for shape {item['shape_id']}"
                        )
                    target = page_obj.Shapes.ItemFromID(item["expected_target_shape_id"])
                    if connection_formula_matches(
                        after_x_formula,
                        str(target.Name),
                        item["expected_target_connection_row"],
                    ):
                        raise RuntimeError(
                            f"Detach verification failed for shape {item['shape_id']} {x_name}"
                        )
                    detach_results.append({
                        "shape_id": item["shape_id"],
                        "endpoint": item["endpoint"],
                        "expected_target_shape_id": item["expected_target_shape_id"],
                        "expected_target_connection_row": item["expected_target_connection_row"],
                        "before": {
                            "x_formula_u": before_x_formula,
                            "y_formula_u": before_y_formula,
                            "x_mm": before_x_mm,
                            "y_mm": before_y_mm,
                        },
                        "after": {
                            "x_formula_u": after_x_formula,
                            "y_formula_u": after_y_formula,
                            "x_mm": after_x_mm,
                            "y_mm": after_y_mm,
                        },
                        "verified": True,
                    })

                selected.Move(dx, dy, "mm")

                moved_snapshot = [
                    shape_snapshot(page_obj.Shapes.ItemFromID(sid)) for sid in shape_ids
                ]
                tolerance_mm = 0.01
                for source_row, moved_row in zip(source_snapshot, moved_snapshot):
                    actual_dx = moved_row["pin_x_mm"] - source_row["pin_x_mm"]
                    actual_dy = moved_row["pin_y_mm"] - source_row["pin_y_mm"]
                    if abs(actual_dx - dx) > tolerance_mm or abs(actual_dy - dy) > tolerance_mm:
                        raise RuntimeError(
                            "Visio exact move verification failed for shape "
                            f"{source_row['shape_id']}: requested ({dx:.6f}, {dy:.6f}) mm, "
                            f"got ({actual_dx:.6f}, {actual_dy:.6f}) mm"
                        )

                glue_results = []
                for item in glue_items:
                    shape = page_obj.Shapes.ItemFromID(item["shape_id"])
                    target = page_obj.Shapes.ItemFromID(item["target_shape_id"])
                    x_cell, _y_cell, x_name, _y_name = endpoint_cells(shape, item["endpoint"])
                    target_cell_name = f"Connections.X{item['target_connection_row']}"
                    target_cell = target.CellsU(target_cell_name)
                    x_cell.GlueTo(target_cell)
                    endpoint_formula = str(x_cell.FormulaU)
                    if not connection_formula_matches(
                        endpoint_formula,
                        str(target.Name),
                        item["target_connection_row"],
                    ):
                        raise RuntimeError(
                            f"Glue formula verification failed for moved shape {item['shape_id']} "
                            f"to target {item['target_shape_id']} {target_cell_name}: "
                            f"{endpoint_formula}"
                        )
                    glue_results.append({
                        "shape_id": item["shape_id"],
                        "endpoint": item["endpoint"],
                        "target_shape_id": item["target_shape_id"],
                        "target_connection_row": item["target_connection_row"],
                        "endpoint_formula_u": endpoint_formula,
                        "verified": True,
                    })

                document.EndUndoScope(scope_id, True)
                committed = True
            except Exception:
                try:
                    document.EndUndoScope(scope_id, False)
                except Exception:
                    pass
                try:
                    select_ids(previous_ids)
                except Exception:
                    pass
                raise

            if bool(select_result):
                select_ids(shape_ids)
            else:
                try:
                    select_ids(previous_ids)
                except Exception:
                    pass

            return ok({
                "shape_ids": shape_ids,
                "source_shapes": source_snapshot,
                "moved_shapes": moved_snapshot,
                "dx_mm": dx,
                "dy_mm": dy,
                "verification_tolerance_mm": tolerance_mm,
                "detach_results": detach_results,
                "glue_results": glue_results,
                "undo_scope": "EnergoLogic: Move Shapes Exact",
                "undo_scope_owner": "document",
                "undo_committed": committed,
                "result_selected": bool(select_result),
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def duplicate_shapes_exact(
        shape_ids_json: str,
        dx_mm: float,
        dy_mm: float,
        page: str = "",
        doc_name: str = "",
        select_result: bool = True,
        glue_items_json: str = "[]",
        new_cell_id: str = "",
    ) -> str:
        """Duplicate explicit top-level shapes and move the copy by an exact mm offset.

        The native Visio Selection.Duplicate + Selection.Move operation is wrapped in
        one UndoScope. Any exception rolls the entire duplicate/move operation back.
        The source shapes are never modified.
        """
        try:
            import json
            import math

            raw_ids = json.loads(shape_ids_json)
            if not isinstance(raw_ids, list) or not raw_ids or len(raw_ids) > 100:
                raise ValueError("shape_ids_json must be a JSON array with 1..100 items")
            shape_ids = [int(value) for value in raw_ids]
            if len(set(shape_ids)) != len(shape_ids):
                raise ValueError("shape_ids_json must not contain duplicate shape IDs")
            if any(value <= 0 for value in shape_ids):
                raise ValueError("shape IDs must be positive integers")

            dx = float(dx_mm)
            dy = float(dy_mm)
            if not math.isfinite(dx) or not math.isfinite(dy):
                raise ValueError("dx_mm and dy_mm must be finite")
            if abs(dx) > 2000.0 or abs(dy) > 2000.0:
                raise ValueError("dx_mm and dy_mm must be within +/-2000 mm")
            if abs(dx) < 1e-12 and abs(dy) < 1e-12:
                raise ValueError("duplicate offset must not be zero")

            cell_id = str(new_cell_id).strip()
            if cell_id:
                import re
                if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", cell_id) is None:
                    raise ValueError(
                        "new_cell_id must use 1..128 ASCII letters, digits, dot, "
                        "underscore, colon or hyphen"
                    )

            page_obj = visio._resolve_page(doc_name, parse_page(page))
            document = page_obj.Document
            app = page_obj.Application
            window = app.ActiveWindow
            try:
                window.Page = page_obj
            except Exception:
                try:
                    page_obj.Activate()
                except Exception:
                    pass

            def shape_snapshot(shape):
                try:
                    master = shape.Master
                    master_name = str(master.NameU) if master is not None else None
                except Exception:
                    master_name = None
                try:
                    text_value = str(shape.Text)
                except Exception:
                    text_value = ""
                try:
                    pin_x_mm = float(shape.CellsU("PinX").ResultIU) * 25.4
                    pin_y_mm = float(shape.CellsU("PinY").ResultIU) * 25.4
                except Exception:
                    pin_x_mm = None
                    pin_y_mm = None
                return {
                    "shape_id": int(shape.ID),
                    "shape_name": str(shape.Name),
                    "master_name": master_name,
                    "text": text_value,
                    "pin_x_mm": pin_x_mm,
                    "pin_y_mm": pin_y_mm,
                }

            source_shapes = [page_obj.Shapes.ItemFromID(sid) for sid in shape_ids]
            source_snapshot = [shape_snapshot(shape) for shape in source_shapes]

            raw_glue_items = json.loads(glue_items_json)
            if not isinstance(raw_glue_items, list) or len(raw_glue_items) > 32:
                raise ValueError("glue_items_json must be a JSON array with at most 32 items")
            glue_items = []
            for raw in raw_glue_items:
                if not isinstance(raw, dict):
                    raise ValueError("each glue item must be an object")
                source_sid = int(raw["source_shape_id"])
                if source_sid not in shape_ids:
                    raise ValueError(
                        f"glue source_shape_id {source_sid} is not in duplicated shape IDs"
                    )
                endpoint = str(raw["endpoint"]).strip().lower()
                if endpoint not in {"begin", "end"}:
                    raise ValueError("glue endpoint must be begin/end")
                target_sid = int(raw["target_shape_id"])
                row_number = int(raw["target_connection_row"])
                if target_sid <= 0:
                    raise ValueError("glue target_shape_id must be positive")
                if row_number < 1 or row_number > 256:
                    raise ValueError("glue target_connection_row must be within 1..256")
                # Resolve targets before entering the Undo scope so bad IDs fail without mutation.
                page_obj.Shapes.ItemFromID(target_sid)
                glue_items.append({
                    "source_shape_id": source_sid,
                    "endpoint": endpoint,
                    "target_shape_id": target_sid,
                    "target_connection_row": row_number,
                })

            previous_ids = []
            try:
                previous = window.Selection
                for index in range(1, int(previous.Count) + 1):
                    previous_ids.append(int(previous.Item(index).ID))
            except Exception:
                previous_ids = []

            def select_ids(ids):
                window.DeselectAll()
                for sid in ids:
                    window.Select(page_obj.Shapes.ItemFromID(int(sid)), 2)  # visSelect

            select_ids(shape_ids)
            selected = window.Selection
            if int(selected.Count) != len(shape_ids):
                raise RuntimeError(
                    f"Visio selected {int(selected.Count)} shapes, expected {len(shape_ids)}"
                )

            shape_count_before = int(page_obj.Shapes.Count)
            preexisting_shape_ids = {
                int(page_obj.Shapes.Item(index).ID)
                for index in range(1, shape_count_before + 1)
            }
            ui_duplicate_created = False
            committed = False
            try:
                # Use the actual Visio UI Duplicate command (visCmdUFEditDuplicate=1024).
                # Direct COM mutations on this workstation do not create user-facing
                # undo units, while the built-in UI command does. Post-processing the
                # selected duplicate therefore keeps Ctrl+Z pointed at the duplicate.
                app.DoCmd(1024)
                ui_duplicate_created = True
                duplicated = window.Selection
                if duplicated is None:
                    raise RuntimeError("Visio UI Duplicate produced no result selection")
                if int(duplicated.Count) != len(shape_ids):
                    raise RuntimeError(
                        f"Visio duplicated {int(duplicated.Count)} shapes, expected {len(shape_ids)}"
                    )

                duplicate_ids_before_move = [
                    int(duplicated.Item(index).ID)
                    for index in range(1, int(duplicated.Count) + 1)
                ]
                duplicate_snapshot_before_move = [
                    shape_snapshot(page_obj.Shapes.ItemFromID(sid))
                    for sid in duplicate_ids_before_move
                ]

                def centroid(rows):
                    coords = [
                        (row["pin_x_mm"], row["pin_y_mm"])
                        for row in rows
                        if row["pin_x_mm"] is not None and row["pin_y_mm"] is not None
                    ]
                    if len(coords) != len(rows):
                        raise RuntimeError("Cannot determine selection centroid for exact duplicate")
                    return (
                        sum(item[0] for item in coords) / len(coords),
                        sum(item[1] for item in coords) / len(coords),
                    )

                source_centroid = centroid(source_snapshot)
                duplicate_centroid = centroid(duplicate_snapshot_before_move)
                native_dx = duplicate_centroid[0] - source_centroid[0]
                native_dy = duplicate_centroid[1] - source_centroid[1]
                correction_dx = dx - native_dx
                correction_dy = dy - native_dy

                # Visio Duplicate applies its own UI-style paste offset. Compensate
                # it so the final engineering displacement equals the request.
                duplicated.Move(correction_dx, correction_dy, "mm")
                new_ids = [
                    int(duplicated.Item(index).ID)
                    for index in range(1, int(duplicated.Count) + 1)
                ]
                if len(set(new_ids)) != len(new_ids):
                    raise RuntimeError("Visio returned duplicate IDs in duplicated selection")
                if set(new_ids) & set(shape_ids):
                    raise RuntimeError("Visio duplicate selection reused source shape IDs")

                new_snapshot = [
                    shape_snapshot(page_obj.Shapes.ItemFromID(sid)) for sid in new_ids
                ]
                source_to_new = dict(zip(shape_ids, new_ids))
                tolerance_mm = 0.01
                for source_row, new_row in zip(source_snapshot, new_snapshot):
                    if source_row["master_name"] != new_row["master_name"]:
                        raise RuntimeError(
                            "Visio duplicate selection order changed master correspondence"
                        )
                    if source_row["text"] != new_row["text"]:
                        raise RuntimeError(
                            "Visio duplicate selection order changed text correspondence"
                        )
                    pair_dx = new_row["pin_x_mm"] - source_row["pin_x_mm"]
                    pair_dy = new_row["pin_y_mm"] - source_row["pin_y_mm"]
                    if abs(pair_dx - dx) > tolerance_mm or abs(pair_dy - dy) > tolerance_mm:
                        raise RuntimeError(
                            "Visio duplicate correspondence verification failed for "
                            f"source shape {source_row['shape_id']}: "
                            f"requested ({dx:.6f}, {dy:.6f}) mm, "
                            f"got ({pair_dx:.6f}, {pair_dy:.6f}) mm"
                        )

                final_centroid = centroid(new_snapshot)
                final_dx = final_centroid[0] - source_centroid[0]
                final_dy = final_centroid[1] - source_centroid[1]
                if abs(final_dx - dx) > tolerance_mm or abs(final_dy - dy) > tolerance_mm:
                    raise RuntimeError(
                        "Visio exact duplicate verification failed: "
                        f"requested ({dx:.6f}, {dy:.6f}) mm, "
                        f"got ({final_dx:.6f}, {final_dy:.6f}) mm"
                    )

                identity_results = []
                if cell_id:
                    # visSectionUser = 242, visTagDefault = 0. The row is added
                    # only to duplicated shape INSTANCES; VTD masters are untouched.
                    for duplicate_sid in new_ids:
                        shape = page_obj.Shapes.ItemFromID(duplicate_sid)
                        if not bool(shape.SectionExists(242, 0)):
                            shape.AddSection(242)
                        if not bool(shape.CellExistsU("User.EnergoLogicCellId", 0)):
                            shape.AddNamedRow(242, "EnergoLogicCellId", 0)
                        identity_cell = shape.CellsU("User.EnergoLogicCellId")
                        identity_cell.FormulaU = f'"{cell_id}"'
                        formula_u = str(identity_cell.FormulaU)
                        if formula_u.strip().strip('"') != cell_id:
                            raise RuntimeError(
                                f"EnergoLogicCellId verification failed for duplicate "
                                f"shape {duplicate_sid}: {formula_u!r}"
                            )
                        identity_results.append({
                            "shape_id": duplicate_sid,
                            "user_cell": "User.EnergoLogicCellId",
                            "cell_id": cell_id,
                            "formula_u": formula_u,
                            "verified": True,
                        })

                glue_results = []
                for item in glue_items:
                    duplicate_sid = source_to_new[item["source_shape_id"]]
                    shape = page_obj.Shapes.ItemFromID(duplicate_sid)
                    target = page_obj.Shapes.ItemFromID(item["target_shape_id"])
                    endpoint = item["endpoint"]
                    source_cell_name = "BeginX" if endpoint == "begin" else "EndX"
                    target_cell_name = f"Connections.X{item['target_connection_row']}"
                    if not bool(target.CellExistsU(target_cell_name, 0)):
                        raise KeyError(
                            f"Target shape {item['target_shape_id']} has no {target_cell_name}"
                        )
                    source_cell = shape.CellsU(source_cell_name)
                    target_cell = target.CellsU(target_cell_name)
                    source_cell.GlueTo(target_cell)

                    endpoint_formula = str(source_cell.FormulaU)
                    target_name = str(target.Name)
                    expected_row = item["target_connection_row"]
                    formula_verified = (
                        target_name.casefold() in endpoint_formula.casefold()
                        and (
                            f"Connections.{expected_row}.X".casefold()
                            in endpoint_formula.casefold()
                            or f"Connections.X{expected_row}".casefold()
                            in endpoint_formula.casefold()
                        )
                    )
                    if not formula_verified:
                        raise RuntimeError(
                            f"Glue formula verification failed for duplicate shape {duplicate_sid} "
                            f"to target {item['target_shape_id']} {target_cell_name}: "
                            f"{endpoint_formula}"
                        )

                    # Best-effort immediate Connects observation. Some live Visio COM
                    # sessions lag this collection until the operation returns, so the
                    # high-level caller performs the authoritative post-commit
                    # get_connections verification as well.
                    connects_verified = False
                    try:
                        connects = shape.Connects
                        for connect_index in range(1, int(connects.Count) + 1):
                            connect = connects.Item(connect_index)
                            try:
                                to_id = int(connect.ToSheet.ID)
                                from_name = str(connect.FromCell.NameU)
                                to_name = str(connect.ToCell.NameU)
                            except Exception:
                                continue
                            acceptable_target_names = {
                                target_cell_name.casefold(),
                                f"Connections.{expected_row}.X".casefold(),
                            }
                            if (
                                to_id == item["target_shape_id"]
                                and from_name.casefold() == source_cell_name.casefold()
                                and to_name.casefold() in acceptable_target_names
                            ):
                                connects_verified = True
                                break
                    except Exception:
                        connects_verified = False

                    glue_results.append({
                        "source_shape_id": item["source_shape_id"],
                        "duplicate_shape_id": duplicate_sid,
                        "endpoint": endpoint,
                        "target_shape_id": item["target_shape_id"],
                        "target_connection_row": item["target_connection_row"],
                        "endpoint_formula_u": endpoint_formula,
                        "formula_verified": formula_verified,
                        "connects_immediate_verified": connects_verified,
                        "post_commit_connects_verification_required": True,
                    })

                committed = True
            except Exception:
                rollback_verified = False
                if ui_duplicate_created:
                    try:
                        app.DoCmd(1017)  # visCmdEditUndo
                        rollback_verified = int(page_obj.Shapes.Count) == shape_count_before
                    except Exception:
                        rollback_verified = False
                    if not rollback_verified:
                        # Last-resort bounded cleanup. Only shapes created during this
                        # synchronous call are eligible; source/existing shapes are never deleted.
                        current_ids = [
                            int(page_obj.Shapes.Item(index).ID)
                            for index in range(1, int(page_obj.Shapes.Count) + 1)
                        ]
                        for sid in reversed(current_ids):
                            if sid not in preexisting_shape_ids:
                                try:
                                    page_obj.Shapes.ItemFromID(sid).Delete()
                                except Exception:
                                    pass
                        rollback_verified = int(page_obj.Shapes.Count) == shape_count_before
                    if not rollback_verified:
                        raise RuntimeError(
                            "Duplicate failed and automatic rollback could not restore shape count"
                        )
                try:
                    select_ids(previous_ids)
                except Exception:
                    pass
                raise

            # The UI Duplicate command already leaves the duplicate selected. Avoid a
            # post-scope Select/Deselect operation so the operator's next Ctrl+Z
            # targets the engineering transaction itself.
            if not bool(select_result):
                try:
                    select_ids(previous_ids)
                except Exception:
                    pass

            return ok({
                "source_shape_ids": shape_ids,
                "new_shape_ids": new_ids,
                "source_shapes": source_snapshot,
                "new_shapes": new_snapshot,
                "dx_mm": dx,
                "dy_mm": dy,
                "native_duplicate_offset_mm": {"x": native_dx, "y": native_dy},
                "applied_move_mm": {"x": correction_dx, "y": correction_dy},
                "verified_final_offset_mm": {"x": final_dx, "y": final_dy},
                "verification_tolerance_mm": tolerance_mm,
                "source_to_new_shape_ids": {str(key): value for key, value in source_to_new.items()},
                "new_cell_id": cell_id or None,
                "identity_results": identity_results,
                "glue_results": glue_results,
                "undo_strategy": "visCmdUFEditDuplicate",
                "undo_command_id": 1024,
                "single_user_undo_expected": True,
                "undo_committed": committed,
                "result_selected": bool(select_result),
                "mapping_basis": "selection-order; qualify before identity-sensitive use",
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def install_energologic_editor_ui(
        page: str = "",
        doc_name: str = "",
    ) -> str:
        # Build/register/connect the full EnergoLogic Visio editor panel.
        try:
            import base64
            import gzip
            import os
            import shutil
            import subprocess
            import winreg

            if os.name != "nt":
                raise RuntimeError("EnergoLogic editor UI is Windows-only")

            page_obj = visio._resolve_page(doc_name, parse_page(page))
            app = page_obj.Application
            addins = app.COMAddIns
            addins.Update()

            current_progid = "EnergoLogic.VisioEditorAddinV349"
            editor_progid_prefix = "EnergoLogic.VisioEditorAddinV"

            # Keep early known CLSIDs so partially-unregistered historical builds
            # can still be cleaned. Later builds are discovered dynamically.
            known_legacy_clsids = {
                "EnergoLogic.VisioEditorAddinV31": "{F2236480-88B8-42B3-AEC4-0707D59A14FC}",
                "EnergoLogic.VisioEditorAddinV32": "{9B2D0D65-A68C-44D0-A523-612148808DBD}",
                "EnergoLogic.VisioEditorAddinV33": "{54D4E77E-73B0-4D45-94E2-B138DF35D1A3}",
                "EnergoLogic.VisioEditorAddinV34": "{A6E63A2D-0DA5-4E84-9B2B-5B3E6944B5F4}",
                "EnergoLogic.VisioEditorAddinV35": "{D93F00C2-1C95-4D0A-A0A9-609E25B9794C}",
                "EnergoLogic.VisioEditorAddinV36": "{81705A73-9C25-4E72-84A8-F58E4C818AAF}",
                "EnergoLogic.VisioEditorAddinV37": "{3D58EA6C-A51F-41B9-A46D-BF0FB3BA7C5A}",
                "EnergoLogic.VisioEditorAddinV38": "{9974BD0D-D56E-45F5-BB8C-7A21485C6730}",
                "EnergoLogic.VisioEditorAddinV39": "{B42A3C6E-8C1F-44AB-A486-93C6AB3D8F39}",
                "EnergoLogic.VisioEditorAddinV310": "{D1C940D2-5A7E-4B4B-A92A-2D443A0DBA85}",
                "EnergoLogic.VisioEditorAddinV311": "{6D8D560D-1F9F-4CB8-BED7-5FCBB70B1F2C}",
                "EnergoLogic.VisioEditorAddinV312": "{2F8B22F0-0A1B-4E30-B850-09B1F7197D3D}",
                "EnergoLogic.VisioEditorAddinV313": "{1A6AF8E1-2576-4EF3-96EC-676904B6DA57}",
                "EnergoLogic.VisioEditorAddinV314": "{6989E63C-E667-4B14-B85B-210710468940}",
                "EnergoLogic.VisioEditorAddinV315": "{E82068B0-D05D-4646-82B0-0CA923733CAF}",
                "EnergoLogic.VisioEditorAddinV316": "{89DDBB87-8513-5078-9BF3-1DA6D75B2454}",
                "EnergoLogic.VisioEditorAddinV317": "{D0F27C51-9E15-4C2D-A584-170EA8B7F317}",
                "EnergoLogic.VisioEditorAddinV318": "{6BC8DE0D-79B4-4E0D-9E0A-C6E6A7E0F318}",
                "EnergoLogic.VisioEditorAddinV319": "{A2ECDF6D-77BB-4B3A-8B29-3B736850F319}",
                "EnergoLogic.VisioEditorAddinV320": "{08DA44F1-A58D-4E53-8F2F-A1107D57F320}",
                "EnergoLogic.VisioEditorAddinV321": "{9D1B5AC1-0C47-4C18-BB03-7ED263E8F321}",
                "EnergoLogic.VisioEditorAddinV322": "{D65447E9-8176-4EBB-8CC4-4DAA1C3AF322}",
                "EnergoLogic.VisioEditorAddinV323": "{3C74BB1A-284A-414B-BAE0-5D413682F323}",
                "EnergoLogic.VisioEditorAddinV324": "{7F0BF42E-719C-4A53-9926-DFE2B0EEF324}",
                "EnergoLogic.VisioEditorAddinV325": "{8E9D3160-A441-4944-9471-728178F5F325}",
                "EnergoLogic.VisioEditorAddinV326": "{B0DB7395-E237-4F35-BED6-AE59C2C5F326}",
                "EnergoLogic.VisioEditorAddinV327": "{9A7903D3-1371-4AF6-B80A-01F6C039F327}",
                "EnergoLogic.VisioEditorAddinV328": "{8E75F86D-AF28-455B-B20C-62492D9BF328}",
            }

            legacy_progids = set(known_legacy_clsids)

            # Live COMAddIns discovery removes loaded stale Ribbon providers from
            # the current Visio process, not only their registry entries.
            try:
                for index in range(1, int(addins.Count) + 1):
                    item = addins.Item(index)
                    candidate = str(item.ProgId)
                    if (
                        candidate.startswith(editor_progid_prefix)
                        and candidate != current_progid
                    ):
                        legacy_progids.add(candidate)
            except Exception:
                pass

            # Registry discovery makes this future-proof for disconnected builds.
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Visio\Addins",
                    0,
                    winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                ) as key:
                    index = 0
                    while True:
                        try:
                            candidate = winreg.EnumKey(key, index)
                            index += 1
                        except OSError:
                            break
                        if (
                            candidate.startswith(editor_progid_prefix)
                            and candidate != current_progid
                        ):
                            legacy_progids.add(candidate)
            except FileNotFoundError:
                pass

            # Also include orphaned ProgID class registrations left by interrupted
            # historical installs. They do not create a Ribbon by themselves but
            # should not accumulate forever.
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Classes",
                    0,
                    winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                ) as key:
                    index = 0
                    while True:
                        try:
                            candidate = winreg.EnumKey(key, index)
                            index += 1
                        except OSError:
                            break
                        if (
                            candidate.startswith(editor_progid_prefix)
                            and candidate != current_progid
                        ):
                            legacy_progids.add(candidate)
            except FileNotFoundError:
                pass

            def read_progid_clsid(progid):
                if progid in known_legacy_clsids:
                    return known_legacy_clsids[progid]
                try:
                    with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER,
                        "Software\\Classes\\" + progid + "\\CLSID",
                        0,
                        winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                    ) as key:
                        value, _ = winreg.QueryValueEx(key, "")
                        return str(value).strip()
                except (FileNotFoundError, OSError):
                    return ""


            def delete_tree(root, subkey):
                try:
                    with winreg.OpenKey(
                        root, subkey, 0,
                        winreg.KEY_READ | winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY,
                    ) as key:
                        children = []
                        index = 0
                        while True:
                            try:
                                children.append(winreg.EnumKey(key, index))
                                index += 1
                            except OSError:
                                break
                    for child in children:
                        delete_tree(root, subkey + "\\" + child)
                    winreg.DeleteKeyEx(root, subkey, winreg.KEY_WOW64_64KEY, 0)
                except FileNotFoundError:
                    pass

            removed_legacy = []
            for legacy_progid in sorted(legacy_progids):
                legacy_clsid = read_progid_clsid(legacy_progid)
                try:
                    legacy_item = addins.Item(legacy_progid)
                    if bool(legacy_item.Connect):
                        legacy_item.Connect = False
                except Exception:
                    pass

                legacy_keys = [
                    "Software\\Microsoft\\Visio\\Addins\\" + legacy_progid,
                    "Software\\Classes\\" + legacy_progid,
                ]
                if legacy_clsid:
                    legacy_keys.append(
                        "Software\\Classes\\CLSID\\" + legacy_clsid
                    )
                for legacy_key in legacy_keys:
                    delete_tree(winreg.HKEY_CURRENT_USER, legacy_key)
                removed_legacy.append(legacy_progid)

            removed_build_dirs = []
            current_build_dir_name = "energologic_visio_editor_addin_v349"
            for candidate_dir in workspace.glob("energologic_visio_editor_addin_v*"):
                if (
                    not candidate_dir.is_dir()
                    or candidate_dir.name == current_build_dir_name
                ):
                    continue
                try:
                    shutil.rmtree(candidate_dir)
                    removed_build_dirs.append(candidate_dir.name)
                except Exception:
                    # A DLL can remain locked until Visio finishes unloading an old
                    # COM add-in. Registry/Ribbon cleanup is authoritative; the next
                    # install can retry filesystem cleanup.
                    pass

            try:
                stale_bar = app.CommandBars.Item("EnergoLogic")
                stale_bar.Delete()
            except Exception:
                pass
            addins.Update()

            build_dir = workspace / "energologic_visio_editor_addin_v349"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV349.dll"
            helper_source_path = build_dir / "EnergoLogicTopologyRestoreHelper.cs"
            helper_exe_path = build_dir / "EnergoLogic.TopologyRestoreHelper.exe"
            helper_source_path.write_bytes(gzip.decompress(base64.b64decode(TOPOLOGY_HELPER_SOURCE_B64)))
            staged_editor_source = workspace / "managed_payloads" / "EnergoLogicVisioEditorAddin.cs"
            if not staged_editor_source.is_file():
                raise FileNotFoundError(
                    "EnergoLogic editor source payload is not staged; run visio_managed_update first"
                )
            source_path.write_bytes(staged_editor_source.read_bytes())

            extensibility_ref = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\PublicAssemblies\Microsoft.VisualStudio.Interop.dll")
            office_ref = Path(r"C:\Program Files\Microsoft Office\root\Office16\ADDINS\PowerPivot Excel Add-in\OFFICE.dll")
            framework = Path(r"C:\WINDOWS\Microsoft.NET\Framework64\v4.0.30319")
            refs = [
                extensibility_ref,
                office_ref,
                framework / "System.Windows.Forms.dll",
                framework / "System.Drawing.dll",
                framework / "Microsoft.CSharp.dll",
            ]
            for reference in refs:
                if not reference.is_file():
                    raise FileNotFoundError(f"required assembly not found: {reference}")
            for reference in (extensibility_ref, office_ref):
                shutil.copy2(reference, build_dir / reference.name)

            csc = framework / "csc.exe"
            compile_args = [
                str(csc),
                "/nologo",
                "/target:library",
                "/platform:x64",
                "/optimize+",
                f"/out:{dll_path}",
            ] + [f"/reference:{reference}" for reference in refs] + [str(source_path)]
            compiled = subprocess.run(
                compile_args,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
            if compiled.returncode != 0 or not dll_path.is_file():
                raise RuntimeError(
                    "EnergoLogic editor add-in compilation failed: "
                    + (compiled.stdout + "\n" + compiled.stderr)[-6000:]
                )

            helper_compile_args = [
                str(csc),
                "/nologo",
                "/target:exe",
                "/platform:x64",
                "/optimize+",
                f"/out:{helper_exe_path}",
                f"/reference:{framework / 'Microsoft.CSharp.dll'}",
                str(helper_source_path),
            ]
            helper_compiled = subprocess.run(
                helper_compile_args,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
            if helper_compiled.returncode != 0 or not helper_exe_path.is_file():
                raise RuntimeError(
                    "EnergoLogic topology helper compilation failed: "
                    + (helper_compiled.stdout + "\n" + helper_compiled.stderr)[-6000:]
                )

            clsid = "{7FA902A8-D36C-4ED0-B299-445A538AF349}"
            progid = current_progid
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV349, Version=0.3.49.0, Culture=neutral, PublicKeyToken=null"
            codebase = dll_path.resolve().as_uri()

            def set_string(root, subkey, name, value):
                with winreg.CreateKeyEx(
                    root,
                    subkey,
                    0,
                    winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY,
                ) as key:
                    winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

            def set_dword(root, subkey, name, value):
                with winreg.CreateKeyEx(
                    root,
                    subkey,
                    0,
                    winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY,
                ) as key:
                    winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, int(value))

            classes = r"Software\Classes"
            set_string(winreg.HKEY_CURRENT_USER, classes + "\\" + progid, "", "EnergoLogic Visio Editor")
            set_string(winreg.HKEY_CURRENT_USER, classes + "\\" + progid + r"\CLSID", "", clsid)
            clsid_key = classes + "\\CLSID\\" + clsid
            set_string(winreg.HKEY_CURRENT_USER, clsid_key, "", "EnergoLogic Visio Editor")
            set_string(winreg.HKEY_CURRENT_USER, clsid_key + r"\ProgId", "", progid)
            category = "{62C8FE65-4EBB-45E7-B440-6E39B2CDBF29}"
            set_string(
                winreg.HKEY_CURRENT_USER,
                clsid_key + "\\Implemented Categories\\" + category,
                "",
                "",
            )
            inproc = clsid_key + r"\InprocServer32"
            set_string(winreg.HKEY_CURRENT_USER, inproc, "", "mscoree.dll")
            set_string(winreg.HKEY_CURRENT_USER, inproc, "ThreadingModel", "Both")
            set_string(winreg.HKEY_CURRENT_USER, inproc, "Class", class_name)
            set_string(winreg.HKEY_CURRENT_USER, inproc, "Assembly", assembly_name)
            set_string(winreg.HKEY_CURRENT_USER, inproc, "RuntimeVersion", "v4.0.30319")
            set_string(winreg.HKEY_CURRENT_USER, inproc, "CodeBase", codebase)

            addin_key = "Software\\Microsoft\\Visio\\Addins\\" + progid
            set_string(winreg.HKEY_CURRENT_USER, addin_key, "FriendlyName", "EnergoLogic Visio Editor")
            set_string(winreg.HKEY_CURRENT_USER, addin_key, "Description", "EnergoLogic engineering editor tools for Visio")
            set_dword(winreg.HKEY_CURRENT_USER, addin_key, "LoadBehavior", 0)

            addins.Update()
            addin = addins.Item(progid)
            connected_before = bool(addin.Connect)
            if not connected_before:
                addin.Connect = True
            connected_after = bool(addin.Connect)
            if not connected_after:
                raise RuntimeError("Visio listed EnergoLogic editor add-in but did not connect it")

            toggle_present = False
            try:
                bar = app.CommandBars.Item("EnergoLogic")
                for index in range(1, int(bar.Controls.Count) + 1):
                    if str(bar.Controls.Item(index).Tag) == "EnergoLogic.Editor.Toggle":
                        toggle_present = True
                        break
            except Exception:
                pass

            addins.Update()
            editor_addins_after = []
            try:
                for index in range(1, int(addins.Count) + 1):
                    item = addins.Item(index)
                    candidate = str(item.ProgId)
                    if candidate.startswith(editor_progid_prefix):
                        editor_addins_after.append({
                            "progid": candidate,
                            "connected": bool(item.Connect),
                        })
            except Exception:
                pass

            return ok({
                "progid": progid,
                "dll_path": str(dll_path),
                "source_path": str(source_path),
                "topology_helper_path": str(helper_exe_path),
                "compiled": True,
                "connected_before": connected_before,
                "connected_after": connected_after,
                "load_behavior": 0,
                "toggle_present": toggle_present,
                "ui": "native RibbonX + drawing context menu + modeless WinForms parameter panel",
                "tabs": ["Ячейки", "Геометрия", "Проверка"],
                "removed_legacy_versions": removed_legacy,
                "removed_build_dirs": removed_build_dirs,
                "editor_addins_after": editor_addins_after,
                "single_editor_addin": (
                    len(editor_addins_after) == 1
                    and editor_addins_after[0]["progid"] == progid
                    and editor_addins_after[0]["connected"]
                ),
                "migration": "all legacy editor registrations -> v3.49",
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def get_energologic_editor_ui_status(
        page: str = "",
        doc_name: str = "",
    ) -> str:
        # Read registration/connection/toggle state for the EnergoLogic editor UI.
        try:
            import winreg
            progid = "EnergoLogic.VisioEditorAddinV349"
            key_path = "Software\\Microsoft\\Visio\\Addins\\" + progid
            registry_exists = False
            load_behavior = None
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    key_path,
                    0,
                    winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                ) as key:
                    registry_exists = True
                    load_behavior = int(winreg.QueryValueEx(key, "LoadBehavior")[0])
            except FileNotFoundError:
                pass

            page_obj = visio._resolve_page(doc_name, parse_page(page))
            app = page_obj.Application
            addins = app.COMAddIns
            addins.Update()
            listed = False
            connected = False
            try:
                item = addins.Item(progid)
                listed = True
                connected = bool(item.Connect)
            except Exception:
                pass

            toggle_present = False
            toggle_visible = False
            try:
                bar = app.CommandBars.Item("EnergoLogic")
                for index in range(1, int(bar.Controls.Count) + 1):
                    control = bar.Controls.Item(index)
                    if str(control.Tag) == "EnergoLogic.Editor.Toggle":
                        toggle_present = True
                        toggle_visible = bool(control.Visible)
                        break
            except Exception:
                pass

            return ok({
                "progid": progid,
                "registry_exists": registry_exists,
                "load_behavior": load_behavior,
                "listed": listed,
                "connected": connected,
                "toggle_present": toggle_present,
                "toggle_visible": toggle_visible,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def schedule_energologic_editor_duplicate_right_test(
        shape_ids_json: str,
        page: str = "",
        doc_name: str = "",
    ) -> str:
        # Select explicit shapes, return, then invoke the real WinForms button from a child process.
        try:
            import base64
            import gzip
            import json
            import os
            import subprocess
            import sys

            if os.name != "nt":
                raise RuntimeError("EnergoLogic UI test is Windows-only")
            raw_ids = json.loads(shape_ids_json)
            if not isinstance(raw_ids, list) or not raw_ids or len(raw_ids) > 100:
                raise ValueError("shape_ids_json must be a JSON array with 1..100 items")
            shape_ids = [int(value) for value in raw_ids]
            if len(set(shape_ids)) != len(shape_ids) or any(value <= 0 for value in shape_ids):
                raise ValueError("shape IDs must be unique positive integers")

            page_obj = visio._resolve_page(doc_name, parse_page(page))
            app = page_obj.Application
            try:
                app.ActiveWindow.Page = page_obj
            except Exception:
                page_obj.Activate()
            window = app.ActiveWindow
            window.DeselectAll()
            for sid in shape_ids:
                window.Select(page_obj.Shapes.ItemFromID(sid), 2)
            if int(window.Selection.Count) != len(shape_ids):
                raise RuntimeError("could not create exact EnergoLogic UI test selection")

            result_path = workspace / "energologic_editor_ui_test_result.json"
            helper_path = workspace / "energologic_editor_ui_test_helper.py"
            stdout_path = workspace / "energologic_editor_ui_test_stdout.txt"
            stderr_path = workspace / "energologic_editor_ui_test_stderr.txt"
            for target in (result_path, stdout_path, stderr_path):
                if target.exists():
                    target.unlink()
            helper_path.write_bytes(gzip.decompress(base64.b64decode("H4sIAAAAAAAC/6VX3WrjRhS+91MMupKoo7XTLnQNKW2zTgksWZOkDcWEQZZGzmwljZgZxRZlId3C3rRXpVd9ilIo7EV/XsF+hX2SnvnRn+Vsuq0J8ejM+fnmO2eOjmPOUoRxXMiCE4wRTXPGJQqyjMlAUpaJwcDKQlnmRHSf/BXNOuIXgmXVWpS1WNKUDGIVKw/kTUIXVaAZPA4Gg4jEaMWpJJgTUSTSVWoTvTsEkzJhQTRBEQ3lXEg+RGzxgoTy2kMHn6AzlpHJAMFHGfnGjSRr6SowflSkuXCtjyEimVAnDURI6dFJkAjiKWHIIpotj5xCxgcfO56FlAY0c3UQOKaJYfBhFQodaYAunNMP+PJ2Pr72Wjp78ILFt1pDfRwhAy5J5EzQJS/IsNkAUiO2wjErMrWrUba2F4WULLt3O0xo+A3Zt0M4ZxzkjmOEL/X/Du+t4w3tOcyZVAZ9kRCSu2N/BARpIS8ntftCEP7hIRyxKY0oSXwjrrU6Jo2Zf0HkjLOQCPF0dvrZKuDE9Wo9sg5JLtFUf0FRdj3kgRC1YJFiTQDgGK1Ho5PHTWQqEwJiZ5oRvmTP2JKG6O3dz2jzZvPn9rvtq+3d9vvNH5vf4enV9gf0FRWUOY1jw7oqLOVk88vmr83fmzfbO/j+bfMrmPyI3r7+yRnUFrqoTSp1Od6sMihiqCRdUVAX3WMkJFvqogIN17LyBZFX2sMlOHimFa60H8/r2C6KuCE+5CSAjBYZhaomGPZiwt00WLvjYRXlAzTecbEvook1VO61pQuLHTNOoHNkSsO/DZKCNMfPIZ0NqKvTs5Mvz44vv55N3QonXjCWDGvY+JbRCOc9QRPQsCkmKKFCzoEndaPm103MT1XQTgJIVqTY2NnD4CQPeJB6XfZpjBSaivhTYVhQRbBIiOUc+mLUS6mHjo5McXU9tgD7QZ6TLHJVZvdkz3KousBg5zr5U8BvoAi3dZYhGjU+ADu065qdru+ACoLOi0xd4KlqAG7nApCISsatrXZj+krj3XSBebcrKeI13lqLMXUvLIb5wfj6PgeKAG2vTJrUPtiFdm7i+1dBeEOT6KEi2Jvd1t3v59jC+Z85PlbgqkQrZoYt0PuyXbHwXtl+WuTQHKE7oHO6vKmcvDPtnbdNL+3WQUXR/sRbF3XizfN/ST2Ht2jnDWMW59PjS7fPUOs+123tHDy4BkDdaBYlJ7GrfHue9zChx6xIIh0BGm2E2vxaOhaKLNEic23bug7iJySW0IH1mqs8eOjRI3TYqJcddcnySnvBwH+6q77Ds43enTb0AKACO/oV1ACB8ceBCG0xPHrDrqWG2dYxuMHWQGpvWZA7Htagsgb9Er7LZu9lvWJJhMOCC+hG/QzPnp+etVPcpPVYm8yYcDvZbLx5PauLG7Yy1WBv2pOeyuccxkH7ImSXLNeKfUdEnjBOllwx3vLotYaOemwa+Yf7HDT4gZ3yHstxzzJlsMDklgDratAZHUKTqP8eVv9ov3pVStUQ2bvwHViP330gVRFNHvw1lMuOqLTJ2R3wUCCUbNLDZUZYhQrmJxdUjH1MsyBJWpPlvxtqbVMewbgPPQPjLEjVjyDo+A7GavjH2LFjv+4DF6WQJJ2uqXTNTwNv8A9hJvKGQQ0AAA==")))

            creationflags = 0x08000000  # CREATE_NO_WINDOW; stay in the interactive user session.
            with open(stdout_path, "wb") as out, open(stderr_path, "wb") as err_file:
                proc = subprocess.Popen(
                    [sys.executable, str(helper_path), str(result_path)],
                    cwd=str(workspace),
                    stdin=subprocess.DEVNULL,
                    stdout=out,
                    stderr=err_file,
                    creationflags=creationflags,
                    close_fds=False,
                )
            return ok({
                "scheduled": True,
                "action": "duplicate_right",
                "button": "Копировать →",
                "shape_ids": shape_ids,
                "helper_pid": int(proc.pid),
                "helper_path": str(helper_path),
                "result_path": str(result_path),
                "stdout_path": str(stdout_path),
                "stderr_path": str(stderr_path),
                "returns_before_ui_click": True,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def get_energologic_editor_ui_test_result() -> str:
        # Read the detached WinForms click helper result and process logs.
        try:
            import json
            result_path = workspace / "energologic_editor_ui_test_result.json"
            stdout_path = workspace / "energologic_editor_ui_test_stdout.txt"
            stderr_path = workspace / "energologic_editor_ui_test_stderr.txt"
            payload = None
            if result_path.is_file():
                payload = json.loads(result_path.read_text(encoding="utf-8-sig"))
            return ok({
                "available": payload is not None,
                "result": payload,
                "stdout": stdout_path.read_text(encoding="utf-8", errors="replace")[-4000:] if stdout_path.is_file() else "",
                "stderr": stderr_path.read_text(encoding="utf-8", errors="replace")[-4000:] if stderr_path.is_file() else "",
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def set_energologic_editor_acceptance_selection(
        shape_ids_json: str,
        page: str = "",
        doc_name: str = "",
    ) -> str:
        # Set only the active Visio selection for bounded editor acceptance.
        try:
            import json
            raw = json.loads(shape_ids_json)
            if not isinstance(raw, list) or not raw or len(raw) > 100:
                raise ValueError("shape_ids_json must be a JSON array with 1..100 items")
            shape_ids = [int(value) for value in raw]
            if len(set(shape_ids)) != len(shape_ids) or any(value <= 0 for value in shape_ids):
                raise ValueError("shape IDs must be unique positive integers")
            page_obj = visio._resolve_page(doc_name, parse_page(page))
            app = page_obj.Application
            try:
                app.ActiveWindow.Page = page_obj
            except Exception:
                page_obj.Activate()
            window = app.ActiveWindow
            window.DeselectAll()
            for shape_id in shape_ids:
                window.Select(page_obj.Shapes.ItemFromID(shape_id), 2)
            selected = [
                int(window.Selection.Item(index).ID)
                for index in range(1, int(window.Selection.Count) + 1)
            ]
            if sorted(selected) != sorted(shape_ids):
                raise RuntimeError(
                    f"Visio selection mismatch: requested={shape_ids!r}, selected={selected!r}"
                )
            return ok({
                "document": str(page_obj.Document.Name),
                "page": str(page_obj.Name),
                "selected_shape_ids": selected,
                "selection_only": True,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def invoke_energologic_editor_api(
        action: str,
        args_json: str = "{}",
        shape_ids_json: str = "",
        page: str = "",
        doc_name: str = "",
    ) -> str:
        # Invoke only fixed EnergoLogic editor v2 API actions for live acceptance.
        try:
            import json
            payload = json.loads(args_json or "{}")
            if not isinstance(payload, dict):
                raise ValueError("args_json must decode to an object")
            page_obj = visio._resolve_page(doc_name, parse_page(page))
            app = page_obj.Application
            try:
                app.ActiveWindow.Page = page_obj
            except Exception:
                page_obj.Activate()
            window = app.ActiveWindow
            requested_selection = []
            if str(shape_ids_json).strip():
                raw_selection = json.loads(shape_ids_json)
                if not isinstance(raw_selection, list) or not raw_selection or len(raw_selection) > 100:
                    raise ValueError("shape_ids_json must be a JSON array with 1..100 items")
                requested_selection = [int(value) for value in raw_selection]
                if len(set(requested_selection)) != len(requested_selection) or any(value <= 0 for value in requested_selection):
                    raise ValueError("shape IDs must be unique positive integers")
                window.DeselectAll()
                for shape_id in requested_selection:
                    window.Select(page_obj.Shapes.ItemFromID(shape_id), 2)
                actual_selection = [
                    int(window.Selection.Item(index).ID)
                    for index in range(1, int(window.Selection.Count) + 1)
                ]
                if sorted(actual_selection) != sorted(requested_selection):
                    raise RuntimeError(
                        f"Visio selection mismatch before editor action: requested={requested_selection!r}, "
                        f"selected={actual_selection!r}"
                    )
            addins = app.COMAddIns
            addins.Update()
            addin = addins.Item("EnergoLogic.VisioEditorAddinV349")
            if not bool(addin.Connect):
                raise RuntimeError("EnergoLogic editor v2 add-in is not connected")
            api = addin.Object
            if api is None:
                raise RuntimeError("EnergoLogic editor v2 COM API object is not published")
            before_shape_count = int(page_obj.Shapes.Count)
            key = str(action).strip().lower()
            zero = {
                "duplicate_left": "ApiDuplicateLeft",
                "duplicate_right": "ApiDuplicateRight",
                "move_left": "ApiMoveLeft",
                "move_right": "ApiMoveRight",
                "select_cell": "ApiSelectCell",
                "duplicate_selected_left": "ApiDuplicateSelectedLeft",
                "duplicate_selected_right": "ApiDuplicateSelectedRight",
                "duplicate_selected": "ApiDuplicateSelected",
                "distribute_selection_x": "ApiDistributeSelectionX",
                "distribute_selection_y": "ApiDistributeSelectionY",
                "measure_selection_distance": "ApiMeasureSelectionDistance",
                "snap_selection_grid_5": "ApiSnapSelectionGrid5",
                "bind_cell_identity": "ApiBindCellIdentity",
                "capture_replacement_sample": "ApiCaptureReplacementSample",
                "replace_equipment_from_sample": "ApiReplaceEquipmentFromSample",
                "insert_equipment_into_connection_from_sample": "ApiInsertEquipmentIntoConnectionFromSample",
                "repair_glue_preview": "ApiRepairGluePreview",
                "repair_glue_apply": "ApiRepairGlueApply",
                "doctor": "ApiDoctor",
                "visual_diagnostics": "ApiVisualDiagnostics",
                "bus_diagnostics": "ApiBusDiagnostics",
                "extend_bus_right": "ApiExtendBusRight",
                "trim_bus_right": "ApiTrimBusRight",
                "reconnect_begin": "ApiReconnectBegin",
                "reconnect_end": "ApiReconnectEnd",
                "align_x": "ApiAlignX",
                "align_y": "ApiAlignY",
                "measure_pitch": "ApiMeasurePitch",
                "coordinates": "ApiCoordinates",
                "nudge_left": "ApiNudgeLeft",
                "nudge_right": "ApiNudgeRight",
                "nudge_up": "ApiNudgeUp",
                "nudge_down": "ApiNudgeDown",
                "show_panel": "ApiShowPanel",
                "ui_status": "ApiUiStatus",
                "start_base_copy_interactive": "ApiStartBaseCopyInteractive",
                "start_base_move_interactive": "ApiStartBaseMoveInteractive",
                "start_base_copy_capture": "ApiStartBaseCopyCapture",
                "start_base_paste_interactive": "ApiStartBasePasteInteractive",
                "clear_base_clipboard": "ApiClearBaseClipboard",
                "base_clipboard_status": "ApiBaseClipboardStatus",
                "cancel_interactive_mode": "ApiCancelInteractiveMode",
                "interaction_status": "ApiInteractionStatus",
                "version": "ApiVersion",
                "operation_status": "ApiOperationStatus",
                "complete_pending_topology": "ApiCompletePendingTopology",
            }
            def invoke_zero(name):
                value = getattr(api, name)
                return value() if callable(value) else value

            if key in zero:
                result = invoke_zero(zero[key])
            elif key == "exact_offset":
                result = api.ApiExactOffset(float(payload["dx_mm"]), float(payload["dy_mm"]))
            elif key in {"base_copy", "base_move"}:
                values = [float(payload[name]) for name in ("base_x_mm", "base_y_mm", "target_x_mm", "target_y_mm")]
                result = api.ApiBaseCopy(*values) if key == "base_copy" else api.ApiBaseMove(*values)
            elif key == "distribute_pitch":
                result = api.ApiDistributePitch(float(payload["pitch_mm"]))
            elif key == "renumber_cell":
                result = api.ApiRenumberCell(str(payload["new_designation"]))
            else:
                raise ValueError(f"unsupported EnergoLogic editor action: {action!r}")
            selected = [
                int(window.Selection.Item(index).ID)
                for index in range(1, int(window.Selection.Count) + 1)
            ]
            return ok({
                "action": key,
                "result": str(result),
                "api_version": str(invoke_zero("ApiVersion")),
                "progid": "EnergoLogic.VisioEditorAddinV349",
                "page": str(page_obj.Name),
                "document": str(page_obj.Document.Name),
                "shape_count_before": before_shape_count,
                "shape_count_after": int(page_obj.Shapes.Count),
                "selected_shape_ids": selected,
                "requested_shape_ids": requested_selection,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def get_energologic_editor_ui_diagnostics() -> str:
        # Read visible WinForms child controls and texts without touching the drawing.
        try:
            import ctypes
            import os
            if os.name != "nt":
                raise RuntimeError("EnergoLogic UI diagnostics are Windows-only")
            user32 = ctypes.windll.user32

            def text_of(hwnd):
                length = int(user32.GetWindowTextLengthW(hwnd))
                buf = ctypes.create_unicode_buffer(max(1, length + 1))
                user32.GetWindowTextW(hwnd, buf, len(buf))
                return buf.value

            def class_of(hwnd):
                buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, buf, len(buf))
                return buf.value

            proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            windows = []
            @proc
            def enum_top(hwnd, _lparam):
                if bool(user32.IsWindowVisible(hwnd)) and text_of(hwnd) == "EnergoLogic — инструменты Visio":
                    windows.append(int(hwnd))
                return True
            user32.EnumWindows(enum_top, 0)
            if not windows:
                return ok({"window_found": False, "controls": []})
            root = windows[-1]
            controls = []
            @proc
            def enum_child(hwnd, _lparam):
                value = text_of(hwnd)
                cls = class_of(hwnd)
                if value or "EDIT" in cls.upper() or "BUTTON" in cls.upper():
                    controls.append({
                        "hwnd": int(hwnd),
                        "class": cls,
                        "text": value,
                        "visible": bool(user32.IsWindowVisible(hwnd)),
                        "enabled": bool(user32.IsWindowEnabled(hwnd)),
                    })
                return True
            user32.EnumChildWindows(root, enum_child, 0)
            return ok({
                "window_found": True,
                "window_hwnd": root,
                "controls": controls,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def uninstall_energologic_editor_ui() -> str:
        # Disconnect and remove every EnergoLogic editor UI registration.
        try:
            import winreg
            prefix = "EnergoLogic.VisioEditorAddinV"
            discovered = set()
            addins = None
            try:
                page_obj = visio._resolve_page(
                    "KRU-35_normal_scheme_v2_energologic_qol_host_v1.vsdm",
                    "MCP-v2",
                )
                addins = page_obj.Application.COMAddIns
                addins.Update()
                for index in range(1, int(addins.Count) + 1):
                    item = addins.Item(index)
                    candidate = str(item.ProgId)
                    if candidate.startswith(prefix):
                        discovered.add(candidate)
            except Exception:
                pass

            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Visio\Addins",
                    0,
                    winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                ) as key:
                    index = 0
                    while True:
                        try:
                            candidate = winreg.EnumKey(key, index)
                            index += 1
                        except OSError:
                            break
                        if candidate.startswith(prefix):
                            discovered.add(candidate)
            except FileNotFoundError:
                pass

            def read_clsid(progid):
                try:
                    with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER,
                        "Software\\Classes\\" + progid + "\\CLSID",
                        0,
                        winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                    ) as key:
                        value, _ = winreg.QueryValueEx(key, "")
                        return str(value).strip()
                except (FileNotFoundError, OSError):
                    return ""

            def delete_tree(root, subkey):
                try:
                    with winreg.OpenKey(
                        root,
                        subkey,
                        0,
                        winreg.KEY_READ | winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY,
                    ) as key:
                        children = []
                        index = 0
                        while True:
                            try:
                                children.append(winreg.EnumKey(key, index))
                                index += 1
                            except OSError:
                                break
                    for child in children:
                        delete_tree(root, subkey + "\\" + child)
                    winreg.DeleteKeyEx(root, subkey, winreg.KEY_WOW64_64KEY, 0)
                except FileNotFoundError:
                    pass

            removed = []
            for progid in sorted(discovered):
                try:
                    if addins is not None:
                        item = addins.Item(progid)
                        if bool(item.Connect):
                            item.Connect = False
                except Exception:
                    pass
                clsid = read_clsid(progid)
                targets = [
                    "Software\\Microsoft\\Visio\\Addins\\" + progid,
                    "Software\\Classes\\" + progid,
                ]
                if clsid:
                    targets.append("Software\\Classes\\CLSID\\" + clsid)
                for target in targets:
                    delete_tree(winreg.HKEY_CURRENT_USER, target)
                removed.append(progid)

            return ok({
                "removed": True,
                "hkcu_only": True,
                "removed_progids": removed,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def vtd_connection_control(
        mode: str,
        page: str = "",
        doc_name: str = "",
        stencil_name: str = "Трансформаторы.vss",
        selection_shape_id: int = 0,
    ) -> str:
        """Start or stop the native VTD connection-control VBA from an open VTD stencil.

        This is deliberately narrow: it can invoke only ThisDocument.StartCode or
        ThisDocument.StopCode, and only from a known VTD/GOST stencil already open
        in the live Visio instance. No arbitrary VBA text is accepted.
        """
        try:
            action = str(mode).strip().lower()
            macro = {
                "start": "ThisDocument.StartCode",
                "stop": "ThisDocument.StopCode",
            }.get(action)
            if macro is None:
                raise ValueError("mode must be 'start' or 'stop'")

            allowed = {
                "Генераторы, двигатели.vss",
                "Дополнительные элементы (Энергосбыт).vss",
                "Коммутационные аппараты.vss",
                "Линии, заземление.vss",
                "Предохранители.vss",
                "Разрядники, ОПН.vss",
                "Трансформаторы.vss",
                "Устройства компенсации, фильтры.vss",
                "Шины.vss",
                "Штамп, рамки, текст (ГОСТ).vss",
            }
            requested = str(stencil_name).strip()
            if requested not in allowed:
                raise ValueError("stencil_name is not an approved VTD stencil")

            page_obj = visio._resolve_page(doc_name, parse_page(page))
            app = page_obj.Application
            try:
                page_obj.Application.ActiveWindow.Page = page_obj
            except Exception:
                try:
                    page_obj.Activate()
                except Exception:
                    pass

            selected_shape = None
            if int(selection_shape_id) > 0:
                selected_shape = page_obj.Shapes.ItemFromID(int(selection_shape_id))
                window = app.ActiveWindow
                # visDeselectAll | visSelect = 256 | 2 = 258
                window.Select(selected_shape, 258)

            stencil = None
            for index in range(1, int(app.Documents.Count) + 1):
                candidate = app.Documents.Item(index)
                names = {str(getattr(candidate, "Name", "")), str(getattr(candidate, "NameU", ""))}
                if requested in names:
                    stencil = candidate
                    break
            if stencil is None:
                raise KeyError(f"Open VTD stencil not found: {requested}")

            stencil.ExecuteLine(macro)
            return ok({
                "mode": action,
                "macro": macro,
                "stencil_name": str(stencil.Name),
                "active_document": str(app.ActiveDocument.Name) if app.ActiveDocument else None,
                "active_page": str(app.ActivePage.Name) if app.ActivePage else None,
                "selected_shape_id": int(selected_shape.ID) if selected_shape is not None else None,
                "selected_shape_name": str(selected_shape.Name) if selected_shape is not None else None,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def batch_glue_endpoints(
        items_json: str,
        page: str = "",
        doc_name: str = "",
    ) -> str:
        """Glue existing 1-D BeginX/EndX endpoints to native connection-point rows."""
        try:
            import json
            items = json.loads(items_json)
            if not isinstance(items, list) or not items or len(items) > 300:
                raise ValueError("items_json must be a JSON array with 1..300 items")
            page_obj = visio._resolve_page(doc_name, parse_page(page))
            results = []
            for item in items:
                sid = int(item["shape_id"])
                target_sid = int(item["target_shape_id"])
                endpoint = str(item["endpoint"]).strip().lower()
                row_number = int(item["target_connection_row"])
                if endpoint not in {"begin", "end"}:
                    raise ValueError(f"endpoint must be begin/end for shape {sid}")
                if row_number < 1 or row_number > 256:
                    raise ValueError(f"target_connection_row out of range for shape {sid}")

                shape = page_obj.Shapes.ItemFromID(sid)
                target = page_obj.Shapes.ItemFromID(target_sid)
                source_cell_name = "BeginX" if endpoint == "begin" else "EndX"
                source_cell = shape.CellsU(source_cell_name)

                # Connection point rows are exposed as Connections.X1, X2, ... in
                # universal ShapeSheet names. GlueTo on the X cell binds the whole
                # 1-D endpoint (X/Y) to the native connection point.
                target_cell_name = f"Connections.X{row_number}"
                if not bool(target.CellExistsU(target_cell_name, 0)):
                    raise KeyError(
                        f"Target shape {target_sid} has no {target_cell_name}"
                    )
                target_cell = target.CellsU(target_cell_name)

                before = {
                    "x_formula_u": str(shape.CellsU(source_cell_name).FormulaU),
                    "y_formula_u": str(shape.CellsU("BeginY" if endpoint == "begin" else "EndY").FormulaU),
                }
                source_cell.GlueTo(target_cell)
                after = {
                    "x_formula_u": str(shape.CellsU(source_cell_name).FormulaU),
                    "y_formula_u": str(shape.CellsU("BeginY" if endpoint == "begin" else "EndY").FormulaU),
                }
                results.append({
                    "shape_id": sid,
                    "shape_name": str(shape.Name),
                    "endpoint": endpoint,
                    "target_shape_id": target_sid,
                    "target_shape_name": str(target.Name),
                    "target_connection_row": row_number,
                    "before": before,
                    "after": after,
                })
            return ok({"count": len(results), "results": results})
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def operator_notes_peek(limit: int = 20) -> str:
        """Read pending operator notes written by Visio Bridge Console without acknowledging them."""
        try:
            import json
            bounded = max(1, min(int(limit), 100))
            rows = []
            for path in sorted(pending_dir.glob("note-*.json"), key=lambda item: item.stat().st_mtime)[:bounded]:
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if not isinstance(payload, dict):
                    continue
                note_id = str(payload.get("id", ""))
                text_value = str(payload.get("text", ""))
                if not note_id.startswith("note-") or not text_value:
                    continue
                rows.append({
                    "id": note_id,
                    "created_at": str(payload.get("created_at", "")),
                    "text": text_value,
                    "source": str(payload.get("source", "")),
                })
            return ok({"count": len(rows), "notes": rows})
        except Exception as exc:
            return err(exc)


    @mcp.tool()
    def operator_notes_ack(note_ids_json: str) -> str:
        """Acknowledge pending operator notes after they have been read/acted upon."""
        try:
            import json
            import os
            import re
            note_ids = json.loads(note_ids_json)
            if not isinstance(note_ids, list) or len(note_ids) > 100:
                raise ValueError("note_ids_json must be a JSON array with at most 100 IDs")
            moved = []
            for raw in note_ids:
                note_id = str(raw)
                if re.fullmatch(r"note-[0-9a-f]{32}", note_id) is None:
                    raise ValueError(f"Invalid note ID: {note_id}")
                source = pending_dir / f"{note_id}.json"
                target = acked_dir / f"{note_id}.json"
                if source.exists():
                    os.replace(source, target)
                    moved.append(note_id)
                elif target.exists():
                    moved.append(note_id)
            return ok({"acknowledged": moved, "count": len(moved)})
        except Exception as exc:
            return err(exc)


    @mcp.tool()
    def operator_reply_send(text: str, note_ids_json: str = "[]") -> str:
        """Write one ChatGPT/bridge reply into the Console side-channel."""
        try:
            import json
            import os
            from datetime import datetime, timezone
            value = str(text).strip()
            if not value or len(value) > 8000:
                raise ValueError("Reply text must contain 1..8000 characters")
            note_ids = json.loads(note_ids_json)
            if not isinstance(note_ids, list) or len(note_ids) > 100:
                raise ValueError("note_ids_json must be a JSON array with at most 100 IDs")
            reply_id = "reply-" + uuid.uuid4().hex
            payload = {
                "id": reply_id,
                "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                "text": value,
                "note_ids": [str(item) for item in note_ids],
                "source": "chatgpt-visio-bridge",
            }
            target = replies_dir / f"{reply_id}.json"
            temp = replies_dir / f".{reply_id}.tmp"
            temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            os.replace(temp, target)
            return ok({"reply_id": reply_id, "created_at": payload["created_at"]})
        except Exception as exc:
            return err(exc)


    @mcp.tool()
    def install_bridge_console() -> str:
        """Install/update the server-pinned Visio Bridge Console and a Desktop shortcut."""
        try:
            import base64 as _base64
            import hashlib
            import os
            import tkinter as _tkinter
            import win32com.client

            pythonw_exe = root / "venv312" / "Scripts" / "pythonw.exe"
            if not pythonw_exe.exists():
                raise FileNotFoundError("Visio Python venv pythonw not found")
            tkinter_version = str(_tkinter.TkVersion)

            raw = _base64.b64decode(CONSOLE_SOURCE_B64.encode("ascii"), validate=True)
            source = raw.decode("utf-8")
            compile(source, "visio_bridge_console.pyw", "exec")

            console_dir = root / "console"
            console_dir.mkdir(parents=True, exist_ok=True)
            target = console_dir / "visio_bridge_console.pyw"
            temp = console_dir / ".visio_bridge_console.pyw.update"
            temp.write_bytes(raw)
            os.replace(temp, target)

            shell = win32com.client.Dispatch("WScript.Shell")
            desktop = Path(str(shell.SpecialFolders("Desktop")))
            shortcut_path = desktop / "Visio Bridge Console.lnk"
            shortcut = shell.CreateShortcut(str(shortcut_path))
            shortcut.TargetPath = str(pythonw_exe)
            shortcut.Arguments = f'"{target}"'
            shortcut.WorkingDirectory = str(console_dir)
            shortcut.Description = "OpenAI Visio live bridge console"
            visio_icon = Path(os.environ.get("ProgramFiles", r"C:\\Program Files")) / "Microsoft Office" / "root" / "Office16" / "VISIO.EXE"
            if visio_icon.exists():
                shortcut.IconLocation = str(visio_icon) + ",0"
            shortcut.Save()

            return ok({
                "console_version": "2026.10.02.3",
                "console_path": str(target),
                "shortcut_path": str(shortcut_path),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "tkinter": tkinter_version,
            })
        except Exception as exc:
            return err(exc)

