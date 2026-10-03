from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.104"
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
            build_dir = workspace / "energologic_visio_editor_addin_v38"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV38.dll"
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

            clsid = "{9974BD0D-D56E-45F5-BB8C-7A21485C6730}"
            progid = "EnergoLogic.VisioEditorAddinV38"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV38, Version=0.3.8.0, Culture=neutral, PublicKeyToken=null"
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
            progid = "EnergoLogic.VisioEditorAddinV38"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV38")
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
                "progid": "EnergoLogic.VisioEditorAddinV38",
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
            progid = "EnergoLogic.VisioEditorAddinV38"
            clsid = "{9974BD0D-D56E-45F5-BB8C-7A21485C6730}"
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

