from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.88"
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
            build_dir = workspace / "energologic_visio_editor_addin_v21"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV21.dll"
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

            clsid = "{4A78D159-46C8-4AF8-9CA4-5B8A5D25F421}"
            progid = "EnergoLogic.VisioEditorAddinV21"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV21, Version=0.2.1.0, Culture=neutral, PublicKeyToken=null"
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
            progid = "EnergoLogic.VisioEditorAddinV21"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV21")
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
                "progid": "EnergoLogic.VisioEditorAddinV21",
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
            progid = "EnergoLogic.VisioEditorAddinV21"
            clsid = "{4A78D159-46C8-4AF8-9CA4-5B8A5D25F421}"
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

