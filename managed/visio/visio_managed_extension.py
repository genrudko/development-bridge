from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.84"
CONSOLE_SOURCE_B64 = "__CONSOLE_SOURCE_B64__"


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
            build_dir = workspace / "energologic_visio_editor_addin_v2"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV2.dll"
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

            clsid = "{9C760F65-31D1-49B5-A53A-A13580D67E92}"
            progid = "EnergoLogic.VisioEditorAddinV2"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV2, Version=0.2.1.0, Culture=neutral, PublicKeyToken=null"
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

            page_obj = visio._resolve_page(doc_name, parse_page(page))
            app = page_obj.Application
            addins = app.COMAddIns
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
                "compiled": True,
                "connected_before": connected_before,
                "connected_after": connected_after,
                "load_behavior": 0,
                "toggle_present": toggle_present,
                "ui": "modeless WinForms panel + Visio CommandBar toggle",
                "tabs": ["Ячейки", "Геометрия", "Проверка"],
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
            progid = "EnergoLogic.VisioEditorAddinV2"
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
    def invoke_energologic_editor_api(
        action: str,
        args_json: str = "{}",
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
            addins = app.COMAddIns
            addins.Update()
            addin = addins.Item("EnergoLogic.VisioEditorAddinV2")
            if not bool(addin.Connect):
                raise RuntimeError("EnergoLogic editor v2 add-in is not connected")
            api = addin.Object
            if api is None:
                raise RuntimeError("EnergoLogic editor v2 COM API object is not published")
            key = str(action).strip().lower()
            zero = {
                "duplicate_left": "ApiDuplicateLeft",
                "duplicate_right": "ApiDuplicateRight",
                "move_left": "ApiMoveLeft",
                "move_right": "ApiMoveRight",
                "select_cell": "ApiSelectCell",
                "repair_glue_preview": "ApiRepairGluePreview",
                "repair_glue_apply": "ApiRepairGlueApply",
                "doctor": "ApiDoctor",
                "align_x": "ApiAlignX",
                "align_y": "ApiAlignY",
                "measure_pitch": "ApiMeasurePitch",
                "show_panel": "ApiShowPanel",
                "version": "ApiVersion",
            }
            if key in zero:
                result = getattr(api, zero[key])()
            elif key == "exact_offset":
                result = api.ApiExactOffset(float(payload["dx_mm"]), float(payload["dy_mm"]))
            elif key in {"base_copy", "base_move"}:
                values = [float(payload[name]) for name in ("base_x_mm", "base_y_mm", "target_x_mm", "target_y_mm")]
                result = api.ApiBaseCopy(*values) if key == "base_copy" else api.ApiBaseMove(*values)
            elif key == "distribute_pitch":
                result = api.ApiDistributePitch(float(payload["pitch_mm"]))
            else:
                raise ValueError(f"unsupported EnergoLogic editor action: {action!r}")
            return ok({
                "action": key,
                "result": str(result),
                "api_version": str(api.ApiVersion()),
                "progid": "EnergoLogic.VisioEditorAddinV2",
                "page": str(page_obj.Name),
                "document": str(page_obj.Document.Name),
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
            progid = "EnergoLogic.VisioEditorAddinV2"
            clsid = "{9C760F65-31D1-49B5-A53A-A13580D67E92}"
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

