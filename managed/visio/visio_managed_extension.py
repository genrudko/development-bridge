from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.97"
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
            build_dir = workspace / "energologic_visio_editor_addin_v31"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV31.dll"
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

            clsid = "{F2236480-88B8-42B3-AEC4-0707D59A14FC}"
            progid = "EnergoLogic.VisioEditorAddinV31"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV31, Version=0.3.1.0, Culture=neutral, PublicKeyToken=null"
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
            progid = "EnergoLogic.VisioEditorAddinV31"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV31")
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
                "progid": "EnergoLogic.VisioEditorAddinV31",
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
            progid = "EnergoLogic.VisioEditorAddinV31"
            clsid = "{F2236480-88B8-42B3-AEC4-0707D59A14FC}"
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

