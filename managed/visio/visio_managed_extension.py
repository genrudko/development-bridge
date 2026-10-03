from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.111"
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

            page_obj = visio._resolve_page(doc_name, parse_page(page))
            app = page_obj.Application
            addins = app.COMAddIns
            addins.Update()

            legacy_editor_versions = [
                ("EnergoLogic.VisioEditorAddinV31", "{F2236480-88B8-42B3-AEC4-0707D59A14FC}"),
                ("EnergoLogic.VisioEditorAddinV32", "{9B2D0D65-A68C-44D0-A523-612148808DBD}"),
                ("EnergoLogic.VisioEditorAddinV33", "{54D4E77E-73B0-4D45-94E2-B138DF35D1A3}"),
                ("EnergoLogic.VisioEditorAddinV34", "{A6E63A2D-0DA5-4E84-9B2B-5B3E6944B5F4}"),
                ("EnergoLogic.VisioEditorAddinV35", "{D93F00C2-1C95-4D0A-A0A9-609E25B9794C}"),
                ("EnergoLogic.VisioEditorAddinV36", "{81705A73-9C25-4E72-84A8-F58E4C818AAF}"),
                ("EnergoLogic.VisioEditorAddinV37", "{3D58EA6C-A51F-41B9-A46D-BF0FB3BA7C5A}"),
                ("EnergoLogic.VisioEditorAddinV38", "{9974BD0D-D56E-45F5-BB8C-7A21485C6730}"),
                ("EnergoLogic.VisioEditorAddinV39", "{B42A3C6E-8C1F-44AB-A486-93C6AB3D8F39}"),
                ("EnergoLogic.VisioEditorAddinV310", "{D1C940D2-5A7E-4B4B-A92A-2D443A0DBA85}"),
                ("EnergoLogic.VisioEditorAddinV311", "{6D8D560D-1F9F-4CB8-BED7-5FCBB70B1F2C}"),
                ("EnergoLogic.VisioEditorAddinV312", "{2F8B22F0-0A1B-4E30-B850-09B1F7197D3D}"),
            ]

            def delete_tree(root, subkey):
                try:
                    with winreg.OpenKey(
                        root, subkey, 0,
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

            removed_legacy = []
            for legacy_progid, legacy_clsid in legacy_editor_versions:
                try:
                    legacy_item = addins.Item(legacy_progid)
                    if bool(legacy_item.Connect):
                        legacy_item.Connect = False
                except Exception:
                    pass
                for legacy_key in (
                    "Software\\Microsoft\\Visio\\Addins\\" + legacy_progid,
                    "Software\\Classes\\" + legacy_progid,
                    "Software\\Classes\\CLSID\\" + legacy_clsid,
                ):
                    delete_tree(winreg.HKEY_CURRENT_USER, legacy_key)
                removed_legacy.append(legacy_progid)

            try:
                stale_bar = app.CommandBars.Item("EnergoLogic")
                stale_bar.Delete()
            except Exception:
                pass
            addins.Update()

            build_dir = workspace / "energologic_visio_editor_addin_v313"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV313.dll"
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

            clsid = "{1A6AF8E1-2576-4EF3-96EC-676904B6DA57}"
            progid = "EnergoLogic.VisioEditorAddinV313"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV313, Version=0.3.13.0, Culture=neutral, PublicKeyToken=null"
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
                "removed_legacy_versions": removed_legacy,
                "migration": "v3.1-v3.12 -> v3.13",
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
            progid = "EnergoLogic.VisioEditorAddinV313"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV313")
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
                "operation_status": "ApiOperationStatus",
                "complete_pending_topology": "ApiCompletePendingTopology",
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
                "progid": "EnergoLogic.VisioEditorAddinV313",
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
            progid = "EnergoLogic.VisioEditorAddinV313"
            clsid = "{1A6AF8E1-2576-4EF3-96EC-676904B6DA57}"
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

