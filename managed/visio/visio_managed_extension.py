from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.136"
CONSOLE_SOURCE_B64 = "__CONSOLE_SOURCE_B64__"
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

            legacy_editor_versions = [
                ("EnergoLogic.VisioEditorAddinV31", "{F2236480-88B8-42B3-AEC4-0707D59A14FC}"),
                ("EnergoLogic.VisioEditorAddinV32", "{9B2D0D65-A68C-44D0-A523-612148808DBD}"),
                ("EnergoLogic.VisioEditorAddinV33", "{54D4E77E-73B0-4D45-94E2-B138DF35D1A3}"),
                ("EnergoLogic.VisioEditorAddinV34", "{A6E63A2D-0DA5-4E84-9B2B-5B3E6944B5F4}"),
                ("EnergoLogic.VisioEditorAddinV35", "{D93F00C2-1C95-4D0A-A0A9-609E25B9794C}"),
                ("EnergoLogic.VisioEditorAddinV36", "{81705A73-9C25-4E72-84A8-F58E4C818AAF}"),
                ("EnergoLogic.VisioEditorAddinV37", "{3D58EA6C-A51F-41B9-A46D-BF0FB3BA7C5A}"),
                ("EnergoLogic.VisioEditorAddinV38", "{9974BD0D-D56E-45F5-BB8C-7A21485C6730}"),
                ("EnergoLogic.VisioEditorAddinV39", "{B42A3C6E-8C1F-44AB-A486-93C6AB3D8F39}"),
                ("EnergoLogic.VisioEditorAddinV310", "{D1C940D2-5A7E-4B4B-A92A-2D443A0DBA85}"),
                ("EnergoLogic.VisioEditorAddinV311", "{6D8D560D-1F9F-4CB8-BED7-5FCBB70B1F2C}"),
                ("EnergoLogic.VisioEditorAddinV312", "{2F8B22F0-0A1B-4E30-B850-09B1F7197D3D}"),
                ("EnergoLogic.VisioEditorAddinV313", "{1A6AF8E1-2576-4EF3-96EC-676904B6DA57}"),
                ("EnergoLogic.VisioEditorAddinV314", "{6989E63C-E667-4B14-B85B-210710468940}"),
                ("EnergoLogic.VisioEditorAddinV315", "{E82068B0-D05D-4646-82B0-0CA923733CAF}"),
                ("EnergoLogic.VisioEditorAddinV316", "{89DDBB87-8513-5078-9BF3-1DA6D75B2454}"),
                ("EnergoLogic.VisioEditorAddinV317", "{D0F27C51-9E15-4C2D-A584-170EA8B7F317}"),
                ("EnergoLogic.VisioEditorAddinV318", "{6BC8DE0D-79B4-4E0D-9E0A-C6E6A7E0F318}"),
                ("EnergoLogic.VisioEditorAddinV319", "{A2ECDF6D-77BB-4B3A-8B29-3B736850F319}"),
                ("EnergoLogic.VisioEditorAddinV320", "{08DA44F1-A58D-4E53-8F2F-A1107D57F320}"),
                ("EnergoLogic.VisioEditorAddinV321", "{9D1B5AC1-0C47-4C18-BB03-7ED263E8F321}"),
                ("EnergoLogic.VisioEditorAddinV322", "{D65447E9-8176-4EBB-8CC4-4DAA1C3AF322}"),
                ("EnergoLogic.VisioEditorAddinV323", "{3C74BB1A-284A-414B-BAE0-5D413682F323}"),
                ("EnergoLogic.VisioEditorAddinV324", "{7F0BF42E-719C-4A53-9926-DFE2B0EEF324}"),
                ("EnergoLogic.VisioEditorAddinV325", "{8E9D3160-A441-4944-9471-728178F5F325}"),
                ("EnergoLogic.VisioEditorAddinV326", "{B0DB7395-E237-4F35-BED6-AE59C2C5F326}"),
                ("EnergoLogic.VisioEditorAddinV327", "{9A7903D3-1371-4AF6-B80A-01F6C039F327}"),
                ("EnergoLogic.VisioEditorAddinV328", "{8E75F86D-AF28-455B-B20C-62492D9BF328}"),
            ]

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
            for legacy_progid, legacy_clsid in legacy_editor_versions:
                try:
                    legacy_item = addins.Item(legacy_progid)
                    if bool(legacy_item.Connect):
                        legacy_item.Connect = False
                except Exception:
                    pass
                for legacy_key in (
                    "Software\\Microsoft\\Visio\\Addins\\" + legacy_progid,
                    "Software\\Classes\\" + legacy_progid,
                    "Software\\Classes\\CLSID\\" + legacy_clsid,
                ):
                    delete_tree(winreg.HKEY_CURRENT_USER, legacy_key)
                removed_legacy.append(legacy_progid)

            try:
                stale_bar = app.CommandBars.Item("EnergoLogic")
                stale_bar.Delete()
            except Exception:
                pass
            addins.Update()

            build_dir = workspace / "energologic_visio_editor_addin_v336"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV336.dll"
            helper_source_path = build_dir / "EnergoLogicTopologyRestoreHelper.cs"
            helper_exe_path = build_dir / "EnergoLogic.TopologyRestoreHelper.exe"
            helper_source_path.write_bytes(gzip.decompress(base64.b64decode(TOPOLOGY_HELPER_SOURCE_B64)))
            source_path.write_bytes(gzip.decompress(base64.b64decode("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")))

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

            clsid = "{98DC22DA-BC28-48C5-B79B-C90E6A7CF336}"
            progid = "EnergoLogic.VisioEditorAddinV336"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV336, Version=0.3.36.0, Culture=neutral, PublicKeyToken=null"
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
                "ui": "modeless WinForms panel + Visio CommandBar toggle",
                "tabs": ["Ячейки", "Геометрия", "Проверка"],
                "removed_legacy_versions": removed_legacy,
                "migration": "v3.1-v3.35 -> v3.36",
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
            progid = "EnergoLogic.VisioEditorAddinV336"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV336")
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
                "progid": "EnergoLogic.VisioEditorAddinV336",
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
        # Disconnect and remove only the EnergoLogic editor UI registration.
        try:
            import winreg
            progid = "EnergoLogic.VisioEditorAddinV336"
            clsid = "{98DC22DA-BC28-48C5-B79B-C90E6A7CF336}"
            try:
                page_obj = visio._resolve_page(
                    "KRU-35_normal_scheme_v2_energologic_qol_host_v1.vsdm",
                    "MCP-v2",
                )
                addins = page_obj.Application.COMAddIns
                addins.Update()
                item = addins.Item(progid)
                if bool(item.Connect):
                    item.Connect = False
            except Exception:
                pass

            targets = [
                "Software\\Microsoft\\Visio\\Addins\\" + progid,
                "Software\\Classes\\" + progid,
                "Software\\Classes\\CLSID\\" + clsid,
            ]

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

            for target in targets:
                delete_tree(winreg.HKEY_CURRENT_USER, target)
            return ok({"progid": progid, "removed": True, "hkcu_only": True})
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

