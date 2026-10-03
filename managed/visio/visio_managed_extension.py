from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.92"
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
            build_dir = workspace / "energologic_visio_editor_addin_v26"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV26.dll"
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

            clsid = "{6F58CA11-8162-41B9-981E-2E671371D3C7}"
            progid = "EnergoLogic.VisioEditorAddinV26"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV26, Version=0.2.6.0, Culture=neutral, PublicKeyToken=null"
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
            progid = "EnergoLogic.VisioEditorAddinV26"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV26")
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
                "progid": "EnergoLogic.VisioEditorAddinV26",
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
            progid = "EnergoLogic.VisioEditorAddinV26"
            clsid = "{6F58CA11-8162-41B9-981E-2E671371D3C7}"
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

