from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.95"
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
            build_dir = workspace / "energologic_visio_editor_addin_v29"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV29.dll"
            source_path.write_bytes(gzip.decompress(base64.b64decode("H4sIAAAAAAAC/+19a3Mcx5Hgd/6K4nhjY8YctgGQepAQqMWDlHAniDwClImQaEZjpgG0NNM96u4hZ0whQo+wZJ980ln2hw2HL+S7vdjYbws9aEEUSf2DDcxf0C/ZzKxHV3dXdffgIftulxESprursl6ZWfmqrGHsBztsfRwnXn/+zFB7cpbDXs/rJH4YxM5LXuBFfidXYiVy78Nj7u1LvXDL7fm/dLFq7tsrfvB27tVNb1s0k/8wDBK/7zmrQeJF4WDdi+75HS/OldrwRgnA2Bn23OjqaBB5cYw9zpX6uR90w/uxcy2M+urb1VHiBbG/5ff8ZCxfrvmdKIzD7cS5vr0N7cE0RN78mTOvu3Hs9bd648tsOey/5kO9ntdMoqHXuqN/XBS/NvwEvjeuwrzthK+EO36HYaWQXe36SRg1zLVe8yLsfrMx48w5l5wZLHYmcPtePHA7HtOgETAO68yDMwz++ThPgdtjsef2vC7r9AA+e6k39DbcaMdLqBAviv8Gw60edApqMf59tTtv+ngzvF94HycRTWDQHYRQhn/fO1PSjWWv11sNtkN7JxaDzm4YWTqxNIztXza8qO9Di5YS670wMX5YDoOAY17tMWrfX/Hj5AX4cIUhhqx2Y7bAAu9++r7ZKqmzBsvtRSW1ymdT9fwG9q18Ytd33YE3xeJ2Q/jrsdv9vu3Tpv3TCozDDTreWl8Ng/6+XiQaev3S0O82G7MXl2euzi1eO3/xmWuz8L+rz5+/dO3SxfOLl5auPreyeHV2ee75hqxC/GAbyGFjPPCaADfzwlFPq/HK0O2JWumY+Ue2qtESJ6PFgZ+bRIEC8GFlOIDqbuK94m0n+sIaitz0d3YtZdbCeyUQ8GtJ5XUP+SQSkvn7TW/g+hHS+43Iu+d796uKLQ4GvbFlMGEHZsTSj93w/g038CzduDpyOwnwzthLmgIpuqO1fltiSHe81jdWXOz5O8Htpv3bpvnbkht7y+FgLFvbGqm2tsbqZ5K+TcZWOLgEx4Wz5rnxMPJu+Eln1zK7Pv7eGiaikIA3wAfL5MiNIcsdyqnquedXLiw9BwS1vHxt5vzFZ5eeO790aXHl/MXlxYvLS0tzy9cuPKeo6kYU7qx2MxuWo+0xi92uH7w2d0mVX0ZGpGitmX0kQlwcJmGRAk18jF1mqysbme14rl2LQgeRfw9IjoVbbyKcu+6AEyFJE9ZC3e5qsBpwRlUsxttCSYHd3Yb/F0vArPfdoLvkRuzulhuVFVgaJkkYsLtJuLPT8/hTsfzdfIWr97wgie8uw2Deot8vw9eeF0lA4rEIKfLcbhj0xgxEIm/E7u4AnfOffJ+h301VDf/9Q6P54gsJiQBXXv/F2Warfedc62y6xcTNFy+/4dyGQlF4f3Tlje651jtvOPyRnuBjq9HOwKRmrg+48Li6E8AOuQzkxd7JfoFhD3xAh1b1QDqqP8gBK4f0i2L/Zcdll//u2H3O74H3Qr/Lrgdp002BcospWrYZCKx3RZG1sOsx7Xdb4uiiRNE2TMQ2W4wid8w6wzgJ+y3V6oNM93Xch5lZNFECL6ejP5aUz9lySTRmD4Bbg/QJQ9sN4yRTlt4413l3F1iy68fzbI9Bi51dqLeXgUWt9XobGhHonBH/GXeVPdsUAwdNEaKJM5q+oUm96fWBlfM5rTuDfMT+NmsS3bOzgF/DXo/9/d+zs/TGAZHCjwdhDKvPeYOz3IMn6LJ16BwUh5RbCJ0nmEsAczF+0HqaXU3R5VZx5XJcL7d81ASMwTqKPNIYOpvFv2wB60ISQsW3Bl2g+WZhoTL9yFZcB46VDAdIjT1vyrpL3o4frO8OE9AJA0vNAkOS8wmEZcEfqWOZv5I0Tyumz5Ncr2QXuCmxs9XgHmjP3esDL6IyV0cdj1hPs8EVyMMnhw/Z4feHTw+/Pnx0+N3kk8lHk98dPmnkCAr/RV4yjALLtsjXxbRCYsQ0W0bStUyAnCJojnOgbGPpJhezLfzfAmtq71pQzdGes5WBuAGPhUAEtV8FpRgA6PJKw0QkgoawvddFtTvzOeyWOK+VdQAxm6J8m63FIfToRhj7OIVOnx43wgF88WM0GzivubDRthkJYfP6ZNajdGASrIkKmQ+fZ+fhzwsL1B2YkCCJwh7uO0PQQpl/7lyrAsvSORSVWYfloL3u35k3Yuc6TbBz9W0Q3OJmx9lwd9qZSXa4eORwhGi0Ga+BdOhGfgyzcz3qojbeahUaKHbVNDuAP3FBgpo3Vt0CKeGt4qe9M/YnIsFsi4IGz1R1rJnvVCu7QogygCnimWTgvnrkNQoIU/7I0akEmZxldyAYbgklZKvAkuaK59a0rPJ6Mu4h3SFF0Bt6QRRBj6I/pe2HYS/xB2i4w34cfg6c7NHh/uE3h/uT9ye/Rda2jzwOWNtvWd1BCS0IJRGYM2NJKUJzqbG2yN28HvB5oS+tsk5QCXZuwSqly03d2l0bF870oYCHbDmJelzO2YLJZcu4SfdWvG132EtszDpTCDqyDQTvHV0m08paGkwFK0Fx7J13WEGuKlKhFKBg0VLVrIkCZ24xsAEhqIn5lVIadi4vcPIvS8i8NsJrEVCpucQiyJi4EOVzYDUVwbYidmH1gUw452db80UBxW5OssGpAJNanFIA+K5WHzSDlKF2RWXdXJXWzhixyqobrFkplPQjmT3aHHnrAhR2LyM4AlQLnjSRaQsjjWal05LSCdTUKUyCafzwp98z4IpGJsgFP8EuocC+0yhtrpY1Lh1CpjgvR+a6siak3S6FQm+ajVGjRsVNQ8VxRcWjWPzSRrA2mc03IjeIt4mZEBIhGKyPFdG2V9WFaY2FpV0QiDdNH7KGRo1CswbIUiQut0RquJ0rqGyVZdCV0TKFwx1bjYyInPo4eM0sg0OpuOtHXNU/ouYhPw/cHdxzUdEgtu7dgBc5JUU4qhhsjj0oS3aFe16E72GX6HMGhqNCYC1zO3E4jDqe9EsBFCzrkCMmdlYTr4+QVlea2IaT8WBZAHLznAbwJS/R6i2N0clFPWozCXS1K37jN3ZOm8TctgkTzOFTQYJN4LKN5mpdDRDH5MdrkeeJ5nHBWtmqzupKm/bvl914d92Tjq78WCV74l1Y6+c6AHrIDT+43Wix8+J7dprVdzPYcSnYzQqwm428HJ768nh57sujCVfOPdSFvGhp3IQxXWGjFsi+WK1g+yKcgvJiChXAXDlqko/n9TuyXeIjGTeiKtE01edEJmuvuTEQX6a6KFCjMorwdaoCg/Nc0LC5htsFjNOGWKHMZkmKSMhOT37XYATRp4l0NOyunCPgTPqiE0iFSG3bN8SWPWtTYk65Pki/0YqgQ2lZ69KUUs11d5ueyurl7Aw4vcCtaIaIDJHRkbHrVtAN1/FLU3EBdoXNsBczeuBldvhHkC6+PzyYvAt/vxQK2eTTyUcgiXx7+GjyAYO338PXffj7tMEuH6X+d/CAtXODIdWlA6qNb1FHkmhcgSw43pVwud9tzs7MXTRMssSmrtxiupntgIeJOIrHm20kNLUpBG6ZQdOrQmr+ajqr3peHD2HWnkw+OPyOTHwk6H2HLyafMJD4+LzCzy8nHx9+jZIh/PcEXn1qsvyl3Ala56xJjQoZTdp9W+WUzwCEKZiMheB5N+rahOQ6Qa2jkDz+U72207yEXiD47Acbte+Zxp2a8WbIjJdHCoMFzz4NiG0aB7FMAZ/a1/07rVaKhYIJwVtUsxUzmQYE8SJ8Z+wbUeQU+H0AGstjjrKI4YDdk3cnnwImgzrDJv+D0Jm+T95H3sGIzRykmC84CtU/mGf0Filmf/IhEgG8gIq8Afxvv1FrxYR0ELhI/ivCpSjxBsQ+mK7mADfvweszd1BEyO4mhRLzFS2My1qYrWxh1thCyoq4SjICKHJEqMGlj6BZNPr9giwjNw+Xx2AFXXKupphLb65vc3lVBmq1zNxRh/ECm6nJBA//Fzo1YNlgm0Dm9kT0Rds8EBm+VPhweNAo4e/QGu+mnXEIlNe6a5pboZJAYVIMcLto4CxcboBEjWEWzqvefQq3QOGO28KbjVcbUzFFYM0JB+8FiZ+Mm3Ze1067YmgCTRgyYK2p5kCoAfJDm+UFYPqciYYzwAZlzt8ek5HEDtkm/NdqQe39RROu5swSHgo0ArpJc3nYg7ceamzO8jCKYALFq7aRa3Hjyr8qnNpnk/cMLGafPZjZc9jhn4DFvIcMiT2Y3WM/fPgZezC3N491voaSB4dfsQcXLs84MzN7DHjP43laAdzLn0I1rIjAngqZ5wnwfrHCCOEpMMSvpRHH3NuCsFaQvjRxStP22ppCBwxg1Jov8Yhs4yr16ohWsM6pIEmCZlssWquGWzGv5itD4n9q+Kes4etqNwvvB0KOy2jjWcX1uMo+NPL/tnZ/AqrU5ySekFBDrOBgamWqHoTTU6cUzVVspVViwYqXwManNibXtHcYquXNIqUoKnmUWZGTghFKQ0oEKt093dPZOt3/b/ZNIX5z7PwNl7mPt2t+LzZgDvbJyW+KFsNm3R0S9MaqXbDezqc7wSq2O7GfLZ7WfjYVjWUcVJ9lzBD7aJd4D9QwTV7fh6WAXSlnEuXWknPwqaj0tZnidU/Z5NeAKk8mH6dAxDbXcBrzdabZ6PvSPF9ljuo1N9l1Frdi4BktUGNmvfOXMA4wfT2Wr+sqOP9bI5QDruw8xOE+PfwLvH+fHX4x+ZjHP5ANCPEXZvhxwyIvHF8OSk1EPtmHBBvYCAevePe8XinacIHg1RBjtnHKibdxDPILaFNnL83tfP8HBOiPcPEPv9XYxilscXn8909jYzlhBi0I0DxHl9lt4MLAXX/yk59w9tpmm8CH9TfAWTkljH9UtmfweooVHKQu0zqOVBvP1ETMBG0gWyO7sJigVWRrPP8jUP7vyFvP7eGfssMDNvlQ8E3+BrkdrCQaOEgt/JIioEA1nHwyef8/CP0jDtT0RrwHrFLN6FNEfjl/8FBfii4H89fiNIiBOBd1LcR5l2DUqW2kt9ikfJOV3t6Bk/HRKXNb1DllF53ZDFzLeZRzIE3pOcp7j1K3kT+lwwhtpdI7xFmKNGB9WtM7VNNDVFZTcw9Bj4+JczbnUD20U/bv42AejMKOedkWCshn+jw9/klHAe1f1B2j/wEppIbbIQNxbIY4a4M4a4UIeKv5GLrKvVAi/Whm9M5xbegVdnSkr5fduKYtvTWd4b1js7oXl9OD/eFvUmh8gCo3sA7r3vfwMvu3P9zOyYtteAcy5FxehpSbdn6f5hoOV8U/L1gJ8NNfRf7k0YXiwR358enbmo8jYyEyq60BRM65utvDHw6/EzuBsIrgnItlkVvEF7QsIApxJfSAyjwGxfMxI01iP6+dF/ypU4mAcsq2/YhOo1npLC5yMyn3k9FGmXkJUpuWEePJG6MGYiLxZcQ7adSdVg7NwctKkp/RjCKKP5l8Ks8qPGW3DUKnpejmKQiWdWW48kiL+Ih75zoXv/jGV7oa0nhai4PWk5ZPR7HW1o4Y1lNim8YQBWHiXDAwR0W6fFpgZ7s1AGpFwo18F08bWCbkdJlgNjj4+NZH4nDSBHmFNslUlPS6+CW2cTcqnMrB0zI4EVHCrcXE2ia/Bi73FTdGZnlcdvUmHzO1wk+J4U0+mPxK2i4fHj6yad3JbLkXBNlXPXffXBWg2XJAav5EiyBWneXhp7IqVKk5n/+qh1hkDpbSdH3MMELnXRIY0Nz0WJhm4cVjiz+OwsPxmJi0mgjf3FzRzZfMqndmczPB0gRDojMgMJ2QFVWJl61aBuKy6Pcy4zAf3QsL9aNb/gXxklGw03do7z18otl7v8C3k9/CpD4Uxt+i1nbCIskRCJYT63oYJc0ulN3BI1HK9dDztoHPqccIDw3VjezFutWOdCxVShA6SGq/GiYVqwQq0JBjq95ZhbcOP/3qbYQCzzPt29B7r4IjTi3xUTDce+QLe5i1AdST+R5mgq1M0tMW8RnJZiTjsQ1jMRg3O6hQdlIGRRBadcf1GQznoeg8MaAnxIAe5qLCJFkRq0rdKLgPIC97wlUczrMeGqVCTCYgTj/wvq/5gew7vjfFwm+A1u8pSmpL5LsCCnTPDXSTiLVksyxQIxYUyV1nsS1oIxZ65ZqbTnfqwGuVnDMXAaoaztU6Xp6NWCmPVNniQSrp/J5jvsXq6aM7d1qpdRB596bvAew9s+UmE7eTDIlz5DcwGnNxE8N+2Ojc6FwQDZwXmw2O3Zl75niRtlPIubAhHXACOSCZCB2QXHgqOI+w0DfcHwG7VtYwALswH0hbjKOWbF8nmoiiH3IUYACOlEZmOyIxZxk0IdiWOHvy7ygB+/jHJnLq3Z8LnDYfm1NkoCep6tk4CkMsAQUQ56UuLeXjBwAEbZKz5RZwRf6y/FyFzVstLGqIhrg4TPGR+IFJkTuVyLuqyLQjRqRVRaZNEZFWNg3Hjck6RlzWkWKzTsCNPl2MVs3gqb1aYWflm6yDioQfdJJmesLvyNaKfKTVgUWuQ1kH7Q/0dh8VCKmcSVvuvtLUJh87jOsgPCSnjkqV3TNaFLHDbRs/prlCO5pP/HPAkwFcD3qAJ/Qm8t4e+pEH67zt48b3o8QQn5xdF2Ti2enEfD4lMtI8L9ejwAsrnjN42NTJSqufwR7LFchiBlqQe+UpMeBri71eroxRq5TirDxYKnK4eV1Jzghuaej3usv5L3RmwwRTk7k5WBk7Iv+CiO5p4HNyuq2O9VSrQFUJUjikyH3Y2EIxAiirAV8boPLVSBB2FuZEsThhWJWwW2W7JI8dyM8f5Sdy/SBuylf/1RvzHZmAk6SVwi9rQE1aUeTyFPd9STcIqzlBozCfCzQMk3AlzeZd3Y1fXW1TVoMtslVqOsX58LRpGHKAtY02/5TTPIG2vkKGm3OMUCQfys/vkTPtC6VzYmE1EngndPSHFPSnfCpVqGuiNKATN+j6mDSvBIGNNa1YfM+NmDdA5FVz1qorjhpaYgTKBKf8uOPAEfmqcakE/6mSDIWkJdW19bejhGtaN8L7APB2vw+yljfgUmobzSrnmPZ9U/9+Ab+XaHBdtPvNOjPTBiuYpoj8p3z5TJ8fMDUVTE1LG3N20wv428Ys3fQAf9uYl5seNvEhzcQN77pszx76kOKSga75rMxyZ2+rdkBDWQq2DO5qjctkCUK+otVy0mHYsicQ20uhTE/nfxbHUB+LmFztFCJ6B56giUmzI2nyFr1IE5FydGfNH37zf9ksCUutRp3OXoHSeohhWgBtbPl5AFzVCswWC2B84owzY7Am1A0vyo3/oTgjh2N+hK+EkAHlHvEQAjRif0cOGRBYJ78qzskP7/6BoS+aPGePMZQPyn0kIB/IaRWMkRscSN6d/MaU2xJ51ZZHnuTMXGVLiX2568WdyJdp8qYwkjyY2bssJKQHs3s6P42dB3PwggvmPFwdcIjHddPRBt1Cgh2VRKR+z6X0rL0jktaetTUtopEmCreU8nD4R9qrcHkwgPR9XVrksr82HUWYpcK0mcGt+G4v3LnpxZhGzg3i+5Rib82LY5DMlsIRT76WwSpGyonWy8tvBG8Euc6hwoGvD/9R6D4YycCtLDiYFxvZvJSEYdpg4XPaB54mL3Y2vfjVUP+wCojq/LchzHjx1Fx6oJnGdHYhM1SElU57RiZXB9ERdblDDSlHhgC/LzS4Ck1qequUPvqTtz1lNG8hp+mobVEhihjfyqN8+YkpQ1PVVHQ87bv0EK9TTkWnqw7LFHMn5bf/W9fiSMXecrtld6sUkhP1OXnXzExUzLtL1Kaj8/S+EZte3TR6P3jcjmhYKmUlCQSkwjmor2qWC91GlXPQwswhdRVKv0tVWjWF9dTYqpqr0hFL4Y3rwdOVRzM8FC0Cj/JAi+H+fNeLZGSsUk4obFsJbWaNY2RTNcakY1AAgfO8TazV1wc7pGTFqVUPoB8S7EvjnyXRUMkGj6RGRgejRMsf/oQphZ+XGR00+mbyQSoF04YO2/Q+KsJ0DDAvALYZlVMbJBT6gP7/PsbeYLXGiegWOFs43nSyCvZc/FxtsEVAak50nULfKNY7u17fE1z5MgMZEOP9PgYBGEh02IGCbu+8ONf6Bd/0xRQUFY28NKDa+eOf8+3kNZRMA1zKy3UdD02yw8/1ctKTng+Myp4gmHzsvBFx2UxIzv8FlrPZoJfttJkN9y2vSbhMqfQz02lIapwLQskGn+i7mG2n07LvSVvrlGbYFZ8+udH4BcLPtDfDwH976Indw1qsTpI72X5lxvaSI7wqANIinp7l3VVcGZlx1vnTEiMi0s584s6NUiOaQEMBgfKSxwaOZVhjNSj7geQfZ6WVbst6bpzY8u8fefH4PQNpnlTTyhm4GL90oJl2zhthnlTRRW80X8rnhAgAvY5pPng1kVcbQ/IxdBX18S/FqTdxUoiSaoHiTdo7boZY0REKUU4lqJ23CRg4Rgd8RwLzbyk1V4lnHLNW0BGE/FGlTwSLUv3jrIyPsU09PQLGZZCszdUqwW5Wuzaky1M94V9nFwTYGy7inRJn01dr7qBMNCYISYiOJ4m0ckuqYEw6hCtsJ3IHuxbelClZgz9Bd1oc4Ot+944pwKgejGMKxWUh5qcj86aXYqZhDBvRGATI9IsmB9sFM1FbuykI5iMVkEXIg7xfszWt5KbWhlh3Htp8Rb1c+TvlQuD0ctbZzFg1oqof3peN6/sWWccXk/+OEdhoBXxCkX6oeMP/pWQJjZ7vIfkUI/IfMyjxK3w1+bhRRocdwKoa6L6euJ23xN6DP0WV9HW+ApVybgzjXX06smXuA8vwEJ+xqEWmf2DUETtD1EpEG+GgaRMIcHR8rx9GpfpYhpwDJCyOOFDvTkuDpdY4AHDaGIPyuCrNJcU9g4q2OEO9IoJYDC4sc/ka7Aj7+5/8SONH2qaVERHrsSaK2uGLVPQNocqvYm3SZgp8pzoqsMhbZKPTB0n8kyU4OBNzr5/+kBET/LzP5Ndkx/9W6GmPVNzwfE7t4sJJpp8GL4UK0xIFC04KFU5XGdDGIQgbp2UTIOkml8XdnL9dBroS0NvKelLd9myrPBUbNLaJKgw9OfzOrHvoYfEDumbbVMUdaVVexbMF1ipHpfm8majspK81AA8xc8xeoDG25EjHtnJXaGAtObxxmZpFsM4Dms84M9lyVPuc6UvurM2rHpBfjIHQ4ooGkne1lbuQebLikAC76/a2ERkJ+s/YXL71VC/rZwLUUxstrctJCJA8YgrVG300ZTvbcVi8zUJpjfa0mSCtaCQDFnx1naJy/eKxekGTFvxLE9HI6udprYQ9cYZcyYB8Cxyn6AG+ECqeOWpoOc85IZ3g35A2+ZHUKb8SItzB5EM8N6xxX+k+1QyJJLL9BZXCDBN+TG+/Bt0QU+DgsQ9qC6PTDzI5xfCFjTTVjLzAsfd8xXzQzZ4Ce1MhBzMDSJw2i8w50hVF6WiU+QgbRXhI5bSI39IcwzIIPltMf7ckzt9kiNpUKg16zpZOib5YTZx/we2jfcYevsLDTzIw0W1tiPKXMVzZwipO19BGJG/RQKnTdndGsaKKxIWqYjWy61VqNRDUmGefRbOBOEpCe2wmZNtuR5BAoKqdC/EzUWV5Zu11Cx0x8vJYY2ZUwcLNtAQuVxR7MqT9n8KPBoM7uhuNpEpGp8aqvWjynAFVEscMCtNTsmdwO54UmwhKieHuQQrJnla+WzxBRHD1owXxyMbN6FDQDAi+aiWIHXUrgx7T8tMHQ9W25/HTQiLY/KESlIuat+CBaafwbF25IU+uv/FcVzlh4mG9kqO7JBy/MNV87CsVQEZ6qlRi+7SzxcUDgkeme05k8jTPNixfxvctv/wN0l96J3WWhIgMcYb4aLhhopK4qvRDDmt67fBP5vSiscgsao4APECs55eyFEWgpxZ8px5m1D0DovPrOkEyuDqC5U1dX0KC1NIm4QUgJReXVyyouFY+cnHv5hEGaau3mrKBNtCFNTQGRIB7XgR6fbgaJBfmmgCs4hA+rszMfGkkKF9tOWUUl1R+KTUiuUSwvO589PlBlNKWIUnPYt2KvchB9GhYTCSW2SG2fxNxoCnyCrQkVJp6mHUdtsOjylZvlYe0m8lDMr6iB5v64mxE4xtuFHvpnVJqxuCb38dUJK8OUW6i23zxvo/E2/Gi8uVts3AoGC4K0kRCVzQPebFHdQ04hehRRavm0AGKLeCpQDTe3GhV36trOIpa3F4SJT5kXSzM7fXC+173+v0AT6dakG96B9DRleRMh3Iazekoy6dvDz2yKTTjlVF6D25HiUFuP5pW/M8qketTnlShsLsAhv4FP9F1rZgKCj7qSvEUttFyJM5l4sqicea8Wi1Mlf4Lk5ukmIzp5PyldbJZ/Uc06ctb6ivC63DWQiR/1KJrmv7Zi6Xme3aZ5V7ZO3tWok3KfKg3reMSWjbbPOVPTzMXpJb7ySeTT6Rf8BFsEu+mpwzoHj08ozX59PCbyW8dxgPLZXA20Om3/ASl1HWQmN/X7997zIPW0Ual2bjabPIReR+/wP2JxEe620wlLMb1dhrHo3MjfZkoqk5EjRFY3x1YogosgQCnEjfL98daUbN5oc5Oiqqzb/LOvqk6iw7sbF/fNF3Ol5riB6/n61H/3mw5qyt3mAbVFL97NG1HSFPQdqk4k2HeuoBRByMylSN+lKNWNMh0SCBAkwpYKCcWGmbOrE/xutVRhTQGa3hYndlQm4nXywTRl+d4JusC1hBSxzvviHhur6cSOs3WvyyCq5dohNnXI6XUKW8VJtGcfNziyY5k8EMxx9H0Mmj+gHtp9L0dEdTgjxQ9j7WPHTVfjFTxTd5uM+swMZnykJ0UwYTcI7Rt3jjIF4Tu9tAdOtnF656VW346TP7FOE4zh7FzGXN582xNH89Dfnfaet8V/nQdZ9u0oZLt8F0e9/PEYHZ8QtvoY3p1kB6fwk8AXAsEoim2OYXO8lwL+mjwTQ3HjmA8ULom18nmT0+5SPnNdidHaiKXis5x5VBzRaqYbdWYSe9IA+uzysbq1WDYB/TY4oE8pTqHrHmfeKuB3eaCpzgLXvH4UBbxBqVa+oOsyftc6v2fK7cbaIJ9QZ43m+9UcoUSu3RF0gfpRywELosmuJ9jWZjxMH64XuKFXPqBn/2M3Yj8Poh+0vEUbuN5uWT3MuPX+PJ7ZKU7MAZtpCdxir22sQLlEy/Iw4y9yAem8UsvTg+00eSv73owjZG37QFbQ0/T1lgwfxoGcJhd0GSSXbcAkmryJGEh8toYZwEP9Q577i3m9sLAY37MgjBBPhH2wp3x+djd9pwjXoHXkQPWGDq9mC+5BFrco4tkyq/DFaQqgSlKxa/1b4XO9Yn8pQIgp2sEV56IfxvwHae4tFAS2ouQXaxUHZx+65SdwvB+ZU0VKYrECB0kVERzBwveqrI/vwgo37DvtXyAZc1thCfXmDJAFWzFaWspWtfMblt/9y9zVyouJM74XH176PbiplyQdo6/tMVZIJ721I+B+K9HXbKo7QTAf5fd2Ks8CLhG/ULPA/+1wO6mdl9s6aa3440c+tjkK1ViJTmrADnrww6wkriOpSSiLSet+lIUDgeUU0EAsa7mi4yb1rld3QSBjspUrKMV/OVy8HP1wM+XOSxQzND2sgcstZAqXJXJRiLMS6AFdKjdZW9+yswfUhLN8/Nrbq+3hSHWyD294J4fhUHfw4PD9/H4ZbrhhFuwm9xzxXGeHdhR+n2v68POnLvCGIC6sBnx8/AbocM2dn2+/wRk3sBj2fFwMAgjhBrAkzfCa1z8RG0u2BncUGLHtOeKj4Vz9DA+8cnEWVLnW3yrmSWrliM3sHqsptyZRrJCrginNEwIc3cHZkWnMNFlwynIs/2UpKxyCCLDtlhDjjN9iawNwJ5Rw05SWVIqVDsSHV22w2wchXbkjkh0cdPbzoyPv5VwhUfNPj0aneWco3x5YsQ+yRMzTFC23mb/0PgFIekbTvON7rnW3zXavOT1AU9PovFhg5VCNaAWtirRU7Hr+vxqAKfjf2XaF96hU1M4q5HuIBexin31KpWtetKcydh1RIFO5rIx2kCrpbqASzM2KUQrdaukGGdhgU0ykn10uCRQj1GV2CCyTd6qbvPWCTWKpJCVdwIakUZmNcQc9s471l28CP3WtODLjNGEw6TdFwRKNWGVomStlKh0GF60p8fcWLcDC9MQMAqHIPbOTCmg5GFLQUXbgioFFls4jq6JH02hlyEhaUDJlOkQq20vudS9R+unKDaa1mZggDGuAUNLvmGMUi1E3I8MQr8t2H5sKLteAAZ/ysqMeZlxjQXIpEMqn/52Lmd2W+oeFevCpcMTWBzerADU0NOY3aYD1uH9lNdOsV+TcKhHTYnRpc216h/aEm5uS4APdlMDmxtlUaTm4jSX/KW/WxTQe1e9zFoiqqpF1k0ilUs8VXiAORV3MTgAfU45Vz0yamV5SD8jtzy7kO3gdA75z8XpDTTwPzrcF8flvqezG99xF9X39HF/8uHhgQifFKlKJr9Gt1YFm5OXuOs5hjDOTSb8mo4Xi2o18Zzy3FDKGwEdDx+E9zO3d9XyxsqUVGW5r6Zx0BYSbOXctDLNlS5ZeJFBrsii0iKxgzTu2A/iAbcsmjQ9+U2eTbhSnSDjaJbNWDVSYm49YZNrPe/eUUyvSg9EX0O3vEwSlpWoZcStacjNRF8QcygxYVpMuuVzJk27paZPygtzHONnatM9TRPrX81U/aObq1OTdYrkcvbstfZKkgwXzdClTnCbKVqKPMdUn6hPkouSEqXvNBxf21LSapWgA931W9phEsx+nO5ijGIrn1T8dKzuR7e8H9/6/iNY4E/bCm/Qv05OMi9R0DKNbJ5UIzZVgGtwKHiavo6FjpCii32L4mpfL+y4PcxWoM5UZGR73pw6SzFfC9ymFdx4SnAowWHnZng23M2ihbfIXZ3bmxsh2iubfGxt0Sl+uoIgpj83W9V9QJ5wWxgQb7OfsrlnnIv1am2KWpuVtY5/9UV90aEQHSGxp9adGIaxynq3CxczTW+eqdHM5lTNVCcozR8xHclMpbfxEgM5tnp1x7LuplZ3c75yPdKkp9D8T7EP5xDYT/FGd5GGYK6ctZbvZyjE6Qs8rcCxd+TY2yNGFsuDkqB38J8qKourL1n3ABUpCzQWOlYzW5s0DH50snWM6OIclz1ZB4fsucV9YY42U4hQI2eoKWO1JVF17eySRqCZMGhrsWaFJu12u+simrWoSmsfRcjrlRppwOKauaL5qnIhC9YUf8CKXpijn/WdU6cupJy6gDJ9JFJenMnYo+tsN5pFW4oWGSvltILK2AZoahFlJOSTcblwwhtRssmojUmrSQwZib/jEq6sxfnXudwm9rORJuJSm5GQQ9TFNmPxonB18snFP6v4DVuULc2L4WiDpOVmpoSIs53mqPtxz1iojhgOVxz5ZIXAHi7H2A+pt9LwEyO2UhmFrFLM1GYgF19c3pq8mo3dQy0M2zY0pmJCF3ix/K2H6l/VjfKUHqDfb5i6Kzqljldn+owdy+QIFlKzmBqsUHRZy+zf9NLa4JobJ16ELMDWpHzdV4GrvM68OlekZw1G4VP2rs/NSCWdsrpPKdVRF+OsknGuY9N6TPkZee2aEw67josU0MfekQwi2fP3AKeP0ecQRgm758frnIthn2A+5y7mrrwVWRZiXooP5KaWcmFd/9DMwiumXqCcBDkzZh50Fc7yzC+8deDGor1c0xVuvaqV0OAjxnSBkRfG1ijWKw44Q73W5nSKbrzRQAGBryFdGKSbNDnZCPRIb1Lx3J7XZZ2eG8fsatdPwgghAubjnzNZHJAIBepul2IExVbG7gKb9bUTYIWCSNZL4YjdjRM3GcYlJV/FwxJ+59ZgJbwfsLvd0RRlx/XLbk0Bd2sKuMkUcJMp4FLiQU1XGQCrB+pNV0zeOshoKWwUzBcKk5BlFwz/EetdKF4jRUf338Pjw5MPtJsR6AREzmT+c7+boBX14lxOmHrZ83d2Efqzl/JRfn7g94f9df+XMgcx/mxeeB7EsmdnZoo5iKOEZ9GkRO848sw7IBhE7fVO5Hm58WHZpRDTqFFeD1Fbe+NAy3hMZwMYt+m4DV7dtRpsuPFbW3QjiuHiqGthIJUk/NlsrHs7ocdurQKBX7qWG8xGOFgLY+0KquxXdwvPaUWwiSTulozO094+wBsw3qJMoZ23+AAAYjud64uXZvICFFRHCZZ4BPxOgZJc29AvWs5bXGTVHS801fw9pQOiU+J0zvxTW/3OroeRSkUIOR96vj5OgiNKx+ryBngB4mTxG++l8ZPsQKs44T3vFXcM8vwNN/B6/Kpr6CY9zeV1W34RtlgMDplfrNbEa+fQ338gBsRP6f3w4f8EJGjGba+1cOXmMGg24S+nR2dliLHWQP+Uov/8bKvVas+0Z47d4mc1W6QGZ6dq8HNap4cqycdB5SDxUvPM+GZPoLnPqpsTg5umtc/0E8Z4wvJLaPSTzK0N1nb5mTpqmQ9zztgwymNhb9gP1gdu0OTvXsJ31B/0lkqW1kQQRiiAsdkBEJg8Xl/rhfd1tMZYd/5LMKrcdwNfWQphYvoaa5mdA/aMFVf8SN1CknlGXoRbVxvIB+dlR7QmnpqzIInlmJPqmGlVYGvx5L2JuP65e34mH8h7Ds2rot2cjjfetTnLbRXuTK7RB+1iwR/e/ec6LVJbbbpqr9iicSFVNyqZFDC6lJNmPxkW8pqPiiJHPJENkV0ka4N8ujTFgoE6zrXxhZl5/4WL86RxQ4ccgdk8fVZq91Avm7jHb4xBvr3hRR3Ysdtzz+Tn5S7Z8kEMap5/Zmamjf8Bf0Ipz/A6u4bUA202yWbpbnm9ByjjLDT+7Q+32+I+0sVhEmJnFnBx9jjTLQKAvhjYY412Ni3tzNnaGbcvFNrhyMfC7e3Y47mDNIKgK2K4WCZzUfIklPwKicl7wMjwhrKvrIh6deR2kusEXCVngwELb276ZszfFEkmPwreUc7g6WuW14nPF82jdEcLOhuWWZExVxSM7XajbR7EYs/fgSojugVdwRqXwdqsgDVuVA/VHXEGbxgmfJozrbE7htW3VBkTm8+SwdZogbB9bgZQnf5HZLA1Nr5OzKUTU+npkPnwd8B6vzncxzUoUM0FIzZvIdUYP1mBbxpIxQIcSeXC1KOgHGUckwqjuGhsKMFRXKw1CgncNAoLcByFhRS2Ogul8h2/N+oLmrmHNmRecmOP7MwbkRvEeK6Nb4CKrrcKlL41zr9JCmUSGzeQfe8vVMhuR+0930xPq/uFFdrqAGI8YyRX+GSk8K0+LLelSt9A4aTbE33O0n52caYWsv0LTznMZdKHh4+sW9qzRsyjVgGznzUvYN9zMY9euor/COtESSUzKY/1haNM4Wu8XlNjw5jrOIXzZ7obs5BC2YYBeDdl5G8NE48nIldLSP2vu4piNLAuxsnAHgIdPlsEU5TMvLBKwCYFM64vXXOh7HjS9MVWm/08cgfYVzwovEBkkhfYeM9KxGtdBxfLLO+Qsms88hrmomhraE6hMcxEBlPbbM0dSVPQQmoIegb3qjbjSJ+5+pNBF3/DU94hc0S0Erd4vgdc+ANKGHVguqAVQ+/lFa0ifd4XMMZvGCFlWuwrdUfrgZZ1it++ldM/LPeHOo2Cd06aH3KaG01VgTVwc6kU8IURlaPQQh6B1oa9xO/5gZzOm57bvR70xuJxvQON9ZbcKF5IfzqveVHidzC375LbeQs4VRgtrI/jxOvT79jhhjA5/7ptEKeHUv196TCe7EiiTS4nVz4fF03ngTndYDazIE468JmHOI3zpplxpJtc69g6fWmYyy9SKKUPHMRQk8Wmqpxu+Sddb9bpubAYgjAXdCJ9vqBAaUBz3Jl/yeNDpoxWOYdimWJoALP5h8KEH5vA2yEj4ADcVXQ9QMPoci/ENDJN7ffVe8BaFqOdmHll2Xs8B8t7N8VtnAtMe3TQkSHAoV8OymIa/B4h6Tx7GdlQS7rj8n7iLZAGnGzvvBquL2RX14ZBR50XcUszUHFXoUQYYRXnVZotY5qBwrWlucp0azG6Zq5Fvhd0e+MmHouokcu2sKkeOaW38O+R0xfDnIWNjMPlO6vpah6v4/fdHqUU8rrmjGIrvEyaVvsejwLOpNCGzcxN6iTQ5i21Wkzf3+W9EXhVgngv9oq2+OCO1AfuT2grSMVeF1bnT79nmnjzUN2/yEUcfrUZnzlKig9SVv566h8JKcQqqhqZJiy4kZbpDKMFvEmX7lzE6xBhDYD5qQJnF0ROXShX/GqOVYNihetyDR0v2KakTd3S6UL5wYLJxPUgx3vR/8FtlAuzz8+0NTvXwlxbGrkWLrRN3Hl2ppXjzoMj2LGemUHB98g1TXM8yPtw9YkVIraQruUJJ8CwNiNu/bILiOJFbBcxUOpmNG7+wJUJqmDax8RkXni+veZGO36QmbFnWu3sdkpw9uYZyDY9v/PWuYVdFVixNV/VeZJAjzUA8j4uXLgwU97ti8ftdtY1i3qb5JN9HyR09eCO0gcVlKMd58/AeSAY1wLCENxtAUEQB1zgTFXw2hs9F/oPKL0adCIPEwMtzDjPrJlWcG9eOf73zvw7rC2Gyd/sAAA=")))

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

            clsid = "{78D3B7F1-CCF0-46B7-B9AD-4CA4CBB2CF37}"
            progid = "EnergoLogic.VisioEditorAddinV29"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV29, Version=0.2.9.0, Culture=neutral, PublicKeyToken=null"
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
            progid = "EnergoLogic.VisioEditorAddinV29"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV29")
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
                "progid": "EnergoLogic.VisioEditorAddinV29",
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
            progid = "EnergoLogic.VisioEditorAddinV29"
            clsid = "{78D3B7F1-CCF0-46B7-B9AD-4CA4CBB2CF37}"
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

