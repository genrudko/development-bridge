from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.100"
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
            build_dir = workspace / "energologic_visio_editor_addin_v34"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV34.dll"
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

            clsid = "{A6E63A2D-0DA5-4E84-9B2B-5B3E6944B5F4}"
            progid = "EnergoLogic.VisioEditorAddinV34"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV34, Version=0.3.4.0, Culture=neutral, PublicKeyToken=null"
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
            progid = "EnergoLogic.VisioEditorAddinV34"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV34")
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
                "progid": "EnergoLogic.VisioEditorAddinV34",
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
            progid = "EnergoLogic.VisioEditorAddinV34"
            clsid = "{A6E63A2D-0DA5-4E84-9B2B-5B3E6944B5F4}"
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

