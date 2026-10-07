from __future__ import annotations

import base64
import gzip
import hashlib
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.06.213"
CONSOLE_SOURCE_B64 = "__CONSOLE_SOURCE_B64__"
PORTABLE_KIT_TEMPLATE_B64 = "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"
TOPOLOGY_HELPER_SOURCE_B64 = "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"


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
            import subprocess
            import zipfile
            from datetime import datetime, timezone

            version = "0.3.64"
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

            # Build release binaries on the build workstation. The target
            # installer only validates/copies these artifacts and therefore does not
            # require csc.exe, Office PIA or Visual Studio interop assemblies.
            bin_dir = kit_dir / "bin"
            bin_dir.mkdir(parents=True, exist_ok=True)
            portable_dll = bin_dir / "EnergoLogic.VisioEditorAddinV364.dll"
            portable_helper = bin_dir / "EnergoLogic.TopologyRestoreHelper.exe"

            framework_candidates = [
                Path(r"C:\WINDOWS\Microsoft.NET\Framework64\v4.0.30319"),
                Path(r"C:\WINDOWS\Microsoft.NET\Framework\v4.0.30319"),
            ]
            framework = next(
                (candidate for candidate in framework_candidates if (candidate / "csc.exe").is_file()),
                None,
            )
            if framework is None:
                raise FileNotFoundError("build host: .NET Framework 4.x csc.exe not found")

            office_candidates = list(Path(r"C:\WINDOWS\Microsoft.NET\assembly\GAC_MSIL\Office").glob("*/Office.dll"))
            office_candidates += list(Path(r"C:\WINDOWS\assembly\GAC_MSIL\Office").glob("*/Office.dll"))
            office_candidates += [Path(r"C:\Program Files\Microsoft Office\root\Office16\ADDINS\PowerPivot Excel Add-in\OFFICE.dll")]
            office_ref = next((candidate for candidate in office_candidates if candidate.is_file()), None)
            if office_ref is None:
                raise FileNotFoundError("build host: Office.dll not found for compile-time type embedding")

            csc = framework / "csc.exe"
            editor_compile = subprocess.run(
                [
                    str(csc),
                    "/nologo",
                    "/target:library",
                    "/platform:anycpu",
                    "/optimize+",
                    f"/out:{portable_dll}",
                    f"/link:{office_ref}",
                    f"/reference:{framework / 'System.Windows.Forms.dll'}",
                    f"/reference:{framework / 'System.Drawing.dll'}",
                    f"/reference:{framework / 'Microsoft.CSharp.dll'}",
                    str(payload / "EnergoLogicVisioEditorAddin.cs"),
                ],
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
            if editor_compile.returncode != 0 or not portable_dll.is_file():
                raise RuntimeError(
                    "portable editor binary compilation failed: "
                    + (editor_compile.stdout + "\n" + editor_compile.stderr)[-6000:]
                )

            helper_compile = subprocess.run(
                [
                    str(csc),
                    "/nologo",
                    "/target:exe",
                    "/platform:anycpu",
                    "/optimize+",
                    f"/out:{portable_helper}",
                    f"/reference:{framework / 'Microsoft.CSharp.dll'}",
                    str(payload / "EnergoLogicTopologyRestoreHelper.cs"),
                ],
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
            if helper_compile.returncode != 0 or not portable_helper.is_file():
                raise RuntimeError(
                    "portable topology helper compilation failed: "
                    + (helper_compile.stdout + "\n" + helper_compile.stderr)[-6000:]
                )

            # Verify emitted assembly dependencies before the artifacts enter the manifest.
            dependency_check = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-Command",
                    "$a=[Reflection.Assembly]::ReflectionOnlyLoadFrom('" + str(portable_dll).replace("'", "''") + "'); "
                    "$bad=@($a.GetReferencedAssemblies() | ? {$_.Name -match '^(Office|Extensibility|Microsoft\\.VisualStudio\\.Interop)$'}); "
                    "if($bad.Count){$bad | % FullName; exit 41}; "
                    "Write-Output 'RUNTIME_PIA_DEPENDENCY=NONE'",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if dependency_check.returncode != 0:
                raise RuntimeError(
                    "portable binary dependency validation failed: "
                    + (dependency_check.stdout + "\n" + dependency_check.stderr)[-3000:]
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
                "editor_api_version": "0.3.64",
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

            # Validate the exact final package with the target-side installer.
            # CompileOnly now validates prebuilt binaries and never compiles or registers.
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

            current_progid = "EnergoLogic.VisioEditorAddinV364"
            editor_progid_prefix = "EnergoLogic.VisioEditorAddinV"
            architecture = (
                os.environ.get("PROCESSOR_ARCHITEW6432")
                or os.environ.get("PROCESSOR_ARCHITECTURE")
                or ""
            ).upper()
            registry_views = (
                [winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY]
                if "64" in architecture
                else [0]
            )

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
                "EnergoLogic.VisioEditorAddinV360": "{8B7F2A13-1F51-47F4-9D1A-A7E0F360C001}",
                "EnergoLogic.VisioEditorAddinV361": "{8B7F2A13-1F51-47F4-9D1A-A7E0F361C001}",
                "EnergoLogic.VisioEditorAddinV362": "{8B7F2A13-1F51-47F4-9D1A-A7E0F362C001}",
                "EnergoLogic.VisioEditorAddinV363": "{8B7F2A13-1F51-47F4-9D1A-A7E0F363C001}",
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

            def discover_editor_progids(subkey):
                for view in registry_views:
                    try:
                        with winreg.OpenKey(
                            winreg.HKEY_CURRENT_USER,
                            subkey,
                            0,
                            winreg.KEY_READ | view,
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

            # Registry discovery covers both 32- and 64-bit Visio registrations.
            discover_editor_progids(r"Software\Microsoft\Visio\Addins")
            # Also include orphaned ProgID class registrations left by interrupted
            # historical installs.
            discover_editor_progids(r"Software\Classes")

            def read_progid_clsid(progid):
                if progid in known_legacy_clsids:
                    return known_legacy_clsids[progid]
                for view in registry_views:
                    try:
                        with winreg.OpenKey(
                            winreg.HKEY_CURRENT_USER,
                            "Software\\Classes\\" + progid + "\\CLSID",
                            0,
                            winreg.KEY_READ | view,
                        ) as key:
                            value, _ = winreg.QueryValueEx(key, "")
                            if value:
                                return str(value).strip()
                    except (FileNotFoundError, OSError):
                        pass
                return ""


            def delete_tree_view(root, subkey, view):
                try:
                    with winreg.OpenKey(
                        root, subkey, 0,
                        winreg.KEY_READ | winreg.KEY_WRITE | view,
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
                        delete_tree_view(root, subkey + "\\" + child, view)
                    winreg.DeleteKeyEx(root, subkey, view, 0)
                except FileNotFoundError:
                    pass

            def delete_tree(root, subkey):
                for view in registry_views:
                    delete_tree_view(root, subkey, view)


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

            # If this ProgID was already connected with a stale CLSID/assembly,
            # disconnect and remove its current registration before re-binding it.
            current_existing_clsid = read_progid_clsid(current_progid)
            try:
                current_item = addins.Item(current_progid)
                if bool(current_item.Connect):
                    current_item.Connect = False
            except Exception:
                pass
            for current_key in [
                "Software\\Microsoft\\Visio\\Addins\\" + current_progid,
                "Software\\Classes\\" + current_progid,
            ]:
                delete_tree(winreg.HKEY_CURRENT_USER, current_key)
            if (
                current_existing_clsid
                and current_existing_clsid.upper() != "{8B7F2A13-1F51-47F4-9D1A-A7E0F364C001}"
            ):
                delete_tree(
                    winreg.HKEY_CURRENT_USER,
                    "Software\\Classes\\CLSID\\" + current_existing_clsid,
                )
            addins.Update()

            removed_build_dirs = []
            current_build_dir_name = "energologic_visio_editor_addin_v364"
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

            build_dir = workspace / "energologic_visio_editor_addin_v364"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV364.dll"
            helper_source_path = build_dir / "EnergoLogicTopologyRestoreHelper.cs"
            helper_exe_path = build_dir / "EnergoLogic.TopologyRestoreHelper.exe"
            helper_source_path.write_bytes(gzip.decompress(base64.b64decode(TOPOLOGY_HELPER_SOURCE_B64)))
            staged_editor_source = workspace / "managed_payloads" / "EnergoLogicVisioEditorAddin.cs"
            if not staged_editor_source.is_file():
                raise FileNotFoundError(
                    "EnergoLogic editor source payload is not staged; run visio_managed_update first"
                )
            source_path.write_bytes(staged_editor_source.read_bytes())

            framework_candidates = [
                Path(r"C:\WINDOWS\Microsoft.NET\Framework64\v4.0.30319"),
                Path(r"C:\WINDOWS\Microsoft.NET\Framework\v4.0.30319"),
            ]
            framework = next(
                (candidate for candidate in framework_candidates if (candidate / "csc.exe").is_file()),
                None,
            )
            if framework is None:
                raise FileNotFoundError(".NET Framework 4.x csc.exe not found")

            office_candidates = list(Path(r"C:\WINDOWS\Microsoft.NET\assembly\GAC_MSIL\Office").glob("*/Office.dll"))
            office_candidates += list(Path(r"C:\WINDOWS\assembly\GAC_MSIL\Office").glob("*/Office.dll"))
            office_candidates += [Path(r"C:\Program Files\Microsoft Office\root\Office16\ADDINS\PowerPivot Excel Add-in\OFFICE.dll")]
            office_ref = next((candidate for candidate in office_candidates if candidate.is_file()), None)
            if office_ref is None:
                raise FileNotFoundError("Microsoft Office PIA (Office.dll) not found for compile-time type embedding")

            framework_refs = [
                framework / "System.Windows.Forms.dll",
                framework / "System.Drawing.dll",
                framework / "Microsoft.CSharp.dll",
            ]
            for reference in framework_refs:
                if not reference.is_file():
                    raise FileNotFoundError(f"required framework assembly not found: {reference}")

            csc = framework / "csc.exe"
            compile_args = [
                str(csc),
                "/nologo",
                "/target:library",
                "/platform:anycpu",
                "/optimize+",
                f"/out:{dll_path}",
                f"/link:{office_ref}",
            ] + [f"/reference:{reference}" for reference in framework_refs] + [str(source_path)]
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
                "/platform:anycpu",
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

            clsid = "{8B7F2A13-1F51-47F4-9D1A-A7E0F364C001}"
            progid = current_progid
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV364, Version=0.3.64.0, Culture=neutral, PublicKeyToken=null"
            codebase = dll_path.resolve().as_uri()

            def set_string(root, subkey, name, value):
                for view in registry_views:
                    with winreg.CreateKeyEx(
                        root,
                        subkey,
                        0,
                        winreg.KEY_WRITE | view,
                    ) as key:
                        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

            def set_dword(root, subkey, name, value):
                for view in registry_views:
                    with winreg.CreateKeyEx(
                        root,
                        subkey,
                        0,
                        winreg.KEY_WRITE | view,
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
                    len([item for item in editor_addins_after if item["connected"]]) == 1
                    and any(
                        item["progid"] == progid and item["connected"]
                        for item in editor_addins_after
                    )
                ),
                "migration": "all legacy editor registrations -> v3.64",
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
            progid = "EnergoLogic.VisioEditorAddinV364"
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
            window = app.ActiveWindow
            # Do not re-assign the already-active page. Even a same-page assignment
            # can trigger Visio/VTD UI events and create a separate native Undo unit.
            active_page = window.Page
            active_name = str(getattr(active_page, "NameU", "") or getattr(active_page, "Name", ""))
            target_name = str(getattr(page_obj, "NameU", "") or getattr(page_obj, "Name", ""))
            active_doc = str(getattr(active_page.Document, "Name", "") or "")
            target_doc = str(getattr(page_obj.Document, "Name", "") or "")
            if active_name != target_name or active_doc != target_doc:
                try:
                    window.Page = page_obj
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
            # Do not call COMAddIns.Update() in the command hot path. On live Visio
            # this refresh creates a separate user-visible native Undo unit even for
            # a read-only ApiVersion call, which masks the helper-owned transaction.
            addins = app.COMAddIns
            addin = addins.Item("EnergoLogic.VisioEditorAddinV364")
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
                "progid": "EnergoLogic.VisioEditorAddinV364",
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
    def refresh_energologic_topology_helper() -> str:
        """Recompile only the external topology helper for the currently installed V364 add-in."""
        try:
            import base64 as _base64
            import gzip as _gzip
            import hashlib
            import subprocess

            build_dir = workspace / "energologic_visio_editor_addin_v364"
            if not build_dir.is_dir():
                raise FileNotFoundError("V364 build directory is not installed")
            source_path = build_dir / "EnergoLogicTopologyRestoreHelper.cs"
            exe_path = build_dir / "EnergoLogic.TopologyRestoreHelper.exe"
            source = _gzip.decompress(_base64.b64decode(TOPOLOGY_HELPER_SOURCE_B64))
            source_path.write_bytes(source)
            framework = Path(r"C:\WINDOWS\Microsoft.NET\Framework64\v4.0.30319")
            csc = framework / "csc.exe"
            compiled = subprocess.run(
                [
                    str(csc),
                    "/nologo",
                    "/target:exe",
                    "/platform:x64",
                    "/optimize+",
                    f"/out:{exe_path}",
                    f"/reference:{framework / 'Microsoft.CSharp.dll'}",
                    str(source_path),
                ],
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
            if compiled.returncode != 0 or not exe_path.is_file():
                raise RuntimeError(
                    "EnergoLogic topology helper refresh failed: "
                    + (compiled.stdout + "\\n" + compiled.stderr)[-6000:]
                )
            return ok({
                "refreshed": True,
                "source_path": str(source_path),
                "exe_path": str(exe_path),
                "source_sha256": hashlib.sha256(source).hexdigest(),
                "apartment": "STA",
                "selection_strategy": "off-screen-prepared-before-undo-scope",
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def diagnose_visio_crash_events(minutes: int = 120) -> str:
        """Read-only Windows Application log + WER evidence for recent Visio crashes."""
        try:
            import os
            import datetime as _dt
            from pathlib import Path as _Path
            import win32evtlog
            import win32com.client

            window = max(5, min(int(minutes), 1440))
            cutoff = _dt.datetime.now() - _dt.timedelta(minutes=window)
            process = None
            try:
                app = win32com.client.GetActiveObject("Visio.Application")
                reported_pid = int(getattr(app, "ProcessID", 0) or 0)
                process = {
                    "reported_process_id": reported_pid,
                    "version": str(getattr(app, "Version", "") or ""),
                    "visible": bool(getattr(app, "Visible", False)),
                    "documents": int(app.Documents.Count),
                }
                try:
                    import win32api, win32con, win32process
                    hwnd = int(getattr(app.ActiveWindow, "WindowHandle32", 0) or 0)
                    process["window_handle"] = hwnd
                    _thread_id, real_pid = win32process.GetWindowThreadProcessId(hwnd)
                    process["process_id"] = int(real_pid)
                    handle = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION, False, int(real_pid))
                    try:
                        created, exited, kernel, user = win32process.GetProcessTimes(handle)
                        process["created"] = created.Format("%Y-%m-%dT%H:%M:%S")
                    finally:
                        win32api.CloseHandle(handle)
                except Exception as time_exc:
                    process["process_time_error"] = str(time_exc)
            except Exception as exc:
                process = {"active_object": False, "error": str(exc)}

            handle = win32evtlog.OpenEventLog(None, "Application")
            flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
            events = []
            try:
                stop = False
                while len(events) < 30 and not stop:
                    batch = win32evtlog.ReadEventLog(handle, flags, 0)
                    if not batch:
                        break
                    for event in batch:
                        when = event.TimeGenerated
                        try:
                            when_dt = _dt.datetime.fromtimestamp(when.timestamp())
                        except Exception:
                            when_dt = _dt.datetime.now()
                        if when_dt < cutoff:
                            stop = True
                            break
                        source = str(event.SourceName or "")
                        if source not in {"Application Error", "Application Hang", "Windows Error Reporting", ".NET Runtime", "Microsoft Office 16 Alerts", "Microsoft Office Alerts"}:
                            continue
                        inserts = [str(x) for x in (event.StringInserts or [])]
                        message = " | ".join(inserts)
                        events.append({
                            "time": when_dt.isoformat(),
                            "source": source,
                            "event_id": int(event.EventID & 0xFFFF),
                            "event_type": int(event.EventType),
                            "strings": inserts[:40],
                        })
            finally:
                try: win32evtlog.CloseEventLog(handle)
                except Exception: pass

            wer = []
            roots = []
            local = os.environ.get("LOCALAPPDATA")
            program = os.environ.get("ProgramData")
            if local:
                roots.append(_Path(local) / "Microsoft" / "Windows" / "WER" / "ReportArchive")
            if program:
                roots.append(_Path(program) / "Microsoft" / "Windows" / "WER" / "ReportArchive")
            for root in roots:
                try:
                    if not root.exists():
                        continue
                    for item in root.iterdir():
                        try:
                            if not item.is_dir():
                                continue
                            stamp = _dt.datetime.fromtimestamp(item.stat().st_mtime)
                            name = item.name
                            if stamp < cutoff:
                                continue
                            if "visio" not in name.lower() and "office" not in name.lower():
                                continue
                            wer.append({"path": str(item), "modified": stamp.isoformat()})
                        except Exception:
                            continue
                except Exception:
                    continue

            return ok({"window_minutes": window, "process": process, "events": events, "wer": wer})
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
    def inspect_vtd_vba_source(
        max_matches: int = 120,
        document_name: str = "",
        include_all_components: bool = False,
    ) -> str:
        """Read-only inspection of VBA projects/components in open Visio documents/stencils."""
        try:
            import win32com.client
            app = win32com.client.GetActiveObject("Visio.Application")
            limit = max(10, min(int(max_matches), 500))
            requested = str(document_name or "").strip().casefold()
            keywords = [
                "StartCode", "StopCode", "ShapeChanged", "CellChanged",
                "Connections", "Glue", "BeginX", "EndX", "AddAdvise",
                "WithEvents", "Selection", "Document_", "Window_",
                "SETF", "EventXFMod", "MarkerEvent", "QueueMarkerEvent",
            ]
            projects = []
            total_matches = 0
            for index in range(1, int(app.Documents.Count) + 1):
                doc = app.Documents.Item(index)
                name = str(getattr(doc, "Name", "") or "")
                name_u = str(getattr(doc, "NameU", "") or "")
                full_name = str(getattr(doc, "FullName", "") or "")
                if requested and requested not in {name.casefold(), name_u.casefold()}:
                    continue
                entry = {
                    "document": name,
                    "name_u": name_u,
                    "full_name": full_name,
                    "type": int(getattr(doc, "Type", 0) or 0),
                    "components": [],
                }
                try:
                    project = doc.VBProject
                    entry["project_name"] = str(getattr(project, "Name", "") or "")
                    components = project.VBComponents
                    entry["component_count"] = int(components.Count)
                    for cidx in range(1, int(components.Count) + 1):
                        component = components.Item(cidx)
                        comp_name = str(getattr(component, "Name", "") or "")
                        comp_type = int(getattr(component, "Type", 0) or 0)
                        code_module = component.CodeModule
                        count = int(getattr(code_module, "CountOfLines", 0) or 0)
                        procedures = []
                        if count > 0:
                            line_no = 1
                            seen_proc = set()
                            while line_no <= count:
                                try:
                                    proc = str(code_module.ProcOfLine(line_no, 0) or "")
                                except Exception:
                                    proc = ""
                                if proc and proc not in seen_proc:
                                    seen_proc.add(proc)
                                    procedures.append(proc)
                                line_no += 1
                        matches = []
                        if count > 0 and total_matches < limit:
                            source = str(code_module.Lines(1, count) or "")
                            lines = source.splitlines()
                            seen = set()
                            for source_line_no, line in enumerate(lines, 1):
                                if not any(keyword.casefold() in line.casefold() for keyword in keywords):
                                    continue
                                snippet_start = max(1, source_line_no - 3)
                                snippet_end = min(len(lines), source_line_no + 5)
                                key = (snippet_start, snippet_end)
                                if key in seen:
                                    continue
                                seen.add(key)
                                matches.append({
                                    "start_line": snippet_start,
                                    "end_line": snippet_end,
                                    "lines": [
                                        {"line": n, "text": lines[n - 1]}
                                        for n in range(snippet_start, snippet_end + 1)
                                    ],
                                })
                                total_matches += 1
                                if total_matches >= limit:
                                    break
                        if include_all_components or matches:
                            entry["components"].append({
                                "name": comp_name,
                                "type": comp_type,
                                "line_count": count,
                                "procedures": procedures,
                                "matches": matches,
                            })
                except Exception as exc:
                    entry["vbproject_error"] = str(exc)
                if include_all_components or entry.get("components") or entry.get("vbproject_error"):
                    projects.append(entry)
            return ok({
                "match_limit": limit,
                "match_count": total_matches,
                "requested_document": document_name or None,
                "include_all_components": bool(include_all_components),
                "projects": projects,
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

