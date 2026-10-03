from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.74"
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
    def install_energologic_classic_com_addin_probe(
        page: str = "",
        doc_name: str = "",
    ) -> str:
        """Build and register a fixed HKCU-only EnergoLogic Visio COM add-in probe.

        The add-in is intentionally tiny: one Ribbon tab and one fixed Duplicate-40
        button used to qualify true in-process user-context Undo. No arbitrary source,
        command, registry path or ProgID is accepted from callers.
        """
        try:
            import json
            import os
            import shutil
            import subprocess
            import winreg

            if os.name != "nt":
                raise RuntimeError("classic COM add-in probe is Windows-only")

            build_dir = workspace / "energologic_visio_qol_addin_probe"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioQolAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioQolAddin.dll"

            source = r"""using System;
using System.Runtime.InteropServices;
using System.Reflection;
using Extensibility;
using Microsoft.Office.Core;

[assembly: ComVisible(true)]
[assembly: AssemblyTitle("EnergoLogic Visio QoL Add-in")]
[assembly: AssemblyVersion("0.2.0.0")]

namespace EnergoLogicVisioQol
{
    [ComVisible(true)]
    [Guid("7D679776-1D6B-4D0D-9123-E3E4FB21F806")]
    [ProgId("EnergoLogic.VisioQolAddin")]
    [ClassInterface(ClassInterfaceType.AutoDual)]
    public sealed class VisioQolAddin : IDTExtensibility2, IRibbonExtensibility
    {
        private object _application;

        public void OnConnection(object Application, ext_ConnectMode ConnectMode,
            object AddInInst, ref Array custom)
        {
            _application = Application;
        }

        public void OnDisconnection(ext_DisconnectMode RemoveMode, ref Array custom)
        {
            _application = null;
        }

        public void OnAddInsUpdate(ref Array custom) { }
        public void OnStartupComplete(ref Array custom) { }
        public void OnBeginShutdown(ref Array custom) { }

        public string GetCustomUI(string RibbonID)
        {
            return @"<customUI xmlns='http://schemas.microsoft.com/office/2009/07/customui'>
<ribbon><tabs>
<tab id='EnergoLogicTab' label='EnergoLogic' keytip='Z'>
<group id='EnergoLogicQolGroup' label='QoL'>
<button id='EnergoLogicUndoProbeDuplicate40' label='Duplicate 40 (Undo probe)' keytip='D' size='large' onAction='OnUndoProbeDuplicate40'/>
</group>
</tab>
</tabs></ribbon>
</customUI>";
        }

        public void OnUndoProbeDuplicate40(IRibbonControl control)
        {
            if (_application == null)
                throw new InvalidOperationException("Visio application is not connected");

            dynamic app = _application;
            dynamic window = app.ActiveWindow;
            dynamic selection = window.Selection;
            int sourceCount = (int)selection.Count;
            if (sourceCount < 1)
                throw new InvalidOperationException("No shapes selected");

            int scopeId = (int)app.BeginUndoScope("EnergoLogic: Duplicate Cell Probe");
            bool commit = false;
            try
            {
                app.DoCmd(1024);
                dynamic duplicate = window.Selection;
                if ((int)duplicate.Count != sourceCount)
                    throw new InvalidOperationException("Duplicate selection count mismatch");
                duplicate.Move(40.0, 0.0, "mm");
                commit = true;
            }
            finally
            {
                app.EndUndoScope(scopeId, commit);
            }
        }
    }
}
"""
            source_path.write_text(source, encoding="utf-8")

            extensibility_ref = Path(
                r"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\PublicAssemblies\Microsoft.VisualStudio.Interop.dll"
            )
            office_ref = Path(
                r"C:\Program Files\Microsoft Office\root\Office16\ADDINS\PowerPivot Excel Add-in\OFFICE.dll"
            )
            for reference in (extensibility_ref, office_ref):
                if not reference.is_file():
                    raise FileNotFoundError(f"required Microsoft interop assembly not found: {reference}")
                shutil.copy2(reference, build_dir / reference.name)

            csc = Path(r"C:\WINDOWS\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
            if not csc.is_file():
                raise FileNotFoundError(f"C# compiler not found: {csc}")
            compile_result = subprocess.run(
                [
                    str(csc),
                    "/nologo",
                    "/target:library",
                    "/platform:x64",
                    "/optimize+",
                    f"/reference:{extensibility_ref}",
                    f"/reference:{office_ref}",
                    f"/out:{dll_path}",
                    str(source_path),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if compile_result.returncode != 0 or not dll_path.is_file():
                raise RuntimeError(
                    "C# add-in compilation failed: "
                    + (compile_result.stdout + "\n" + compile_result.stderr)[-4000:]
                )

            clsid = "{7D679776-1D6B-4D0D-9123-E3E4FB21F806}"
            progid = "EnergoLogic.VisioQolAddin"
            class_name = "EnergoLogicVisioQol.VisioQolAddin"
            assembly_name = "EnergoLogic.VisioQolAddin, Version=0.2.0.0, Culture=neutral, PublicKeyToken=null"
            runtime_version = "v4.0.30319"
            codebase = dll_path.resolve().as_uri()

            def set_string(root, subkey, name, value):
                with winreg.CreateKeyEx(root, subkey, 0, winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY) as key:
                    winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

            def set_dword(root, subkey, name, value):
                with winreg.CreateKeyEx(root, subkey, 0, winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY) as key:
                    winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, int(value))

            classes = r"Software\Classes"
            set_string(winreg.HKEY_CURRENT_USER, classes + "\\" + progid, "", "EnergoLogic Visio QoL Add-in")
            set_string(winreg.HKEY_CURRENT_USER, classes + "\\" + progid + r"\CLSID", "", clsid)
            clsid_key = classes + "\\CLSID\\" + clsid
            set_string(winreg.HKEY_CURRENT_USER, clsid_key, "", "EnergoLogic Visio QoL Add-in")
            set_string(winreg.HKEY_CURRENT_USER, clsid_key + r"\ProgId", "", progid)
            office_addin_category = "{62C8FE65-4EBB-45E7-B440-6E39B2CDBF29}"
            set_string(
                winreg.HKEY_CURRENT_USER,
                clsid_key + "\\Implemented Categories\\" + office_addin_category,
                "",
                "",
            )
            inproc = clsid_key + r"\InprocServer32"
            set_string(winreg.HKEY_CURRENT_USER, inproc, "", "mscoree.dll")
            set_string(winreg.HKEY_CURRENT_USER, inproc, "ThreadingModel", "Both")
            set_string(winreg.HKEY_CURRENT_USER, inproc, "Class", class_name)
            set_string(winreg.HKEY_CURRENT_USER, inproc, "Assembly", assembly_name)
            set_string(winreg.HKEY_CURRENT_USER, inproc, "RuntimeVersion", runtime_version)
            set_string(winreg.HKEY_CURRENT_USER, inproc, "CodeBase", codebase)

            # Visio is the Office-family exception: its add-in discovery key is
            # HKCU\Software\Microsoft\Visio\Addins\<ProgID>, not
            # HKCU\Software\Microsoft\Office\Visio\Addins\<ProgID>.
            visio_addin_key = "Software\\Microsoft\\Visio\\Addins\\" + progid
            set_string(winreg.HKEY_CURRENT_USER, visio_addin_key, "FriendlyName", "EnergoLogic Visio QoL")
            set_string(winreg.HKEY_CURRENT_USER, visio_addin_key, "Description", "EnergoLogic engineering QoL commands for Visio")
            set_dword(winreg.HKEY_CURRENT_USER, visio_addin_key, "LoadBehavior", 0)

            # Clean the stale qualification key written by <= 2026.10.03.59.
            stale_office_key = "Software\\Microsoft\\Office\\Visio\\Addins\\" + progid
            try:
                winreg.DeleteKeyEx(
                    winreg.HKEY_CURRENT_USER,
                    stale_office_key,
                    winreg.KEY_WOW64_64KEY,
                    0,
                )
            except FileNotFoundError:
                pass

            listed_in_com_addins = False
            discovery_error = None
            try:
                page_obj = visio._resolve_page(doc_name, parse_page(page))
                app = page_obj.Application
                addins = app.COMAddIns
                addins.Update()
                for index in range(1, int(addins.Count) + 1):
                    item = addins.Item(index)
                    if str(item.ProgId).casefold() == progid.casefold():
                        listed_in_com_addins = True
                        break
            except Exception as exc:
                discovery_error = f"{type(exc).__name__}: {exc}"[:1000]

            return ok({
                "progid": progid,
                "clsid": clsid,
                "dll_path": str(dll_path),
                "source_path": str(source_path),
                "compiler": str(csc),
                "compile_stdout": compile_result.stdout[-1000:],
                "compile_stderr": compile_result.stderr[-1000:],
                "hkcu_only": True,
                "load_behavior": 0,
                "visio_addin_registry_key": visio_addin_key,
                "office_addin_category": office_addin_category,
                "extensibility_reference": str(extensibility_ref),
                "office_reference": str(office_ref),
                "listed_in_com_addins": listed_in_com_addins,
                "connect_attempted": False,
                "discovery_error": discovery_error,
                "ribbon_tab": "EnergoLogic",
                "tab_keytip": "Z",
                "button_keytip": "D",
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def enable_energologic_classic_com_addin_probe_autoload() -> str:
        """Enable startup loading only for the fixed EnergoLogic qualification add-in."""
        try:
            import winreg
            progid = "EnergoLogic.VisioQolAddin"
            key_path = "Software\\Microsoft\\Visio\\Addins\\" + progid
            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER,
                key_path,
                0,
                winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY,
            ) as key:
                winreg.SetValueEx(key, "LoadBehavior", 0, winreg.REG_DWORD, 3)
            return ok({
                "progid": progid,
                "load_behavior": 3,
                "scope": "HKCU",
                "qualification_only": True,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def restart_energologic_visio_qualification_copy_graceful() -> str:
        """Save, quit and relaunch only the fixed single-document qualification copy."""
        try:
            import os
            import subprocess
            import time

            if os.name != "nt":
                raise RuntimeError("Visio qualification restart is Windows-only")
            target = workspace / "KRU-35_normal_scheme_v2_energologic_qol_host_v1.vsdm"
            exe = Path(r"C:\Program Files\Microsoft Office\root\Office16\VISIO.EXE")
            if not target.is_file():
                raise FileNotFoundError(f"qualification document not found: {target}")
            if not exe.is_file():
                raise FileNotFoundError(f"Visio executable not found: {exe}")

            page_obj = visio._resolve_page(
                "KRU-35_normal_scheme_v2_energologic_qol_host_v1.vsdm",
                "MCP-v2",
            )
            app = page_obj.Application
            documents = app.Documents
            drawing_documents = []
            document_inventory = []
            for index in range(1, int(documents.Count) + 1):
                candidate = documents.Item(index)
                try:
                    doc_type = int(candidate.Type)
                except Exception:
                    doc_type = None
                try:
                    candidate_name = str(candidate.Name)
                except Exception:
                    candidate_name = f"<document-{index}>"
                try:
                    candidate_full_name = str(candidate.FullName)
                except Exception:
                    candidate_full_name = ""
                document_inventory.append({
                    "index": index,
                    "name": candidate_name,
                    "full_name": candidate_full_name,
                    "type": doc_type,
                })
                # VisDocumentTypes: visTypeStencil = 2. Stencils are support
                # documents and do not block restarting the one qualification drawing.
                if doc_type != 2:
                    drawing_documents.append(candidate)

            if len(drawing_documents) != 1:
                raise RuntimeError(
                    "refusing graceful restart: expected exactly one non-stencil Visio document; "
                    f"inventory={document_inventory!r}"
                )
            document = drawing_documents[0]
            full_name = Path(str(document.FullName)).resolve()
            if full_name != target.resolve():
                raise RuntimeError(
                    "refusing graceful restart: the only non-stencil Visio document is not "
                    f"the fixed qualification copy; inventory={document_inventory!r}"
                )

            document.Save()
            app.Quit()

            for _ in range(40):
                ps = subprocess.run(
                    [
                        "powershell.exe",
                        "-NoProfile",
                        "-NonInteractive",
                        "-Command",
                        "@(Get-Process VISIO -ErrorAction SilentlyContinue).Count",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if int((ps.stdout or "0").strip() or "0") == 0:
                    break
                time.sleep(0.25)
            else:
                raise RuntimeError("Visio did not exit after graceful Application.Quit()")

            proc = subprocess.Popen(
                [str(exe), str(target)],
                cwd=str(workspace),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return ok({
                "restarted": True,
                "new_pid": int(proc.pid),
                "document": str(target),
                "graceful_quit": True,
                "saved_before_quit": True,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def connect_energologic_classic_com_addin_probe(
        page: str = "",
        doc_name: str = "",
    ) -> str:
        """Connect only the fixed registered probe; registration stays non-autoloading."""
        try:
            page_obj = visio._resolve_page(doc_name, parse_page(page))
            app = page_obj.Application
            addins = app.COMAddIns
            addins.Update()
            addin = addins.Item("EnergoLogic.VisioQolAddin")
            before = bool(addin.Connect)
            if not before:
                addin.Connect = True
            after = bool(addin.Connect)
            return ok({
                "progid": "EnergoLogic.VisioQolAddin",
                "connected_before": before,
                "connected_after": after,
                "load_behavior_remains": 0,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def get_energologic_classic_com_addin_probe_status(
        page: str = "",
        doc_name: str = "",
    ) -> str:
        """Read registry, COM activation and Visio COMAddIns state for the fixed probe."""
        try:
            import pythoncom
            import win32com.client
            import winreg

            progid = "EnergoLogic.VisioQolAddin"
            clsid = "{7D679776-1D6B-4D0D-9123-E3E4FB21F806}"

            def read_values(root, subkey):
                result = {"exists": False, "values": {}, "subkeys": []}
                try:
                    with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                        result["exists"] = True
                        index = 0
                        while True:
                            try:
                                name, value, kind = winreg.EnumValue(key, index)
                                result["values"][name or "(Default)"] = {"value": value, "kind": kind}
                                index += 1
                            except OSError:
                                break
                        index = 0
                        while True:
                            try:
                                result["subkeys"].append(winreg.EnumKey(key, index))
                                index += 1
                            except OSError:
                                break
                except FileNotFoundError:
                    pass
                return result

            registry = {
                "visio_addin": read_values(
                    winreg.HKEY_CURRENT_USER,
                    "Software\\Microsoft\\Visio\\Addins\\" + progid,
                ),
                "stale_office_visio_addin": read_values(
                    winreg.HKEY_CURRENT_USER,
                    "Software\\Microsoft\\Office\\Visio\\Addins\\" + progid,
                ),
                "progid": read_values(
                    winreg.HKEY_CURRENT_USER,
                    "Software\\Classes\\" + progid,
                ),
                "progid_clsid": read_values(
                    winreg.HKEY_CURRENT_USER,
                    "Software\\Classes\\" + progid + r"\CLSID",
                ),
                "clsid": read_values(
                    winreg.HKEY_CURRENT_USER,
                    "Software\\Classes\\CLSID\\" + clsid,
                ),
                "inproc": read_values(
                    winreg.HKEY_CURRENT_USER,
                    "Software\\Classes\\CLSID\\" + clsid + r"\InprocServer32",
                ),
                "implemented_categories": read_values(
                    winreg.HKEY_CURRENT_USER,
                    "Software\\Classes\\CLSID\\" + clsid + r"\Implemented Categories",
                ),
            }

            clsid_from_progid = None
            clsid_error = None
            try:
                clsid_from_progid = str(pythoncom.CLSIDFromProgID(progid))
            except Exception as exc:
                clsid_error = f"{type(exc).__name__}: {exc}"[:1000]

            dispatch_created = False
            dispatch_error = None
            try:
                obj = win32com.client.Dispatch(progid)
                dispatch_created = obj is not None
                obj = None
            except Exception as exc:
                dispatch_error = f"{type(exc).__name__}: {exc}"[:1500]

            page_obj = visio._resolve_page(doc_name, parse_page(page))
            app = page_obj.Application
            addins = app.COMAddIns
            update_error = None
            try:
                addins.Update()
            except Exception as exc:
                update_error = f"{type(exc).__name__}: {exc}"[:1000]

            collection = []
            for index in range(1, int(addins.Count) + 1):
                item = addins.Item(index)
                row = {"index": index}
                for attr, key in (
                    ("ProgId", "progid"),
                    ("Guid", "guid"),
                    ("Description", "description"),
                    ("Connect", "connect"),
                ):
                    try:
                        row[key] = getattr(item, attr)
                    except Exception as exc:
                        row[key + "_error"] = f"{type(exc).__name__}: {exc}"[:500]
                collection.append(row)

            return ok({
                "progid": progid,
                "expected_clsid": clsid,
                "registry": registry,
                "clsid_from_progid": clsid_from_progid,
                "clsid_error": clsid_error,
                "dispatch_created": dispatch_created,
                "dispatch_error": dispatch_error,
                "com_addins_update_error": update_error,
                "com_addins_count": int(addins.Count),
                "com_addins": collection,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def get_energologic_ribbon_accessibility_probe(
        page: str = "",
        doc_name: str = "",
    ) -> str:
        # Read the live Visio UI Automation tree for EnergoLogic Ribbon elements.
        try:
            import json
            import subprocess

            page_obj = visio._resolve_page(doc_name, parse_page(page))
            app = page_obj.Application
            try:
                app.ActiveWindow.Page = page_obj
            except Exception:
                page_obj.Activate()
            window = app.ActiveWindow
            hwnd = int(window.WindowHandle32)
            if hwnd <= 0:
                raise RuntimeError("Visio active window returned an invalid HWND")

            import ctypes
            user32 = ctypes.windll.user32
            GA_ROOT = 2
            root_hwnd = int(user32.GetAncestor(hwnd, GA_ROOT)) or hwnd

            ps = f"""$ErrorActionPreference='Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]{root_hwnd})
if ($null -eq $root) {{ throw 'UIAutomation root element was not found' }}
$all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
$matches = @()
$sample = @()
for ($i = 0; $i -lt $all.Count; $i++) {{
  $el = $all.Item($i)
  $name = [string]$el.Current.Name
  $aid = [string]$el.Current.AutomationId
  $cls = [string]$el.Current.ClassName
  $type = [string]$el.Current.ControlType.ProgrammaticName
  $row = [pscustomobject]@{{ index=$i; name=$name; automation_id=$aid; class_name=$cls; control_type=$type }}
  $hay = ($name + ' ' + $aid + ' ' + $cls).ToLowerInvariant()
  if ($hay.Contains('energologic') -or $hay.Contains('duplicate 40')) {{ $matches += $row }}
  if ($name -and $sample.Count -lt 160) {{ $sample += $row }}
}}
[pscustomobject]@{{ element_count=$all.Count; matches=@($matches); named_sample=@($sample); energologic_found=($matches.Count -gt 0) }} | ConvertTo-Json -Depth 6 -Compress
"""
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    ps,
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    "PowerShell UI Automation probe failed: "
                    + (result.stdout + "\n" + result.stderr)[-3000:]
                )
            payload = json.loads(result.stdout or "{}")
            return ok({
                "document": str(page_obj.Document.Name),
                "page": str(page_obj.Name),
                "root_window_handle32": root_hwnd,
                "element_count": payload.get("element_count", 0),
                "matches": payload.get("matches", []),
                "named_sample": payload.get("named_sample", []),
                "energologic_found": bool(payload.get("energologic_found", False)),
                "backend": ".NET UIAutomationClient",
            })
        except Exception as exc:
            return err(exc)


    @mcp.tool()
    def keyboard_run_energologic_classic_com_addin_probe(
        shape_ids_json: str,
        page: str = "",
        doc_name: str = "",
    ) -> str:
        """Invoke the fixed EnergoLogic Ribbon probe through real Office KeyTips."""
        try:
            import ctypes
            import ctypes.wintypes
            import json
            import time

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
                raise RuntimeError("Could not create the exact source selection")

            # Ensure our fixed COM add-in is actually connected before pressing KeyTips.
            addins = app.COMAddIns
            addins.Update()
            addin = addins.Item("EnergoLogic.VisioQolAddin")
            if not bool(addin.Connect):
                addin.Connect = True
            if not bool(addin.Connect):
                raise RuntimeError("EnergoLogic classic COM add-in is registered but not connected")

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            hwnd = int(window.WindowHandle32)
            if hwnd <= 0:
                raise RuntimeError("Visio active window returned an invalid HWND")
            GA_ROOT = 2
            SW_RESTORE = 9
            VK_MENU = 0x12
            VK_Z = 0x5A
            VK_D = 0x44
            KEYEVENTF_KEYUP = 0x0002
            root_hwnd = int(user32.GetAncestor(hwnd, GA_ROOT)) or hwnd

            def press(vk):
                user32.keybd_event(vk, 0, 0, 0)
                user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)

            foreground_hwnd = int(user32.GetForegroundWindow())
            current_thread = int(kernel32.GetCurrentThreadId())
            target_thread = int(user32.GetWindowThreadProcessId(root_hwnd, None))
            foreground_thread = (
                int(user32.GetWindowThreadProcessId(foreground_hwnd, None))
                if foreground_hwnd else 0
            )
            attached = []
            before_count = int(page_obj.Shapes.Count)
            try:
                for other_thread in (foreground_thread, target_thread):
                    if other_thread and other_thread != current_thread:
                        if bool(user32.AttachThreadInput(current_thread, other_thread, True)):
                            attached.append(other_thread)
                user32.ShowWindow(root_hwnd, SW_RESTORE)
                user32.BringWindowToTop(root_hwnd)
                user32.SetForegroundWindow(root_hwnd)
                user32.SetActiveWindow(root_hwnd)
                time.sleep(0.25)

                # Real Office Ribbon KeyTip path: Alt -> Z (EnergoLogic) -> D (probe).
                press(VK_MENU)
                time.sleep(0.35)
                press(VK_Z)
                time.sleep(0.35)
                press(VK_D)
                for _ in range(50):
                    time.sleep(0.1)
                    if int(page_obj.Shapes.Count) == before_count + len(shape_ids):
                        break
            finally:
                for other_thread in reversed(attached):
                    try:
                        user32.AttachThreadInput(current_thread, other_thread, False)
                    except Exception:
                        pass

            after_count = int(page_obj.Shapes.Count)
            if after_count != before_count + len(shape_ids):
                raise RuntimeError(
                    f"EnergoLogic Ribbon probe expected {before_count + len(shape_ids)} shapes, "
                    f"got {after_count}"
                )
            return ok({
                "document": str(page_obj.Document.Name),
                "page": str(page_obj.Name),
                "shape_count_before": before_count,
                "shape_count_after": after_count,
                "source_shape_ids": shape_ids,
                "progid": "EnergoLogic.VisioQolAddin",
                "launch_path": "Office Ribbon KeyTips Alt-Z-D",
                "ribbon_callback_launched": True,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def uninstall_energologic_classic_com_addin_probe() -> str:
        """Remove only the fixed EnergoLogic classic COM add-in probe HKCU registration."""
        try:
            import winreg

            clsid = "{7D679776-1D6B-4D0D-9123-E3E4FB21F806}"
            progid = "EnergoLogic.VisioQolAddin"
            targets = [
                "Software\\Microsoft\\Visio\\Addins\\" + progid,
                # Also remove the stale qualification key from versions <= .59.
                "Software\\Microsoft\\Office\\Visio\\Addins\\" + progid,
                "Software\\Classes\\" + progid,
                "Software\\Classes\\CLSID\\" + clsid,
            ]

            def delete_tree(root, subkey):
                try:
                    with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ | winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY) as key:
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
    def install_energologic_commandbar_com_addin_probe(
        page: str = "",
        doc_name: str = "",
    ) -> str:
        # Build/register a fixed non-autoloading command-bar-only COM add-in probe.
        try:
            import os
            import shutil
            import subprocess
            import winreg

            if os.name != "nt":
                raise RuntimeError("command-bar COM add-in probe is Windows-only")

            build_dir = workspace / "energologic_visio_qol_commandbar_probe"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioQolCommandBarAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioQolCommandBarAddin.dll"

            source = r"""using System;
using System.Reflection;
using System.Runtime.InteropServices;
using Extensibility;
using Microsoft.Office.Core;

[assembly: ComVisible(true)]
[assembly: AssemblyTitle("EnergoLogic Visio QoL CommandBar Add-in")]
[assembly: AssemblyVersion("0.1.0.0")]

namespace EnergoLogicVisioQolCommandBar
{
    [ComVisible(true)]
    [Guid("F62D8474-1A5C-4A9E-88B5-4AA67D1C5510")]
    [ProgId("EnergoLogic.VisioQolCommandBarAddin")]
    [ClassInterface(ClassInterfaceType.None)]
    public sealed class Connect : IDTExtensibility2
    {
        private object _application;
        private CommandBar _bar;
        private CommandBarButton _button;
        private _CommandBarButtonEvents_ClickEventHandler _clickHandler;

        public void OnConnection(object Application, ext_ConnectMode ConnectMode,
            object AddInInst, ref Array custom)
        {
            _application = Application;
            if (ConnectMode != ext_ConnectMode.ext_cm_Startup)
                InstallUi();
        }

        public void OnDisconnection(ext_DisconnectMode RemoveMode, ref Array custom)
        {
            _button = null;
            _bar = null;
            _application = null;
        }

        public void OnAddInsUpdate(ref Array custom) { }

        public void OnStartupComplete(ref Array custom)
        {
            InstallUi();
        }

        public void OnBeginShutdown(ref Array custom) { }

        private void InstallUi()
        {
            if (_application == null)
                throw new InvalidOperationException("Visio application is not connected");

            dynamic app = _application;
            CommandBars bars = (CommandBars)app.CommandBars;
            const string barName = "EnergoLogic QoL Probe";
            const string buttonTag = "EnergoLogic.Duplicate40.UndoProbe";

            try
            {
                _bar = bars[barName];
            }
            catch
            {
                _bar = bars.Add(
                    barName,
                    MsoBarPosition.msoBarFloating,
                    Missing.Value,
                    true);
            }

            try { _bar.Context = "2*"; } catch { }

            _button = null;
            for (int i = 1; i <= _bar.Controls.Count; i++)
            {
                CommandBarControl control = _bar.Controls[i];
                if (String.Equals(control.Tag, buttonTag, StringComparison.Ordinal))
                {
                    _button = control as CommandBarButton;
                    if (_button != null)
                        break;
                }
            }

            if (_button == null)
            {
                _button = (CommandBarButton)_bar.Controls.Add(
                    MsoControlType.msoControlButton,
                    Missing.Value,
                    Missing.Value,
                    Missing.Value,
                    true);
            }

            _button.Caption = "EnergoLogic Duplicate 40";
            _button.Tag = buttonTag;
            _button.Style = MsoButtonStyle.msoButtonCaption;
            _button.TooltipText = "EnergoLogic Duplicate 40 — Undo qualification";
            _button.Visible = true;
            _button.OnAction = "!<EnergoLogic.VisioQolCommandBarAddin>";

            _clickHandler = new _CommandBarButtonEvents_ClickEventHandler(OnProbeClick);
            _button.Click += _clickHandler;
            _bar.Visible = true;
        }

        private void OnProbeClick(CommandBarButton Ctrl, ref bool CancelDefault)
        {
            CancelDefault = false;
            RunDuplicate40();
        }

        private void RunDuplicate40()
        {
            dynamic app = _application;
            dynamic window = app.ActiveWindow;
            dynamic selection = window.Selection;
            int sourceCount = (int)selection.Count;
            if (sourceCount < 1)
                throw new InvalidOperationException("No shapes selected");

            int scopeId = (int)app.BeginUndoScope("EnergoLogic: Duplicate Cell Probe");
            bool commit = false;
            try
            {
                app.DoCmd(1024);
                dynamic duplicate = window.Selection;
                if ((int)duplicate.Count != sourceCount)
                    throw new InvalidOperationException("Duplicate selection count mismatch");
                duplicate.Move(40.0, 0.0, "mm");
                commit = true;
            }
            finally
            {
                app.EndUndoScope(scopeId, commit);
            }
        }
    }
}
"""
            source_path.write_text(source, encoding="utf-8")

            extensibility_ref = Path(
                r"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\PublicAssemblies\Microsoft.VisualStudio.Interop.dll"
            )
            office_ref = Path(
                r"C:\Program Files\Microsoft Office\root\Office16\ADDINS\PowerPivot Excel Add-in\OFFICE.dll"
            )
            for reference in (extensibility_ref, office_ref):
                if not reference.is_file():
                    raise FileNotFoundError(f"required Microsoft interop assembly not found: {reference}")
                shutil.copy2(reference, build_dir / reference.name)

            csc = Path(r"C:\WINDOWS\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
            if not csc.is_file():
                raise FileNotFoundError(f"C# compiler not found: {csc}")
            compile_result = subprocess.run(
                [
                    str(csc),
                    "/nologo",
                    "/target:library",
                    "/platform:x64",
                    "/optimize+",
                    f"/reference:{extensibility_ref}",
                    f"/reference:{office_ref}",
                    f"/out:{dll_path}",
                    str(source_path),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if compile_result.returncode != 0 or not dll_path.is_file():
                raise RuntimeError(
                    "C# command-bar add-in compilation failed: "
                    + (compile_result.stdout + "\n" + compile_result.stderr)[-4000:]
                )

            clsid = "{F62D8474-1A5C-4A9E-88B5-4AA67D1C5510}"
            progid = "EnergoLogic.VisioQolCommandBarAddin"
            class_name = "EnergoLogicVisioQolCommandBar.Connect"
            assembly_name = (
                "EnergoLogic.VisioQolCommandBarAddin, Version=0.1.0.0, "
                "Culture=neutral, PublicKeyToken=null"
            )
            codebase = dll_path.resolve().as_uri()

            def set_string(root, subkey, name, value):
                with winreg.CreateKeyEx(
                    root, subkey, 0, winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY
                ) as key:
                    winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

            def set_dword(root, subkey, name, value):
                with winreg.CreateKeyEx(
                    root, subkey, 0, winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY
                ) as key:
                    winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, int(value))

            classes = r"Software\Classes"
            set_string(winreg.HKEY_CURRENT_USER, classes + "\\" + progid, "", "EnergoLogic Visio QoL CommandBar Add-in")
            set_string(winreg.HKEY_CURRENT_USER, classes + "\\" + progid + r"\CLSID", "", clsid)
            clsid_key = classes + "\\CLSID\\" + clsid
            set_string(winreg.HKEY_CURRENT_USER, clsid_key, "", "EnergoLogic Visio QoL CommandBar Add-in")
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
            set_string(winreg.HKEY_CURRENT_USER, addin_key, "FriendlyName", "EnergoLogic Visio QoL CommandBar")
            set_string(winreg.HKEY_CURRENT_USER, addin_key, "Description", "EnergoLogic temporary command-bar Undo qualification")
            set_dword(winreg.HKEY_CURRENT_USER, addin_key, "LoadBehavior", 0)

            listed = False
            discovery_error = None
            try:
                page_obj = visio._resolve_page(doc_name, parse_page(page))
                addins = page_obj.Application.COMAddIns
                addins.Update()
                for index in range(1, int(addins.Count) + 1):
                    if str(addins.Item(index).ProgId).casefold() == progid.casefold():
                        listed = True
                        break
            except Exception as exc:
                discovery_error = f"{type(exc).__name__}: {exc}"[:1200]

            return ok({
                "progid": progid,
                "clsid": clsid,
                "dll_path": str(dll_path),
                "source_path": str(source_path),
                "load_behavior": 0,
                "hkcu_only": True,
                "listed_in_com_addins": listed,
                "discovery_error": discovery_error,
                "ribbon_extensibility": False,
                "command_bar_name": "EnergoLogic QoL Probe",
                "button_caption": "EnergoLogic Duplicate 40",
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def connect_energologic_commandbar_com_addin_probe(
        page: str = "",
        doc_name: str = "",
    ) -> str:
        # Connect only the fixed non-autoloading command-bar probe.
        try:
            page_obj = visio._resolve_page(doc_name, parse_page(page))
            app = page_obj.Application
            addins = app.COMAddIns
            addins.Update()
            addin = addins.Item("EnergoLogic.VisioQolCommandBarAddin")
            before = bool(addin.Connect)
            if not before:
                addin.Connect = True
            after = bool(addin.Connect)
            command_bar_present = False
            button_present = False
            try:
                bar = app.CommandBars.Item("EnergoLogic QoL Probe")
                command_bar_present = bar is not None
                if command_bar_present:
                    for index in range(1, int(bar.Controls.Count) + 1):
                        control = bar.Controls.Item(index)
                        if str(control.Tag) == "EnergoLogic.Duplicate40.UndoProbe":
                            button_present = True
                            break
            except Exception:
                pass
            return ok({
                "progid": "EnergoLogic.VisioQolCommandBarAddin",
                "connected_before": before,
                "connected_after": after,
                "command_bar_present": command_bar_present,
                "button_present": button_present,
                "load_behavior_remains": 0,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def get_energologic_commandbar_com_addin_probe_status(
        page: str = "",
        doc_name: str = "",
    ) -> str:
        # Read current registration, connection and command-bar/button state.
        try:
            import winreg
            progid = "EnergoLogic.VisioQolCommandBarAddin"
            addin_key = "Software\\Microsoft\\Visio\\Addins\\" + progid
            load_behavior = None
            registry_exists = False
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    addin_key,
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
            for index in range(1, int(addins.Count) + 1):
                item = addins.Item(index)
                if str(item.ProgId).casefold() == progid.casefold():
                    listed = True
                    connected = bool(item.Connect)
                    break

            command_bar_present = False
            command_bar_visible = False
            button_present = False
            button_visible = False
            try:
                bar = app.CommandBars.Item("EnergoLogic QoL Probe")
                command_bar_present = bar is not None
                command_bar_visible = bool(bar.Visible)
                if bar is not None:
                    for index in range(1, int(bar.Controls.Count) + 1):
                        control = bar.Controls.Item(index)
                        if str(control.Tag) == "EnergoLogic.Duplicate40.UndoProbe":
                            button_present = True
                            button_visible = bool(control.Visible)
                            break
            except Exception:
                pass

            return ok({
                "progid": progid,
                "registry_exists": registry_exists,
                "load_behavior": load_behavior,
                "listed_in_com_addins": listed,
                "connected": connected,
                "command_bar_present": command_bar_present,
                "command_bar_visible": command_bar_visible,
                "button_present": button_present,
                "button_visible": button_visible,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def execute_energologic_commandbar_com_addin_probe(
        shape_ids_json: str,
        page: str = "",
        doc_name: str = "",
    ) -> str:
        # Execute the fixed Office CommandBar button after selecting exact source IDs.
        try:
            import json
            import time
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
                raise RuntimeError("Could not create the exact source selection")

            addins = app.COMAddIns
            addins.Update()
            addin = addins.Item("EnergoLogic.VisioQolCommandBarAddin")
            if not bool(addin.Connect):
                raise RuntimeError("EnergoLogic command-bar add-in is not connected")

            bar = app.CommandBars.Item("EnergoLogic QoL Probe")
            button = None
            for index in range(1, int(bar.Controls.Count) + 1):
                control = bar.Controls.Item(index)
                if str(control.Tag) == "EnergoLogic.Duplicate40.UndoProbe":
                    button = control
                    break
            if button is None:
                raise RuntimeError("EnergoLogic command-bar probe button was not found")

            before_count = int(page_obj.Shapes.Count)
            button.Execute()
            expected = before_count + len(shape_ids)
            for _ in range(50):
                if int(page_obj.Shapes.Count) == expected:
                    break
                time.sleep(0.1)
            after_count = int(page_obj.Shapes.Count)
            if after_count != expected:
                raise RuntimeError(
                    f"CommandBar probe expected {expected} shapes, got {after_count}"
                )
            return ok({
                "document": str(page_obj.Document.Name),
                "page": str(page_obj.Name),
                "source_shape_ids": shape_ids,
                "shape_count_before": before_count,
                "shape_count_after": after_count,
                "launch_path": "Office CommandBarButton.Execute",
                "in_process_callback_expected": True,
                "load_behavior": 0,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def mouse_run_energologic_commandbar_com_addin_probe(
        shape_ids_json: str,
        page: str = "",
        doc_name: str = "",
    ) -> str:
        # Physically click the fixed visible CommandBar button after exact selection.
        try:
            import ctypes
            import json
            import time

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
                raise RuntimeError("Could not create the exact source selection")

            addins = app.COMAddIns
            addins.Update()
            addin = addins.Item("EnergoLogic.VisioQolCommandBarAddin")
            if not bool(addin.Connect):
                raise RuntimeError("EnergoLogic command-bar add-in is not connected")

            bar = app.CommandBars.Item("EnergoLogic QoL Probe")
            if not bool(bar.Visible):
                bar.Visible = True
            button = None
            for index in range(1, int(bar.Controls.Count) + 1):
                control = bar.Controls.Item(index)
                if str(control.Tag) == "EnergoLogic.Duplicate40.UndoProbe":
                    button = control
                    break
            if button is None:
                raise RuntimeError("EnergoLogic command-bar probe button was not found")
            if not bool(button.Visible):
                button.Visible = True

            left = int(button.Left)
            top = int(button.Top)
            width = int(button.Width)
            height = int(button.Height)
            if width <= 0 or height <= 0:
                raise RuntimeError(
                    f"CommandBar button returned invalid bounds: left={left} top={top} "
                    f"width={width} height={height}"
                )
            x = left + width // 2
            y = top + height // 2

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            hwnd = int(window.WindowHandle32)
            if hwnd <= 0:
                raise RuntimeError("Visio active window returned an invalid HWND")
            GA_ROOT = 2
            SW_RESTORE = 9
            MOUSEEVENTF_LEFTDOWN = 0x0002
            MOUSEEVENTF_LEFTUP = 0x0004
            root_hwnd = int(user32.GetAncestor(hwnd, GA_ROOT)) or hwnd

            foreground_hwnd = int(user32.GetForegroundWindow())
            current_thread = int(kernel32.GetCurrentThreadId())
            target_thread = int(user32.GetWindowThreadProcessId(root_hwnd, None))
            foreground_thread = (
                int(user32.GetWindowThreadProcessId(foreground_hwnd, None))
                if foreground_hwnd else 0
            )
            attached = []
            before_count = int(page_obj.Shapes.Count)
            old_cursor = ctypes.wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(old_cursor))
            try:
                for other_thread in (foreground_thread, target_thread):
                    if other_thread and other_thread != current_thread:
                        if bool(user32.AttachThreadInput(current_thread, other_thread, True)):
                            attached.append(other_thread)
                user32.ShowWindow(root_hwnd, SW_RESTORE)
                user32.BringWindowToTop(root_hwnd)
                user32.SetForegroundWindow(root_hwnd)
                user32.SetActiveWindow(root_hwnd)
                time.sleep(0.35)
                user32.SetCursorPos(x, y)
                time.sleep(0.15)
                user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                expected = before_count + len(shape_ids)
                for _ in range(50):
                    if int(page_obj.Shapes.Count) == expected:
                        break
                    time.sleep(0.1)
            finally:
                user32.SetCursorPos(int(old_cursor.x), int(old_cursor.y))
                for other_thread in reversed(attached):
                    try:
                        user32.AttachThreadInput(current_thread, other_thread, False)
                    except Exception:
                        pass

            after_count = int(page_obj.Shapes.Count)
            expected = before_count + len(shape_ids)
            if after_count != expected:
                raise RuntimeError(
                    f"Physical CommandBar click expected {expected} shapes, got {after_count}; "
                    f"button_bounds=({left},{top},{width},{height})"
                )
            return ok({
                "document": str(page_obj.Document.Name),
                "page": str(page_obj.Name),
                "source_shape_ids": shape_ids,
                "shape_count_before": before_count,
                "shape_count_after": after_count,
                "button_bounds": {
                    "left": left,
                    "top": top,
                    "width": width,
                    "height": height,
                    "click_x": x,
                    "click_y": y,
                },
                "launch_path": "physical mouse click on Office CommandBarButton",
                "physical_ui_event": True,
                "load_behavior": 0,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def schedule_energologic_commandbar_physical_click_probe(
        shape_ids_json: str,
        page: str = "",
        doc_name: str = "",
    ) -> str:
        # Schedule the fixed physical button click after this COM call has returned.
        try:
            import ctypes
            import ctypes.wintypes
            import json
            import os
            import subprocess
            import sys

            if os.name != "nt":
                raise RuntimeError("asynchronous CommandBar click probe is Windows-only")
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
                raise RuntimeError("Could not create the exact source selection")

            addins = app.COMAddIns
            addins.Update()
            addin = addins.Item("EnergoLogic.VisioQolCommandBarAddin")
            if not bool(addin.Connect):
                raise RuntimeError("EnergoLogic command-bar add-in is not connected")

            bar = app.CommandBars.Item("EnergoLogic QoL Probe")
            if not bool(bar.Visible):
                bar.Visible = True
            button = None
            for index in range(1, int(bar.Controls.Count) + 1):
                control = bar.Controls.Item(index)
                if str(control.Tag) == "EnergoLogic.Duplicate40.UndoProbe":
                    button = control
                    break
            if button is None:
                raise RuntimeError("EnergoLogic command-bar probe button was not found")
            if not bool(button.Visible):
                button.Visible = True

            left = int(button.Left)
            top = int(button.Top)
            width = int(button.Width)
            height = int(button.Height)
            if width <= 0 or height <= 0:
                raise RuntimeError(
                    f"CommandBar button returned invalid bounds: left={left} top={top} "
                    f"width={width} height={height}"
                )
            x = left + width // 2
            y = top + height // 2

            user32 = ctypes.windll.user32
            hwnd = int(window.WindowHandle32)
            if hwnd <= 0:
                raise RuntimeError("Visio active window returned an invalid HWND")
            GA_ROOT = 2
            root_hwnd = int(user32.GetAncestor(hwnd, GA_ROOT)) or hwnd
            cursor = ctypes.wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(cursor))
            old_x = int(cursor.x)
            old_y = int(cursor.y)
            before_count = int(page_obj.Shapes.Count)

            helper = f'''import ctypes,time\ntime.sleep(1.0)\nu=ctypes.windll.user32\nu.ShowWindow({root_hwnd},9)\nu.BringWindowToTop({root_hwnd})\nu.SetForegroundWindow({root_hwnd})\nu.SetActiveWindow({root_hwnd})\ntime.sleep(0.20)\nu.SetCursorPos({x},{y})\ntime.sleep(0.10)\nu.mouse_event(0x0002,0,0,0,0)\nu.mouse_event(0x0004,0,0,0,0)\ntime.sleep(0.15)\nu.SetCursorPos({old_x},{old_y})\n'''
            creationflags = 0x08000000 | 0x00000008 | 0x00000200
            proc = subprocess.Popen(
                [sys.executable, "-c", helper],
                cwd=str(workspace),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
                close_fds=True,
            )
            return ok({
                "document": str(page_obj.Document.Name),
                "page": str(page_obj.Name),
                "source_shape_ids": shape_ids,
                "shape_count_before": before_count,
                "expected_shape_count_after": before_count + len(shape_ids),
                "button_bounds": {
                    "left": left,
                    "top": top,
                    "width": width,
                    "height": height,
                    "click_x": x,
                    "click_y": y,
                },
                "root_window_handle32": root_hwnd,
                "helper_pid": int(proc.pid),
                "delay_seconds": 1.0,
                "scheduled": True,
                "returns_before_physical_click": True,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def schedule_energologic_physical_undo_probe(
        page: str = "",
        doc_name: str = "",
    ) -> str:
        # Schedule one physical Ctrl+Z after this COM call has returned.
        try:
            import ctypes
            import os
            import subprocess
            import sys

            if os.name != "nt":
                raise RuntimeError("asynchronous physical Undo probe is Windows-only")
            page_obj = visio._resolve_page(doc_name, parse_page(page))
            app = page_obj.Application
            try:
                app.ActiveWindow.Page = page_obj
            except Exception:
                page_obj.Activate()
            window = app.ActiveWindow
            hwnd = int(window.WindowHandle32)
            if hwnd <= 0:
                raise RuntimeError("Visio active window returned an invalid HWND")
            user32 = ctypes.windll.user32
            GA_ROOT = 2
            root_hwnd = int(user32.GetAncestor(hwnd, GA_ROOT)) or hwnd
            before_count = int(page_obj.Shapes.Count)

            helper = f'''import ctypes,time\ntime.sleep(1.0)\nu=ctypes.windll.user32\nu.ShowWindow({root_hwnd},9)\nu.BringWindowToTop({root_hwnd})\nu.SetForegroundWindow({root_hwnd})\nu.SetActiveWindow({root_hwnd})\ntime.sleep(0.20)\nu.keybd_event(0x11,0,0,0)\nu.keybd_event(0x5A,0,0,0)\nu.keybd_event(0x5A,0,0x0002,0)\nu.keybd_event(0x11,0,0x0002,0)\n'''
            creationflags = 0x08000000 | 0x00000008 | 0x00000200
            proc = subprocess.Popen(
                [sys.executable, "-c", helper],
                cwd=str(workspace),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
                close_fds=True,
            )
            return ok({
                "document": str(page_obj.Document.Name),
                "page": str(page_obj.Name),
                "shape_count_before": before_count,
                "root_window_handle32": root_hwnd,
                "helper_pid": int(proc.pid),
                "delay_seconds": 1.0,
                "keyboard_chord": "Ctrl+Z",
                "scheduled": True,
                "returns_before_physical_undo": True,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def uninstall_energologic_commandbar_com_addin_probe() -> str:
        # Disconnect and remove only the fixed command-bar probe registration.
        try:
            import winreg
            progid = "EnergoLogic.VisioQolCommandBarAddin"
            clsid = "{F62D8474-1A5C-4A9E-88B5-4AA67D1C5510}"
            try:
                page_obj = visio._resolve_page(
                    "KRU-35_normal_scheme_v2_energologic_qol_host_v1.vsdm",
                    "MCP-v2",
                )
                addins = page_obj.Application.COMAddIns
                addins.Update()
                addin = addins.Item(progid)
                if bool(addin.Connect):
                    addin.Connect = False
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
    def install_energologic_editor_ui(
        page: str = "",
        doc_name: str = "",
    ) -> str:
        # Build/register/connect the full EnergoLogic Visio editor panel.
        try:
            import base64
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
            source_path.write_bytes(base64.b64decode("dXNpbmcgU3lzdGVtOwp1c2luZyBTeXN0ZW0uQ29sbGVjdGlvbnMuR2VuZXJpYzsKdXNpbmcgU3lzdGVtLkRyYXdpbmc7CnVzaW5nIFN5c3RlbS5HbG9iYWxpemF0aW9uOwp1c2luZyBTeXN0ZW0uTGlucTsKdXNpbmcgU3lzdGVtLlJlZmxlY3Rpb247CnVzaW5nIFN5c3RlbS5SdW50aW1lLkludGVyb3BTZXJ2aWNlczsKdXNpbmcgU3lzdGVtLlRleHQuUmVndWxhckV4cHJlc3Npb25zOwp1c2luZyBTeXN0ZW0uV2luZG93cy5Gb3JtczsKdXNpbmcgRXh0ZW5zaWJpbGl0eTsKdXNpbmcgTWljcm9zb2Z0Lk9mZmljZS5Db3JlOwoKW2Fzc2VtYmx5OiBDb21WaXNpYmxlKHRydWUpXQpbYXNzZW1ibHk6IEFzc2VtYmx5VGl0bGUoIkVuZXJnb0xvZ2ljIFZpc2lvIEVkaXRvciIpXQpbYXNzZW1ibHk6IEFzc2VtYmx5VmVyc2lvbigiMC4xLjAuMCIpXQoKbmFtZXNwYWNlIEVuZXJnb0xvZ2ljVmlzaW9FZGl0b3IKewogICAgaW50ZXJuYWwgc2VhbGVkIGNsYXNzIEdsdWVUYXJnZXQKICAgIHsKICAgICAgICBwdWJsaWMgaW50IFRhcmdldElkOwogICAgICAgIHB1YmxpYyBpbnQgUm93OwogICAgICAgIHB1YmxpYyBzdHJpbmcgRW5kcG9pbnQ7CiAgICB9CgogICAgaW50ZXJuYWwgc2VhbGVkIGNsYXNzIENlbGxJbmZvCiAgICB7CiAgICAgICAgcHVibGljIGludCBBbmNob3JJZDsKICAgICAgICBwdWJsaWMgaW50IEJ1c0lkOwogICAgICAgIHB1YmxpYyBpbnQgQnVzVGVybWluYWxJZDsKICAgICAgICBwdWJsaWMgaW50IFNsb3Q7CiAgICAgICAgcHVibGljIGludCBDb25uZWN0aW9uUm93OwogICAgICAgIHB1YmxpYyBzdHJpbmcgRW5kcG9pbnQ7CiAgICAgICAgcHVibGljIExpc3Q8aW50PiBDb3JlSWRzID0gbmV3IExpc3Q8aW50PigpOwogICAgICAgIHB1YmxpYyBMaXN0PGludD4gTWVtYmVySWRzID0gbmV3IExpc3Q8aW50PigpOwogICAgfQoKICAgIGludGVybmFsIHNlYWxlZCBjbGFzcyBDb25uZWN0aW9uUG9pbnRJbmZvCiAgICB7CiAgICAgICAgcHVibGljIGludCBTaGFwZUlkOwogICAgICAgIHB1YmxpYyBpbnQgUm93OwogICAgICAgIHB1YmxpYyBkb3VibGUgWG1tOwogICAgICAgIHB1YmxpYyBkb3VibGUgWW1tOwogICAgICAgIHB1YmxpYyBkb3VibGUgRGlzdGFuY2VNbTsKICAgIH0KCiAgICBbQ29tVmlzaWJsZSh0cnVlKV0KICAgIFtHdWlkKCJFMzFEMEY0NS04QTVBLTQ3RDctQTRBMy1DRkI3RjBDOEI3MzEiKV0KICAgIFtQcm9nSWQoIkVuZXJnb0xvZ2ljLlZpc2lvRWRpdG9yQWRkaW4iKV0KICAgIFtDbGFzc0ludGVyZmFjZShDbGFzc0ludGVyZmFjZVR5cGUuTm9uZSldCiAgICBwdWJsaWMgc2VhbGVkIGNsYXNzIENvbm5lY3QgOiBJRFRFeHRlbnNpYmlsaXR5MgogICAgewogICAgICAgIHByaXZhdGUgb2JqZWN0IF9hcHBsaWNhdGlvbjsKICAgICAgICBwcml2YXRlIEVkaXRvckZvcm0gX2Zvcm07CiAgICAgICAgcHJpdmF0ZSBDb21tYW5kQmFyIF9iYXI7CiAgICAgICAgcHJpdmF0ZSBDb21tYW5kQmFyQnV0dG9uIF90b2dnbGVCdXR0b247CiAgICAgICAgcHJpdmF0ZSBfQ29tbWFuZEJhckJ1dHRvbkV2ZW50c19DbGlja0V2ZW50SGFuZGxlciBfdG9nZ2xlSGFuZGxlcjsKICAgICAgICBwcml2YXRlIHJlYWRvbmx5IFJlZ2V4IF9nbHVlUmVnZXggPSBuZXcgUmVnZXgoCiAgICAgICAgICAgIEAiU2hlZXRcLihcZCspIUNvbm5lY3Rpb25zKD86XC5YKFxkKyl8XC4oXGQrKVwuWCkiLAogICAgICAgICAgICBSZWdleE9wdGlvbnMuSWdub3JlQ2FzZSB8IFJlZ2V4T3B0aW9ucy5Db21waWxlZCk7CgogICAgICAgIHB1YmxpYyB2b2lkIE9uQ29ubmVjdGlvbihvYmplY3QgQXBwbGljYXRpb24sIGV4dF9Db25uZWN0TW9kZSBDb25uZWN0TW9kZSwgb2JqZWN0IEFkZEluSW5zdCwgcmVmIEFycmF5IGN1c3RvbSkKICAgICAgICB7CiAgICAgICAgICAgIF9hcHBsaWNhdGlvbiA9IEFwcGxpY2F0aW9uOwogICAgICAgICAgICBJbnN0YWxsVG9nZ2xlQnV0dG9uKCk7CiAgICAgICAgICAgIFNob3dQYW5lbCgpOwogICAgICAgIH0KCiAgICAgICAgcHVibGljIHZvaWQgT25EaXNjb25uZWN0aW9uKGV4dF9EaXNjb25uZWN0TW9kZSBSZW1vdmVNb2RlLCByZWYgQXJyYXkgY3VzdG9tKQogICAgICAgIHsKICAgICAgICAgICAgdHJ5IHsgaWYgKF9mb3JtICE9IG51bGwgJiYgIV9mb3JtLklzRGlzcG9zZWQpIF9mb3JtLkNsb3NlKCk7IH0gY2F0Y2ggeyB9CiAgICAgICAgICAgIF9mb3JtID0gbnVsbDsKICAgICAgICAgICAgX3RvZ2dsZUJ1dHRvbiA9IG51bGw7CiAgICAgICAgICAgIF9iYXIgPSBudWxsOwogICAgICAgICAgICBfYXBwbGljYXRpb24gPSBudWxsOwogICAgICAgIH0KCiAgICAgICAgcHVibGljIHZvaWQgT25BZGRJbnNVcGRhdGUocmVmIEFycmF5IGN1c3RvbSkgeyB9CiAgICAgICAgcHVibGljIHZvaWQgT25TdGFydHVwQ29tcGxldGUocmVmIEFycmF5IGN1c3RvbSkgeyB9CiAgICAgICAgcHVibGljIHZvaWQgT25CZWdpblNodXRkb3duKHJlZiBBcnJheSBjdXN0b20pIHsgfQoKICAgICAgICBwcml2YXRlIGR5bmFtaWMgQXBwCiAgICAgICAgewogICAgICAgICAgICBnZXQKICAgICAgICAgICAgewogICAgICAgICAgICAgICAgaWYgKF9hcHBsaWNhdGlvbiA9PSBudWxsKSB0aHJvdyBuZXcgSW52YWxpZE9wZXJhdGlvbkV4Y2VwdGlvbigiVmlzaW8g0L3QtSDQv9C+0LTQutC70Y7Rh9GR0L0iKTsKICAgICAgICAgICAgICAgIHJldHVybiBfYXBwbGljYXRpb247CiAgICAgICAgICAgIH0KICAgICAgICB9CgogICAgICAgIHByaXZhdGUgdm9pZCBJbnN0YWxsVG9nZ2xlQnV0dG9uKCkKICAgICAgICB7CiAgICAgICAgICAgIGR5bmFtaWMgYXBwID0gQXBwOwogICAgICAgICAgICBDb21tYW5kQmFycyBiYXJzID0gKENvbW1hbmRCYXJzKWFwcC5Db21tYW5kQmFyczsKICAgICAgICAgICAgY29uc3Qgc3RyaW5nIGJhck5hbWUgPSAiRW5lcmdvTG9naWMiOwogICAgICAgICAgICB0cnkgeyBfYmFyID0gYmFyc1tiYXJOYW1lXTsgfQogICAgICAgICAgICBjYXRjaCB7IF9iYXIgPSBiYXJzLkFkZChiYXJOYW1lLCBNc29CYXJQb3NpdGlvbi5tc29CYXJUb3AsIE1pc3NpbmcuVmFsdWUsIHRydWUpOyB9CgogICAgICAgICAgICBfdG9nZ2xlQnV0dG9uID0gbnVsbDsKICAgICAgICAgICAgZm9yIChpbnQgaSA9IDE7IGkgPD0gX2Jhci5Db250cm9scy5Db3VudDsgaSsrKQogICAgICAgICAgICB7CiAgICAgICAgICAgICAgICBDb21tYW5kQmFyQ29udHJvbCBjID0gX2Jhci5Db250cm9sc1tpXTsKICAgICAgICAgICAgICAgIGlmIChTdHJpbmcuRXF1YWxzKGMuVGFnLCAiRW5lcmdvTG9naWMuRWRpdG9yLlRvZ2dsZSIsIFN0cmluZ0NvbXBhcmlzb24uT3JkaW5hbCkpCiAgICAgICAgICAgICAgICB7CiAgICAgICAgICAgICAgICAgICAgX3RvZ2dsZUJ1dHRvbiA9IGMgYXMgQ29tbWFuZEJhckJ1dHRvbjsKICAgICAgICAgICAgICAgICAgICBicmVhazsKICAgICAgICAgICAgICAgIH0KICAgICAgICAgICAgfQogICAgICAgICAgICBpZiAoX3RvZ2dsZUJ1dHRvbiA9PSBudWxsKQogICAgICAgICAgICAgICAgX3RvZ2dsZUJ1dHRvbiA9IChDb21tYW5kQmFyQnV0dG9uKV9iYXIuQ29udHJvbHMuQWRkKE1zb0NvbnRyb2xUeXBlLm1zb0NvbnRyb2xCdXR0b24sIE1pc3NpbmcuVmFsdWUsIE1pc3NpbmcuVmFsdWUsIE1pc3NpbmcuVmFsdWUsIHRydWUpOwoKICAgICAgICAgICAgX3RvZ2dsZUJ1dHRvbi5DYXB0aW9uID0gIkVuZXJnb0xvZ2ljIjsKICAgICAgICAgICAgX3RvZ2dsZUJ1dHRvbi5UYWcgPSAiRW5lcmdvTG9naWMuRWRpdG9yLlRvZ2dsZSI7CiAgICAgICAgICAgIF90b2dnbGVCdXR0b24uU3R5bGUgPSBNc29CdXR0b25TdHlsZS5tc29CdXR0b25DYXB0aW9uOwogICAgICAgICAgICBfdG9nZ2xlQnV0dG9uLlRvb2x0aXBUZXh0ID0gItCf0L7QutCw0LfQsNGC0Ywg0L/QsNC90LXQu9GMIEVuZXJnb0xvZ2ljIjsKICAgICAgICAgICAgX3RvZ2dsZUJ1dHRvbi5WaXNpYmxlID0gdHJ1ZTsKICAgICAgICAgICAgX3RvZ2dsZUhhbmRsZXIgPSBuZXcgX0NvbW1hbmRCYXJCdXR0b25FdmVudHNfQ2xpY2tFdmVudEhhbmRsZXIoT25Ub2dnbGVDbGljayk7CiAgICAgICAgICAgIF90b2dnbGVCdXR0b24uQ2xpY2sgKz0gX3RvZ2dsZUhhbmRsZXI7CiAgICAgICAgICAgIF9iYXIuVmlzaWJsZSA9IHRydWU7CiAgICAgICAgfQoKICAgICAgICBwcml2YXRlIHZvaWQgT25Ub2dnbGVDbGljayhDb21tYW5kQmFyQnV0dG9uIEN0cmwsIHJlZiBib29sIENhbmNlbERlZmF1bHQpCiAgICAgICAgewogICAgICAgICAgICBDYW5jZWxEZWZhdWx0ID0gZmFsc2U7CiAgICAgICAgICAgIFNob3dQYW5lbCgpOwogICAgICAgIH0KCiAgICAgICAgcHVibGljIHZvaWQgU2hvd1BhbmVsKCkKICAgICAgICB7CiAgICAgICAgICAgIGlmIChfZm9ybSA9PSBudWxsIHx8IF9mb3JtLklzRGlzcG9zZWQpCiAgICAgICAgICAgICAgICBfZm9ybSA9IG5ldyBFZGl0b3JGb3JtKHRoaXMpOwogICAgICAgICAgICBpZiAoIV9mb3JtLlZpc2libGUpIF9mb3JtLlNob3coKTsKICAgICAgICAgICAgX2Zvcm0uQnJpbmdUb0Zyb250KCk7CiAgICAgICAgICAgIF9mb3JtLkFjdGl2YXRlKCk7CiAgICAgICAgfQoKICAgICAgICBpbnRlcm5hbCBzdHJpbmcgRHVwbGljYXRlQ2VsbChpbnQgZGlyZWN0aW9uKQogICAgICAgIHsKICAgICAgICAgICAgZHluYW1pYyBhcHAgPSBBcHA7CiAgICAgICAgICAgIGR5bmFtaWMgcGFnZSA9IGFwcC5BY3RpdmVQYWdlOwogICAgICAgICAgICBDZWxsSW5mbyBjZWxsID0gRGlzY292ZXJDZWxsRnJvbVNlbGVjdGlvbihwYWdlKTsKICAgICAgICAgICAgZHluYW1pYyBzb3VyY2VUZXJtaW5hbCA9IHBhZ2UuU2hhcGVzLkl0ZW1Gcm9tSUQoY2VsbC5CdXNUZXJtaW5hbElkKTsKICAgICAgICAgICAgZHluYW1pYyB0YXJnZXRUZXJtaW5hbCA9IEdldEJ1c1Rlcm1pbmFsQnlTbG90KHBhZ2UsIGNlbGwuQnVzSWQsIGNlbGwuU2xvdCArIGRpcmVjdGlvbik7CiAgICAgICAgICAgIGludCB0YXJnZXRTbG90ID0gR2V0U2xvdCh0YXJnZXRUZXJtaW5hbCk7CiAgICAgICAgICAgIEVuc3VyZVRlcm1pbmFsRnJlZShwYWdlLCAoaW50KXRhcmdldFRlcm1pbmFsLklELCBuZXcgSGFzaFNldDxpbnQ+KCkpOwogICAgICAgICAgICBkb3VibGUgZHggPSBHZXRNbSh0YXJnZXRUZXJtaW5hbCwgIlBpblgiKSAtIEdldE1tKHNvdXJjZVRlcm1pbmFsLCAiUGluWCIpOwogICAgICAgICAgICBkb3VibGUgZHkgPSBHZXRNbSh0YXJnZXRUZXJtaW5hbCwgIlBpblkiKSAtIEdldE1tKHNvdXJjZVRlcm1pbmFsLCAiUGluWSIpOwoKICAgICAgICAgICAgTGlzdDxpbnQ+IHNvdXJjZUlkcyA9IGNlbGwuTWVtYmVySWRzLk9yZGVyQnkoeCA9PiB4KS5Ub0xpc3QoKTsKICAgICAgICAgICAgU2VsZWN0SWRzKHBhZ2UsIHNvdXJjZUlkcyk7CiAgICAgICAgICAgIExpc3Q8ZG91YmxlW10+IHNvdXJjZVBvaW50cyA9IHNvdXJjZUlkcy5TZWxlY3QoaWQgPT4gbmV3W10geyBHZXRNbShwYWdlLlNoYXBlcy5JdGVtRnJvbUlEKGlkKSwgIlBpblgiKSwgR2V0TW0ocGFnZS5TaGFwZXMuSXRlbUZyb21JRChpZCksICJQaW5ZIikgfSkuVG9MaXN0KCk7CiAgICAgICAgICAgIExpc3Q8c3RyaW5nPiBzb3VyY2VNYXN0ZXJzID0gc291cmNlSWRzLlNlbGVjdChpZCA9PiBNYXN0ZXJOYW1lKHBhZ2UuU2hhcGVzLkl0ZW1Gcm9tSUQoaWQpKSkuVG9MaXN0KCk7CiAgICAgICAgICAgIExpc3Q8c3RyaW5nPiBzb3VyY2VUZXh0cyA9IHNvdXJjZUlkcy5TZWxlY3QoaWQgPT4gU2FmZVRleHQocGFnZS5TaGFwZXMuSXRlbUZyb21JRChpZCkpKS5Ub0xpc3QoKTsKCiAgICAgICAgICAgIGludCBzY29wZSA9IChpbnQpYXBwLkJlZ2luVW5kb1Njb3BlKGRpcmVjdGlvbiA+IDAgPyAiRW5lcmdvTG9naWM6INCa0L7Qv9C40YDQvtCy0LDRgtGMINGP0YfQtdC50LrRgyDQstC/0YDQsNCy0L4iIDogIkVuZXJnb0xvZ2ljOiDQmtC+0L/QuNGA0L7QstCw0YLRjCDRj9GH0LXQudC60YMg0LLQu9C10LLQviIpOwogICAgICAgICAgICBib29sIGNvbW1pdCA9IGZhbHNlOwogICAgICAgICAgICB0cnkKICAgICAgICAgICAgewogICAgICAgICAgICAgICAgYXBwLkRvQ21kKDEwMjQpOwogICAgICAgICAgICAgICAgZHluYW1pYyBkdXBsaWNhdGVkID0gYXBwLkFjdGl2ZVdpbmRvdy5TZWxlY3Rpb247CiAgICAgICAgICAgICAgICBpZiAoKGludClkdXBsaWNhdGVkLkNvdW50ICE9IHNvdXJjZUlkcy5Db3VudCkgdGhyb3cgbmV3IEludmFsaWRPcGVyYXRpb25FeGNlcHRpb24oIlZpc2lvINCy0LXRgNC90YPQuyDQvdC10L/QvtC70L3Rg9GOINC60L7Qv9C40Y4g0LLRi9C00LXQu9C10L3QuNGPIik7CiAgICAgICAgICAgICAgICBMaXN0PGludD4gbmV3SWRzID0gU2VsZWN0aW9uSWRzKGR1cGxpY2F0ZWQpOwogICAgICAgICAgICAgICAgTGlzdDxkb3VibGVbXT4gbmV3UG9pbnRzID0gbmV3SWRzLlNlbGVjdChpZCA9PiBuZXdbXSB7IEdldE1tKHBhZ2UuU2hhcGVzLkl0ZW1Gcm9tSUQoaWQpLCAiUGluWCIpLCBHZXRNbShwYWdlLlNoYXBlcy5JdGVtRnJvbUlEKGlkKSwgIlBpblkiKSB9KS5Ub0xpc3QoKTsKICAgICAgICAgICAgICAgIGZvciAoaW50IGkgPSAwOyBpIDwgc291cmNlSWRzLkNvdW50OyBpKyspCiAgICAgICAgICAgICAgICB7CiAgICAgICAgICAgICAgICAgICAgaWYgKE1hc3Rlck5hbWUocGFnZS5TaGFwZXMuSXRlbUZyb21JRChuZXdJZHNbaV0pKSAhPSBzb3VyY2VNYXN0ZXJzW2ldIHx8IFNhZmVUZXh0KHBhZ2UuU2hhcGVzLkl0ZW1Gcm9tSUQobmV3SWRzW2ldKSkgIT0gc291cmNlVGV4dHNbaV0pCiAgICAgICAgICAgICAgICAgICAgICAgIHRocm93IG5ldyBJbnZhbGlkT3BlcmF0aW9uRXhjZXB0aW9uKCJWaXNpbyDQuNC30LzQtdC90LjQuyDQv9C+0YDRj9C00L7QuiDRjdC70LXQvNC10L3RgtC+0LIg0L/RgNC4INC60L7Qv9C40YDQvtCy0LDQvdC40Lg7INC+0L/QtdGA0LDRhtC40Y8g0L7RgtC80LXQvdC10L3QsCIpOwogICAgICAgICAgICAgICAgfQogICAgICAgICAgICAgICAgZG91YmxlIG5hdGl2ZUR4ID0gbmV3UG9pbnRzLkF2ZXJhZ2UocCA9PiBwWzBdKSAtIHNvdXJjZVBvaW50cy5BdmVyYWdlKHAgPT4gcFswXSk7CiAgICAgICAgICAgICAgICBkb3VibGUgbmF0aXZlRHkgPSBuZXdQb2ludHMuQXZlcmFnZShwID0+IHBbMV0pIC0gc291cmNlUG9pbnRzLkF2ZXJhZ2UocCA9PiBwWzFdKTsKICAgICAgICAgICAgICAgIGR1cGxpY2F0ZWQuTW92ZShkeCAtIG5hdGl2ZUR4LCBkeSAtIG5hdGl2ZUR5LCAibW0iKTsKCiAgICAgICAgICAgICAgICBpbnQgYW5jaG9ySW5kZXggPSBzb3VyY2VJZHMuSW5kZXhPZihjZWxsLkFuY2hvcklkKTsKICAgICAgICAgICAgICAgIGlmIChhbmNob3JJbmRleCA8IDApIHRocm93IG5ldyBJbnZhbGlkT3BlcmF0aW9uRXhjZXB0aW9uKCLQndC1INC90LDQudC00LXQvSBhbmNob3Ig0Y/Rh9C10LnQutC4INCyINC60L7Qv9C40LgiKTsKICAgICAgICAgICAgICAgIGR5bmFtaWMgbmV3QW5jaG9yID0gcGFnZS5TaGFwZXMuSXRlbUZyb21JRChuZXdJZHNbYW5jaG9ySW5kZXhdKTsKICAgICAgICAgICAgICAgIHN0cmluZyBuZXdDZWxsSWQgPSAiY2VsbDoiICsgR3VpZC5OZXdHdWlkKCkuVG9TdHJpbmcoIk4iKTsKICAgICAgICAgICAgICAgIGZvcmVhY2ggKGludCBpZCBpbiBuZXdJZHMpIFNldENlbGxJZGVudGl0eShwYWdlLlNoYXBlcy5JdGVtRnJvbUlEKGlkKSwgbmV3Q2VsbElkKTsKICAgICAgICAgICAgICAgIEdsdWVFbmRwb2ludChuZXdBbmNob3IsIGNlbGwuRW5kcG9pbnQsIHRhcmdldFRlcm1pbmFsLCBjZWxsLkNvbm5lY3Rpb25Sb3cpOwogICAgICAgICAgICAgICAgVmVyaWZ5R2x1ZShuZXdBbmNob3IsIGNlbGwuRW5kcG9pbnQsIChpbnQpdGFyZ2V0VGVybWluYWwuSUQsIGNlbGwuQ29ubmVjdGlvblJvdyk7CiAgICAgICAgICAgICAgICBjb21taXQgPSB0cnVlOwogICAgICAgICAgICAgICAgcmV0dXJuIFN0cmluZy5Gb3JtYXQoQ3VsdHVyZUluZm8uQ3VycmVudEN1bHR1cmUsCiAgICAgICAgICAgICAgICAgICAgIuKckyDQr9GH0LXQudC60LAg0YHQutC+0L/QuNGA0L7QstCw0L3QsCB7MH0uINCc0LXRgdGC0L4gezF9IOKGkiB7Mn07INGB0LTQstC40LMgezM6MC4wMH0g0LzQvDsgR2x1ZSDQstC+0YHRgdGC0LDQvdC+0LLQu9C10L07IGlkZW50aXR5INGB0L7Qt9C00LDQvdCwLiIsCiAgICAgICAgICAgICAgICAgICAgZGlyZWN0aW9uID4gMCA/ICLQstC/0YDQsNCy0L4iIDogItCy0LvQtdCy0L4iLCBjZWxsLlNsb3QsIHRhcmdldFNsb3QsIGR4KTsKICAgICAgICAgICAgfQogICAgICAgICAgICBmaW5hbGx5CiAgICAgICAgICAgIHsKICAgICAgICAgICAgICAgIGFwcC5FbmRVbmRvU2NvcGUoc2NvcGUsIGNvbW1pdCk7CiAgICAgICAgICAgIH0KICAgICAgICB9CgogICAgICAgIGludGVybmFsIHN0cmluZyBNb3ZlQ2VsbChpbnQgZGlyZWN0aW9uKQogICAgICAgIHsKICAgICAgICAgICAgZHluYW1pYyBhcHAgPSBBcHA7CiAgICAgICAgICAgIGR5bmFtaWMgcGFnZSA9IGFwcC5BY3RpdmVQYWdlOwogICAgICAgICAgICBDZWxsSW5mbyBjZWxsID0gRGlzY292ZXJDZWxsRnJvbVNlbGVjdGlvbihwYWdlKTsKICAgICAgICAgICAgZHluYW1pYyBzb3VyY2VUZXJtaW5hbCA9IHBhZ2UuU2hhcGVzLkl0ZW1Gcm9tSUQoY2VsbC5CdXNUZXJtaW5hbElkKTsKICAgICAgICAgICAgZHluYW1pYyB0YXJnZXRUZXJtaW5hbCA9IEdldEJ1c1Rlcm1pbmFsQnlTbG90KHBhZ2UsIGNlbGwuQnVzSWQsIGNlbGwuU2xvdCArIGRpcmVjdGlvbik7CiAgICAgICAgICAgIEhhc2hTZXQ8aW50PiBvd24gPSBuZXcgSGFzaFNldDxpbnQ+KGNlbGwuTWVtYmVySWRzKTsKICAgICAgICAgICAgRW5zdXJlVGVybWluYWxGcmVlKHBhZ2UsIChpbnQpdGFyZ2V0VGVybWluYWwuSUQsIG93bik7CiAgICAgICAgICAgIGRvdWJsZSBkeCA9IEdldE1tKHRhcmdldFRlcm1pbmFsLCAiUGluWCIpIC0gR2V0TW0oc291cmNlVGVybWluYWwsICJQaW5YIik7CiAgICAgICAgICAgIGRvdWJsZSBkeSA9IEdldE1tKHRhcmdldFRlcm1pbmFsLCAiUGluWSIpIC0gR2V0TW0oc291cmNlVGVybWluYWwsICJQaW5ZIik7CgogICAgICAgICAgICBpbnQgc2NvcGUgPSAoaW50KWFwcC5CZWdpblVuZG9TY29wZShkaXJlY3Rpb24gPiAwID8gIkVuZXJnb0xvZ2ljOiDQn9C10YDQtdC80LXRgdGC0LjRgtGMINGP0YfQtdC50LrRgyDQstC/0YDQsNCy0L4iIDogIkVuZXJnb0xvZ2ljOiDQn9C10YDQtdC80LXRgdGC0LjRgtGMINGP0YfQtdC50LrRgyDQstC70LXQstC+Iik7CiAgICAgICAgICAgIGJvb2wgY29tbWl0ID0gZmFsc2U7CiAgICAgICAgICAgIHRyeQogICAgICAgICAgICB7CiAgICAgICAgICAgICAgICBkeW5hbWljIGFuY2hvciA9IHBhZ2UuU2hhcGVzLkl0ZW1Gcm9tSUQoY2VsbC5BbmNob3JJZCk7CiAgICAgICAgICAgICAgICBEZXRhY2hFbmRwb2ludChhbmNob3IsIGNlbGwuRW5kcG9pbnQpOwogICAgICAgICAgICAgICAgU2VsZWN0SWRzKHBhZ2UsIGNlbGwuTWVtYmVySWRzKTsKICAgICAgICAgICAgICAgIGFwcC5BY3RpdmVXaW5kb3cuU2VsZWN0aW9uLk1vdmUoZHgsIGR5LCAibW0iKTsKICAgICAgICAgICAgICAgIEdsdWVFbmRwb2ludChhbmNob3IsIGNlbGwuRW5kcG9pbnQsIHRhcmdldFRlcm1pbmFsLCBjZWxsLkNvbm5lY3Rpb25Sb3cpOwogICAgICAgICAgICAgICAgVmVyaWZ5R2x1ZShhbmNob3IsIGNlbGwuRW5kcG9pbnQsIChpbnQpdGFyZ2V0VGVybWluYWwuSUQsIGNlbGwuQ29ubmVjdGlvblJvdyk7CiAgICAgICAgICAgICAgICBjb21taXQgPSB0cnVlOwogICAgICAgICAgICAgICAgcmV0dXJuIFN0cmluZy5Gb3JtYXQoQ3VsdHVyZUluZm8uQ3VycmVudEN1bHR1cmUsCiAgICAgICAgICAgICAgICAgICAgIuKckyDQr9GH0LXQudC60LAg0L/QtdGA0LXQvNC10YnQtdC90LAgezB9LiDQnNC10YHRgtC+IHsxfSDihpIgezJ9OyDRgdC00LLQuNCzIHszOjAuMDB9INC80Lw7IEdsdWUg0L/RgNC+0LLQtdGA0LXQvS4iLAogICAgICAgICAgICAgICAgICAgIGRpcmVjdGlvbiA+IDAgPyAi0LLQv9GA0LDQstC+IiA6ICLQstC70LXQstC+IiwgY2VsbC5TbG90LCBHZXRTbG90KHRhcmdldFRlcm1pbmFsKSwgZHgpOwogICAgICAgICAgICB9CiAgICAgICAgICAgIGZpbmFsbHkgeyBhcHAuRW5kVW5kb1Njb3BlKHNjb3BlLCBjb21taXQpOyB9CiAgICAgICAgfQoKICAgICAgICBpbnRlcm5hbCBzdHJpbmcgU2VsZWN0Q2VsbCgpCiAgICAgICAgewogICAgICAgICAgICBkeW5hbWljIHBhZ2UgPSBBcHAuQWN0aXZlUGFnZTsKICAgICAgICAgICAgQ2VsbEluZm8gY2VsbCA9IERpc2NvdmVyQ2VsbEZyb21TZWxlY3Rpb24ocGFnZSk7CiAgICAgICAgICAgIFNlbGVjdElkcyhwYWdlLCBjZWxsLk1lbWJlcklkcyk7CiAgICAgICAgICAgIHJldHVybiAi4pyTINCS0YvQtNC10LvQtdC90LAg0LLRgdGPINGP0YfQtdC50LrQsDogIiArIGNlbGwuTWVtYmVySWRzLkNvdW50ICsgIiDRjdC70LXQvNC10L3RgtC+0LIsINC80LXRgdGC0L4g0YjQuNC90YsgIiArIGNlbGwuU2xvdCArICIuIjsKICAgICAgICB9CgogICAgICAgIGludGVybmFsIHN0cmluZyBFeGFjdE9mZnNldChkb3VibGUgZHgsIGRvdWJsZSBkeSkKICAgICAgICB7CiAgICAgICAgICAgIGlmIChNYXRoLkFicyhkeCkgPCAxZS05ICYmIE1hdGguQWJzKGR5KSA8IDFlLTkpIHRocm93IG5ldyBJbnZhbGlkT3BlcmF0aW9uRXhjZXB0aW9uKCLQodC80LXRidC10L3QuNC1INC90LUg0LzQvtC20LXRgiDQsdGL0YLRjCDQvdGD0LvQtdCy0YvQvCIpOwogICAgICAgICAgICBkeW5hbWljIGFwcCA9IEFwcDsKICAgICAgICAgICAgZHluYW1pYyBwYWdlID0gYXBwLkFjdGl2ZVBhZ2U7CiAgICAgICAgICAgIExpc3Q8aW50PiBpZHMgPSBDdXJyZW50VG9wTGV2ZWxTZWxlY3Rpb24ocGFnZSk7CiAgICAgICAgICAgIEVuc3VyZU5vRXh0ZXJuYWxHbHVlKHBhZ2UsIGlkcyk7CiAgICAgICAgICAgIGludCBzY29wZSA9IChpbnQpYXBwLkJlZ2luVW5kb1Njb3BlKCJFbmVyZ29Mb2dpYzog0KLQvtGH0L3Ri9C5INGB0LTQstC40LMiKTsKICAgICAgICAgICAgYm9vbCBjb21taXQgPSBmYWxzZTsKICAgICAgICAgICAgdHJ5CiAgICAgICAgICAgIHsKICAgICAgICAgICAgICAgIFNlbGVjdElkcyhwYWdlLCBpZHMpOwogICAgICAgICAgICAgICAgYXBwLkFjdGl2ZVdpbmRvdy5TZWxlY3Rpb24uTW92ZShkeCwgZHksICJtbSIpOwogICAgICAgICAgICAgICAgY29tbWl0ID0gdHJ1ZTsKICAgICAgICAgICAgICAgIHJldHVybiBTdHJpbmcuRm9ybWF0KEN1bHR1cmVJbmZvLkN1cnJlbnRDdWx0dXJlLCAi4pyTINCi0L7Rh9C90YvQuSDRgdC00LLQuNCzOiBYIHswOjAuIyMjfSDQvNC8LCBZIHsxOjAuIyMjfSDQvNC8LiIsIGR4LCBkeSk7CiAgICAgICAgICAgIH0KICAgICAgICAgICAgZmluYWxseSB7IGFwcC5FbmRVbmRvU2NvcGUoc2NvcGUsIGNvbW1pdCk7IH0KICAgICAgICB9CgogICAgICAgIGludGVybmFsIHN0cmluZyBCYXNlUG9pbnRUcmFuc2Zvcm0oYm9vbCBjb3B5LCBkb3VibGUgYngsIGRvdWJsZSBieSwgZG91YmxlIHR4LCBkb3VibGUgdHkpCiAgICAgICAgewogICAgICAgICAgICBkb3VibGUgZHggPSB0eCAtIGJ4OwogICAgICAgICAgICBkb3VibGUgZHkgPSB0eSAtIGJ5OwogICAgICAgICAgICBpZiAoTWF0aC5BYnMoZHgpIDwgMWUtOSAmJiBNYXRoLkFicyhkeSkgPCAxZS05KSB0aHJvdyBuZXcgSW52YWxpZE9wZXJhdGlvbkV4Y2VwdGlvbigi0JHQsNC30L7QstCw0Y8g0Lgg0YbQtdC70LXQstCw0Y8g0YLQvtGH0LrQuCDRgdC+0LLQv9Cw0LTQsNGO0YIiKTsKICAgICAgICAgICAgZHluYW1pYyBhcHAgPSBBcHA7CiAgICAgICAgICAgIGR5bmFtaWMgcGFnZSA9IGFwcC5BY3RpdmVQYWdlOwogICAgICAgICAgICBMaXN0PGludD4gaWRzID0gQ3VycmVudFRvcExldmVsU2VsZWN0aW9uKHBhZ2UpOwogICAgICAgICAgICBFbnN1cmVOb0V4dGVybmFsR2x1ZShwYWdlLCBpZHMpOwogICAgICAgICAgICBpbnQgc2NvcGUgPSAoaW50KWFwcC5CZWdpblVuZG9TY29wZShjb3B5ID8gIkVuZXJnb0xvZ2ljOiDQmtC+0L/QuNGA0L7QstCw0YLRjCDRgSDQsdCw0LfQvtCy0L7QuSDRgtC+0YfQutC+0LkiIDogIkVuZXJnb0xvZ2ljOiDQn9C10YDQtdC80LXRgdGC0LjRgtGMINGBINCx0LDQt9C+0LLQvtC5INGC0L7Rh9C60L7QuSIpOwogICAgICAgICAgICBib29sIGNvbW1pdCA9IGZhbHNlOwogICAgICAgICAgICB0cnkKICAgICAgICAgICAgewogICAgICAgICAgICAgICAgU2VsZWN0SWRzKHBhZ2UsIGlkcyk7CiAgICAgICAgICAgICAgICBpZiAoY29weSkKICAgICAgICAgICAgICAgIHsKICAgICAgICAgICAgICAgICAgICBMaXN0PGRvdWJsZVtdPiBzcmMgPSBpZHMuU2VsZWN0KGlkID0+IG5ld1tdIHsgR2V0TW0ocGFnZS5TaGFwZXMuSXRlbUZyb21JRChpZCksICJQaW5YIiksIEdldE1tKHBhZ2UuU2hhcGVzLkl0ZW1Gcm9tSUQoaWQpLCAiUGluWSIpIH0pLlRvTGlzdCgpOwogICAgICAgICAgICAgICAgICAgIGFwcC5Eb0NtZCgxMDI0KTsKICAgICAgICAgICAgICAgICAgICBkeW5hbWljIGR1cCA9IGFwcC5BY3RpdmVXaW5kb3cuU2VsZWN0aW9uOwogICAgICAgICAgICAgICAgICAgIGlmICgoaW50KWR1cC5Db3VudCAhPSBpZHMuQ291bnQpIHRocm93IG5ldyBJbnZhbGlkT3BlcmF0aW9uRXhjZXB0aW9uKCLQndC10L/QvtC70L3QsNGPINC60L7Qv9C40Y8g0LLRi9C00LXQu9C10L3QuNGPIik7CiAgICAgICAgICAgICAgICAgICAgTGlzdDxpbnQ+IG5ld0lkcyA9IFNlbGVjdGlvbklkcyhkdXApOwogICAgICAgICAgICAgICAgICAgIExpc3Q8ZG91YmxlW10+IG5vdyA9IG5ld0lkcy5TZWxlY3QoaWQgPT4gbmV3W10geyBHZXRNbShwYWdlLlNoYXBlcy5JdGVtRnJvbUlEKGlkKSwgIlBpblgiKSwgR2V0TW0ocGFnZS5TaGFwZXMuSXRlbUZyb21JRChpZCksICJQaW5ZIikgfSkuVG9MaXN0KCk7CiAgICAgICAgICAgICAgICAgICAgZG91YmxlIG5keCA9IG5vdy5BdmVyYWdlKHAgPT4gcFswXSkgLSBzcmMuQXZlcmFnZShwID0+IHBbMF0pOwogICAgICAgICAgICAgICAgICAgIGRvdWJsZSBuZHkgPSBub3cuQXZlcmFnZShwID0+IHBbMV0pIC0gc3JjLkF2ZXJhZ2UocCA9PiBwWzFdKTsKICAgICAgICAgICAgICAgICAgICBkdXAuTW92ZShkeCAtIG5keCwgZHkgLSBuZHksICJtbSIpOwogICAgICAgICAgICAgICAgICAgIHN0cmluZyBjZWxsSWQgPSAiY2VsbDoiICsgR3VpZC5OZXdHdWlkKCkuVG9TdHJpbmcoIk4iKTsKICAgICAgICAgICAgICAgICAgICBmb3JlYWNoIChpbnQgaWQgaW4gbmV3SWRzKSBpZiAoSGFzQ2VsbElkZW50aXR5KHBhZ2UuU2hhcGVzLkl0ZW1Gcm9tSUQoaWQpKSkgU2V0Q2VsbElkZW50aXR5KHBhZ2UuU2hhcGVzLkl0ZW1Gcm9tSUQoaWQpLCBjZWxsSWQpOwogICAgICAgICAgICAgICAgfQogICAgICAgICAgICAgICAgZWxzZSBhcHAuQWN0aXZlV2luZG93LlNlbGVjdGlvbi5Nb3ZlKGR4LCBkeSwgIm1tIik7CiAgICAgICAgICAgICAgICBjb21taXQgPSB0cnVlOwogICAgICAgICAgICAgICAgcmV0dXJuIFN0cmluZy5Gb3JtYXQoQ3VsdHVyZUluZm8uQ3VycmVudEN1bHR1cmUsICLinJMgezB9INC/0L4g0LHQsNC30L7QstC+0Lkg0YLQvtGH0LrQtTogzpRYIHsxOjAuIyMjfSDQvNC8LCDOlFkgezI6MC4jIyN9INC80LwuIiwgY29weSA/ICLQmtC+0L/QuNGA0L7QstCw0L3QuNC1IiA6ICLQn9C10YDQtdC80LXRidC10L3QuNC1IiwgZHgsIGR5KTsKICAgICAgICAgICAgfQogICAgICAgICAgICBmaW5hbGx5IHsgYXBwLkVuZFVuZG9TY29wZShzY29wZSwgY29tbWl0KTsgfQogICAgICAgIH0KCiAgICAgICAgaW50ZXJuYWwgc3RyaW5nIEFsaWduKHN0cmluZyBheGlzKQogICAgICAgIHsKICAgICAgICAgICAgZHluYW1pYyBhcHAgPSBBcHA7CiAgICAgICAgICAgIGR5bmFtaWMgcGFnZSA9IGFwcC5BY3RpdmVQYWdlOwogICAgICAgICAgICBMaXN0PGludD4gaWRzID0gQ3VycmVudFRvcExldmVsU2VsZWN0aW9uKHBhZ2UpOwogICAgICAgICAgICBpZiAoaWRzLkNvdW50IDwgMikgdGhyb3cgbmV3IEludmFsaWRPcGVyYXRpb25FeGNlcHRpb24oItCU0LvRjyDQstGL0YDQsNCy0L3QuNCy0LDQvdC40Y8g0LLRi9Cx0LXRgNC40YLQtSDQvNC40L3QuNC80YPQvCDQtNCy0LAg0Y3Qu9C10LzQtdC90YLQsCIpOwogICAgICAgICAgICBFbnN1cmVOb0V4dGVybmFsR2x1ZShwYWdlLCBpZHMpOwogICAgICAgICAgICBkeW5hbWljIGZpcnN0ID0gcGFnZS5TaGFwZXMuSXRlbUZyb21JRChpZHNbMF0pOwogICAgICAgICAgICBkb3VibGUgdGFyZ2V0ID0gR2V0TW0oZmlyc3QsIGF4aXMgPT0gIngiID8gIlBpblgiIDogIlBpblkiKTsKICAgICAgICAgICAgaW50IHNjb3BlID0gKGludClhcHAuQmVnaW5VbmRvU2NvcGUoYXhpcyA9PSAieCIgPyAiRW5lcmdvTG9naWM6INCS0YvRgNC+0LLQvdGP0YLRjCDQv9C+IFgiIDogIkVuZXJnb0xvZ2ljOiDQktGL0YDQvtCy0L3Rj9GC0Ywg0L/QviBZIik7CiAgICAgICAgICAgIGJvb2wgY29tbWl0ID0gZmFsc2U7CiAgICAgICAgICAgIHRyeQogICAgICAgICAgICB7CiAgICAgICAgICAgICAgICBmb3JlYWNoIChpbnQgaWQgaW4gaWRzKQogICAgICAgICAgICAgICAgewogICAgICAgICAgICAgICAgICAgIGR5bmFtaWMgc2hhcGUgPSBwYWdlLlNoYXBlcy5JdGVtRnJvbUlEKGlkKTsKICAgICAgICAgICAgICAgICAgICBTZXRNbShzaGFwZSwgYXhpcyA9PSAieCIgPyAiUGluWCIgOiAiUGluWSIsIHRhcmdldCk7CiAgICAgICAgICAgICAgICB9CiAgICAgICAgICAgICAgICBTZWxlY3RJZHMocGFnZSwgaWRzKTsKICAgICAgICAgICAgICAgIGNvbW1pdCA9IHRydWU7CiAgICAgICAgICAgICAgICByZXR1cm4gU3RyaW5nLkZvcm1hdChDdWx0dXJlSW5mby5DdXJyZW50Q3VsdHVyZSwgIuKckyDQktGL0YDQvtCy0L3QtdC90L4gezB9INGN0LvQtdC80LXQvdGC0L7QsiDQv9C+IHsxfSA9IHsyOjAuIyMjfSDQvNC8LiIsIGlkcy5Db3VudCwgYXhpcy5Ub1VwcGVySW52YXJpYW50KCksIHRhcmdldCk7CiAgICAgICAgICAgIH0KICAgICAgICAgICAgZmluYWxseSB7IGFwcC5FbmRVbmRvU2NvcGUoc2NvcGUsIGNvbW1pdCk7IH0KICAgICAgICB9CgogICAgICAgIGludGVybmFsIHN0cmluZyBNZWFzdXJlUGl0Y2goKQogICAgICAgIHsKICAgICAgICAgICAgZHluYW1pYyBwYWdlID0gQXBwLkFjdGl2ZVBhZ2U7CiAgICAgICAgICAgIExpc3Q8Q2VsbEluZm8+IGNlbGxzID0gU2VsZWN0ZWRDZWxscyhwYWdlKTsKICAgICAgICAgICAgaWYgKGNlbGxzLkNvdW50ICE9IDIpIHRocm93IG5ldyBJbnZhbGlkT3BlcmF0aW9uRXhjZXB0aW9uKCLQlNC70Y8g0LjQt9C80LXRgNC10L3QuNGPINGI0LDQs9CwINCy0YvQsdC10YDQuNGC0LUg0Y3Qu9C10LzQtdC90YLRiyDRgNC+0LLQvdC+INC00LLRg9GFINGP0YfQtdC10LoiKTsKICAgICAgICAgICAgZHluYW1pYyB0MSA9IHBhZ2UuU2hhcGVzLkl0ZW1Gcm9tSUQoY2VsbHNbMF0uQnVzVGVybWluYWxJZCk7CiAgICAgICAgICAgIGR5bmFtaWMgdDIgPSBwYWdlLlNoYXBlcy5JdGVtRnJvbUlEKGNlbGxzWzFdLkJ1c1Rlcm1pbmFsSWQpOwogICAgICAgICAgICBpZiAoY2VsbHNbMF0uQnVzSWQgIT0gY2VsbHNbMV0uQnVzSWQpIHRocm93IG5ldyBJbnZhbGlkT3BlcmF0aW9uRXhjZXB0aW9uKCLQr9GH0LXQudC60Lgg0L/QvtC00LrQu9GO0YfQtdC90Ysg0Log0YDQsNC30L3Ri9C8INGI0LjQvdCw0LwiKTsKICAgICAgICAgICAgZG91YmxlIHBpdGNoID0gTWF0aC5BYnMoR2V0TW0odDIsICJQaW5YIikgLSBHZXRNbSh0MSwgIlBpblgiKSk7CiAgICAgICAgICAgIHJldHVybiBwaXRjaC5Ub1N0cmluZygiMC4jIyMiLCBDdWx0dXJlSW5mby5JbnZhcmlhbnRDdWx0dXJlKTsKICAgICAgICB9CgogICAgICAgIGludGVybmFsIHN0cmluZyBEaXN0cmlidXRlUGl0Y2goZG91YmxlIHBpdGNoKQogICAgICAgIHsKICAgICAgICAgICAgaWYgKHBpdGNoIDw9IDApIHRocm93IG5ldyBJbnZhbGlkT3BlcmF0aW9uRXhjZXB0aW9uKCLQqNCw0LMg0LTQvtC70LbQtdC9INCx0YvRgtGMINCx0L7Qu9GM0YjQtSDQvdGD0LvRjyIpOwogICAgICAgICAgICBkeW5hbWljIGFwcCA9IEFwcDsKICAgICAgICAgICAgZHluYW1pYyBwYWdlID0gYXBwLkFjdGl2ZVBhZ2U7CiAgICAgICAgICAgIExpc3Q8Q2VsbEluZm8+IGNlbGxzID0gU2VsZWN0ZWRDZWxscyhwYWdlKS5PcmRlckJ5KGMgPT4gR2V0TW0ocGFnZS5TaGFwZXMuSXRlbUZyb21JRChjLkJ1c1Rlcm1pbmFsSWQpLCAiUGluWCIpKS5Ub0xpc3QoKTsKICAgICAgICAgICAgaWYgKGNlbGxzLkNvdW50IDwgMikgdGhyb3cgbmV3IEludmFsaWRPcGVyYXRpb25FeGNlcHRpb24oItCU0LvRjyDRgNCw0YHQv9GA0LXQtNC10LvQtdC90LjRjyDQstGL0LHQtdGA0LjRgtC1INC80LjQvdC40LzRg9C8INC00LLQtSDRj9GH0LXQudC60LgiKTsKICAgICAgICAgICAgaW50IGJ1c0lkID0gY2VsbHNbMF0uQnVzSWQ7CiAgICAgICAgICAgIGlmIChjZWxscy5BbnkoYyA9PiBjLkJ1c0lkICE9IGJ1c0lkKSkgdGhyb3cgbmV3IEludmFsaWRPcGVyYXRpb25FeGNlcHRpb24oItCS0YHQtSDQstGL0LHRgNCw0L3QvdGL0LUg0Y/Rh9C10LnQutC4INC00L7Qu9C20L3RiyDQsdGL0YLRjCDQvdCwINC+0LTQvdC+0Lkg0YjQuNC90LUiKTsKICAgICAgICAgICAgaW50IHN0YXJ0U2xvdCA9IGNlbGxzLk1pbihjID0+IGMuU2xvdCk7CiAgICAgICAgICAgIExpc3Q8VHVwbGU8Q2VsbEluZm8sIGR5bmFtaWM+PiBwbGFuID0gbmV3IExpc3Q8VHVwbGU8Q2VsbEluZm8sIGR5bmFtaWM+PigpOwogICAgICAgICAgICBIYXNoU2V0PGludD4gc2VsZWN0ZWRNZW1iZXJzID0gbmV3IEhhc2hTZXQ8aW50PihjZWxscy5TZWxlY3RNYW55KGMgPT4gYy5NZW1iZXJJZHMpKTsKICAgICAgICAgICAgZm9yIChpbnQgaSA9IDA7IGkgPCBjZWxscy5Db3VudDsgaSsrKQogICAgICAgICAgICB7CiAgICAgICAgICAgICAgICBkeW5hbWljIHRhcmdldCA9IEdldEJ1c1Rlcm1pbmFsQnlTbG90KHBhZ2UsIGJ1c0lkLCBzdGFydFNsb3QgKyBpKTsKICAgICAgICAgICAgICAgIGlmIChpID4gMCkKICAgICAgICAgICAgICAgIHsKICAgICAgICAgICAgICAgICAgICBkeW5hbWljIHByZXYgPSBHZXRCdXNUZXJtaW5hbEJ5U2xvdChwYWdlLCBidXNJZCwgc3RhcnRTbG90ICsgaSAtIDEpOwogICAgICAgICAgICAgICAgICAgIGRvdWJsZSBhY3R1YWwgPSBNYXRoLkFicyhHZXRNbSh0YXJnZXQsICJQaW5YIikgLSBHZXRNbShwcmV2LCAiUGluWCIpKTsKICAgICAgICAgICAgICAgICAgICBpZiAoTWF0aC5BYnMoYWN0dWFsIC0gcGl0Y2gpID4gMC4yNSkKICAgICAgICAgICAgICAgICAgICAgICAgdGhyb3cgbmV3IEludmFsaWRPcGVyYXRpb25FeGNlcHRpb24oU3RyaW5nLkZvcm1hdChDdWx0dXJlSW5mby5DdXJyZW50Q3VsdHVyZSwgItCo0LjQvdCwINC40LzQtdC10YIg0YjQsNCzIHswOjAuIyMjfSDQvNC8LCDQsCDQt9Cw0LTQsNC9IHsxOjAuIyMjfSDQvNC8IiwgYWN0dWFsLCBwaXRjaCkpOwogICAgICAgICAgICAgICAgfQogICAgICAgICAgICAgICAgRW5zdXJlVGVybWluYWxGcmVlKHBhZ2UsIChpbnQpdGFyZ2V0LklELCBzZWxlY3RlZE1lbWJlcnMpOwogICAgICAgICAgICAgICAgcGxhbi5BZGQoVHVwbGUuQ3JlYXRlKGNlbGxzW2ldLCB0YXJnZXQpKTsKICAgICAgICAgICAgfQoKICAgICAgICAgICAgaW50IHNjb3BlID0gKGludClhcHAuQmVnaW5VbmRvU2NvcGUoIkVuZXJnb0xvZ2ljOiDQoNCw0YHQv9GA0LXQtNC10LvQuNGC0Ywg0Y/Rh9C10LnQutC4Iik7CiAgICAgICAgICAgIGJvb2wgY29tbWl0ID0gZmFsc2U7CiAgICAgICAgICAgIHRyeQogICAgICAgICAgICB7CiAgICAgICAgICAgICAgICBmb3JlYWNoIChUdXBsZTxDZWxsSW5mbywgZHluYW1pYz4gcm93IGluIHBsYW4pCiAgICAgICAgICAgICAgICB7CiAgICAgICAgICAgICAgICAgICAgQ2VsbEluZm8gY2VsbCA9IHJvdy5JdGVtMTsKICAgICAgICAgICAgICAgICAgICBkeW5hbWljIHRhcmdldCA9IHJvdy5JdGVtMjsKICAgICAgICAgICAgICAgICAgICBpZiAoKGludCl0YXJnZXQuSUQgPT0gY2VsbC5CdXNUZXJtaW5hbElkKSBjb250aW51ZTsKICAgICAgICAgICAgICAgICAgICBkeW5hbWljIHNvdXJjZVRlcm1pbmFsID0gcGFnZS5TaGFwZXMuSXRlbUZyb21JRChjZWxsLkJ1c1Rlcm1pbmFsSWQpOwogICAgICAgICAgICAgICAgICAgIGRvdWJsZSBkeCA9IEdldE1tKHRhcmdldCwgIlBpblgiKSAtIEdldE1tKHNvdXJjZVRlcm1pbmFsLCAiUGluWCIpOwogICAgICAgICAgICAgICAgICAgIGRvdWJsZSBkeSA9IEdldE1tKHRhcmdldCwgIlBpblkiKSAtIEdldE1tKHNvdXJjZVRlcm1pbmFsLCAiUGluWSIpOwogICAgICAgICAgICAgICAgICAgIGR5bmFtaWMgYW5jaG9yID0gcGFnZS5TaGFwZXMuSXRlbUZyb21JRChjZWxsLkFuY2hvcklkKTsKICAgICAgICAgICAgICAgICAgICBEZXRhY2hFbmRwb2ludChhbmNob3IsIGNlbGwuRW5kcG9pbnQpOwogICAgICAgICAgICAgICAgICAgIFNlbGVjdElkcyhwYWdlLCBjZWxsLk1lbWJlcklkcyk7CiAgICAgICAgICAgICAgICAgICAgYXBwLkFjdGl2ZVdpbmRvdy5TZWxlY3Rpb24uTW92ZShkeCwgZHksICJtbSIpOwogICAgICAgICAgICAgICAgICAgIEdsdWVFbmRwb2ludChhbmNob3IsIGNlbGwuRW5kcG9pbnQsIHRhcmdldCwgY2VsbC5Db25uZWN0aW9uUm93KTsKICAgICAgICAgICAgICAgIH0KICAgICAgICAgICAgICAgIFNlbGVjdElkcyhwYWdlLCBjZWxscy5TZWxlY3RNYW55KGMgPT4gYy5NZW1iZXJJZHMpLkRpc3RpbmN0KCkuVG9MaXN0KCkpOwogICAgICAgICAgICAgICAgY29tbWl0ID0gdHJ1ZTsKICAgICAgICAgICAgICAgIHJldHVybiAi4pyTINCv0YfQtdC50LrQuCDRgNCw0YHQv9GA0LXQtNC10LvQtdC90Ysg0L/QviDRgNC10LDQu9GM0L3Ri9C8INGC0L7Rh9C60LDQvCDRiNC40L3Riy4g0KjQsNCzOiAiICsgcGl0Y2guVG9TdHJpbmcoIjAuIyMjIiwgQ3VsdHVyZUluZm8uQ3VycmVudEN1bHR1cmUpICsgIiDQvNC8LiI7CiAgICAgICAgICAgIH0KICAgICAgICAgICAgZmluYWxseSB7IGFwcC5FbmRVbmRvU2NvcGUoc2NvcGUsIGNvbW1pdCk7IH0KICAgICAgICB9CgogICAgICAgIGludGVybmFsIHN0cmluZyBSZXBhaXJHbHVlKGJvb2wgcHJldmlld09ubHkpCiAgICAgICAgewogICAgICAgICAgICBkeW5hbWljIGFwcCA9IEFwcDsKICAgICAgICAgICAgZHluYW1pYyBwYWdlID0gYXBwLkFjdGl2ZVBhZ2U7CiAgICAgICAgICAgIExpc3Q8aW50PiBpZHMgPSBDdXJyZW50VG9wTGV2ZWxTZWxlY3Rpb24ocGFnZSk7CiAgICAgICAgICAgIGlmIChpZHMuQ291bnQgIT0gMSkgdGhyb3cgbmV3IEludmFsaWRPcGVyYXRpb25FeGNlcHRpb24oItCU0LvRjyBSZXBhaXIgR2x1ZSDQstGL0LHQtdGA0LjRgtC1INC+0LTQuNC9INGN0LvQtdC80LXQvdGCIik7CiAgICAgICAgICAgIGR5bmFtaWMgc2hhcGUgPSBwYWdlLlNoYXBlcy5JdGVtRnJvbUlEKGlkc1swXSk7CiAgICAgICAgICAgIExpc3Q8Q29ubmVjdGlvblBvaW50SW5mbz4gcG9pbnRzID0gR2V0QWxsQ29ubmVjdGlvblBvaW50cyhwYWdlKTsKICAgICAgICAgICAgTGlzdDxUdXBsZTxzdHJpbmcsIGRvdWJsZSwgZG91YmxlPj4gZW5kcG9pbnRzID0gbmV3IExpc3Q8VHVwbGU8c3RyaW5nLCBkb3VibGUsIGRvdWJsZT4+KCk7CiAgICAgICAgICAgIGZvcmVhY2ggKHN0cmluZyBlbmRwb2ludCBpbiBuZXdbXSB7ICJiZWdpbiIsICJlbmQiIH0pCiAgICAgICAgICAgIHsKICAgICAgICAgICAgICAgIGlmICghSGFzRW5kcG9pbnQoc2hhcGUsIGVuZHBvaW50KSkgY29udGludWU7CiAgICAgICAgICAgICAgICBpZiAoVHJ5R2V0R2x1ZVRhcmdldChzaGFwZSwgZW5kcG9pbnQpICE9IG51bGwpIGNvbnRpbnVlOwogICAgICAgICAgICAgICAgZW5kcG9pbnRzLkFkZChUdXBsZS5DcmVhdGUoZW5kcG9pbnQsIEdldE1tKHNoYXBlLCBlbmRwb2ludCA9PSAiYmVnaW4iID8gIkJlZ2luWCIgOiAiRW5kWCIpLCBHZXRNbShzaGFwZSwgZW5kcG9pbnQgPT0gImJlZ2luIiA/ICJCZWdpblkiIDogIkVuZFkiKSkpOwogICAgICAgICAgICB9CiAgICAgICAgICAgIGlmIChlbmRwb2ludHMuQ291bnQgPT0gMCkgdGhyb3cgbmV3IEludmFsaWRPcGVyYXRpb25FeGNlcHRpb24oItCjINCy0YvQsdGA0LDQvdC90L7Qs9C+INGN0LvQtdC80LXQvdGC0LAg0L3QtdGCINGB0LLQvtCx0L7QtNC90L7Qs9C+IGVuZHBvaW50INC00LvRjyDRgNC10LzQvtC90YLQsCIpOwoKICAgICAgICAgICAgTGlzdDxUdXBsZTxzdHJpbmcsIENvbm5lY3Rpb25Qb2ludEluZm8+PiBjYW5kaWRhdGVzID0gbmV3IExpc3Q8VHVwbGU8c3RyaW5nLCBDb25uZWN0aW9uUG9pbnRJbmZvPj4oKTsKICAgICAgICAgICAgZm9yZWFjaCAodmFyIGVwIGluIGVuZHBvaW50cykKICAgICAgICAgICAgewogICAgICAgICAgICAgICAgZm9yZWFjaCAoQ29ubmVjdGlvblBvaW50SW5mbyBwIGluIHBvaW50cykKICAgICAgICAgICAgICAgIHsKICAgICAgICAgICAgICAgICAgICBpZiAocC5TaGFwZUlkID09IGlkc1swXSkgY29udGludWU7CiAgICAgICAgICAgICAgICAgICAgZG91YmxlIGQgPSBNYXRoLlNxcnQoTWF0aC5Qb3cocC5YbW0gLSBlcC5JdGVtMiwgMikgKyBNYXRoLlBvdyhwLlltbSAtIGVwLkl0ZW0zLCAyKSk7CiAgICAgICAgICAgICAgICAgICAgaWYgKGQgPD0gMS4wKQogICAgICAgICAgICAgICAgICAgIHsKICAgICAgICAgICAgICAgICAgICAgICAgQ29ubmVjdGlvblBvaW50SW5mbyBjb3B5ID0gbmV3IENvbm5lY3Rpb25Qb2ludEluZm8geyBTaGFwZUlkID0gcC5TaGFwZUlkLCBSb3cgPSBwLlJvdywgWG1tID0gcC5YbW0sIFltbSA9IHAuWW1tLCBEaXN0YW5jZU1tID0gZCB9OwogICAgICAgICAgICAgICAgICAgICAgICBjYW5kaWRhdGVzLkFkZChUdXBsZS5DcmVhdGUoZXAuSXRlbTEsIGNvcHkpKTsKICAgICAgICAgICAgICAgICAgICB9CiAgICAgICAgICAgICAgICB9CiAgICAgICAgICAgIH0KICAgICAgICAgICAgY2FuZGlkYXRlcyA9IGNhbmRpZGF0ZXMuT3JkZXJCeShjID0+IGMuSXRlbTIuRGlzdGFuY2VNbSkuVG9MaXN0KCk7CiAgICAgICAgICAgIGlmIChjYW5kaWRhdGVzLkNvdW50ID09IDApIHRocm93IG5ldyBJbnZhbGlkT3BlcmF0aW9uRXhjZXB0aW9uKCLQoNGP0LTQvtC8INC90LUg0L3QsNC50LTQtdC90L4g0L3QuCDQvtC00L3QvtC5INGA0LXQsNC70YzQvdC+0LkgY29ubmVjdGlvbiBwb2ludCAo4omkIDEg0LzQvCkiKTsKICAgICAgICAgICAgaWYgKGNhbmRpZGF0ZXMuQ291bnQgPiAxICYmIE1hdGguQWJzKGNhbmRpZGF0ZXNbMF0uSXRlbTIuRGlzdGFuY2VNbSAtIGNhbmRpZGF0ZXNbMV0uSXRlbTIuRGlzdGFuY2VNbSkgPCAwLjA1KQogICAgICAgICAgICAgICAgdGhyb3cgbmV3IEludmFsaWRPcGVyYXRpb25FeGNlcHRpb24oItCd0LDQudC00LXQvdC+INC90LXRgdC60L7Qu9GM0LrQviDQvtC00LjQvdCw0LrQvtCy0L4g0LHQu9C40LfQutC40YUgY29ubmVjdGlvbiBwb2ludCDigJQg0LDQstGC0L7QvNCw0YLQuNGH0LXRgdC60LjQuSDRgNC10LzQvtC90YIg0LfQsNC/0YDQtdGJ0ZHQvSIpOwogICAgICAgICAgICB2YXIgYmVzdCA9IGNhbmRpZGF0ZXNbMF07CiAgICAgICAgICAgIHN0cmluZyBkZXNjcmlwdGlvbiA9IFN0cmluZy5Gb3JtYXQoQ3VsdHVyZUluZm8uQ3VycmVudEN1bHR1cmUsICJ7MH06IHNoYXBlIHsxfSwgQ29ubmVjdGlvbnMuezJ9LCDRgNCw0YHRgdGC0L7Rj9C90LjQtSB7MzowLiMjI30g0LzQvCIsIGJlc3QuSXRlbTEsIGJlc3QuSXRlbTIuU2hhcGVJZCwgYmVzdC5JdGVtMi5Sb3csIGJlc3QuSXRlbTIuRGlzdGFuY2VNbSk7CiAgICAgICAgICAgIGlmIChwcmV2aWV3T25seSkgcmV0dXJuICLQmtCw0L3QtNC40LTQsNGCIFJlcGFpciBHbHVlOiAiICsgZGVzY3JpcHRpb247CiAgICAgICAgICAgIERpYWxvZ1Jlc3VsdCBhbnN3ZXIgPSBNZXNzYWdlQm94LlNob3coItCd0LDQudC00LXQvSDQutCw0L3QtNC40LTQsNGCOlxuXG4iICsgZGVzY3JpcHRpb24gKyAiXG5cbtCY0YHQv9GA0LDQstC40YLRjCBHbHVlPyIsICJFbmVyZ29Mb2dpYyDigJQgUmVwYWlyIEdsdWUiLCBNZXNzYWdlQm94QnV0dG9ucy5ZZXNObywgTWVzc2FnZUJveEljb24uUXVlc3Rpb24pOwogICAgICAgICAgICBpZiAoYW5zd2VyICE9IERpYWxvZ1Jlc3VsdC5ZZXMpIHJldHVybiAiUmVwYWlyIEdsdWUg0L7RgtC80LXQvdGR0L0g0L/QvtC70YzQt9C+0LLQsNGC0LXQu9C10LwuIjsKICAgICAgICAgICAgaW50IHNjb3BlID0gKGludClhcHAuQmVnaW5VbmRvU2NvcGUoIkVuZXJnb0xvZ2ljOiBSZXBhaXIgR2x1ZSIpOwogICAgICAgICAgICBib29sIGNvbW1pdCA9IGZhbHNlOwogICAgICAgICAgICB0cnkKICAgICAgICAgICAgewogICAgICAgICAgICAgICAgR2x1ZUVuZHBvaW50KHNoYXBlLCBiZXN0Lkl0ZW0xLCBwYWdlLlNoYXBlcy5JdGVtRnJvbUlEKGJlc3QuSXRlbTIuU2hhcGVJZCksIGJlc3QuSXRlbTIuUm93KTsKICAgICAgICAgICAgICAgIFZlcmlmeUdsdWUoc2hhcGUsIGJlc3QuSXRlbTEsIGJlc3QuSXRlbTIuU2hhcGVJZCwgYmVzdC5JdGVtMi5Sb3cpOwogICAgICAgICAgICAgICAgY29tbWl0ID0gdHJ1ZTsKICAgICAgICAgICAgICAgIHJldHVybiAi4pyTIEdsdWUg0LLQvtGB0YHRgtCw0L3QvtCy0LvQtdC9LiAiICsgZGVzY3JpcHRpb247CiAgICAgICAgICAgIH0KICAgICAgICAgICAgZmluYWxseSB7IGFwcC5FbmRVbmRvU2NvcGUoc2NvcGUsIGNvbW1pdCk7IH0KICAgICAgICB9CgogICAgICAgIGludGVybmFsIHN0cmluZyBEb2N0b3IoKQogICAgICAgIHsKICAgICAgICAgICAgZHluYW1pYyBwYWdlID0gQXBwLkFjdGl2ZVBhZ2U7CiAgICAgICAgICAgIExpc3Q8Q29ubmVjdGlvblBvaW50SW5mbz4gcG9pbnRzID0gR2V0QWxsQ29ubmVjdGlvblBvaW50cyhwYWdlKTsKICAgICAgICAgICAgTGlzdDxpbnQ+IGJhZCA9IG5ldyBMaXN0PGludD4oKTsKICAgICAgICAgICAgTGlzdDxzdHJpbmc+IG1lc3NhZ2VzID0gbmV3IExpc3Q8c3RyaW5nPigpOwogICAgICAgICAgICBmb3IgKGludCBpID0gMTsgaSA8PSAoaW50KXBhZ2UuU2hhcGVzLkNvdW50OyBpKyspCiAgICAgICAgICAgIHsKICAgICAgICAgICAgICAgIGR5bmFtaWMgc2hhcGUgPSBwYWdlLlNoYXBlcy5JdGVtKGkpOwogICAgICAgICAgICAgICAgaW50IGlkID0gKGludClzaGFwZS5JRDsKICAgICAgICAgICAgICAgIGZvcmVhY2ggKHN0cmluZyBlcCBpbiBuZXdbXSB7ICJiZWdpbiIsICJlbmQiIH0pCiAgICAgICAgICAgICAgICB7CiAgICAgICAgICAgICAgICAgICAgaWYgKCFIYXNFbmRwb2ludChzaGFwZSwgZXApIHx8IFRyeUdldEdsdWVUYXJnZXQoc2hhcGUsIGVwKSAhPSBudWxsKSBjb250aW51ZTsKICAgICAgICAgICAgICAgICAgICBkb3VibGUgeCA9IEdldE1tKHNoYXBlLCBlcCA9PSAiYmVnaW4iID8gIkJlZ2luWCIgOiAiRW5kWCIpOwogICAgICAgICAgICAgICAgICAgIGRvdWJsZSB5ID0gR2V0TW0oc2hhcGUsIGVwID09ICJiZWdpbiIgPyAiQmVnaW5ZIiA6ICJFbmRZIik7CiAgICAgICAgICAgICAgICAgICAgdmFyIG5lYXIgPSBwb2ludHMuV2hlcmUocCA9PiBwLlNoYXBlSWQgIT0gaWQgJiYgTWF0aC5TcXJ0KE1hdGguUG93KHAuWG1tIC0geCwgMikgKyBNYXRoLlBvdyhwLlltbSAtIHksIDIpKSA8PSAwLjgpLlRvTGlzdCgpOwogICAgICAgICAgICAgICAgICAgIGlmIChuZWFyLkNvdW50ID4gMCkKICAgICAgICAgICAgICAgICAgICB7CiAgICAgICAgICAgICAgICAgICAgICAgIGJhZC5BZGQoaWQpOwogICAgICAgICAgICAgICAgICAgICAgICBtZXNzYWdlcy5BZGQoIlNoYXBlICIgKyBpZCArICIgIiArIGVwICsgIjog0LLQuNC30YPQsNC70YzQvdC+INC60LDRgdCw0LXRgtGB0Y8gY29ubmVjdGlvbiBwb2ludCwg0L3QviBHbHVlINC+0YLRgdGD0YLRgdGC0LLRg9C10YIiKTsKICAgICAgICAgICAgICAgICAgICB9CiAgICAgICAgICAgICAgICB9CiAgICAgICAgICAgIH0KICAgICAgICAgICAgaWYgKGJhZC5Db3VudCA+IDApIFNlbGVjdElkcyhwYWdlLCBiYWQuRGlzdGluY3QoKS5Ub0xpc3QoKSk7CiAgICAgICAgICAgIGlmIChtZXNzYWdlcy5Db3VudCA9PSAwKSByZXR1cm4gIuKckyBTY2hlbWUgRG9jdG9yOiDRj9Cy0L3Ri9GFIHN0cnVjdHVyYWwt0L/RgNC+0LHQu9C10LwgR2x1ZSDQvdC1INC90LDQudC00LXQvdC+LiI7CiAgICAgICAgICAgIHJldHVybiAi4pqgIFNjaGVtZSBEb2N0b3I6INC90LDQudC00LXQvdC+INC/0YDQvtCx0LvQtdC8OiAiICsgbWVzc2FnZXMuQ291bnQgKyAiLiDQn9GA0L7QsdC70LXQvNC90YvQtSDRjdC70LXQvNC10L3RgtGLINCy0YvQtNC10LvQtdC90YsuXHJcbiIgKyBTdHJpbmcuSm9pbigiXHJcbiIsIG1lc3NhZ2VzLlRha2UoOCkuVG9BcnJheSgpKTsKICAgICAgICB9CgogICAgICAgIHByaXZhdGUgTGlzdDxDZWxsSW5mbz4gU2VsZWN0ZWRDZWxscyhkeW5hbWljIHBhZ2UpCiAgICAgICAgewogICAgICAgICAgICBMaXN0PGludD4gc2VsZWN0aW9uID0gQ3VycmVudFRvcExldmVsU2VsZWN0aW9uKHBhZ2UpOwogICAgICAgICAgICBEaWN0aW9uYXJ5PGludCwgQ2VsbEluZm8+IHVuaXF1ZSA9IG5ldyBEaWN0aW9uYXJ5PGludCwgQ2VsbEluZm8+KCk7CiAgICAgICAgICAgIGZvcmVhY2ggKGludCBpZCBpbiBzZWxlY3Rpb24pCiAgICAgICAgICAgIHsKICAgICAgICAgICAgICAgIENlbGxJbmZvIGNlbGwgPSBEaXNjb3ZlckNlbGwocGFnZSwgaWQpOwogICAgICAgICAgICAgICAgaWYgKCF1bmlxdWUuQ29udGFpbnNLZXkoY2VsbC5BbmNob3JJZCkpIHVuaXF1ZS5BZGQoY2VsbC5BbmNob3JJZCwgY2VsbCk7CiAgICAgICAgICAgIH0KICAgICAgICAgICAgcmV0dXJuIHVuaXF1ZS5WYWx1ZXMuVG9MaXN0KCk7CiAgICAgICAgfQoKICAgICAgICBwcml2YXRlIENlbGxJbmZvIERpc2NvdmVyQ2VsbEZyb21TZWxlY3Rpb24oZHluYW1pYyBwYWdlKQogICAgICAgIHsKICAgICAgICAgICAgTGlzdDxpbnQ+IHNlbGVjdGlvbiA9IEN1cnJlbnRUb3BMZXZlbFNlbGVjdGlvbihwYWdlKTsKICAgICAgICAgICAgRXhjZXB0aW9uIGxhc3QgPSBudWxsOwogICAgICAgICAgICBmb3JlYWNoIChpbnQgaWQgaW4gc2VsZWN0aW9uKQogICAgICAgICAgICB7CiAgICAgICAgICAgICAgICB0cnkgeyByZXR1cm4gRGlzY292ZXJDZWxsKHBhZ2UsIGlkKTsgfQogICAgICAgICAgICAgICAgY2F0Y2ggKEV4Y2VwdGlvbiBleCkgeyBsYXN0ID0gZXg7IH0KICAgICAgICAgICAgfQogICAgICAgICAgICB0aHJvdyBuZXcgSW52YWxpZE9wZXJhdGlvbkV4Y2VwdGlvbigi0J3QtSDRg9C00LDQu9C+0YHRjCDQvtC/0YDQtdC00LXQu9C40YLRjCDRj9GH0LXQudC60YMg0L/QviDQstGL0LTQtdC70LXQvdC40Y4uINCS0YvQtNC10LvQuNGC0LUg0LvRjtCx0L7QuSDRjdC70LXQutGC0YDQuNGH0LXRgdC60LjQuSDRjdC70LXQvNC10L3RgiDQvdGD0LbQvdC+0Lkg0Y/Rh9C10LnQutC4LiIsIGxhc3QpOwogICAgICAgIH0KCiAgICAgICAgcHJpdmF0ZSBDZWxsSW5mbyBEaXNjb3ZlckNlbGwoZHluYW1pYyBwYWdlLCBpbnQgc2VsZWN0ZWRJZCkKICAgICAgICB7CiAgICAgICAgICAgIERpY3Rpb25hcnk8aW50LCBpbnQ+IGNoaWxkUGFyZW50ID0gQnVpbGRDaGlsZFBhcmVudE1hcChwYWdlKTsKICAgICAgICAgICAgSGFzaFNldDxpbnQ+IHRvcCA9IFRvcExldmVsSWRzKHBhZ2UpOwogICAgICAgICAgICBEaWN0aW9uYXJ5PGludCwgSGFzaFNldDxpbnQ+PiBncmFwaCA9IG5ldyBEaWN0aW9uYXJ5PGludCwgSGFzaFNldDxpbnQ+PigpOwogICAgICAgICAgICBmb3JlYWNoIChpbnQgaWQgaW4gdG9wKSBncmFwaFtpZF0gPSBuZXcgSGFzaFNldDxpbnQ+KCk7CiAgICAgICAgICAgIGZvcmVhY2ggKGludCBpZCBpbiB0b3ApCiAgICAgICAgICAgIHsKICAgICAgICAgICAgICAgIGR5bmFtaWMgc2hhcGUgPSBwYWdlLlNoYXBlcy5JdGVtRnJvbUlEKGlkKTsKICAgICAgICAgICAgICAgIGZvcmVhY2ggKHN0cmluZyBlcCBpbiBuZXdbXSB7ICJiZWdpbiIsICJlbmQiIH0pCiAgICAgICAgICAgICAgICB7CiAgICAgICAgICAgICAgICAgICAgR2x1ZVRhcmdldCB0YXJnZXQgPSBUcnlHZXRHbHVlVGFyZ2V0KHNoYXBlLCBlcCk7CiAgICAgICAgICAgICAgICAgICAgaWYgKHRhcmdldCAhPSBudWxsICYmIHRvcC5Db250YWlucyh0YXJnZXQuVGFyZ2V0SWQpKQogICAgICAgICAgICAgICAgICAgIHsKICAgICAgICAgICAgICAgICAgICAgICAgZ3JhcGhbaWRdLkFkZCh0YXJnZXQuVGFyZ2V0SWQpOwogICAgICAgICAgICAgICAgICAgICAgICBncmFwaFt0YXJnZXQuVGFyZ2V0SWRdLkFkZChpZCk7CiAgICAgICAgICAgICAgICAgICAgfQogICAgICAgICAgICAgICAgfQogICAgICAgICAgICB9CiAgICAgICAgICAgIGlmICghdG9wLkNvbnRhaW5zKHNlbGVjdGVkSWQpKSB0aHJvdyBuZXcgSW52YWxpZE9wZXJhdGlvbkV4Y2VwdGlvbigi0JLRi9Cx0YDQsNC90L3Ri9C5INC+0LHRitC10LrRgiDQvdC1INGP0LLQu9GP0LXRgtGB0Y8gdG9wLWxldmVsINGN0LvQtdC80LXQvdGC0L7QvCDRgdGF0LXQvNGLIik7CiAgICAgICAgICAgIEhhc2hTZXQ8aW50PiBjb3JlID0gbmV3IEhhc2hTZXQ8aW50PigpOwogICAgICAgICAgICBTdGFjazxpbnQ+IHN0YWNrID0gbmV3IFN0YWNrPGludD4oKTsKICAgICAgICAgICAgc3RhY2suUHVzaChzZWxlY3RlZElkKTsKICAgICAgICAgICAgd2hpbGUgKHN0YWNrLkNvdW50ID4gMCkKICAgICAgICAgICAgewogICAgICAgICAgICAgICAgaW50IGN1ciA9IHN0YWNrLlBvcCgpOwogICAgICAgICAgICAgICAgaWYgKCFjb3JlLkFkZChjdXIpKSBjb250aW51ZTsKICAgICAgICAgICAgICAgIGZvcmVhY2ggKGludCBuIGluIGdyYXBoW2N1cl0pIGlmICghY29yZS5Db250YWlucyhuKSkgc3RhY2suUHVzaChuKTsKICAgICAgICAgICAgfQoKICAgICAgICAgICAgTGlzdDxUdXBsZTxpbnQsIEdsdWVUYXJnZXQsIGludD4+IGFuY2hvcnMgPSBuZXcgTGlzdDxUdXBsZTxpbnQsIEdsdWVUYXJnZXQsIGludD4+KCk7CiAgICAgICAgICAgIGZvcmVhY2ggKGludCBpZCBpbiBjb3JlKQogICAgICAgICAgICB7CiAgICAgICAgICAgICAgICBkeW5hbWljIHNoYXBlID0gcGFnZS5TaGFwZXMuSXRlbUZyb21JRChpZCk7CiAgICAgICAgICAgICAgICBmb3JlYWNoIChzdHJpbmcgZXAgaW4gbmV3W10geyAiYmVnaW4iLCAiZW5kIiB9KQogICAgICAgICAgICAgICAgewogICAgICAgICAgICAgICAgICAgIEdsdWVUYXJnZXQgdGFyZ2V0ID0gVHJ5R2V0R2x1ZVRhcmdldChzaGFwZSwgZXApOwogICAgICAgICAgICAgICAgICAgIGlmICh0YXJnZXQgIT0gbnVsbCAmJiBjaGlsZFBhcmVudC5Db250YWluc0tleSh0YXJnZXQuVGFyZ2V0SWQpKQogICAgICAgICAgICAgICAgICAgICAgICBhbmNob3JzLkFkZChUdXBsZS5DcmVhdGUoaWQsIHRhcmdldCwgY2hpbGRQYXJlbnRbdGFyZ2V0LlRhcmdldElkXSkpOwogICAgICAgICAgICAgICAgfQogICAgICAgICAgICB9CiAgICAgICAgICAgIGlmIChhbmNob3JzLkNvdW50ICE9IDEpIHRocm93IG5ldyBJbnZhbGlkT3BlcmF0aW9uRXhjZXB0aW9uKCLQoyDRj9GH0LXQudC60Lgg0LTQvtC70LbQtdC9INCx0YvRgtGMINGA0L7QstC90L4g0L7QtNC40L0g0LLQvdC10YjQvdC40LkgR2x1ZSDQuiDRiNC40L3QtTsg0L3QsNC50LTQtdC90L46ICIgKyBhbmNob3JzLkNvdW50KTsKICAgICAgICAgICAgdmFyIGFuY2hvciA9IGFuY2hvcnNbMF07CiAgICAgICAgICAgIGR5bmFtaWMgdGVybWluYWwgPSBwYWdlLlNoYXBlcy5JdGVtRnJvbUlEKGFuY2hvci5JdGVtMi5UYXJnZXRJZCk7CiAgICAgICAgICAgIGludCBzbG90ID0gR2V0U2xvdCh0ZXJtaW5hbCk7CiAgICAgICAgICAgIGRvdWJsZSBhbmNob3JYID0gR2V0TW0ocGFnZS5TaGFwZXMuSXRlbUZyb21JRChhbmNob3IuSXRlbTEpLCAiUGluWCIpOwogICAgICAgICAgICBkb3VibGUgbWluWSA9IGNvcmUuTWluKGlkID0+IEdldE1tKHBhZ2UuU2hhcGVzLkl0ZW1Gcm9tSUQoaWQpLCAiUGluWSIpKSAtIDEwLjA7CiAgICAgICAgICAgIGRvdWJsZSBtYXhZID0gY29yZS5NYXgoaWQgPT4gR2V0TW0ocGFnZS5TaGFwZXMuSXRlbUZyb21JRChpZCksICJQaW5ZIikpICsgMTAuMDsKICAgICAgICAgICAgZG91YmxlIHBpdGNoID0gTmVhcmVzdEJ1c1BpdGNoKHBhZ2UsIGFuY2hvci5JdGVtMywgYW5jaG9yLkl0ZW0yLlRhcmdldElkKTsKICAgICAgICAgICAgZG91YmxlIGhhbGYgPSBwaXRjaCAvIDIuMDsKICAgICAgICAgICAgTGlzdDxpbnQ+IG1lbWJlcnMgPSBuZXcgTGlzdDxpbnQ+KGNvcmUpOwogICAgICAgICAgICBmb3JlYWNoIChpbnQgaWQgaW4gdG9wKQogICAgICAgICAgICB7CiAgICAgICAgICAgICAgICBpZiAoaWQgPT0gYW5jaG9yLkl0ZW0zKSBjb250aW51ZTsKICAgICAgICAgICAgICAgIGR5bmFtaWMgc2hhcGUgPSBwYWdlLlNoYXBlcy5JdGVtRnJvbUlEKGlkKTsKICAgICAgICAgICAgICAgIGRvdWJsZSB4ID0gR2V0TW0oc2hhcGUsICJQaW5YIik7CiAgICAgICAgICAgICAgICBkb3VibGUgeSA9IEdldE1tKHNoYXBlLCAiUGluWSIpOwogICAgICAgICAgICAgICAgZG91YmxlIGRpc3RhbmNlID0gTWF0aC5BYnMoeCAtIGFuY2hvclgpOwogICAgICAgICAgICAgICAgaWYgKE1hdGguQWJzKGRpc3RhbmNlIC0gaGFsZikgPD0gMC4wMSAmJiB5ID49IG1pblkgJiYgeSA8PSBtYXhZKQogICAgICAgICAgICAgICAgICAgIHRocm93IG5ldyBJbnZhbGlkT3BlcmF0aW9uRXhjZXB0aW9uKCLQndC10L7QtNC90L7Qt9C90LDRh9C90LDRjyDQs9GA0LDQvdC40YbQsCDRj9GH0LXQudC60Lg6IHNoYXBlICIgKyBpZCArICIg0LvQtdC20LjRgiDRgNC+0LLQvdC+INC80LXQttC00YMg0YHQvtGB0LXQtNC90LjQvNC4INGP0YfQtdC50LrQsNC80LgiKTsKICAgICAgICAgICAgICAgIGlmIChkaXN0YW5jZSA8IGhhbGYgLSAwLjAxICYmIHkgPj0gbWluWSAmJiB5IDw9IG1heFkgJiYgIW1lbWJlcnMuQ29udGFpbnMoaWQpKSBtZW1iZXJzLkFkZChpZCk7CiAgICAgICAgICAgIH0KICAgICAgICAgICAgbWVtYmVycy5Tb3J0KCk7CiAgICAgICAgICAgIHJldHVybiBuZXcgQ2VsbEluZm8gewogICAgICAgICAgICAgICAgQW5jaG9ySWQgPSBhbmNob3IuSXRlbTEsCiAgICAgICAgICAgICAgICBCdXNJZCA9IGFuY2hvci5JdGVtMywKICAgICAgICAgICAgICAgIEJ1c1Rlcm1pbmFsSWQgPSBhbmNob3IuSXRlbTIuVGFyZ2V0SWQsCiAgICAgICAgICAgICAgICBTbG90ID0gc2xvdCwKICAgICAgICAgICAgICAgIENvbm5lY3Rpb25Sb3cgPSBhbmNob3IuSXRlbTIuUm93LAogICAgICAgICAgICAgICAgRW5kcG9pbnQgPSBhbmNob3IuSXRlbTIuRW5kcG9pbnQsCiAgICAgICAgICAgICAgICBDb3JlSWRzID0gY29yZS5PcmRlckJ5KHggPT4geCkuVG9MaXN0KCksCiAgICAgICAgICAgICAgICBNZW1iZXJJZHMgPSBtZW1iZXJzCiAgICAgICAgICAgIH07CiAgICAgICAgfQoKICAgICAgICBwcml2YXRlIGRvdWJsZSBOZWFyZXN0QnVzUGl0Y2goZHluYW1pYyBwYWdlLCBpbnQgYnVzSWQsIGludCBzb3VyY2VUZXJtaW5hbElkKQogICAgICAgIHsKICAgICAgICAgICAgZHluYW1pYyBidXMgPSBwYWdlLlNoYXBlcy5JdGVtRnJvbUlEKGJ1c0lkKTsKICAgICAgICAgICAgZHluYW1pYyBzb3VyY2UgPSBwYWdlLlNoYXBlcy5JdGVtRnJvbUlEKHNvdXJjZVRlcm1pbmFsSWQpOwogICAgICAgICAgICBkb3VibGUgc3ggPSBHZXRNbShzb3VyY2UsICJQaW5YIik7CiAgICAgICAgICAgIExpc3Q8ZG91YmxlPiBkaXN0YW5jZXMgPSBuZXcgTGlzdDxkb3VibGU+KCk7CiAgICAgICAgICAgIGZvciAoaW50IGkgPSAxOyBpIDw9IChpbnQpYnVzLlNoYXBlcy5Db3VudDsgaSsrKQogICAgICAgICAgICB7CiAgICAgICAgICAgICAgICBkeW5hbWljIGNoaWxkID0gYnVzLlNoYXBlcy5JdGVtKGkpOwogICAgICAgICAgICAgICAgaWYgKChpbnQpY2hpbGQuSUQgPT0gc291cmNlVGVybWluYWxJZCkgY29udGludWU7CiAgICAgICAgICAgICAgICB0cnkgeyBHZXRTbG90KGNoaWxkKTsgfQogICAgICAgICAgICAgICAgY2F0Y2ggeyBjb250aW51ZTsgfQogICAgICAgICAgICAgICAgZG91YmxlIGQgPSBNYXRoLkFicyhHZXRNbShjaGlsZCwgIlBpblgiKSAtIHN4KTsKICAgICAgICAgICAgICAgIGlmIChkID4gMC4wMSkgZGlzdGFuY2VzLkFkZChkKTsKICAgICAgICAgICAgfQogICAgICAgICAgICBpZiAoZGlzdGFuY2VzLkNvdW50ID09IDApIHRocm93IG5ldyBJbnZhbGlkT3BlcmF0aW9uRXhjZXB0aW9uKCLQndC1INGD0LTQsNC70L7RgdGMINC+0L/RgNC10LTQtdC70LjRgtGMINGI0LDQsyDRgtC+0YfQtdC6INGI0LjQvdGLIik7CiAgICAgICAgICAgIHJldHVybiBkaXN0YW5jZXMuTWluKCk7CiAgICAgICAgfQoKICAgICAgICBwcml2YXRlIGR5bmFtaWMgR2V0QnVzVGVybWluYWxCeVNsb3QoZHluYW1pYyBwYWdlLCBpbnQgYnVzSWQsIGludCBzbG90KQogICAgICAgIHsKICAgICAgICAgICAgaWYgKHNsb3QgPD0gMCkgdGhyb3cgbmV3IEludmFsaWRPcGVyYXRpb25FeGNlcHRpb24oItCd0LAg0YjQuNC90LUg0L3QtdGCINC80LXRgdGC0LAgIiArIHNsb3QpOwogICAgICAgICAgICBkeW5hbWljIGJ1cyA9IHBhZ2UuU2hhcGVzLkl0ZW1Gcm9tSUQoYnVzSWQpOwogICAgICAgICAgICBMaXN0PGR5bmFtaWM+IGZvdW5kID0gbmV3IExpc3Q8ZHluYW1pYz4oKTsKICAgICAgICAgICAgZm9yIChpbnQgaSA9IDE7IGkgPD0gKGludClidXMuU2hhcGVzLkNvdW50OyBpKyspCiAgICAgICAgICAgIHsKICAgICAgICAgICAgICAgIGR5bmFtaWMgY2hpbGQgPSBidXMuU2hhcGVzLkl0ZW0oaSk7CiAgICAgICAgICAgICAgICB0cnkgeyBpZiAoR2V0U2xvdChjaGlsZCkgPT0gc2xvdCkgZm91bmQuQWRkKGNoaWxkKTsgfQogICAgICAgICAgICAgICAgY2F0Y2ggeyB9CiAgICAgICAgICAgIH0KICAgICAgICAgICAgaWYgKGZvdW5kLkNvdW50ICE9IDEpIHRocm93IG5ldyBJbnZhbGlkT3BlcmF0aW9uRXhjZXB0aW9uKCLQnNC10YHRgtC+INGI0LjQvdGLICIgKyBzbG90ICsgIiDQvdC1INC90LDQudC00LXQvdC+INC40LvQuCDQvdC10L7QtNC90L7Qt9C90LDRh9C90L4iKTsKICAgICAgICAgICAgcmV0dXJuIGZvdW5kWzBdOwogICAgICAgIH0KCiAgICAgICAgcHJpdmF0ZSBpbnQgR2V0U2xvdChkeW5hbWljIHRlcm1pbmFsKQogICAgICAgIHsKICAgICAgICAgICAgdHJ5CiAgICAgICAgICAgIHsKICAgICAgICAgICAgICAgIGlmICgoYm9vbCl0ZXJtaW5hbC5DZWxsRXhpc3RzVSgiVXNlci5zbG90IiwgMCkpCiAgICAgICAgICAgICAgICAgICAgcmV0dXJuIENvbnZlcnQuVG9JbnQzMihNYXRoLlJvdW5kKChkb3VibGUpdGVybWluYWwuQ2VsbHNVKCJVc2VyLnNsb3QiKS5SZXN1bHRJVSkpOwogICAgICAgICAgICB9CiAgICAgICAgICAgIGNhdGNoIHsgfQogICAgICAgICAgICBpbnQgc2xvdDsKICAgICAgICAgICAgaWYgKEludDMyLlRyeVBhcnNlKFNhZmVUZXh0KHRlcm1pbmFsKS5UcmltKCksIE51bWJlclN0eWxlcy5JbnRlZ2VyLCBDdWx0dXJlSW5mby5JbnZhcmlhbnRDdWx0dXJlLCBvdXQgc2xvdCkgJiYgc2xvdCA+IDApIHJldHVybiBzbG90OwogICAgICAgICAgICB0aHJvdyBuZXcgSW52YWxpZE9wZXJhdGlvbkV4Y2VwdGlvbigi0KMgY29ubmVjdGlvbiBwb2ludCDRiNC40L3RiyDQvtGC0YHRg9GC0YHRgtCy0YPQtdGCINC90L7QvNC10YAg0LzQtdGB0YLQsCIpOwogICAgICAgIH0KCiAgICAgICAgcHJpdmF0ZSB2b2lkIEVuc3VyZVRlcm1pbmFsRnJlZShkeW5hbWljIHBhZ2UsIGludCB0ZXJtaW5hbElkLCBIYXNoU2V0PGludD4gYWxsb3dlZE93bmVycykKICAgICAgICB7CiAgICAgICAgICAgIEhhc2hTZXQ8aW50PiB0b3AgPSBUb3BMZXZlbElkcyhwYWdlKTsKICAgICAgICAgICAgZm9yZWFjaCAoaW50IGlkIGluIHRvcCkKICAgICAgICAgICAgewogICAgICAgICAgICAgICAgaWYgKGFsbG93ZWRPd25lcnMuQ29udGFpbnMoaWQpKSBjb250aW51ZTsKICAgICAgICAgICAgICAgIGR5bmFtaWMgc2hhcGUgPSBwYWdlLlNoYXBlcy5JdGVtRnJvbUlEKGlkKTsKICAgICAgICAgICAgICAgIGZvcmVhY2ggKHN0cmluZyBlcCBpbiBuZXdbXSB7ICJiZWdpbiIsICJlbmQiIH0pCiAgICAgICAgICAgICAgICB7CiAgICAgICAgICAgICAgICAgICAgR2x1ZVRhcmdldCB0ID0gVHJ5R2V0R2x1ZVRhcmdldChzaGFwZSwgZXApOwogICAgICAgICAgICAgICAgICAgIGlmICh0ICE9IG51bGwgJiYgdC5UYXJnZXRJZCA9PSB0ZXJtaW5hbElkKQogICAgICAgICAgICAgICAgICAgICAgICB0aHJvdyBuZXcgSW52YWxpZE9wZXJhdGlvbkV4Y2VwdGlvbigi0KbQtdC70LXQstC+0LUg0LzQtdGB0YLQviDRiNC40L3RiyDRg9C20LUg0LfQsNC90Y/RgtC+IHNoYXBlICIgKyBpZCk7CiAgICAgICAgICAgICAgICB9CiAgICAgICAgICAgIH0KICAgICAgICB9CgogICAgICAgIHByaXZhdGUgdm9pZCBFbnN1cmVOb0V4dGVybmFsR2x1ZShkeW5hbWljIHBhZ2UsIExpc3Q8aW50PiBpZHMpCiAgICAgICAgewogICAgICAgICAgICBIYXNoU2V0PGludD4gc2VsZWN0ZWQgPSBuZXcgSGFzaFNldDxpbnQ+KGlkcyk7CiAgICAgICAgICAgIERpY3Rpb25hcnk8aW50LCBpbnQ+IGNoaWxkUGFyZW50ID0gQnVpbGRDaGlsZFBhcmVudE1hcChwYWdlKTsKICAgICAgICAgICAgZm9yZWFjaCAoaW50IGlkIGluIGlkcykKICAgICAgICAgICAgewogICAgICAgICAgICAgICAgZHluYW1pYyBzaGFwZSA9IHBhZ2UuU2hhcGVzLkl0ZW1Gcm9tSUQoaWQpOwogICAgICAgICAgICAgICAgZm9yZWFjaCAoc3RyaW5nIGVwIGluIG5ld1tdIHsgImJlZ2luIiwgImVuZCIgfSkKICAgICAgICAgICAgICAgIHsKICAgICAgICAgICAgICAgICAgICBHbHVlVGFyZ2V0IHRhcmdldCA9IFRyeUdldEdsdWVUYXJnZXQoc2hhcGUsIGVwKTsKICAgICAgICAgICAgICAgICAgICBpZiAodGFyZ2V0ID09IG51bGwpIGNvbnRpbnVlOwogICAgICAgICAgICAgICAgICAgIGludCBvd25lciA9IGNoaWxkUGFyZW50LkNvbnRhaW5zS2V5KHRhcmdldC5UYXJnZXRJZCkgPyBjaGlsZFBhcmVudFt0YXJnZXQuVGFyZ2V0SWRdIDogdGFyZ2V0LlRhcmdldElkOwogICAgICAgICAgICAgICAgICAgIGlmICghc2VsZWN0ZWQuQ29udGFpbnMob3duZXIpKQogICAgICAgICAgICAgICAgICAgICAgICB0aHJvdyBuZXcgSW52YWxpZE9wZXJhdGlvbkV4Y2VwdGlvbigi0JLRi9C00LXQu9C10L3QuNC1INC40LzQtdC10YIg0LLQvdC10YjQvdGO0Y4g0Y3Qu9C10LrRgtGA0LjRh9C10YHQutGD0Y4g0YHQstGP0LfRjC4g0JjRgdC/0L7Qu9GM0LfRg9C50YLQtSDQv9GA0LXQtNC80LXRgtC90YPRjiDQutC+0LzQsNC90LTRgyDRj9GH0LXQudC60LgsINGH0YLQvtCx0Ysg0L3QtSDQv9C+0YDQstCw0YLRjCBHbHVlLiIpOwogICAgICAgICAgICAgICAgfQogICAgICAgICAgICB9CiAgICAgICAgfQoKICAgICAgICBwcml2YXRlIERpY3Rpb25hcnk8aW50LCBpbnQ+IEJ1aWxkQ2hpbGRQYXJlbnRNYXAoZHluYW1pYyBwYWdlKQogICAgICAgIHsKICAgICAgICAgICAgRGljdGlvbmFyeTxpbnQsIGludD4gbWFwID0gbmV3IERpY3Rpb25hcnk8aW50LCBpbnQ+KCk7CiAgICAgICAgICAgIGZvciAoaW50IGkgPSAxOyBpIDw9IChpbnQpcGFnZS5TaGFwZXMuQ291bnQ7IGkrKykKICAgICAgICAgICAgewogICAgICAgICAgICAgICAgZHluYW1pYyB0b3AgPSBwYWdlLlNoYXBlcy5JdGVtKGkpOwogICAgICAgICAgICAgICAgdHJ5CiAgICAgICAgICAgICAgICB7CiAgICAgICAgICAgICAgICAgICAgZm9yIChpbnQgaiA9IDE7IGogPD0gKGludCl0b3AuU2hhcGVzLkNvdW50OyBqKyspCiAgICAgICAgICAgICAgICAgICAgICAgIG1hcFsoaW50KXRvcC5TaGFwZXMuSXRlbShqKS5JRF0gPSAoaW50KXRvcC5JRDsKICAgICAgICAgICAgICAgIH0KICAgICAgICAgICAgICAgIGNhdGNoIHsgfQogICAgICAgICAgICB9CiAgICAgICAgICAgIHJldHVybiBtYXA7CiAgICAgICAgfQoKICAgICAgICBwcml2YXRlIEhhc2hTZXQ8aW50PiBUb3BMZXZlbElkcyhkeW5hbWljIHBhZ2UpCiAgICAgICAgewogICAgICAgICAgICBIYXNoU2V0PGludD4gcmVzdWx0ID0gbmV3IEhhc2hTZXQ8aW50PigpOwogICAgICAgICAgICBmb3IgKGludCBpID0gMTsgaSA8PSAoaW50KXBhZ2UuU2hhcGVzLkNvdW50OyBpKyspIHJlc3VsdC5BZGQoKGludClwYWdlLlNoYXBlcy5JdGVtKGkpLklEKTsKICAgICAgICAgICAgcmV0dXJuIHJlc3VsdDsKICAgICAgICB9CgogICAgICAgIHByaXZhdGUgTGlzdDxpbnQ+IEN1cnJlbnRUb3BMZXZlbFNlbGVjdGlvbihkeW5hbWljIHBhZ2UpCiAgICAgICAgewogICAgICAgICAgICBkeW5hbWljIHNlbCA9IEFwcC5BY3RpdmVXaW5kb3cuU2VsZWN0aW9uOwogICAgICAgICAgICBpZiAoc2VsID09IG51bGwgfHwgKGludClzZWwuQ291bnQgPCAxKSB0aHJvdyBuZXcgSW52YWxpZE9wZXJhdGlvbkV4Y2VwdGlvbigi0KHQvdCw0YfQsNC70LAg0LLRi9C00LXQu9C40YLQtSDQvtCx0YrQtdC60YIo0YspINC90LAg0YHRhdC10LzQtSIpOwogICAgICAgICAgICBIYXNoU2V0PGludD4gdG9wID0gVG9wTGV2ZWxJZHMocGFnZSk7CiAgICAgICAgICAgIExpc3Q8aW50PiBpZHMgPSBuZXcgTGlzdDxpbnQ+KCk7CiAgICAgICAgICAgIGZvciAoaW50IGkgPSAxOyBpIDw9IChpbnQpc2VsLkNvdW50OyBpKyspCiAgICAgICAgICAgIHsKICAgICAgICAgICAgICAgIGR5bmFtaWMgc2hhcGUgPSBzZWwuSXRlbShpKTsKICAgICAgICAgICAgICAgIGludCBpZCA9IChpbnQpc2hhcGUuSUQ7CiAgICAgICAgICAgICAgICBpZiAoIXRvcC5Db250YWlucyhpZCkpCiAgICAgICAgICAgICAgICB7CiAgICAgICAgICAgICAgICAgICAgdHJ5CiAgICAgICAgICAgICAgICAgICAgewogICAgICAgICAgICAgICAgICAgICAgICBkeW5hbWljIHBhcmVudCA9IHNoYXBlLkNvbnRhaW5pbmdTaGFwZTsKICAgICAgICAgICAgICAgICAgICAgICAgaWYgKHBhcmVudCAhPSBudWxsKSBpZCA9IChpbnQpcGFyZW50LklEOwogICAgICAgICAgICAgICAgICAgIH0KICAgICAgICAgICAgICAgICAgICBjYXRjaCB7IH0KICAgICAgICAgICAgICAgIH0KICAgICAgICAgICAgICAgIGlmICghdG9wLkNvbnRhaW5zKGlkKSkgdGhyb3cgbmV3IEludmFsaWRPcGVyYXRpb25FeGNlcHRpb24oItCS0YvQsdGA0LDQvSDQtNC+0YfQtdGA0L3QuNC5INC+0LHRitC10LrRgiwg0LrQvtGC0L7RgNGL0Lkg0L3QtSDRg9C00LDQu9C+0YHRjCDQvdC+0YDQvNCw0LvQuNC30L7QstCw0YLRjCDQtNC+IHRvcC1sZXZlbCBzaGFwZSIpOwogICAgICAgICAgICAgICAgaWYgKCFpZHMuQ29udGFpbnMoaWQpKSBpZHMuQWRkKGlkKTsKICAgICAgICAgICAgfQogICAgICAgICAgICByZXR1cm4gaWRzOwogICAgICAgIH0KCiAgICAgICAgcHJpdmF0ZSBMaXN0PGludD4gU2VsZWN0aW9uSWRzKGR5bmFtaWMgc2VsZWN0aW9uKQogICAgICAgIHsKICAgICAgICAgICAgTGlzdDxpbnQ+IGlkcyA9IG5ldyBMaXN0PGludD4oKTsKICAgICAgICAgICAgZm9yIChpbnQgaSA9IDE7IGkgPD0gKGludClzZWxlY3Rpb24uQ291bnQ7IGkrKykgaWRzLkFkZCgoaW50KXNlbGVjdGlvbi5JdGVtKGkpLklEKTsKICAgICAgICAgICAgcmV0dXJuIGlkczsKICAgICAgICB9CgogICAgICAgIHByaXZhdGUgdm9pZCBTZWxlY3RJZHMoZHluYW1pYyBwYWdlLCBJRW51bWVyYWJsZTxpbnQ+IGlkcykKICAgICAgICB7CiAgICAgICAgICAgIGR5bmFtaWMgd2luZG93ID0gQXBwLkFjdGl2ZVdpbmRvdzsKICAgICAgICAgICAgd2luZG93LkRlc2VsZWN0QWxsKCk7CiAgICAgICAgICAgIGZvcmVhY2ggKGludCBpZCBpbiBpZHMpIHdpbmRvdy5TZWxlY3QocGFnZS5TaGFwZXMuSXRlbUZyb21JRChpZCksIDIpOwogICAgICAgIH0KCiAgICAgICAgcHJpdmF0ZSBHbHVlVGFyZ2V0IFRyeUdldEdsdWVUYXJnZXQoZHluYW1pYyBzaGFwZSwgc3RyaW5nIGVuZHBvaW50KQogICAgICAgIHsKICAgICAgICAgICAgaWYgKCFIYXNFbmRwb2ludChzaGFwZSwgZW5kcG9pbnQpKSByZXR1cm4gbnVsbDsKICAgICAgICAgICAgc3RyaW5nIGNlbGxOYW1lID0gZW5kcG9pbnQgPT0gImJlZ2luIiA/ICJCZWdpblgiIDogIkVuZFgiOwogICAgICAgICAgICBzdHJpbmcgZm9ybXVsYTsKICAgICAgICAgICAgdHJ5IHsgZm9ybXVsYSA9IChzdHJpbmcpc2hhcGUuQ2VsbHNVKGNlbGxOYW1lKS5Gb3JtdWxhVTsgfQogICAgICAgICAgICBjYXRjaCB7IHJldHVybiBudWxsOyB9CiAgICAgICAgICAgIE1hdGNoIG0gPSBfZ2x1ZVJlZ2V4Lk1hdGNoKGZvcm11bGEgPz8gIiIpOwogICAgICAgICAgICBpZiAoIW0uU3VjY2VzcykgcmV0dXJuIG51bGw7CiAgICAgICAgICAgIGludCByb3cgPSBtLkdyb3Vwc1syXS5TdWNjZXNzID8gSW50MzIuUGFyc2UobS5Hcm91cHNbMl0uVmFsdWUsIEN1bHR1cmVJbmZvLkludmFyaWFudEN1bHR1cmUpIDogSW50MzIuUGFyc2UobS5Hcm91cHNbM10uVmFsdWUsIEN1bHR1cmVJbmZvLkludmFyaWFudEN1bHR1cmUpOwogICAgICAgICAgICByZXR1cm4gbmV3IEdsdWVUYXJnZXQgeyBUYXJnZXRJZCA9IEludDMyLlBhcnNlKG0uR3JvdXBzWzFdLlZhbHVlLCBDdWx0dXJlSW5mby5JbnZhcmlhbnRDdWx0dXJlKSwgUm93ID0gcm93LCBFbmRwb2ludCA9IGVuZHBvaW50IH07CiAgICAgICAgfQoKICAgICAgICBwcml2YXRlIGJvb2wgSGFzRW5kcG9pbnQoZHluYW1pYyBzaGFwZSwgc3RyaW5nIGVuZHBvaW50KQogICAgICAgIHsKICAgICAgICAgICAgdHJ5IHsgcmV0dXJuIChib29sKXNoYXBlLkNlbGxFeGlzdHNVKGVuZHBvaW50ID09ICJiZWdpbiIgPyAiQmVnaW5YIiA6ICJFbmRYIiwgMCk7IH0KICAgICAgICAgICAgY2F0Y2ggeyByZXR1cm4gZmFsc2U7IH0KICAgICAgICB9CgogICAgICAgIHByaXZhdGUgdm9pZCBEZXRhY2hFbmRwb2ludChkeW5hbWljIHNoYXBlLCBzdHJpbmcgZW5kcG9pbnQpCiAgICAgICAgewogICAgICAgICAgICBzdHJpbmcgeE5hbWUgPSBlbmRwb2ludCA9PSAiYmVnaW4iID8gIkJlZ2luWCIgOiAiRW5kWCI7CiAgICAgICAgICAgIHN0cmluZyB5TmFtZSA9IGVuZHBvaW50ID09ICJiZWdpbiIgPyAiQmVnaW5ZIiA6ICJFbmRZIjsKICAgICAgICAgICAgZG91YmxlIHggPSBHZXRNbShzaGFwZSwgeE5hbWUpOwogICAgICAgICAgICBkb3VibGUgeSA9IEdldE1tKHNoYXBlLCB5TmFtZSk7CiAgICAgICAgICAgIFNldE1tKHNoYXBlLCB4TmFtZSwgeCk7CiAgICAgICAgICAgIFNldE1tKHNoYXBlLCB5TmFtZSwgeSk7CiAgICAgICAgfQoKICAgICAgICBwcml2YXRlIHZvaWQgR2x1ZUVuZHBvaW50KGR5bmFtaWMgc2hhcGUsIHN0cmluZyBlbmRwb2ludCwgZHluYW1pYyB0YXJnZXQsIGludCByb3cpCiAgICAgICAgewogICAgICAgICAgICBzdHJpbmcgc291cmNlTmFtZSA9IGVuZHBvaW50ID09ICJiZWdpbiIgPyAiQmVnaW5YIiA6ICJFbmRYIjsKICAgICAgICAgICAgc3RyaW5nIHRhcmdldE5hbWUgPSAiQ29ubmVjdGlvbnMuWCIgKyByb3cuVG9TdHJpbmcoQ3VsdHVyZUluZm8uSW52YXJpYW50Q3VsdHVyZSk7CiAgICAgICAgICAgIGlmICghKGJvb2wpdGFyZ2V0LkNlbGxFeGlzdHNVKHRhcmdldE5hbWUsIDApKSB0aHJvdyBuZXcgSW52YWxpZE9wZXJhdGlvbkV4Y2VwdGlvbigi0KMgdGFyZ2V0INC+0YLRgdGD0YLRgdGC0LLRg9C10YIgIiArIHRhcmdldE5hbWUpOwogICAgICAgICAgICBzaGFwZS5DZWxsc1Uoc291cmNlTmFtZSkuR2x1ZVRvKHRhcmdldC5DZWxsc1UodGFyZ2V0TmFtZSkpOwogICAgICAgIH0KCiAgICAgICAgcHJpdmF0ZSB2b2lkIFZlcmlmeUdsdWUoZHluYW1pYyBzaGFwZSwgc3RyaW5nIGVuZHBvaW50LCBpbnQgdGFyZ2V0SWQsIGludCByb3cpCiAgICAgICAgewogICAgICAgICAgICBHbHVlVGFyZ2V0IHRhcmdldCA9IFRyeUdldEdsdWVUYXJnZXQoc2hhcGUsIGVuZHBvaW50KTsKICAgICAgICAgICAgaWYgKHRhcmdldCA9PSBudWxsIHx8IHRhcmdldC5UYXJnZXRJZCAhPSB0YXJnZXRJZCB8fCB0YXJnZXQuUm93ICE9IHJvdykKICAgICAgICAgICAgICAgIHRocm93IG5ldyBJbnZhbGlkT3BlcmF0aW9uRXhjZXB0aW9uKCLQn9GA0L7QstC10YDQutCwIEdsdWUg0L/QvtGB0LvQtSDQvtC/0LXRgNCw0YbQuNC4INC90LUg0L/RgNC+0YjQu9CwIik7CiAgICAgICAgfQoKICAgICAgICBwcml2YXRlIExpc3Q8Q29ubmVjdGlvblBvaW50SW5mbz4gR2V0QWxsQ29ubmVjdGlvblBvaW50cyhkeW5hbWljIHBhZ2UpCiAgICAgICAgewogICAgICAgICAgICBMaXN0PENvbm5lY3Rpb25Qb2ludEluZm8+IHJlc3VsdCA9IG5ldyBMaXN0PENvbm5lY3Rpb25Qb2ludEluZm8+KCk7CiAgICAgICAgICAgIEFjdGlvbjxkeW5hbWljPiBhZGRTaGFwZSA9IG51bGw7CiAgICAgICAgICAgIGFkZFNoYXBlID0gc2hhcGUgPT4KICAgICAgICAgICAgewogICAgICAgICAgICAgICAgaW50IHNpZCA9IChpbnQpc2hhcGUuSUQ7CiAgICAgICAgICAgICAgICBmb3IgKGludCByb3cgPSAxOyByb3cgPD0gMzI7IHJvdysrKQogICAgICAgICAgICAgICAgewogICAgICAgICAgICAgICAgICAgIHN0cmluZyB4TmFtZSA9ICJDb25uZWN0aW9ucy5YIiArIHJvdy5Ub1N0cmluZyhDdWx0dXJlSW5mby5JbnZhcmlhbnRDdWx0dXJlKTsKICAgICAgICAgICAgICAgICAgICBzdHJpbmcgeU5hbWUgPSAiQ29ubmVjdGlvbnMuWSIgKyByb3cuVG9TdHJpbmcoQ3VsdHVyZUluZm8uSW52YXJpYW50Q3VsdHVyZSk7CiAgICAgICAgICAgICAgICAgICAgdHJ5CiAgICAgICAgICAgICAgICAgICAgewogICAgICAgICAgICAgICAgICAgICAgICBpZiAoIShib29sKXNoYXBlLkNlbGxFeGlzdHNVKHhOYW1lLCAwKSkgY29udGludWU7CiAgICAgICAgICAgICAgICAgICAgICAgIGRvdWJsZSB4ID0gKGRvdWJsZSlzaGFwZS5DZWxsc1UoeE5hbWUpLlJlc3VsdElVOwogICAgICAgICAgICAgICAgICAgICAgICBkb3VibGUgeSA9IChkb3VibGUpc2hhcGUuQ2VsbHNVKHlOYW1lKS5SZXN1bHRJVTsKICAgICAgICAgICAgICAgICAgICAgICAgZG91YmxlIHB4ID0gMCwgcHkgPSAwOwogICAgICAgICAgICAgICAgICAgICAgICBzaGFwZS5YWVRvUGFnZSh4LCB5LCBvdXQgcHgsIG91dCBweSk7CiAgICAgICAgICAgICAgICAgICAgICAgIHJlc3VsdC5BZGQobmV3IENvbm5lY3Rpb25Qb2ludEluZm8geyBTaGFwZUlkID0gc2lkLCBSb3cgPSByb3csIFhtbSA9IHB4ICogMjUuNCwgWW1tID0gcHkgKiAyNS40IH0pOwogICAgICAgICAgICAgICAgICAgIH0KICAgICAgICAgICAgICAgICAgICBjYXRjaCB7IH0KICAgICAgICAgICAgICAgIH0KICAgICAgICAgICAgICAgIHRyeSB7IGZvciAoaW50IGkgPSAxOyBpIDw9IChpbnQpc2hhcGUuU2hhcGVzLkNvdW50OyBpKyspIGFkZFNoYXBlKHNoYXBlLlNoYXBlcy5JdGVtKGkpKTsgfQogICAgICAgICAgICAgICAgY2F0Y2ggeyB9CiAgICAgICAgICAgIH07CiAgICAgICAgICAgIGZvciAoaW50IGkgPSAxOyBpIDw9IChpbnQpcGFnZS5TaGFwZXMuQ291bnQ7IGkrKykgYWRkU2hhcGUocGFnZS5TaGFwZXMuSXRlbShpKSk7CiAgICAgICAgICAgIHJldHVybiByZXN1bHQ7CiAgICAgICAgfQoKICAgICAgICBwcml2YXRlIGRvdWJsZSBHZXRNbShkeW5hbWljIHNoYXBlLCBzdHJpbmcgY2VsbCkgeyByZXR1cm4gKGRvdWJsZSlzaGFwZS5DZWxsc1UoY2VsbCkuUmVzdWx0SVUgKiAyNS40OyB9CiAgICAgICAgcHJpdmF0ZSB2b2lkIFNldE1tKGR5bmFtaWMgc2hhcGUsIHN0cmluZyBjZWxsLCBkb3VibGUgdmFsdWUpIHsgc2hhcGUuQ2VsbHNVKGNlbGwpLkZvcm11bGFVID0gdmFsdWUuVG9TdHJpbmcoIjAuIyMjIyMjIyMjIyMjIiwgQ3VsdHVyZUluZm8uSW52YXJpYW50Q3VsdHVyZSkgKyAiIG1tIjsgfQogICAgICAgIHByaXZhdGUgc3RyaW5nIFNhZmVUZXh0KGR5bmFtaWMgc2hhcGUpIHsgdHJ5IHsgcmV0dXJuIChzdHJpbmcpc2hhcGUuVGV4dCA/PyAiIjsgfSBjYXRjaCB7IHJldHVybiAiIjsgfSB9CiAgICAgICAgcHJpdmF0ZSBzdHJpbmcgTWFzdGVyTmFtZShkeW5hbWljIHNoYXBlKSB7IHRyeSB7IGR5bmFtaWMgbSA9IHNoYXBlLk1hc3RlcjsgcmV0dXJuIG0gPT0gbnVsbCA/ICIiIDogKHN0cmluZyltLk5hbWVVOyB9IGNhdGNoIHsgcmV0dXJuICIiOyB9IH0KCiAgICAgICAgcHJpdmF0ZSBib29sIEhhc0NlbGxJZGVudGl0eShkeW5hbWljIHNoYXBlKQogICAgICAgIHsKICAgICAgICAgICAgdHJ5IHsgcmV0dXJuIChib29sKXNoYXBlLkNlbGxFeGlzdHNVKCJVc2VyLkVuZXJnb0xvZ2ljQ2VsbElkIiwgMCk7IH0KICAgICAgICAgICAgY2F0Y2ggeyByZXR1cm4gZmFsc2U7IH0KICAgICAgICB9CgogICAgICAgIHByaXZhdGUgdm9pZCBTZXRDZWxsSWRlbnRpdHkoZHluYW1pYyBzaGFwZSwgc3RyaW5nIGNlbGxJZCkKICAgICAgICB7CiAgICAgICAgICAgIGNvbnN0IHNob3J0IHZpc1NlY3Rpb25Vc2VyID0gMjQyOwogICAgICAgICAgICBpZiAoIShib29sKXNoYXBlLlNlY3Rpb25FeGlzdHModmlzU2VjdGlvblVzZXIsIDApKSBzaGFwZS5BZGRTZWN0aW9uKHZpc1NlY3Rpb25Vc2VyKTsKICAgICAgICAgICAgaWYgKCEoYm9vbClzaGFwZS5DZWxsRXhpc3RzVSgiVXNlci5FbmVyZ29Mb2dpY0NlbGxJZCIsIDApKSBzaGFwZS5BZGROYW1lZFJvdyh2aXNTZWN0aW9uVXNlciwgIkVuZXJnb0xvZ2ljQ2VsbElkIiwgMCk7CiAgICAgICAgICAgIHNoYXBlLkNlbGxzVSgiVXNlci5FbmVyZ29Mb2dpY0NlbGxJZCIpLkZvcm11bGFVID0gIlwiIiArIGNlbGxJZCArICJcIiI7CiAgICAgICAgfQogICAgfQoKICAgIGludGVybmFsIHNlYWxlZCBjbGFzcyBFZGl0b3JGb3JtIDogRm9ybQogICAgewogICAgICAgIHByaXZhdGUgcmVhZG9ubHkgQ29ubmVjdCBfYWRkaW47CiAgICAgICAgcHJpdmF0ZSByZWFkb25seSBUZXh0Qm94IF9zdGF0dXM7CiAgICAgICAgcHJpdmF0ZSByZWFkb25seSBOdW1lcmljVXBEb3duIF9keDsKICAgICAgICBwcml2YXRlIHJlYWRvbmx5IE51bWVyaWNVcERvd24gX2R5OwogICAgICAgIHByaXZhdGUgcmVhZG9ubHkgTnVtZXJpY1VwRG93biBfYng7CiAgICAgICAgcHJpdmF0ZSByZWFkb25seSBOdW1lcmljVXBEb3duIF9ieTsKICAgICAgICBwcml2YXRlIHJlYWRvbmx5IE51bWVyaWNVcERvd24gX3R4OwogICAgICAgIHByaXZhdGUgcmVhZG9ubHkgTnVtZXJpY1VwRG93biBfdHk7CiAgICAgICAgcHJpdmF0ZSByZWFkb25seSBOdW1lcmljVXBEb3duIF9waXRjaDsKCiAgICAgICAgcHVibGljIEVkaXRvckZvcm0oQ29ubmVjdCBhZGRpbikKICAgICAgICB7CiAgICAgICAgICAgIF9hZGRpbiA9IGFkZGluOwogICAgICAgICAgICBUZXh0ID0gIkVuZXJnb0xvZ2ljIOKAlCDQuNC90YHRgtGA0YPQvNC10L3RgtGLIFZpc2lvIjsKICAgICAgICAgICAgV2lkdGggPSA0MjA7CiAgICAgICAgICAgIEhlaWdodCA9IDY5MDsKICAgICAgICAgICAgTWluaW11bVNpemUgPSBuZXcgU2l6ZSgzODAsIDYwMCk7CiAgICAgICAgICAgIFN0YXJ0UG9zaXRpb24gPSBGb3JtU3RhcnRQb3NpdGlvbi5DZW50ZXJTY3JlZW47CiAgICAgICAgICAgIEZvcm1Cb3JkZXJTdHlsZSA9IEZvcm1Cb3JkZXJTdHlsZS5TaXphYmxlVG9vbFdpbmRvdzsKICAgICAgICAgICAgU2hvd0luVGFza2JhciA9IGZhbHNlOwogICAgICAgICAgICBGb250ID0gbmV3IEZvbnQoIlNlZ29lIFVJIiwgOUYpOwogICAgICAgICAgICBUb3BNb3N0ID0gZmFsc2U7CgogICAgICAgICAgICBUYWJDb250cm9sIHRhYnMgPSBuZXcgVGFiQ29udHJvbCB7IERvY2sgPSBEb2NrU3R5bGUuVG9wLCBIZWlnaHQgPSA0OTAgfTsKICAgICAgICAgICAgVGFiUGFnZSBjZWxsVGFiID0gbmV3IFRhYlBhZ2UoItCv0YfQtdC50LrQuCIpOwogICAgICAgICAgICBUYWJQYWdlIGdlb1RhYiA9IG5ldyBUYWJQYWdlKCLQk9C10L7QvNC10YLRgNC40Y8iKTsKICAgICAgICAgICAgVGFiUGFnZSBjaGVja1RhYiA9IG5ldyBUYWJQYWdlKCLQn9GA0L7QstC10YDQutCwIik7CiAgICAgICAgICAgIHRhYnMuVGFiUGFnZXMuQWRkKGNlbGxUYWIpOyB0YWJzLlRhYlBhZ2VzLkFkZChnZW9UYWIpOyB0YWJzLlRhYlBhZ2VzLkFkZChjaGVja1RhYik7CgogICAgICAgICAgICBUYWJsZUxheW91dFBhbmVsIGNlbGxzID0gUGFuZWwyKCk7CiAgICAgICAgICAgIGNlbGxzLkNvbnRyb2xzLkFkZChCdXR0b24oItCa0L7Qv9C40YDQvtCy0LDRgtGMIOKGkCIsIChzLGUpPT5SdW4oKCk9Pl9hZGRpbi5EdXBsaWNhdGVDZWxsKC0xKSkpLDAsMCk7CiAgICAgICAgICAgIGNlbGxzLkNvbnRyb2xzLkFkZChCdXR0b24oItCa0L7Qv9C40YDQvtCy0LDRgtGMIOKGkiIsIChzLGUpPT5SdW4oKCk9Pl9hZGRpbi5EdXBsaWNhdGVDZWxsKDEpKSksMSwwKTsKICAgICAgICAgICAgY2VsbHMuQ29udHJvbHMuQWRkKEJ1dHRvbigi0J/QtdGA0LXQvNC10YHRgtC40YLRjCDihpAiLCAocyxlKT0+UnVuKCgpPT5fYWRkaW4uTW92ZUNlbGwoLTEpKSksMCwxKTsKICAgICAgICAgICAgY2VsbHMuQ29udHJvbHMuQWRkKEJ1dHRvbigi0J/QtdGA0LXQvNC10YHRgtC40YLRjCDihpIiLCAocyxlKT0+UnVuKCgpPT5fYWRkaW4uTW92ZUNlbGwoMSkpKSwxLDEpOwogICAgICAgICAgICBjZWxscy5Db250cm9scy5BZGQoQnV0dG9uKCLQktGL0LTQtdC70LjRgtGMINCy0YHRjiDRj9GH0LXQudC60YMiLCAocyxlKT0+UnVuKCgpPT5fYWRkaW4uU2VsZWN0Q2VsbCgpKSksMCwyKTsKICAgICAgICAgICAgY2VsbHMuU2V0Q29sdW1uU3BhbihjZWxscy5HZXRDb250cm9sRnJvbVBvc2l0aW9uKDAsMiksMik7CiAgICAgICAgICAgIGNlbGxUYWIuQ29udHJvbHMuQWRkKGNlbGxzKTsKCiAgICAgICAgICAgIEZsb3dMYXlvdXRQYW5lbCBnbHVlUGFuZWwgPSBuZXcgRmxvd0xheW91dFBhbmVsIHsgRG9jayA9IERvY2tTdHlsZS5Cb3R0b20sIEhlaWdodCA9IDEyMCwgRmxvd0RpcmVjdGlvbiA9IEZsb3dEaXJlY3Rpb24uVG9wRG93biwgUGFkZGluZyA9IG5ldyBQYWRkaW5nKDEwKSB9OwogICAgICAgICAgICBnbHVlUGFuZWwuQ29udHJvbHMuQWRkKEJ1dHRvbldpZGUoItCd0LDQudGC0Lgg0L/RgNC+0LHQu9C10LzRgyBHbHVlIiwgKHMsZSk9PlJ1bigoKT0+X2FkZGluLlJlcGFpckdsdWUodHJ1ZSkpKSk7CiAgICAgICAgICAgIGdsdWVQYW5lbC5Db250cm9scy5BZGQoQnV0dG9uV2lkZSgiUmVwYWlyIEdsdWXigKYiLCAocyxlKT0+UnVuKCgpPT5fYWRkaW4uUmVwYWlyR2x1ZShmYWxzZSkpKSk7CiAgICAgICAgICAgIGNlbGxUYWIuQ29udHJvbHMuQWRkKGdsdWVQYW5lbCk7CgogICAgICAgICAgICBUYWJsZUxheW91dFBhbmVsIGdlbyA9IG5ldyBUYWJsZUxheW91dFBhbmVsIHsgRG9jayA9IERvY2tTdHlsZS5GaWxsLCBDb2x1bW5Db3VudCA9IDQsIFJvd0NvdW50ID0gOSwgUGFkZGluZyA9IG5ldyBQYWRkaW5nKDEwKSB9OwogICAgICAgICAgICBmb3IoaW50IGk9MDtpPDQ7aSsrKSBnZW8uQ29sdW1uU3R5bGVzLkFkZChuZXcgQ29sdW1uU3R5bGUoU2l6ZVR5cGUuUGVyY2VudCwyNSkpOwogICAgICAgICAgICBfZHggPSBOdW0oLTUwMCw1MDAsMCk7IF9keSA9IE51bSgtNTAwLDUwMCwwKTsKICAgICAgICAgICAgZ2VvLkNvbnRyb2xzLkFkZChuZXcgTGFiZWx7VGV4dD0izpRYLCDQvNC8IixBdXRvU2l6ZT10cnVlfSwwLDApOyBnZW8uQ29udHJvbHMuQWRkKF9keCwxLDApOwogICAgICAgICAgICBnZW8uQ29udHJvbHMuQWRkKG5ldyBMYWJlbHtUZXh0PSLOlFksINC80LwiLEF1dG9TaXplPXRydWV9LDIsMCk7IGdlby5Db250cm9scy5BZGQoX2R5LDMsMCk7CiAgICAgICAgICAgIEJ1dHRvbiBvZmZzZXQgPSBCdXR0b25XaWRlKCLQn9GA0LjQvNC10L3QuNGC0Ywg0YLQvtGH0L3Ri9C5INGB0LTQstC40LMiLCAocyxlKT0+UnVuKCgpPT5fYWRkaW4uRXhhY3RPZmZzZXQoKGRvdWJsZSlfZHguVmFsdWUsKGRvdWJsZSlfZHkuVmFsdWUpKSk7CiAgICAgICAgICAgIGdlby5Db250cm9scy5BZGQob2Zmc2V0LDAsMSk7IGdlby5TZXRDb2x1bW5TcGFuKG9mZnNldCw0KTsKICAgICAgICAgICAgQnV0dG9uIGF4PUJ1dHRvbigi0JLRi9GA0L7QstC90Y/RgtGMIFgiLChzLGUpPT5SdW4oKCk9Pl9hZGRpbi5BbGlnbigieCIpKSk7IEJ1dHRvbiBheT1CdXR0b24oItCS0YvRgNC+0LLQvdGP0YLRjCBZIiwocyxlKT0+UnVuKCgpPT5fYWRkaW4uQWxpZ24oInkiKSkpOwogICAgICAgICAgICBnZW8uQ29udHJvbHMuQWRkKGF4LDAsMik7IGdlby5TZXRDb2x1bW5TcGFuKGF4LDIpOyBnZW8uQ29udHJvbHMuQWRkKGF5LDIsMik7IGdlby5TZXRDb2x1bW5TcGFuKGF5LDIpOwoKICAgICAgICAgICAgX2J4PU51bSgtMjAwMCwyMDAwLDApOyBfYnk9TnVtKC0yMDAwLDIwMDAsMCk7IF90eD1OdW0oLTIwMDAsMjAwMCwwKTsgX3R5PU51bSgtMjAwMCwyMDAwLDApOwogICAgICAgICAgICBnZW8uQ29udHJvbHMuQWRkKG5ldyBMYWJlbHtUZXh0PSLQkdCw0LfQsCBYIixBdXRvU2l6ZT10cnVlfSwwLDMpOyBnZW8uQ29udHJvbHMuQWRkKF9ieCwxLDMpOyBnZW8uQ29udHJvbHMuQWRkKG5ldyBMYWJlbHtUZXh0PSLQkdCw0LfQsCBZIixBdXRvU2l6ZT10cnVlfSwyLDMpOyBnZW8uQ29udHJvbHMuQWRkKF9ieSwzLDMpOwogICAgICAgICAgICBnZW8uQ29udHJvbHMuQWRkKG5ldyBMYWJlbHtUZXh0PSLQptC10LvRjCBYIixBdXRvU2l6ZT10cnVlfSwwLDQpOyBnZW8uQ29udHJvbHMuQWRkKF90eCwxLDQpOyBnZW8uQ29udHJvbHMuQWRkKG5ldyBMYWJlbHtUZXh0PSLQptC10LvRjCBZIixBdXRvU2l6ZT10cnVlfSwyLDQpOyBnZW8uQ29udHJvbHMuQWRkKF90eSwzLDQpOwogICAgICAgICAgICBCdXR0b24gYmM9QnV0dG9uKCLQmtC+0L/QuNGA0L7QstCw0YLRjCDQv9C+INCx0LDQt9C1IiwocyxlKT0+UnVuKCgpPT5fYWRkaW4uQmFzZVBvaW50VHJhbnNmb3JtKHRydWUsKGRvdWJsZSlfYnguVmFsdWUsKGRvdWJsZSlfYnkuVmFsdWUsKGRvdWJsZSlfdHguVmFsdWUsKGRvdWJsZSlfdHkuVmFsdWUpKSk7CiAgICAgICAgICAgIEJ1dHRvbiBibT1CdXR0b24oItCf0LXRgNC10LzQtdGB0YLQuNGC0Ywg0L/QviDQsdCw0LfQtSIsKHMsZSk9PlJ1bigoKT0+X2FkZGluLkJhc2VQb2ludFRyYW5zZm9ybShmYWxzZSwoZG91YmxlKV9ieC5WYWx1ZSwoZG91YmxlKV9ieS5WYWx1ZSwoZG91YmxlKV90eC5WYWx1ZSwoZG91YmxlKV90eS5WYWx1ZSkpKTsKICAgICAgICAgICAgZ2VvLkNvbnRyb2xzLkFkZChiYywwLDUpOyBnZW8uU2V0Q29sdW1uU3BhbihiYywyKTsgZ2VvLkNvbnRyb2xzLkFkZChibSwyLDUpOyBnZW8uU2V0Q29sdW1uU3BhbihibSwyKTsKCiAgICAgICAgICAgIF9waXRjaD1OdW0oMSw1MDAsNDApOyBnZW8uQ29udHJvbHMuQWRkKG5ldyBMYWJlbHtUZXh0PSLQqNCw0LMg0Y/Rh9C10LXQuiwg0LzQvCIsQXV0b1NpemU9dHJ1ZX0sMCw2KTsgZ2VvLkNvbnRyb2xzLkFkZChfcGl0Y2gsMSw2KTsKICAgICAgICAgICAgQnV0dG9uIG1lYXN1cmU9QnV0dG9uKCLQmNC30LzQtdGA0LjRgtGMINGI0LDQsyIsKHMsZSk9PlJ1blBpdGNoTWVhc3VyZSgpKTsgQnV0dG9uIGRpc3Q9QnV0dG9uKCLQoNCw0YHQv9GA0LXQtNC10LvQuNGC0YwiLChzLGUpPT5SdW4oKCk9Pl9hZGRpbi5EaXN0cmlidXRlUGl0Y2goKGRvdWJsZSlfcGl0Y2guVmFsdWUpKSk7CiAgICAgICAgICAgIGdlby5Db250cm9scy5BZGQobWVhc3VyZSwyLDYpOyBnZW8uQ29udHJvbHMuQWRkKGRpc3QsMyw2KTsKICAgICAgICAgICAgZ2VvVGFiLkNvbnRyb2xzLkFkZChnZW8pOwoKICAgICAgICAgICAgRmxvd0xheW91dFBhbmVsIGNoZWNrcyA9IG5ldyBGbG93TGF5b3V0UGFuZWwgeyBEb2NrID0gRG9ja1N0eWxlLkZpbGwsIEZsb3dEaXJlY3Rpb24gPSBGbG93RGlyZWN0aW9uLlRvcERvd24sIFBhZGRpbmcgPSBuZXcgUGFkZGluZygxNCksIFdyYXBDb250ZW50cz1mYWxzZSB9OwogICAgICAgICAgICBjaGVja3MuQ29udHJvbHMuQWRkKEJ1dHRvbldpZGUoItCf0YDQvtCy0LXRgNC40YLRjCDRgdGF0LXQvNGDIiwgKHMsZSk9PlJ1bigoKT0+X2FkZGluLkRvY3RvcigpKSkpOwogICAgICAgICAgICBjaGVja3MuQ29udHJvbHMuQWRkKG5ldyBMYWJlbCB7IEF1dG9TaXplPXRydWUsIE1heGltdW1TaXplPW5ldyBTaXplKDM1MCwwKSwgVGV4dD0iU2NoZW1lIERvY3RvciDQuNGJ0LXRgiDQvtC/0LDRgdC90YvQtSDRgdC70YPRh9Cw0Lg6INCy0LjQt9GD0LDQu9GM0L3QvtC1INC60LDRgdCw0L3QuNC1INCx0LXQtyDRgNC10LDQu9GM0L3QvtCz0L4gR2x1ZSDQuCDQstGL0LTQtdC70Y/QtdGCINC/0YDQvtCx0LvQtdC80L3Ri9C1INGN0LvQtdC80LXQvdGC0YsuIiB9KTsKICAgICAgICAgICAgY2hlY2tUYWIuQ29udHJvbHMuQWRkKGNoZWNrcyk7CgogICAgICAgICAgICBfc3RhdHVzID0gbmV3IFRleHRCb3ggeyBEb2NrPURvY2tTdHlsZS5GaWxsLCBNdWx0aWxpbmU9dHJ1ZSwgUmVhZE9ubHk9dHJ1ZSwgU2Nyb2xsQmFycz1TY3JvbGxCYXJzLlZlcnRpY2FsLCBCYWNrQ29sb3I9U3lzdGVtQ29sb3JzLldpbmRvdywgVGV4dD0iRW5lcmdvTG9naWMg0LPQvtGC0L7Qsi4g0JLRi9Cx0LXRgNC40YLQtSDQvtCx0YrQtdC60YIg0L3QsCDRgdGF0LXQvNC1INC4INC40YHQv9C+0LvRjNC30YPQudGC0LUg0LrQvtC80LDQvdC00YMg0LLRi9GI0LUuIiB9OwogICAgICAgICAgICBQYW5lbCBzdGF0dXNQYW5lbCA9IG5ldyBQYW5lbCB7IERvY2s9RG9ja1N0eWxlLkZpbGwsIFBhZGRpbmc9bmV3IFBhZGRpbmcoOCkgfTsKICAgICAgICAgICAgc3RhdHVzUGFuZWwuQ29udHJvbHMuQWRkKF9zdGF0dXMpOwoKICAgICAgICAgICAgQ29udHJvbHMuQWRkKHN0YXR1c1BhbmVsKTsKICAgICAgICAgICAgQ29udHJvbHMuQWRkKHRhYnMpOwogICAgICAgIH0KCiAgICAgICAgcHJvdGVjdGVkIG92ZXJyaWRlIHZvaWQgT25Gb3JtQ2xvc2luZyhGb3JtQ2xvc2luZ0V2ZW50QXJncyBlKQogICAgICAgIHsKICAgICAgICAgICAgaWYgKGUuQ2xvc2VSZWFzb24gPT0gQ2xvc2VSZWFzb24uVXNlckNsb3NpbmcpIHsgZS5DYW5jZWw9dHJ1ZTsgSGlkZSgpOyByZXR1cm47IH0KICAgICAgICAgICAgYmFzZS5PbkZvcm1DbG9zaW5nKGUpOwogICAgICAgIH0KCiAgICAgICAgcHJpdmF0ZSB2b2lkIFJ1bihGdW5jPHN0cmluZz4gYWN0aW9uKQogICAgICAgIHsKICAgICAgICAgICAgdHJ5IHsgX3N0YXR1cy5UZXh0ID0gYWN0aW9uKCk7IH0KICAgICAgICAgICAgY2F0Y2goRXhjZXB0aW9uIGV4KSB7IF9zdGF0dXMuVGV4dCA9ICLimqAgIiArIEZyaWVuZGx5KGV4KTsgfQogICAgICAgIH0KCiAgICAgICAgcHJpdmF0ZSB2b2lkIFJ1blBpdGNoTWVhc3VyZSgpCiAgICAgICAgewogICAgICAgICAgICB0cnkKICAgICAgICAgICAgewogICAgICAgICAgICAgICAgc3RyaW5nIHZhbHVlID0gX2FkZGluLk1lYXN1cmVQaXRjaCgpOwogICAgICAgICAgICAgICAgZGVjaW1hbCBwYXJzZWQ7CiAgICAgICAgICAgICAgICBpZiAoRGVjaW1hbC5UcnlQYXJzZSh2YWx1ZSwgTnVtYmVyU3R5bGVzLkZsb2F0LCBDdWx0dXJlSW5mby5JbnZhcmlhbnRDdWx0dXJlLCBvdXQgcGFyc2VkKSkgX3BpdGNoLlZhbHVlID0gTWF0aC5NaW4oX3BpdGNoLk1heGltdW0sIE1hdGguTWF4KF9waXRjaC5NaW5pbXVtLCBwYXJzZWQpKTsKICAgICAgICAgICAgICAgIF9zdGF0dXMuVGV4dCA9ICLinJMg0JjQt9C80LXRgNC10L3QvdGL0Lkg0YjQsNCzOiAiICsgdmFsdWUgKyAiINC80LwuIjsKICAgICAgICAgICAgfQogICAgICAgICAgICBjYXRjaChFeGNlcHRpb24gZXgpIHsgX3N0YXR1cy5UZXh0ID0gIuKaoCAiICsgRnJpZW5kbHkoZXgpOyB9CiAgICAgICAgfQoKICAgICAgICBwcml2YXRlIHN0cmluZyBGcmllbmRseShFeGNlcHRpb24gZXgpCiAgICAgICAgewogICAgICAgICAgICBFeGNlcHRpb24gY3VyPWV4OyB3aGlsZShjdXIuSW5uZXJFeGNlcHRpb24hPW51bGwpIGN1cj1jdXIuSW5uZXJFeGNlcHRpb247CiAgICAgICAgICAgIHJldHVybiBjdXIuTWVzc2FnZTsKICAgICAgICB9CgogICAgICAgIHByaXZhdGUgVGFibGVMYXlvdXRQYW5lbCBQYW5lbDIoKQogICAgICAgIHsKICAgICAgICAgICAgVGFibGVMYXlvdXRQYW5lbCBwPW5ldyBUYWJsZUxheW91dFBhbmVse0RvY2s9RG9ja1N0eWxlLlRvcCxIZWlnaHQ9MTgwLENvbHVtbkNvdW50PTIsUm93Q291bnQ9MyxQYWRkaW5nPW5ldyBQYWRkaW5nKDEwKX07CiAgICAgICAgICAgIHAuQ29sdW1uU3R5bGVzLkFkZChuZXcgQ29sdW1uU3R5bGUoU2l6ZVR5cGUuUGVyY2VudCw1MCkpOyBwLkNvbHVtblN0eWxlcy5BZGQobmV3IENvbHVtblN0eWxlKFNpemVUeXBlLlBlcmNlbnQsNTApKTsKICAgICAgICAgICAgcmV0dXJuIHA7CiAgICAgICAgfQogICAgICAgIHByaXZhdGUgQnV0dG9uIEJ1dHRvbihzdHJpbmcgdGV4dCwgRXZlbnRIYW5kbGVyIGgpIHsgQnV0dG9uIGI9bmV3IEJ1dHRvbntUZXh0PXRleHQsRG9jaz1Eb2NrU3R5bGUuRmlsbCxIZWlnaHQ9MzgsTWFyZ2luPW5ldyBQYWRkaW5nKDUpfTsgYi5DbGljays9aDsgcmV0dXJuIGI7IH0KICAgICAgICBwcml2YXRlIEJ1dHRvbiBCdXR0b25XaWRlKHN0cmluZyB0ZXh0LCBFdmVudEhhbmRsZXIgaCkgeyBCdXR0b24gYj1uZXcgQnV0dG9ue1RleHQ9dGV4dCxXaWR0aD0zMzAsSGVpZ2h0PTM4LE1hcmdpbj1uZXcgUGFkZGluZyg0KX07IGIuQ2xpY2srPWg7IHJldHVybiBiOyB9CiAgICAgICAgcHJpdmF0ZSBOdW1lcmljVXBEb3duIE51bShkZWNpbWFsIG1pbiwgZGVjaW1hbCBtYXgsIGRlY2ltYWwgdmFsdWUpIHsgcmV0dXJuIG5ldyBOdW1lcmljVXBEb3due01pbmltdW09bWluLE1heGltdW09bWF4LFZhbHVlPXZhbHVlLERlY2ltYWxQbGFjZXM9MixJbmNyZW1lbnQ9MC41TSxEb2NrPURvY2tTdHlsZS5GaWxsfTsgfQogICAgfQp9Cg=="))

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
    def get_energologic_visio_crash_diagnostics() -> str:
        '''Read bounded Windows process/event diagnostics after the fixed add-in probe.'''
        try:
            import json
            import os
            import subprocess

            if os.name != "nt":
                raise RuntimeError("Visio crash diagnostics are Windows-only")

            ps = r'''$ErrorActionPreference='SilentlyContinue'
$procs = Get-CimInstance Win32_Process -Filter "Name='VISIO.EXE'" | Select-Object ProcessId,Name,CreationDate,ExecutablePath,CommandLine
$since = (Get-Date).AddMinutes(-20)
$events = Get-WinEvent -FilterHashtable @{LogName='Application'; StartTime=$since} -ErrorAction SilentlyContinue |
  Where-Object {
    $_.ProviderName -in @('Application Error','.NET Runtime','Windows Error Reporting') -and
    ($_.Message -match 'VISIO.EXE|EnergoLogic\.VisioQolAddin|EnergoLogicVisioQol')
  } |
  Select-Object -First 30 TimeCreated,ProviderName,Id,LevelDisplayName,Message
[pscustomobject]@{processes=@($procs); events=@($events)} | ConvertTo-Json -Depth 5 -Compress
'''
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    ps,
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    "PowerShell crash diagnostics failed: "
                    + (result.stdout + "\n" + result.stderr)[-3000:]
                )
            payload = json.loads(result.stdout or "{}")
            return ok({
                "processes": payload.get("processes", []),
                "events": payload.get("events", []),
                "powershell_stderr": result.stderr[-1000:],
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def launch_energologic_visio_qualification_copy() -> str:
        """Launch only the fixed EnergoLogic qualification copy when Visio is not running."""
        try:
            import os
            import subprocess

            if os.name != "nt":
                raise RuntimeError("Visio qualification launch is Windows-only")
            target = workspace / "KRU-35_normal_scheme_v2_energologic_qol_host_v1.vsdm"
            exe = Path(r"C:\Program Files\Microsoft Office\root\Office16\VISIO.EXE")
            if not target.is_file():
                raise FileNotFoundError(f"qualification document not found: {target}")
            if not exe.is_file():
                raise FileNotFoundError(f"Visio executable not found: {exe}")

            ps = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "@(Get-Process VISIO -ErrorAction SilentlyContinue).Count",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            running = int((ps.stdout or "0").strip() or "0")
            if running:
                return ok({
                    "launched": False,
                    "reason": "VISIO.EXE is already running",
                    "document": str(target),
                    "process_count": running,
                })
            proc = subprocess.Popen(
                [str(exe), str(target)],
                cwd=str(workspace),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return ok({
                "launched": True,
                "pid": int(proc.pid),
                "document": str(target),
                "visio_executable": str(exe),
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def get_vsto_build_capabilities() -> str:
        """Read bounded Windows/.NET/VSTO build capabilities without mutation."""
        try:
            import json
            import os
            import shutil
            import subprocess

            tools = {
                name: shutil.which(name)
                for name in (
                    "devenv.exe",
                    "msbuild.exe",
                    "dotnet.exe",
                    "csc.exe",
                    "regasm.exe",
                    "gacutil.exe",
                )
            }
            program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
            program_files_x86 = Path(
                os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
            )
            windows = Path(os.environ.get("WINDIR", r"C:\Windows"))
            known = {
                "vswhere": program_files_x86
                / "Microsoft Visual Studio"
                / "Installer"
                / "vswhere.exe",
                "framework_msbuild_4": windows
                / "Microsoft.NET"
                / "Framework64"
                / "v4.0.30319"
                / "MSBuild.exe",
                "framework_csc_4": windows
                / "Microsoft.NET"
                / "Framework64"
                / "v4.0.30319"
                / "csc.exe",
                "framework_regasm_4": windows
                / "Microsoft.NET"
                / "Framework64"
                / "v4.0.30319"
                / "RegAsm.exe",
                "vsto_runtime": program_files
                / "Common Files"
                / "microsoft shared"
                / "VSTO",
                "office_gac_pia": windows
                / "Microsoft.NET"
                / "assembly"
                / "GAC_MSIL"
                / "Microsoft.Office.Interop.Visio",
            }
            known_result = {
                name: {"path": str(path), "exists": path.exists()}
                for name, path in known.items()
            }

            vs_instances = []
            vswhere = known["vswhere"]
            if vswhere.exists():
                try:
                    proc = subprocess.run(
                        [
                            str(vswhere),
                            "-all",
                            "-products",
                            "*",
                            "-format",
                            "json",
                            "-utf8",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        check=False,
                    )
                    if proc.returncode == 0 and proc.stdout.strip():
                        raw = json.loads(proc.stdout)
                        for item in raw:
                            installation_path = str(item.get("installationPath", ""))
                            install = Path(installation_path) if installation_path else None
                            candidates = {}
                            if install is not None:
                                for label, relative in {
                                    "devenv": Path("Common7/IDE/devenv.exe"),
                                    "msbuild": Path("MSBuild/Current/Bin/MSBuild.exe"),
                                    "office_targets": Path("MSBuild/Microsoft/VisualStudio/OfficeTools"),
                                }.items():
                                    candidate = install / relative
                                    candidates[label] = {
                                        "path": str(candidate),
                                        "exists": candidate.exists(),
                                    }
                            vs_instances.append(
                                {
                                    "displayName": item.get("displayName"),
                                    "installationVersion": item.get("installationVersion"),
                                    "installationPath": installation_path,
                                    "isComplete": item.get("isComplete"),
                                    "isLaunchable": item.get("isLaunchable"),
                                    "candidates": candidates,
                                }
                            )
                except Exception as exc:
                    vs_instances = [{"probe_error": f"{type(exc).__name__}: {exc}"}]

            reference_dirs = []
            for root in (
                program_files_x86 / "Reference Assemblies" / "Microsoft" / "VSTO40",
                program_files_x86 / "Microsoft Visual Studio",
            ):
                reference_dirs.append({"path": str(root), "exists": root.exists()})

            reference_candidates = []
            search_roots = [
                program_files / "Microsoft Visual Studio" / "2022" / "Community" / "Common7" / "IDE" / "PublicAssemblies",
                program_files_x86 / "Microsoft Visual Studio" / "2022" / "Community" / "Common7" / "IDE" / "PublicAssemblies",
                program_files_x86 / "Microsoft Visual Studio" / "Shared" / "Visual Studio Tools for Office",
                program_files / "Microsoft Office" / "root",
                program_files_x86 / "Microsoft Office" / "root",
                windows / "Microsoft.NET" / "assembly" / "GAC_MSIL",
            ]
            wanted = {
                "extensibility.dll",
                "office.dll",
                "microsoft.office.core.dll",
                "microsoft.office.interop.visio.dll",
                "microsoft.visualstudio.tools.applications.runtime.dll",
                "microsoft.visualstudio.interop.dll",
            }
            for search_root in search_roots:
                if not search_root.exists():
                    continue
                try:
                    for candidate in search_root.rglob("*.dll"):
                        if candidate.name.casefold() in wanted:
                            reference_candidates.append(str(candidate))
                            if len(reference_candidates) >= 40:
                                break
                except (OSError, PermissionError):
                    pass
                if len(reference_candidates) >= 40:
                    break

            return ok(
                {
                    "path_tools": tools,
                    "known_paths": known_result,
                    "visual_studio_instances": vs_instances,
                    "reference_dirs": reference_dirs,
                    "reference_candidates": sorted(set(reference_candidates)),
                    "process_architecture": os.environ.get("PROCESSOR_ARCHITECTURE"),
                    "program_files": str(program_files),
                    "program_files_x86": str(program_files_x86),
                }
            )
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def get_extension_host_capabilities(page: str = "", doc_name: str = "") -> str:
        """Read bounded desktop Visio extension-host capabilities without mutation."""
        try:
            page_obj = visio._resolve_page(doc_name, parse_page(page))
            app = page_obj.Application
            document = page_obj.Document

            try:
                vba_enabled = bool(app.VBAEnabled)
            except Exception:
                vba_enabled = None
            try:
                document_macros_enabled = bool(document.MacrosEnabled)
            except Exception:
                document_macros_enabled = None

            vbe_accessible = False
            vbprojects_count = None
            vbe_error = None
            try:
                vbe = app.VBE
                vbprojects_count = int(vbe.VBProjects.Count)
                vbe_accessible = True
            except Exception as exc:
                vbe_error = f"{type(exc).__name__}: {exc}"[:500]

            com_addins_accessible = False
            com_addins_count = None
            com_addins_error = None
            try:
                com_addins = app.COMAddIns
                com_addins_count = int(com_addins.Count)
                com_addins_accessible = True
            except Exception as exc:
                com_addins_error = f"{type(exc).__name__}: {exc}"[:500]

            return ok({
                "application_name": str(app.Name),
                "application_version": str(app.Version),
                "document": str(document.Name),
                "page": str(page_obj.Name),
                "vba_enabled": vba_enabled,
                "document_macros_enabled": document_macros_enabled,
                "vbe_accessible": vbe_accessible,
                "vbprojects_count": vbprojects_count,
                "vbe_error": vbe_error,
                "com_addins_accessible": com_addins_accessible,
                "com_addins_count": com_addins_count,
                "com_addins_error": com_addins_error,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def get_undo_status(page: str = "", doc_name: str = "") -> str:
        """Read Visio undo-state diagnostics without mutating the document."""
        try:
            page_obj = visio._resolve_page(doc_name, parse_page(page))
            app = page_obj.Application
            try:
                active_document = str(app.ActiveDocument.Name) if app.ActiveDocument else None
            except Exception:
                active_document = None
            try:
                active_page = str(app.ActivePage.Name) if app.ActivePage else None
            except Exception:
                active_page = None
            try:
                current_scope = int(app.CurrentScope)
            except Exception:
                current_scope = None
            return ok({
                "page": str(page_obj.Name),
                "document": str(page_obj.Document.Name),
                "active_document": active_document,
                "active_page": active_page,
                "undo_enabled": bool(app.UndoEnabled),
                "document_undo_enabled": bool(page_obj.Document.UndoEnabled),
                "undo_levels": int(app.Settings.UndoLevels),
                "current_scope": current_scope,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def keyboard_undo_once(page: str = "", doc_name: str = "") -> str:
        """Send one real Ctrl+Z keystroke to the active Visio window.

        This bounded qualification tool accepts no arbitrary keys. It exists only
        to verify the exact user-facing Undo behavior of QoL transactions.
        """
        try:
            import ctypes
            import time

            page_obj = visio._resolve_page(doc_name, parse_page(page))
            app = page_obj.Application
            window = app.ActiveWindow
            try:
                window.Page = page_obj
            except Exception:
                try:
                    page_obj.Activate()
                except Exception:
                    pass

            hwnd = int(window.WindowHandle32)
            if hwnd <= 0:
                raise RuntimeError("Visio active window returned an invalid HWND")

            user32 = ctypes.windll.user32
            GA_ROOT = 2
            root_hwnd = int(user32.GetAncestor(hwnd, GA_ROOT)) or hwnd
            SW_RESTORE = 9
            VK_CONTROL = 0x11
            VK_Z = 0x5A
            KEYEVENTF_KEYUP = 0x0002

            before_count = int(page_obj.Shapes.Count)
            user32.ShowWindow(hwnd, SW_RESTORE)

            kernel32 = ctypes.windll.kernel32
            foreground_hwnd = int(user32.GetForegroundWindow())
            current_thread = int(kernel32.GetCurrentThreadId())
            target_thread = int(user32.GetWindowThreadProcessId(root_hwnd, None))
            foreground_thread = (
                int(user32.GetWindowThreadProcessId(foreground_hwnd, None))
                if foreground_hwnd else 0
            )
            attached = []
            try:
                for other_thread in (foreground_thread, target_thread):
                    if other_thread and other_thread != current_thread:
                        if bool(user32.AttachThreadInput(current_thread, other_thread, True)):
                            attached.append(other_thread)
                user32.ShowWindow(root_hwnd, SW_RESTORE)
                user32.BringWindowToTop(root_hwnd)
                user32.SetForegroundWindow(root_hwnd)
                user32.SetActiveWindow(root_hwnd)
                time.sleep(0.15)
                focused_hwnd = int(user32.GetForegroundWindow())
                if focused_hwnd != root_hwnd:
                    focused_pid = ctypes.c_ulong(0)
                    root_pid = ctypes.c_ulong(0)
                    user32.GetWindowThreadProcessId(focused_hwnd, ctypes.byref(focused_pid))
                    user32.GetWindowThreadProcessId(root_hwnd, ctypes.byref(root_pid))
                    if int(focused_pid.value) != int(root_pid.value):
                        raise RuntimeError(
                            f"Could not focus the Visio window for Ctrl+Z: "
                            f"child HWND {hwnd}, root HWND {root_hwnd}, "
                            f"foreground HWND {focused_hwnd}"
                        )

                user32.keybd_event(VK_CONTROL, 0, 0, 0)
                user32.keybd_event(VK_Z, 0, 0, 0)
                user32.keybd_event(VK_Z, 0, KEYEVENTF_KEYUP, 0)
                user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
                time.sleep(0.25)
            finally:
                for other_thread in reversed(attached):
                    try:
                        user32.AttachThreadInput(current_thread, other_thread, False)
                    except Exception:
                        pass

            after_count = int(page_obj.Shapes.Count)
            return ok({
                "page": str(page_obj.Name),
                "window_handle32": hwnd,
                "root_window_handle32": root_hwnd,
                "shape_count_before": before_count,
                "shape_count_after": after_count,
                "keyboard_chord": "Ctrl+Z",
                "keyboard_undo_sent": True,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def undo_once(page: str = "", doc_name: str = "") -> str:
        """Undo exactly one Visio user action on the resolved page.

        This is intentionally narrow and exists so compound QoL commands can prove
        that their UndoScope is exposed to the operator as one Ctrl+Z step.
        """
        try:
            page_obj = visio._resolve_page(doc_name, parse_page(page))
            app = page_obj.Application
            try:
                app.ActiveWindow.Page = page_obj
            except Exception:
                try:
                    page_obj.Activate()
                except Exception:
                    pass
            before_count = int(page_obj.Shapes.Count)
            undo_enabled_before = bool(app.UndoEnabled)
            try:
                current_scope_before = int(app.CurrentScope)
            except Exception:
                current_scope_before = None
            # Execute the same built-in Visio UI command as Ctrl+Z.
            # visCmdEditUndo = 1017 and is documented as Automation-safe.
            app.DoCmd(1017)
            after_count = int(page_obj.Shapes.Count)
            try:
                current_scope_after = int(app.CurrentScope)
            except Exception:
                current_scope_after = None
            return ok({
                "page": str(page_obj.Name),
                "shape_count_before": before_count,
                "shape_count_after": after_count,
                "undo_enabled_before": undo_enabled_before,
                "undo_enabled_after": bool(app.UndoEnabled),
                "current_scope_before": current_scope_before,
                "current_scope_after": current_scope_after,
                "undo_command": "visCmdEditUndo",
                "undo_command_id": 1017,
                "undone_once": True,
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

