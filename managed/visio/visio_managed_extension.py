from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.103"
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
            build_dir = workspace / "energologic_visio_editor_addin_v37"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV37.dll"
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

            clsid = "{3D58EA6C-A51F-41B9-A46D-BF0FB3BA7C5A}"
            progid = "EnergoLogic.VisioEditorAddinV37"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV37, Version=0.3.7.0, Culture=neutral, PublicKeyToken=null"
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
            progid = "EnergoLogic.VisioEditorAddinV37"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV37")
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
                "repair_glue_preview": "ApiRepairGluePreview",
                "repair_glue_apply": "ApiRepairGlueApply",
                "doctor": "ApiDoctor",
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
                "progid": "EnergoLogic.VisioEditorAddinV37",
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
            progid = "EnergoLogic.VisioEditorAddinV37"
            clsid = "{3D58EA6C-A51F-41B9-A46D-BF0FB3BA7C5A}"
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

