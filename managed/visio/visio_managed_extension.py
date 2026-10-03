from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.83"
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
            assembly_name = "EnergoLogic.VisioEditorAddinV2, Version=0.2.0.0, Culture=neutral, PublicKeyToken=null"
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

