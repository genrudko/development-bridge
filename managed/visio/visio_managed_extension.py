from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.77"
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
            build_dir = workspace / "energologic_visio_editor_addin"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddin.dll"
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

            clsid = "{E31D0F45-8A5A-47D7-A4A3-CFB7F0C8B731}"
            progid = "EnergoLogic.VisioEditorAddin"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddin, Version=0.1.0.0, Culture=neutral, PublicKeyToken=null"
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
            progid = "EnergoLogic.VisioEditorAddin"
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
    def uninstall_energologic_editor_ui() -> str:
        # Disconnect and remove only the EnergoLogic editor UI registration.
        try:
            import winreg
            progid = "EnergoLogic.VisioEditorAddin"
            clsid = "{E31D0F45-8A5A-47D7-A4A3-CFB7F0C8B731}"
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

