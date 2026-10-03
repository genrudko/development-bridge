from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.99"
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
            build_dir = workspace / "energologic_visio_editor_addin_v33"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV33.dll"
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

            clsid = "{54D4E77E-73B0-4D45-94E2-B138DF35D1A3}"
            progid = "EnergoLogic.VisioEditorAddinV33"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV33, Version=0.3.3.0, Culture=neutral, PublicKeyToken=null"
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
            progid = "EnergoLogic.VisioEditorAddinV33"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV33")
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
                "progid": "EnergoLogic.VisioEditorAddinV33",
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
            progid = "EnergoLogic.VisioEditorAddinV33"
            clsid = "{54D4E77E-73B0-4D45-94E2-B138DF35D1A3}"
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

