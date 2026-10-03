from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.98"
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
            build_dir = workspace / "energologic_visio_editor_addin_v32"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV32.dll"
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

            clsid = "{9B2D0D65-A68C-44D0-A523-612148808DBD}"
            progid = "EnergoLogic.VisioEditorAddinV32"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV32, Version=0.3.2.0, Culture=neutral, PublicKeyToken=null"
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
            progid = "EnergoLogic.VisioEditorAddinV32"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV32")
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
                "progid": "EnergoLogic.VisioEditorAddinV32",
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
            progid = "EnergoLogic.VisioEditorAddinV32"
            clsid = "{9B2D0D65-A68C-44D0-A523-612148808DBD}"
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

