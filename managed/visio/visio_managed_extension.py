from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.75"
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
    def install_energologic_classic_com_addin_probe(
        page: str = "",
        doc_name: str = "",
    ) -> str:
        """Build and register a fixed HKCU-only EnergoLogic Visio COM add-in probe.

        The add-in is intentionally tiny: one Ribbon tab and one fixed Duplicate-40
        button used to qualify true in-process user-context Undo. No arbitrary source,
        command, registry path or ProgID is accepted from callers.
        """
        try:
            import json
            import os
            import shutil
            import subprocess
            import winreg

            if os.name != "nt":
                raise RuntimeError("classic COM add-in probe is Windows-only")

            build_dir = workspace / "energologic_visio_qol_addin_probe"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioQolAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioQolAddin.dll"

            source = r"""using System;
using System.Runtime.InteropServices;
using System.Reflection;
using Extensibility;
using Microsoft.Office.Core;

[assembly: ComVisible(true)]
[assembly: AssemblyTitle("EnergoLogic Visio QoL Add-in")]
[assembly: AssemblyVersion("0.2.0.0")]

namespace EnergoLogicVisioQol
{
    [ComVisible(true)]
    [Guid("7D679776-1D6B-4D0D-9123-E3E4FB21F806")]
    [ProgId("EnergoLogic.VisioQolAddin")]
    [ClassInterface(ClassInterfaceType.AutoDual)]
    public sealed class VisioQolAddin : IDTExtensibility2, IRibbonExtensibility
    {
        private object _application;

        public void OnConnection(object Application, ext_ConnectMode ConnectMode,
            object AddInInst, ref Array custom)
        {
            _application = Application;
        }

        public void OnDisconnection(ext_DisconnectMode RemoveMode, ref Array custom)
        {
            _application = null;
        }

        public void OnAddInsUpdate(ref Array custom) { }
        public void OnStartupComplete(ref Array custom) { }
        public void OnBeginShutdown(ref Array custom) { }

        public string GetCustomUI(string RibbonID)
        {
            return @"<customUI xmlns='http://schemas.microsoft.com/office/2009/07/customui'>
<ribbon><tabs>
<tab id='EnergoLogicTab' label='EnergoLogic' keytip='Z'>
<group id='EnergoLogicQolGroup' label='QoL'>
<button id='EnergoLogicUndoProbeDuplicate40' label='Duplicate 40 (Undo probe)' keytip='D' size='large' onAction='OnUndoProbeDuplicate40'/>
</group>
</tab>
</tabs></ribbon>
</customUI>";
        }

        public void OnUndoProbeDuplicate40(IRibbonControl control)
        {
            if (_application == null)
                throw new InvalidOperationException("Visio application is not connected");

            dynamic app = _application;
            dynamic window = app.ActiveWindow;
            dynamic selection = window.Selection;
            int sourceCount = (int)selection.Count;
            if (sourceCount < 1)
                throw new InvalidOperationException("No shapes selected");

            int scopeId = (int)app.BeginUndoScope("EnergoLogic: Duplicate Cell Probe");
            bool commit = false;
            try
            {
                app.DoCmd(1024);
                dynamic duplicate = window.Selection;
                if ((int)duplicate.Count != sourceCount)
                    throw new InvalidOperationException("Duplicate selection count mismatch");
                duplicate.Move(40.0, 0.0, "mm");
                commit = true;
            }
            finally
            {
                app.EndUndoScope(scopeId, commit);
            }
        }
    }
}
"""
            source_path.write_text(source, encoding="utf-8")

            extensibility_ref = Path(
                r"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\PublicAssemblies\Microsoft.VisualStudio.Interop.dll"
            )
            office_ref = Path(
                r"C:\Program Files\Microsoft Office\root\Office16\ADDINS\PowerPivot Excel Add-in\OFFICE.dll"
            )
            for reference in (extensibility_ref, office_ref):
                if not reference.is_file():
                    raise FileNotFoundError(f"required Microsoft interop assembly not found: {reference}")
                shutil.copy2(reference, build_dir / reference.name)

            csc = Path(r"C:\WINDOWS\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
            if not csc.is_file():
                raise FileNotFoundError(f"C# compiler not found: {csc}")
            compile_result = subprocess.run(
                [
                    str(csc),
                    "/nologo",
                    "/target:library",
                    "/platform:x64",
                    "/optimize+",
                    f"/reference:{extensibility_ref}",
                    f"/reference:{office_ref}",
                    f"/out:{dll_path}",
                    str(source_path),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if compile_result.returncode != 0 or not dll_path.is_file():
                raise RuntimeError(
                    "C# add-in compilation failed: "
                    + (compile_result.stdout + "\n" + compile_result.stderr)[-4000:]
                )

            clsid = "{7D679776-1D6B-4D0D-9123-E3E4FB21F806}"
            progid = "EnergoLogic.VisioQolAddin"
            class_name = "EnergoLogicVisioQol.VisioQolAddin"
            assembly_name = "EnergoLogic.VisioQolAddin, Version=0.2.0.0, Culture=neutral, PublicKeyToken=null"
            runtime_version = "v4.0.30319"
            codebase = dll_path.resolve().as_uri()

            def set_string(root, subkey, name, value):
                with winreg.CreateKeyEx(root, subkey, 0, winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY) as key:
                    winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

            def set_dword(root, subkey, name, value):
                with winreg.CreateKeyEx(root, subkey, 0, winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY) as key:
                    winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, int(value))

            classes = r"Software\Classes"
            set_string(winreg.HKEY_CURRENT_USER, classes + "\\" + progid, "", "EnergoLogic Visio QoL Add-in")
            set_string(winreg.HKEY_CURRENT_USER, classes + "\\" + progid + r"\CLSID", "", clsid)
            clsid_key = classes + "\\CLSID\\" + clsid
            set_string(winreg.HKEY_CURRENT_USER, clsid_key, "", "EnergoLogic Visio QoL Add-in")
            set_string(winreg.HKEY_CURRENT_USER, clsid_key + r"\ProgId", "", progid)
            office_addin_category = "{62C8FE65-4EBB-45E7-B440-6E39B2CDBF29}"
            set_string(
                winreg.HKEY_CURRENT_USER,
                clsid_key + "\\Implemented Categories\\" + office_addin_category,
                "",
                "",
            )
            inproc = clsid_key + r"\InprocServer32"
            set_string(winreg.HKEY_CURRENT_USER, inproc, "", "mscoree.dll")
            set_string(winreg.HKEY_CURRENT_USER, inproc, "ThreadingModel", "Both")
            set_string(winreg.HKEY_CURRENT_USER, inproc, "Class", class_name)
            set_string(winreg.HKEY_CURRENT_USER, inproc, "Assembly", assembly_name)
            set_string(winreg.HKEY_CURRENT_USER, inproc, "RuntimeVersion", runtime_version)
            set_string(winreg.HKEY_CURRENT_USER, inproc, "CodeBase", codebase)

            # Visio is the Office-family exception: its add-in discovery key is
            # HKCU\Software\Microsoft\Visio\Addins\<ProgID>, not
            # HKCU\Software\Microsoft\Office\Visio\Addins\<ProgID>.
            visio_addin_key = "Software\\Microsoft\\Visio\\Addins\\" + progid
            set_string(winreg.HKEY_CURRENT_USER, visio_addin_key, "FriendlyName", "EnergoLogic Visio QoL")
            set_string(winreg.HKEY_CURRENT_USER, visio_addin_key, "Description", "EnergoLogic engineering QoL commands for Visio")
            set_dword(winreg.HKEY_CURRENT_USER, visio_addin_key, "LoadBehavior", 0)

            # Clean the stale qualification key written by <= 2026.10.03.59.
            stale_office_key = "Software\\Microsoft\\Office\\Visio\\Addins\\" + progid
            try:
                winreg.DeleteKeyEx(
                    winreg.HKEY_CURRENT_USER,
                    stale_office_key,
                    winreg.KEY_WOW64_64KEY,
                    0,
                )
            except FileNotFoundError:
                pass

            listed_in_com_addins = False
            discovery_error = None
            try:
                page_obj = visio._resolve_page(doc_name, parse_page(page))
                app = page_obj.Application
                addins = app.COMAddIns
                addins.Update()
                for index in range(1, int(addins.Count) + 1):
                    item = addins.Item(index)
                    if str(item.ProgId).casefold() == progid.casefold():
                        listed_in_com_addins = True
                        break
            except Exception as exc:
                discovery_error = f"{type(exc).__name__}: {exc}"[:1000]

            return ok({
                "progid": progid,
                "clsid": clsid,
                "dll_path": str(dll_path),
                "source_path": str(source_path),
                "compiler": str(csc),
                "compile_stdout": compile_result.stdout[-1000:],
                "compile_stderr": compile_result.stderr[-1000:],
                "hkcu_only": True,
                "load_behavior": 0,
                "visio_addin_registry_key": visio_addin_key,
                "office_addin_category": office_addin_category,
                "extensibility_reference": str(extensibility_ref),
                "office_reference": str(office_ref),
                "listed_in_com_addins": listed_in_com_addins,
                "connect_attempted": False,
                "discovery_error": discovery_error,
                "ribbon_tab": "EnergoLogic",
                "tab_keytip": "Z",
                "button_keytip": "D",
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def enable_energologic_classic_com_addin_probe_autoload() -> str:
        """Enable startup loading only for the fixed EnergoLogic qualification add-in."""
        try:
            import winreg
            progid = "EnergoLogic.VisioQolAddin"
            key_path = "Software\\Microsoft\\Visio\\Addins\\" + progid
            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER,
                key_path,
                0,
                winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY,
            ) as key:
                winreg.SetValueEx(key, "LoadBehavior", 0, winreg.REG_DWORD, 3)
            return ok({
                "progid": progid,
                "load_behavior": 3,
                "scope": "HKCU",
                "qualification_only": True,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def restart_energologic_visio_qualification_copy_graceful() -> str:
        """Save, quit and relaunch only the fixed single-document qualification copy."""
        try:
            import os
            import subprocess
            import time

            if os.name != "nt":
                raise RuntimeError("Visio qualification restart is Windows-only")
            target = workspace / "KRU-35_normal_scheme_v2_energologic_qol_host_v1.vsdm"
            exe = Path(r"C:\Program Files\Microsoft Office\root\Office16\VISIO.EXE")
            if not target.is_file():
                raise FileNotFoundError(f"qualification document not found: {target}")
            if not exe.is_file():
                raise FileNotFoundError(f"Visio executable not found: {exe}")

            page_obj = visio._resolve_page(
                "KRU-35_normal_scheme_v2_energologic_qol_host_v1.vsdm",
                "MCP-v2",
            )
            app = page_obj.Application
            documents = app.Documents
            drawing_documents = []
            document_inventory = []
            for index in range(1, int(documents.Count) + 1):
                candidate = documents.Item(index)
                try:
                    doc_type = int(candidate.Type)
                except Exception:
                    doc_type = None
                try:
                    candidate_name = str(candidate.Name)
                except Exception:
                    candidate_name = f"<document-{index}>"
                try:
                    candidate_full_name = str(candidate.FullName)
                except Exception:
                    candidate_full_name = ""
                document_inventory.append({
                    "index": index,
                    "name": candidate_name,
                    "full_name": candidate_full_name,
                    "type": doc_type,
                })
                # VisDocumentTypes: visTypeStencil = 2. Stencils are support
                # documents and do not block restarting the one qualification drawing.
                if doc_type != 2:
                    drawing_documents.append(candidate)

            if len(drawing_documents) != 1:
                raise RuntimeError(
                    "refusing graceful restart: expected exactly one non-stencil Visio document; "
                    f"inventory={document_inventory!r}"
                )
            document = drawing_documents[0]
            full_name = Path(str(document.FullName)).resolve()
            if full_name != target.resolve():
                raise RuntimeError(
                    "refusing graceful restart: the only non-stencil Visio document is not "
                    f"the fixed qualification copy; inventory={document_inventory!r}"
                )

            document.Save()
            app.Quit()

            for _ in range(40):
                ps = subprocess.run(
                    [
                        "powershell.exe",
                        "-NoProfile",
                        "-NonInteractive",
                        "-Command",
                        "@(Get-Process VISIO -ErrorAction SilentlyContinue).Count",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if int((ps.stdout or "0").strip() or "0") == 0:
                    break
                time.sleep(0.25)
            else:
                raise RuntimeError("Visio did not exit after graceful Application.Quit()")

            proc = subprocess.Popen(
                [str(exe), str(target)],
                cwd=str(workspace),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return ok({
                "restarted": True,
                "new_pid": int(proc.pid),
                "document": str(target),
                "graceful_quit": True,
                "saved_before_quit": True,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def connect_energologic_classic_com_addin_probe(
        page: str = "",
        doc_name: str = "",
    ) -> str:
        """Connect only the fixed registered probe; registration stays non-autoloading."""
        try:
            page_obj = visio._resolve_page(doc_name, parse_page(page))
            app = page_obj.Application
            addins = app.COMAddIns
            addins.Update()
            addin = addins.Item("EnergoLogic.VisioQolAddin")
            before = bool(addin.Connect)
            if not before:
                addin.Connect = True
            after = bool(addin.Connect)
            return ok({
                "progid": "EnergoLogic.VisioQolAddin",
                "connected_before": before,
                "connected_after": after,
                "load_behavior_remains": 0,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def get_energologic_classic_com_addin_probe_status(
        page: str = "",
        doc_name: str = "",
    ) -> str:
        """Read registry, COM activation and Visio COMAddIns state for the fixed probe."""
        try:
            import pythoncom
            import win32com.client
            import winreg

            progid = "EnergoLogic.VisioQolAddin"
            clsid = "{7D679776-1D6B-4D0D-9123-E3E4FB21F806}"

            def read_values(root, subkey):
                result = {"exists": False, "values": {}, "subkeys": []}
                try:
                    with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                        result["exists"] = True
                        index = 0
                        while True:
                            try:
                                name, value, kind = winreg.EnumValue(key, index)
                                result["values"][name or "(Default)"] = {"value": value, "kind": kind}
                                index += 1
                            except OSError:
                                break
                        index = 0
                        while True:
                            try:
                                result["subkeys"].append(winreg.EnumKey(key, index))
                                index += 1
                            except OSError:
                                break
                except FileNotFoundError:
                    pass
                return result

            registry = {
                "visio_addin": read_values(
                    winreg.HKEY_CURRENT_USER,
                    "Software\\Microsoft\\Visio\\Addins\\" + progid,
                ),
                "stale_office_visio_addin": read_values(
                    winreg.HKEY_CURRENT_USER,
                    "Software\\Microsoft\\Office\\Visio\\Addins\\" + progid,
                ),
                "progid": read_values(
                    winreg.HKEY_CURRENT_USER,
                    "Software\\Classes\\" + progid,
                ),
                "progid_clsid": read_values(
                    winreg.HKEY_CURRENT_USER,
                    "Software\\Classes\\" + progid + r"\CLSID",
                ),
                "clsid": read_values(
                    winreg.HKEY_CURRENT_USER,
                    "Software\\Classes\\CLSID\\" + clsid,
                ),
                "inproc": read_values(
                    winreg.HKEY_CURRENT_USER,
                    "Software\\Classes\\CLSID\\" + clsid + r"\InprocServer32",
                ),
                "implemented_categories": read_values(
                    winreg.HKEY_CURRENT_USER,
                    "Software\\Classes\\CLSID\\" + clsid + r"\Implemented Categories",
                ),
            }

            clsid_from_progid = None
            clsid_error = None
            try:
                clsid_from_progid = str(pythoncom.CLSIDFromProgID(progid))
            except Exception as exc:
                clsid_error = f"{type(exc).__name__}: {exc}"[:1000]

            dispatch_created = False
            dispatch_error = None
            try:
                obj = win32com.client.Dispatch(progid)
                dispatch_created = obj is not None
                obj = None
            except Exception as exc:
                dispatch_error = f"{type(exc).__name__}: {exc}"[:1500]

            page_obj = visio._resolve_page(doc_name, parse_page(page))
            app = page_obj.Application
            addins = app.COMAddIns
            update_error = None
            try:
                addins.Update()
            except Exception as exc:
                update_error = f"{type(exc).__name__}: {exc}"[:1000]

            collection = []
            for index in range(1, int(addins.Count) + 1):
                item = addins.Item(index)
                row = {"index": index}
                for attr, key in (
                    ("ProgId", "progid"),
                    ("Guid", "guid"),
                    ("Description", "description"),
                    ("Connect", "connect"),
                ):
                    try:
                        row[key] = getattr(item, attr)
                    except Exception as exc:
                        row[key + "_error"] = f"{type(exc).__name__}: {exc}"[:500]
                collection.append(row)

            return ok({
                "progid": progid,
                "expected_clsid": clsid,
                "registry": registry,
                "clsid_from_progid": clsid_from_progid,
                "clsid_error": clsid_error,
                "dispatch_created": dispatch_created,
                "dispatch_error": dispatch_error,
                "com_addins_update_error": update_error,
                "com_addins_count": int(addins.Count),
                "com_addins": collection,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def get_energologic_ribbon_accessibility_probe(
        page: str = "",
        doc_name: str = "",
    ) -> str:
        # Read the live Visio UI Automation tree for EnergoLogic Ribbon elements.
        try:
            import json
            import subprocess

            page_obj = visio._resolve_page(doc_name, parse_page(page))
            app = page_obj.Application
            try:
                app.ActiveWindow.Page = page_obj
            except Exception:
                page_obj.Activate()
            window = app.ActiveWindow
            hwnd = int(window.WindowHandle32)
            if hwnd <= 0:
                raise RuntimeError("Visio active window returned an invalid HWND")

            import ctypes
            user32 = ctypes.windll.user32
            GA_ROOT = 2
            root_hwnd = int(user32.GetAncestor(hwnd, GA_ROOT)) or hwnd

            ps = f"""$ErrorActionPreference='Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]{root_hwnd})
if ($null -eq $root) {{ throw 'UIAutomation root element was not found' }}
$all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
$matches = @()
$sample = @()
for ($i = 0; $i -lt $all.Count; $i++) {{
  $el = $all.Item($i)
  $name = [string]$el.Current.Name
  $aid = [string]$el.Current.AutomationId
  $cls = [string]$el.Current.ClassName
  $type = [string]$el.Current.ControlType.ProgrammaticName
  $row = [pscustomobject]@{{ index=$i; name=$name; automation_id=$aid; class_name=$cls; control_type=$type }}
  $hay = ($name + ' ' + $aid + ' ' + $cls).ToLowerInvariant()
  if ($hay.Contains('energologic') -or $hay.Contains('duplicate 40')) {{ $matches += $row }}
  if ($name -and $sample.Count -lt 160) {{ $sample += $row }}
}}
[pscustomobject]@{{ element_count=$all.Count; matches=@($matches); named_sample=@($sample); energologic_found=($matches.Count -gt 0) }} | ConvertTo-Json -Depth 6 -Compress
"""
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    ps,
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    "PowerShell UI Automation probe failed: "
                    + (result.stdout + "\n" + result.stderr)[-3000:]
                )
            payload = json.loads(result.stdout or "{}")
            return ok({
                "document": str(page_obj.Document.Name),
                "page": str(page_obj.Name),
                "root_window_handle32": root_hwnd,
                "element_count": payload.get("element_count", 0),
                "matches": payload.get("matches", []),
                "named_sample": payload.get("named_sample", []),
                "energologic_found": bool(payload.get("energologic_found", False)),
                "backend": ".NET UIAutomationClient",
            })
        except Exception as exc:
            return err(exc)


    @mcp.tool()
    def keyboard_run_energologic_classic_com_addin_probe(
        shape_ids_json: str,
        page: str = "",
        doc_name: str = "",
    ) -> str:
        """Invoke the fixed EnergoLogic Ribbon probe through real Office KeyTips."""
        try:
            import ctypes
            import ctypes.wintypes
            import json
            import time

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
                raise RuntimeError("Could not create the exact source selection")

            # Ensure our fixed COM add-in is actually connected before pressing KeyTips.
            addins = app.COMAddIns
            addins.Update()
            addin = addins.Item("EnergoLogic.VisioQolAddin")
            if not bool(addin.Connect):
                addin.Connect = True
            if not bool(addin.Connect):
                raise RuntimeError("EnergoLogic classic COM add-in is registered but not connected")

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            hwnd = int(window.WindowHandle32)
            if hwnd <= 0:
                raise RuntimeError("Visio active window returned an invalid HWND")
            GA_ROOT = 2
            SW_RESTORE = 9
            VK_MENU = 0x12
            VK_Z = 0x5A
            VK_D = 0x44
            KEYEVENTF_KEYUP = 0x0002
            root_hwnd = int(user32.GetAncestor(hwnd, GA_ROOT)) or hwnd

            def press(vk):
                user32.keybd_event(vk, 0, 0, 0)
                user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)

            foreground_hwnd = int(user32.GetForegroundWindow())
            current_thread = int(kernel32.GetCurrentThreadId())
            target_thread = int(user32.GetWindowThreadProcessId(root_hwnd, None))
            foreground_thread = (
                int(user32.GetWindowThreadProcessId(foreground_hwnd, None))
                if foreground_hwnd else 0
            )
            attached = []
            before_count = int(page_obj.Shapes.Count)
            try:
                for other_thread in (foreground_thread, target_thread):
                    if other_thread and other_thread != current_thread:
                        if bool(user32.AttachThreadInput(current_thread, other_thread, True)):
                            attached.append(other_thread)
                user32.ShowWindow(root_hwnd, SW_RESTORE)
                user32.BringWindowToTop(root_hwnd)
                user32.SetForegroundWindow(root_hwnd)
                user32.SetActiveWindow(root_hwnd)
                time.sleep(0.25)

                # Real Office Ribbon KeyTip path: Alt -> Z (EnergoLogic) -> D (probe).
                press(VK_MENU)
                time.sleep(0.35)
                press(VK_Z)
                time.sleep(0.35)
                press(VK_D)
                for _ in range(50):
                    time.sleep(0.1)
                    if int(page_obj.Shapes.Count) == before_count + len(shape_ids):
                        break
            finally:
                for other_thread in reversed(attached):
                    try:
                        user32.AttachThreadInput(current_thread, other_thread, False)
                    except Exception:
                        pass

            after_count = int(page_obj.Shapes.Count)
            if after_count != before_count + len(shape_ids):
                raise RuntimeError(
                    f"EnergoLogic Ribbon probe expected {before_count + len(shape_ids)} shapes, "
                    f"got {after_count}"
                )
            return ok({
                "document": str(page_obj.Document.Name),
                "page": str(page_obj.Name),
                "shape_count_before": before_count,
                "shape_count_after": after_count,
                "source_shape_ids": shape_ids,
                "progid": "EnergoLogic.VisioQolAddin",
                "launch_path": "Office Ribbon KeyTips Alt-Z-D",
                "ribbon_callback_launched": True,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def uninstall_energologic_classic_com_addin_probe() -> str:
        """Remove only the fixed EnergoLogic classic COM add-in probe HKCU registration."""
        try:
            import winreg

            clsid = "{7D679776-1D6B-4D0D-9123-E3E4FB21F806}"
            progid = "EnergoLogic.VisioQolAddin"
            targets = [
                "Software\\Microsoft\\Visio\\Addins\\" + progid,
                # Also remove the stale qualification key from versions <= .59.
                "Software\\Microsoft\\Office\\Visio\\Addins\\" + progid,
                "Software\\Classes\\" + progid,
                "Software\\Classes\\CLSID\\" + clsid,
            ]

            def delete_tree(root, subkey):
                try:
                    with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ | winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY) as key:
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
    def install_energologic_commandbar_com_addin_probe(
        page: str = "",
        doc_name: str = "",
    ) -> str:
        # Build/register a fixed non-autoloading command-bar-only COM add-in probe.
        try:
            import os
            import shutil
            import subprocess
            import winreg

            if os.name != "nt":
                raise RuntimeError("command-bar COM add-in probe is Windows-only")

            build_dir = workspace / "energologic_visio_qol_commandbar_probe"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioQolCommandBarAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioQolCommandBarAddin.dll"

            source = r"""using System;
using System.Reflection;
using System.Runtime.InteropServices;
using Extensibility;
using Microsoft.Office.Core;

[assembly: ComVisible(true)]
[assembly: AssemblyTitle("EnergoLogic Visio QoL CommandBar Add-in")]
[assembly: AssemblyVersion("0.1.0.0")]

namespace EnergoLogicVisioQolCommandBar
{
    [ComVisible(true)]
    [Guid("F62D8474-1A5C-4A9E-88B5-4AA67D1C5510")]
    [ProgId("EnergoLogic.VisioQolCommandBarAddin")]
    [ClassInterface(ClassInterfaceType.None)]
    public sealed class Connect : IDTExtensibility2
    {
        private object _application;
        private CommandBar _bar;
        private CommandBarButton _button;
        private _CommandBarButtonEvents_ClickEventHandler _clickHandler;

        public void OnConnection(object Application, ext_ConnectMode ConnectMode,
            object AddInInst, ref Array custom)
        {
            _application = Application;
            if (ConnectMode != ext_ConnectMode.ext_cm_Startup)
                InstallUi();
        }

        public void OnDisconnection(ext_DisconnectMode RemoveMode, ref Array custom)
        {
            _button = null;
            _bar = null;
            _application = null;
        }

        public void OnAddInsUpdate(ref Array custom) { }

        public void OnStartupComplete(ref Array custom)
        {
            InstallUi();
        }

        public void OnBeginShutdown(ref Array custom) { }

        private void InstallUi()
        {
            if (_application == null)
                throw new InvalidOperationException("Visio application is not connected");

            dynamic app = _application;
            CommandBars bars = (CommandBars)app.CommandBars;
            const string barName = "EnergoLogic QoL Probe";
            const string buttonTag = "EnergoLogic.Duplicate40.UndoProbe";

            try
            {
                _bar = bars[barName];
            }
            catch
            {
                _bar = bars.Add(
                    barName,
                    MsoBarPosition.msoBarFloating,
                    Missing.Value,
                    true);
            }

            try { _bar.Context = "2*"; } catch { }

            _button = null;
            for (int i = 1; i <= _bar.Controls.Count; i++)
            {
                CommandBarControl control = _bar.Controls[i];
                if (String.Equals(control.Tag, buttonTag, StringComparison.Ordinal))
                {
                    _button = control as CommandBarButton;
                    if (_button != null)
                        break;
                }
            }

            if (_button == null)
            {
                _button = (CommandBarButton)_bar.Controls.Add(
                    MsoControlType.msoControlButton,
                    Missing.Value,
                    Missing.Value,
                    Missing.Value,
                    true);
            }

            _button.Caption = "EnergoLogic Duplicate 40";
            _button.Tag = buttonTag;
            _button.Style = MsoButtonStyle.msoButtonCaption;
            _button.TooltipText = "EnergoLogic Duplicate 40 — Undo qualification";
            _button.Visible = true;
            _button.OnAction = "!<EnergoLogic.VisioQolCommandBarAddin>";

            _clickHandler = new _CommandBarButtonEvents_ClickEventHandler(OnProbeClick);
            _button.Click += _clickHandler;
            _bar.Visible = true;
        }

        private void OnProbeClick(CommandBarButton Ctrl, ref bool CancelDefault)
        {
            CancelDefault = false;
            RunDuplicate40();
        }

        private void RunDuplicate40()
        {
            dynamic app = _application;
            dynamic window = app.ActiveWindow;
            dynamic selection = window.Selection;
            int sourceCount = (int)selection.Count;
            if (sourceCount < 1)
                throw new InvalidOperationException("No shapes selected");

            int scopeId = (int)app.BeginUndoScope("EnergoLogic: Duplicate Cell Probe");
            bool commit = false;
            try
            {
                app.DoCmd(1024);
                dynamic duplicate = window.Selection;
                if ((int)duplicate.Count != sourceCount)
                    throw new InvalidOperationException("Duplicate selection count mismatch");
                duplicate.Move(40.0, 0.0, "mm");
                commit = true;
            }
            finally
            {
                app.EndUndoScope(scopeId, commit);
            }
        }
    }
}
"""
            source_path.write_text(source, encoding="utf-8")

            extensibility_ref = Path(
                r"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\PublicAssemblies\Microsoft.VisualStudio.Interop.dll"
            )
            office_ref = Path(
                r"C:\Program Files\Microsoft Office\root\Office16\ADDINS\PowerPivot Excel Add-in\OFFICE.dll"
            )
            for reference in (extensibility_ref, office_ref):
                if not reference.is_file():
                    raise FileNotFoundError(f"required Microsoft interop assembly not found: {reference}")
                shutil.copy2(reference, build_dir / reference.name)

            csc = Path(r"C:\WINDOWS\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
            if not csc.is_file():
                raise FileNotFoundError(f"C# compiler not found: {csc}")
            compile_result = subprocess.run(
                [
                    str(csc),
                    "/nologo",
                    "/target:library",
                    "/platform:x64",
                    "/optimize+",
                    f"/reference:{extensibility_ref}",
                    f"/reference:{office_ref}",
                    f"/out:{dll_path}",
                    str(source_path),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if compile_result.returncode != 0 or not dll_path.is_file():
                raise RuntimeError(
                    "C# command-bar add-in compilation failed: "
                    + (compile_result.stdout + "\n" + compile_result.stderr)[-4000:]
                )

            clsid = "{F62D8474-1A5C-4A9E-88B5-4AA67D1C5510}"
            progid = "EnergoLogic.VisioQolCommandBarAddin"
            class_name = "EnergoLogicVisioQolCommandBar.Connect"
            assembly_name = (
                "EnergoLogic.VisioQolCommandBarAddin, Version=0.1.0.0, "
                "Culture=neutral, PublicKeyToken=null"
            )
            codebase = dll_path.resolve().as_uri()

            def set_string(root, subkey, name, value):
                with winreg.CreateKeyEx(
                    root, subkey, 0, winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY
                ) as key:
                    winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

            def set_dword(root, subkey, name, value):
                with winreg.CreateKeyEx(
                    root, subkey, 0, winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY
                ) as key:
                    winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, int(value))

            classes = r"Software\Classes"
            set_string(winreg.HKEY_CURRENT_USER, classes + "\\" + progid, "", "EnergoLogic Visio QoL CommandBar Add-in")
            set_string(winreg.HKEY_CURRENT_USER, classes + "\\" + progid + r"\CLSID", "", clsid)
            clsid_key = classes + "\\CLSID\\" + clsid
            set_string(winreg.HKEY_CURRENT_USER, clsid_key, "", "EnergoLogic Visio QoL CommandBar Add-in")
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
            set_string(winreg.HKEY_CURRENT_USER, addin_key, "FriendlyName", "EnergoLogic Visio QoL CommandBar")
            set_string(winreg.HKEY_CURRENT_USER, addin_key, "Description", "EnergoLogic temporary command-bar Undo qualification")
            set_dword(winreg.HKEY_CURRENT_USER, addin_key, "LoadBehavior", 0)

            listed = False
            discovery_error = None
            try:
                page_obj = visio._resolve_page(doc_name, parse_page(page))
                addins = page_obj.Application.COMAddIns
                addins.Update()
                for index in range(1, int(addins.Count) + 1):
                    if str(addins.Item(index).ProgId).casefold() == progid.casefold():
                        listed = True
                        break
            except Exception as exc:
                discovery_error = f"{type(exc).__name__}: {exc}"[:1200]

            return ok({
                "progid": progid,
                "clsid": clsid,
                "dll_path": str(dll_path),
                "source_path": str(source_path),
                "load_behavior": 0,
                "hkcu_only": True,
                "listed_in_com_addins": listed,
                "discovery_error": discovery_error,
                "ribbon_extensibility": False,
                "command_bar_name": "EnergoLogic QoL Probe",
                "button_caption": "EnergoLogic Duplicate 40",
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def connect_energologic_commandbar_com_addin_probe(
        page: str = "",
        doc_name: str = "",
    ) -> str:
        # Connect only the fixed non-autoloading command-bar probe.
        try:
            page_obj = visio._resolve_page(doc_name, parse_page(page))
            app = page_obj.Application
            addins = app.COMAddIns
            addins.Update()
            addin = addins.Item("EnergoLogic.VisioQolCommandBarAddin")
            before = bool(addin.Connect)
            if not before:
                addin.Connect = True
            after = bool(addin.Connect)
            command_bar_present = False
            button_present = False
            try:
                bar = app.CommandBars.Item("EnergoLogic QoL Probe")
                command_bar_present = bar is not None
                if command_bar_present:
                    for index in range(1, int(bar.Controls.Count) + 1):
                        control = bar.Controls.Item(index)
                        if str(control.Tag) == "EnergoLogic.Duplicate40.UndoProbe":
                            button_present = True
                            break
            except Exception:
                pass
            return ok({
                "progid": "EnergoLogic.VisioQolCommandBarAddin",
                "connected_before": before,
                "connected_after": after,
                "command_bar_present": command_bar_present,
                "button_present": button_present,
                "load_behavior_remains": 0,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def get_energologic_commandbar_com_addin_probe_status(
        page: str = "",
        doc_name: str = "",
    ) -> str:
        # Read current registration, connection and command-bar/button state.
        try:
            import winreg
            progid = "EnergoLogic.VisioQolCommandBarAddin"
            addin_key = "Software\\Microsoft\\Visio\\Addins\\" + progid
            load_behavior = None
            registry_exists = False
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    addin_key,
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
            for index in range(1, int(addins.Count) + 1):
                item = addins.Item(index)
                if str(item.ProgId).casefold() == progid.casefold():
                    listed = True
                    connected = bool(item.Connect)
                    break

            command_bar_present = False
            command_bar_visible = False
            button_present = False
            button_visible = False
            try:
                bar = app.CommandBars.Item("EnergoLogic QoL Probe")
                command_bar_present = bar is not None
                command_bar_visible = bool(bar.Visible)
                if bar is not None:
                    for index in range(1, int(bar.Controls.Count) + 1):
                        control = bar.Controls.Item(index)
                        if str(control.Tag) == "EnergoLogic.Duplicate40.UndoProbe":
                            button_present = True
                            button_visible = bool(control.Visible)
                            break
            except Exception:
                pass

            return ok({
                "progid": progid,
                "registry_exists": registry_exists,
                "load_behavior": load_behavior,
                "listed_in_com_addins": listed,
                "connected": connected,
                "command_bar_present": command_bar_present,
                "command_bar_visible": command_bar_visible,
                "button_present": button_present,
                "button_visible": button_visible,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def execute_energologic_commandbar_com_addin_probe(
        shape_ids_json: str,
        page: str = "",
        doc_name: str = "",
    ) -> str:
        # Execute the fixed Office CommandBar button after selecting exact source IDs.
        try:
            import json
            import time
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
                raise RuntimeError("Could not create the exact source selection")

            addins = app.COMAddIns
            addins.Update()
            addin = addins.Item("EnergoLogic.VisioQolCommandBarAddin")
            if not bool(addin.Connect):
                raise RuntimeError("EnergoLogic command-bar add-in is not connected")

            bar = app.CommandBars.Item("EnergoLogic QoL Probe")
            button = None
            for index in range(1, int(bar.Controls.Count) + 1):
                control = bar.Controls.Item(index)
                if str(control.Tag) == "EnergoLogic.Duplicate40.UndoProbe":
                    button = control
                    break
            if button is None:
                raise RuntimeError("EnergoLogic command-bar probe button was not found")

            before_count = int(page_obj.Shapes.Count)
            button.Execute()
            expected = before_count + len(shape_ids)
            for _ in range(50):
                if int(page_obj.Shapes.Count) == expected:
                    break
                time.sleep(0.1)
            after_count = int(page_obj.Shapes.Count)
            if after_count != expected:
                raise RuntimeError(
                    f"CommandBar probe expected {expected} shapes, got {after_count}"
                )
            return ok({
                "document": str(page_obj.Document.Name),
                "page": str(page_obj.Name),
                "source_shape_ids": shape_ids,
                "shape_count_before": before_count,
                "shape_count_after": after_count,
                "launch_path": "Office CommandBarButton.Execute",
                "in_process_callback_expected": True,
                "load_behavior": 0,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def mouse_run_energologic_commandbar_com_addin_probe(
        shape_ids_json: str,
        page: str = "",
        doc_name: str = "",
    ) -> str:
        # Physically click the fixed visible CommandBar button after exact selection.
        try:
            import ctypes
            import json
            import time

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
                raise RuntimeError("Could not create the exact source selection")

            addins = app.COMAddIns
            addins.Update()
            addin = addins.Item("EnergoLogic.VisioQolCommandBarAddin")
            if not bool(addin.Connect):
                raise RuntimeError("EnergoLogic command-bar add-in is not connected")

            bar = app.CommandBars.Item("EnergoLogic QoL Probe")
            if not bool(bar.Visible):
                bar.Visible = True
            button = None
            for index in range(1, int(bar.Controls.Count) + 1):
                control = bar.Controls.Item(index)
                if str(control.Tag) == "EnergoLogic.Duplicate40.UndoProbe":
                    button = control
                    break
            if button is None:
                raise RuntimeError("EnergoLogic command-bar probe button was not found")
            if not bool(button.Visible):
                button.Visible = True

            left = int(button.Left)
            top = int(button.Top)
            width = int(button.Width)
            height = int(button.Height)
            if width <= 0 or height <= 0:
                raise RuntimeError(
                    f"CommandBar button returned invalid bounds: left={left} top={top} "
                    f"width={width} height={height}"
                )
            x = left + width // 2
            y = top + height // 2

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            hwnd = int(window.WindowHandle32)
            if hwnd <= 0:
                raise RuntimeError("Visio active window returned an invalid HWND")
            GA_ROOT = 2
            SW_RESTORE = 9
            MOUSEEVENTF_LEFTDOWN = 0x0002
            MOUSEEVENTF_LEFTUP = 0x0004
            root_hwnd = int(user32.GetAncestor(hwnd, GA_ROOT)) or hwnd

            foreground_hwnd = int(user32.GetForegroundWindow())
            current_thread = int(kernel32.GetCurrentThreadId())
            target_thread = int(user32.GetWindowThreadProcessId(root_hwnd, None))
            foreground_thread = (
                int(user32.GetWindowThreadProcessId(foreground_hwnd, None))
                if foreground_hwnd else 0
            )
            attached = []
            before_count = int(page_obj.Shapes.Count)
            old_cursor = ctypes.wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(old_cursor))
            try:
                for other_thread in (foreground_thread, target_thread):
                    if other_thread and other_thread != current_thread:
                        if bool(user32.AttachThreadInput(current_thread, other_thread, True)):
                            attached.append(other_thread)
                user32.ShowWindow(root_hwnd, SW_RESTORE)
                user32.BringWindowToTop(root_hwnd)
                user32.SetForegroundWindow(root_hwnd)
                user32.SetActiveWindow(root_hwnd)
                time.sleep(0.35)
                user32.SetCursorPos(x, y)
                time.sleep(0.15)
                user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                expected = before_count + len(shape_ids)
                for _ in range(50):
                    if int(page_obj.Shapes.Count) == expected:
                        break
                    time.sleep(0.1)
            finally:
                user32.SetCursorPos(int(old_cursor.x), int(old_cursor.y))
                for other_thread in reversed(attached):
                    try:
                        user32.AttachThreadInput(current_thread, other_thread, False)
                    except Exception:
                        pass

            after_count = int(page_obj.Shapes.Count)
            expected = before_count + len(shape_ids)
            if after_count != expected:
                raise RuntimeError(
                    f"Physical CommandBar click expected {expected} shapes, got {after_count}; "
                    f"button_bounds=({left},{top},{width},{height})"
                )
            return ok({
                "document": str(page_obj.Document.Name),
                "page": str(page_obj.Name),
                "source_shape_ids": shape_ids,
                "shape_count_before": before_count,
                "shape_count_after": after_count,
                "button_bounds": {
                    "left": left,
                    "top": top,
                    "width": width,
                    "height": height,
                    "click_x": x,
                    "click_y": y,
                },
                "launch_path": "physical mouse click on Office CommandBarButton",
                "physical_ui_event": True,
                "load_behavior": 0,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def schedule_energologic_commandbar_physical_click_probe(
        shape_ids_json: str,
        page: str = "",
        doc_name: str = "",
    ) -> str:
        # Schedule the fixed physical button click after this COM call has returned.
        try:
            import ctypes
            import ctypes.wintypes
            import json
            import os
            import subprocess
            import sys

            if os.name != "nt":
                raise RuntimeError("asynchronous CommandBar click probe is Windows-only")
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
                raise RuntimeError("Could not create the exact source selection")

            addins = app.COMAddIns
            addins.Update()
            addin = addins.Item("EnergoLogic.VisioQolCommandBarAddin")
            if not bool(addin.Connect):
                raise RuntimeError("EnergoLogic command-bar add-in is not connected")

            bar = app.CommandBars.Item("EnergoLogic QoL Probe")
            if not bool(bar.Visible):
                bar.Visible = True
            button = None
            for index in range(1, int(bar.Controls.Count) + 1):
                control = bar.Controls.Item(index)
                if str(control.Tag) == "EnergoLogic.Duplicate40.UndoProbe":
                    button = control
                    break
            if button is None:
                raise RuntimeError("EnergoLogic command-bar probe button was not found")
            if not bool(button.Visible):
                button.Visible = True

            left = int(button.Left)
            top = int(button.Top)
            width = int(button.Width)
            height = int(button.Height)
            if width <= 0 or height <= 0:
                raise RuntimeError(
                    f"CommandBar button returned invalid bounds: left={left} top={top} "
                    f"width={width} height={height}"
                )
            x = left + width // 2
            y = top + height // 2

            user32 = ctypes.windll.user32
            hwnd = int(window.WindowHandle32)
            if hwnd <= 0:
                raise RuntimeError("Visio active window returned an invalid HWND")
            GA_ROOT = 2
            root_hwnd = int(user32.GetAncestor(hwnd, GA_ROOT)) or hwnd
            cursor = ctypes.wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(cursor))
            old_x = int(cursor.x)
            old_y = int(cursor.y)
            before_count = int(page_obj.Shapes.Count)

            helper = f'''import ctypes,time\ntime.sleep(1.0)\nu=ctypes.windll.user32\nu.ShowWindow({root_hwnd},9)\nu.BringWindowToTop({root_hwnd})\nu.SetForegroundWindow({root_hwnd})\nu.SetActiveWindow({root_hwnd})\ntime.sleep(0.20)\nu.SetCursorPos({x},{y})\ntime.sleep(0.10)\nu.mouse_event(0x0002,0,0,0,0)\nu.mouse_event(0x0004,0,0,0,0)\ntime.sleep(0.15)\nu.SetCursorPos({old_x},{old_y})\n'''
            creationflags = 0x08000000 | 0x00000008 | 0x00000200
            proc = subprocess.Popen(
                [sys.executable, "-c", helper],
                cwd=str(workspace),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
                close_fds=True,
            )
            return ok({
                "document": str(page_obj.Document.Name),
                "page": str(page_obj.Name),
                "source_shape_ids": shape_ids,
                "shape_count_before": before_count,
                "expected_shape_count_after": before_count + len(shape_ids),
                "button_bounds": {
                    "left": left,
                    "top": top,
                    "width": width,
                    "height": height,
                    "click_x": x,
                    "click_y": y,
                },
                "root_window_handle32": root_hwnd,
                "helper_pid": int(proc.pid),
                "delay_seconds": 1.0,
                "scheduled": True,
                "returns_before_physical_click": True,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def schedule_energologic_physical_undo_probe(
        page: str = "",
        doc_name: str = "",
    ) -> str:
        # Schedule one physical Ctrl+Z after this COM call has returned.
        try:
            import ctypes
            import os
            import subprocess
            import sys

            if os.name != "nt":
                raise RuntimeError("asynchronous physical Undo probe is Windows-only")
            page_obj = visio._resolve_page(doc_name, parse_page(page))
            app = page_obj.Application
            try:
                app.ActiveWindow.Page = page_obj
            except Exception:
                page_obj.Activate()
            window = app.ActiveWindow
            hwnd = int(window.WindowHandle32)
            if hwnd <= 0:
                raise RuntimeError("Visio active window returned an invalid HWND")
            user32 = ctypes.windll.user32
            GA_ROOT = 2
            root_hwnd = int(user32.GetAncestor(hwnd, GA_ROOT)) or hwnd
            before_count = int(page_obj.Shapes.Count)

            helper = f'''import ctypes,time\ntime.sleep(1.0)\nu=ctypes.windll.user32\nu.ShowWindow({root_hwnd},9)\nu.BringWindowToTop({root_hwnd})\nu.SetForegroundWindow({root_hwnd})\nu.SetActiveWindow({root_hwnd})\ntime.sleep(0.20)\nu.keybd_event(0x11,0,0,0)\nu.keybd_event(0x5A,0,0,0)\nu.keybd_event(0x5A,0,0x0002,0)\nu.keybd_event(0x11,0,0x0002,0)\n'''
            creationflags = 0x08000000 | 0x00000008 | 0x00000200
            proc = subprocess.Popen(
                [sys.executable, "-c", helper],
                cwd=str(workspace),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
                close_fds=True,
            )
            return ok({
                "document": str(page_obj.Document.Name),
                "page": str(page_obj.Name),
                "shape_count_before": before_count,
                "root_window_handle32": root_hwnd,
                "helper_pid": int(proc.pid),
                "delay_seconds": 1.0,
                "keyboard_chord": "Ctrl+Z",
                "scheduled": True,
                "returns_before_physical_undo": True,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def uninstall_energologic_commandbar_com_addin_probe() -> str:
        # Disconnect and remove only the fixed command-bar probe registration.
        try:
            import winreg
            progid = "EnergoLogic.VisioQolCommandBarAddin"
            clsid = "{F62D8474-1A5C-4A9E-88B5-4AA67D1C5510}"
            try:
                page_obj = visio._resolve_page(
                    "KRU-35_normal_scheme_v2_energologic_qol_host_v1.vsdm",
                    "MCP-v2",
                )
                addins = page_obj.Application.COMAddIns
                addins.Update()
                addin = addins.Item(progid)
                if bool(addin.Connect):
                    addin.Connect = False
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
            build_dir = workspace / "energologic_visio_editor_addin"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddin.dll"
            source_path.write_bytes(gzip.decompress(base64.b64decode("H4sIAAAAAAAC/+19a3PcRpLgd/2KUk/ERvephWtSkscW3fLxIdncMyWdSXmkkBUKdDdIwu4GegC0xF4OI2w5xvacfPaNdz5MTMyF524vNu7byvZwTFuP+Qcb7L/gX3KZWVVAFVCFRvPh9T4UYbOBqsqqysrMylcVRrEfbLH1cZx4g4UzI+XJWQ77fa+b+GEQO697gRf53VyNlch9CI+5t6/3w47b9//Oxaa5sjf94Je5V295m6KbfMEoSPyB56wGiReFw3UveuB3vThXa8PbSQDG1qjvRld3hpEXxzjiXK1f+EEvfBg718JokJZd3Um8IPY7ft9PxvLlmt+NwjjcTJwbm5vQH6Ah8hbOnLnrxrE36PTHl9lyOHjbh3Z9r55EI69xTy1cFL82/ATKa1cBb1vhm+GW32XYKGRXe34SRjVzq7e9CIdfr7WcOafltLDamcAdePHQ7XpMgUbAOKwzu2cY/PMRT4HbZ7Hn9r0e6/YBPnu9P/I23GjLS6gSr4r/hqNOHwYFrRgvX+0tmArfCh8W3sdJRAgMesMQ6vDyvTMlw1j2+v3VYDO0D2Ix6G6HkWUQS6PYXrLhRQMferTUWO+HibFgOQwCTnmV56iUv+nHyatQcIUhhaz2YtZmgfcwe19vlLRZg+X2opJW5dhMR34Tx1aO2PVtd+jNsLi9EP567PZgYCu6Yy9agXm4QddbG2jTuFvkGXr9+sjvAZNcmFtpXbt46fzLi5cWz1/8+crPzy9eXLxwfvna0s+vtZZfXvr5hbmabHIzCrdWexpnOQozLPZ6fpBWXkZ0kQDZBP6p648b46HnXA8DORq58AZMs8tsdWVDExjzeYxH/gM38VjYeRcb3HeHQ4AmhGC+Eh8rSiN2fxP+X6wBCBu4QW/Jjdj9jhuVVVgaJUkYsPtJuLXV9/hTsf79fIOrD7wgie8vwyjfo99vQGnfiyQg8ViEFHluLwz6YwZi19th97dAxPCfnJbpdz1thv/+S2192/OSd5z6O71zjbMZ/cb11y6/49ym178SxfDcqDW19gTyxpBvRqtbAXDcsht77Fd6CUxx6MPiAQ/l6fNB6PfYjSDruS4WajFbpyaDzeS+qLIW9jym/G7KlQUKWw1WgzhpAiY22WIUuWPWHcVJOGikve5qw1eJAZC0aCIN/IdQ3X5/Q1lIVYrgv/Xt8OFNN/D6asGebbrAjt1sxji77A1N8C1vED7w+PyqziaJxmyX+ZusTrTLzsKyj/p99jd/w87SG2c1hm6GYQwrwenbWe7DEwyZ7TGYeHcbAOzpKCJQHJI+Y42uzTWAQcwFOt71Clak0QLHt4Y9IPZ6ASnayPWG64kbJaMhUmHfm7HtkrflB+vbowT0lMDSssCJvTHoBgADCMqyVnLfN5fSDoPrqOGJI6rBku0ofEgcvRo8AI2ud2PoRVTn6k7XI5ar17hSc/j8cJ8d/vXwxeGfD78/fDr5bPLx5LeHz2s54sV/kZeMosAiH/m6mFZIzJiwZWQTCwIkiqA7znl6Z5lQjFkH/9dmdeVdA5o5yrPeGBgpTqSiAK2vg6IGANStqbZgYB1Br9jfXdHs3kKOHySXKHUdIMy6qN9ka3EII7oZxj6i0BnQ40Y4hBI/RlXWedsFwdxktN8uqMisxlXAkKyOSoIPxXML8OfVNg0HEBIkUdhHeQs6OpScO9eYQmUZDkVj1mU5aHf9ewtG6lwnBDtXfzly+3G962y4W00NyQ7fTh1OELUm4y2QD93IjwE7N6IeaoiNRqGD4lBN2AH6iQs77oKxaQe2x/eKRXtn7E/EgnqPggfPTBtYPT+ohr5CSDJAKeKZNJ5B+shbFAim/JGTUwkxOcvuUAjcEk7Qm8CS5qrn1rSs8Xoy7iPfIUfQG3pBHEGPYjyl/YdhP/GHaEziOA6/BEn2/eGTw28Pn0weTT5F0fYEZRyItk9Z1UkJhRcAIs6MNaXKxRWnyipa/UbA8UIljbJBUA12rm3V6uQGah2uTQprYyjQIVtOoj7XKTqAXLaMVkF/xdt0R/3EJqy1SjCQTWB47+j6j1LX0mGmxAiOY7/6FSvoMEUulMoKLFqmyteTbT/OLQZ2IJQigV+pEeHg8sodL1lC4bURXouAS801FkGfw4Ww4CAzGvnWtDLiW62HVjiJ9J4fcZ3wiNumLB66W0gwuEvSmLyb8CK3wwrLn8HK9qEuKaAPvAjfwxQH655w/9QRWMPcTxyOIjDYhKEPULCuQ5Yt2AOJN0BIqyt17MPRXAIWgAm5PBSAr3uJ0m5pjF4DGlGTSaCrPfEby9g5BYm5NQcEc/hUkWATOL3TXKurQTyK0ileizxPdI8L1tCbOqsrTSK+N9x4e92TnoP8XLlJ3tvhQ1gb5AYAm+hNP7hda7DzolxHc1puBjsuBXtnCtg7tfwmkjlHeH3uHCGEp94S3Mi9aGlchzldYTsNENzYrGAkEU1BfYHCFGCuHnXJ53P3nuyXXCrYddrK4fDqIFKgV8D73XugmfG5WQjR7zVS9DUrVkWU7dmmREPl/CwHuubGwOclI+UVUF0s6bsxQ4+4P5b0t+5uUpWqvRW4BiTDEOUJkTwKFbKKbgW9cB1L6inHsSusxV7TFIbL7PAPsGv/9fBg8j78/Vrs3JPPJx/Dvv3d4feTDxm8/SuUPoG/L2rs8lHaP4UHbJ1DFu1xXdgDfcu+BZr/FBUZ57sSLg969bnW/EWD5SRlV0+K854mermP20nlqVmZJtRmELgKjyZ8tqb0ajbz7+vDfcDa88mHh0/JFiRT8Cm+mHzGQJPieIWfX08eg4m4T2h8Dq8+N5mImSSA3rkYSGeFTJ0N39Y442mAkDI0h/ZT4OaCfdUi+yq/CAbTym6z4OpO53iOA7C1Go1s1YUkgbeo/0xjYyMIEg34zjg24oAZ6OkANO9nnESQooCaJu9PPgfKAbWcTf4HkQ+VTx4hrzJi64OM0gQHU/uDBUZvkUKfTD5CooMX0JB3gP89MVHhXpEB+c4XuMhuK8LdyanLWQSVBtBVHyJRDe+27uH2p24ohhoLU3oYl/UwN7WHOWMPGeuvgRpWB+3gfDqjJu7q6eMYCHkwKOzTUli7PGAT9Mjxm1EuvbmxyXUxGdVpmKWRCuNV1qoodA7/F3qbYNlALKMweS7GoghrJIavU3o4PKiVyFPojQ/TrlcKkleGa8KtULehMim9KJ5riIXLNdAWMdThXPceUsgD5QJ3UtRr12tm4eC53W0hIHqAcCG9GiAKEw4e7EE/GZcKonQohi4wMiijW/UUB0LFlQVNllfuqFgLnRlgv+1F/uYYeyiBbFNsK/WQ7rVF21rxMgrXEVpnblJfBqsSdGy0RpzlURQBAsWrplFq1X7449+zw39KaeoJm3xgEDFP2G5rz2GHfwQR8wEKJLY7t8d++OgLtju/t4Bt/gw1Dw6/YbsXLrecVmuPgex5tkArgHvnC2iGDRHYC6FjPAfZL1YYIbwAgfhn3ptTM4+2oBwVtB1FfVEsmaZirIAA2GkslLiqNnGV+lVUGVjnTHEjxa4pFq1Rwd+bN2FRVv2H9fpjWK+qScnCh4Fwc2iWpm6UHdeQhU7+dVuuJ2C6fEnqCSk1JAoOZjZeqkE4PfMl5bkpW+k0tWDFS2DjSzcm17R3GJrlTf5SEpUyymw4ScUItaFUBSrdPd3T2TrdfzP7plC/OXX+huvcx9s1/yo2YA72+clvihanXdUdEkzKabtgtZ2PkyXtfdO2O7GfLZ7WfjYTjwlK4rTwhWb2P0E/wAdghin6+hNYCtiVcu4+7p04B0VFo6/JUln3gk0+AVJ5PnmcARHbXM2pVfKRX91xu8mNzc3YS+rp9tPMtoyyCMKam2w7i50YZEYDzJg57/wrmAyRvR7L11UNnP+tMMoBN3b2cbovDv8C7x+xw68mj3lginwuSL+A4Wc1i75wfD0oc8n45I8RYmAjHL7pPfD6pWTDFYLrIaZPIcpJtnEK8gtkU2Uvze18/wcU6I9x8Q+/U8TGKWxxefr3T2NjOWEBLRjQjKPL7DZIYZCuP/vZz7h4bbI7IIfVNyBZOSeMf1Sxt+TG3K2xEblBjFGvuljB4Thly07GoZ3sbZK9Tax8q6qYCfpAOjt2ZTFBr0hnvPAjcP5vKerM/c+fs8MDNvlIyE3+BqUdrCQ6OMgs/JpC02AaTj6bPPp3wv9IAxW9/x+AqEwx+gKJX+IPHqpr0eVg/qUkDVIg4qKqhzgf7oowB8f/6XjEK0VBcpGQGUMg+TBIFv/wZ4x8oBNShjk4r0rP0OcVwxwVQx1lLZU4B4z4pxbhUD3aJGhhkBZHedSt5B/XII7NEOdsEOesEIEOFGd4L/WDl2zTir+3e1xn7xSHL9LrG25c0enbmM1D3LW5h4vhDw8E2U9Su9lF2xBY0Sqk9y+zf/7d7Zxi04R3oOzM55UdubvkNxSuinOb8cuCOYtF/yKK0mLf3wrq4sHd8ePTd4oeRxlAYk5FLehG81XF7e8OnwrJKsx3xLlYFilyv6JlgT2bW0sHVOcZWEjPGKm8T/JmZCHwN5OuIlG26UdxYvd4QcOiNJMKKnkXUn8kQWrSMmJGWm2nhpRIYhnpTnofZ1WYcvB0lecLwiiS+HOwx0W24wt226AdWareOQUNyCAPcQEqajqp5x0Xo2xlLNJ4nXt/scGU1ZBevkoStJpadzoWoLJ2JLBekNg0xtKFL65tEI4p63K0wM52awjciowb+S7mK1oQcrpCcM1zkW9v+kl3+yTcZCThpK/sCm2SmWrm9bAktkk3qpzplbMKOJH6wN2aJNomn4CU+4Z7zXQZp6/e5DFLV/gFCbzJh5NfSyfb/uH3NvMwmSt316P4qhaXmp8GaK4cUIo/0SOoVWd5DqBsCk0q4vOf1FwA7WgKoesxw1SS90lhQL/IM+FDhBfPLIGjIZIXJppL814EkeaL8ahkLn1n9osSLEUxJD4DBlMZOeUq8bJitq+PPzqjRLCDOvgyLyaf3avt6mkY/w/pklFWzlN0TB4+VxyTX+HbyaeA1H3hpSxaQSesklRi2DSFtItWQaml083RarakFqMnz/4zqzeUovQBRSj2dQOymoKzr6XAmFSFDjGV5CnJZbZpLAYCT92MGwlCo+q8voDp7IvBE7c9J27bz+XqSBoivsyc2yj0kHGfc32eM+i+UQXCs3ci35qPfc0P5NjxvSm7dWM07Hsp2TQlwV0Ba7HvBurRbGvNeln4PBbkxwMasS2ULg32NTdDdxZWaZQcyxJpgwrNVTqNpecRlOcPdHjqQIbfc8y3+KJ8DLLNqqINI+/B7CMAQTtX7h9wu8mIciPy0prmXJTYOA6bzDa6fEUH54Vkxbk785eOl/84g1IH0veAM8gBKQAYFuKaQsGlj5W+5V5iENG6FQxbDp9IU8yjkiJbJceDYtI5DjAAR06jY2rEYs4yqP2JJ5QA/16qTRbUyeNGjf5UkLT5jImiAD1Ju8YmURhSCVg7iJeqvJSP6gII2sfmyt2nKfvL+vNTHKbpwqI5ZMhWwhOxiR+YrJZTyYeali90xDyhaflCM+QJlaHhuJkyx8iWOVLGzAkEN2fLnKmY0rJXKRmofJN1UGv2g25Sz3S7I5vm+fyXA4teh7oOGtv09glqy9ISkY7LJ6lZMnnsMK5w80SJKvaDvmc0KI+CG/I/pm3+ljd0/YgcaSQ/caP1vYc3gv74X5OrEjTfudmUeT5xmeWb195RrYV1zdnwNgtpqiPL4GLkNlHxqiDQbuWJGJBei/1+ro7Rs6FowXxdZYxd/gWl2RP8Gxc1Z1ubelG75dujIB4JUsRDKJBV6+DGDrReg9Ia22tUuOHiLCjdqdARfj0Ju1G2b2HjjWgMiMpu0ioAkFeglAFKkVNUdrxU7r2u+h3TuaPvkc8Z/Y+k1kjvbE+J11Vodkc2g82pUeqhw3lnQ+Ys0J7BN/APOZsP6P0bFHU5/ztlNqHm+gHFbL5KrT2snM4E3gnreJ+SoFLX/TQSNVE/CH436Pl4u0sJoRpbWqn1gRsxb4hEmuKsUVURNPTECJQJTvnxr6EjLvvCpRIyYZpOJnQcaSit/zJKuI1zM3wIAG8PBqDleEOuHzbRoXGOKeV31PILWF5iO/XQvTTntMxG0q7VdDKhiMJ0fPlMxbssRQVL0dLEC8/oBfxt4hVn9AB/m3ipGT3cwYfsGjN412N7C9ahZbRk4GuOlTkeU7QhZm+mu0I02lU617xaXb5aTjaNUo9VBmV2Pv+TOJb3TOQoKqey0An9HJ07igdH0XToRXY7FSd3Vv/hN/+XzZGa0qhVGewVqK2mXGUV0LuVxwPQqlJhrlgB87VaTstgx1fNCsnNf1+cGcI5f4+vxMYP9b7nkWr0lT4lvz+oipNfF3Hyw/u/YxjypADNM0xtgnofC8gHEq1CMHJTnzTNyW9MlzChrOp4FLDUcKXXEvtvz4u7kS/vc5nBPbHb2rsstJbduT1VnsbO7jy84CoxT98FGuJ5rpTqrfomcKCSidLf8xk/K++IpZVnZU2LZKQqoanafvgH2qtweTCh7pGqwXGtW0GHDnPFd/vh1ltejBeXuEH8kC51WfPiGFSppXCHX/ehkQcj/V7p7vI7wTtBrhfU2fH14e+F+YCRb+6owFG9VtNvQiJSUUYNxdkY+MUssXPHi6+HasEqUJzz30aAOsNlFnRKk+Zztq1NE+FkuNOU3fR0LdIfD74g+cu8xkfCACoYIrO7cdS5nryzRjNVhXqlUqRFGy8SaiNPqeUHPwxdTSf+45mrpWcRnXLiP137cSXsJmF0clHdkzSIyLLsuL2yu18Ld2kMOONpyqcoqzcq3MFGnKGS3uyOf5s5WTe69nkGhuiYmjqrKyVnlqXtNqxutZXrtUbrbdjAywqsttmwklWmqMCZ8zAFMc3yKoU3rgZPNcnM8HDDDjy6BlCYY7/Y9iKZ1piq/JTDmqpCZj1+x6bAj0lzp+iv8/K0nE5cEhxQqoHNrNADy5C6bE3AwX+ST6hmjaZJcghmiZ4s/AkohZ+XGR1n+HbyYaZb0u4Ke+YTNC/psFFerWoyqpfuWFDpQ/r/I0ycwGa1E9HYEVs43wxZBf8kFk93QCKgFCeqpq7K8fXutjfwhNC8zECzwmStx6BWAleOulDR7Z8Xp+e+4ruwQEFRfc9vz2k/f/hTvp+83q91wHWn3NDxaBY7/FKtJyPD+awWPZ168th5J+KKktBH/xaWs16jl82smw33Pa9OtEw3qWroNNxpl8sg0DMH1E3GthEp91dJr+KMDscVn4rcaPwq0Wc2mlHg/3LkiQ3DWs3qnshy6NKhTb2ws+SgYJq9ZokDn+XDpVsoXT+I/6s3zgUzGmJGxNpaEXfWl7qmBBkKCHQtZWyQWIY1TidlP/b446x0ajGyvkuWmPH61SMvHr9mVuDJsnIGKcbvnK1ng/N28OJhMURvZ6FUzlW/ugWkK4ain5Ky+SndzlMShsWD65TcnT9U8ZmjHiwVbvWnk8/Ii/idFCPfA7j38/ayJmF4etJfpItCif9ixiPO/ghUpRFSk1s2QqSs9myEledsorHutt/v3XSRtmAVlkbwtJy9WnOHJgLT0lCSEMMokjDltjNF+KgQrrCtyB1uW+SPVrOCDILhNDjAu37vnikpphqMY+q6ZTnAp6PKZlpqFnov0V/typdorVy8DvhIxa0oduRnPRqzamfp2pB4zkNbmNIuV/9euaI3uy51VpurwlTVU9L0XLTvUAJ9NfnvXFhwRYj0pqfwf6k9Qqfn+8g+xZTpZwxq/BpfTR7XyviwC1RVgdzXE7f7nthf8Kdokr3ON6Bazs1RvK2iQ6/zEESGh/SMVS16+67R9OuO0PIQfYTDum3Tx9nx/XwUlYbUNHYOkLE44UC7ew0FVrrGAYBT5hiU5wIpwRweU0t5iwvUKyLxwhD8MdevII5wvP8hjxR5pGxamhpYTTRRpglfpGJUxe8p+SFZNwW5Mz2Tbe+M+T66o4T8/8GS0KolRavp+TL+zw9kTD4hD/h3whb7Ps11XciZVtyW0sZp8O+nqUWiYsG9n6aATU3C4hCEm9GyCZB2k7vr2HzLsUzOJKC3Uw/J9L7nGuWXOkFndzCigYIDM3/52dfKB1kxlWuu5bTMsN2dDLa7Mzvsc3bY8kzBdQ+oOMYcWJ61z9VGBQEXtCfrUgiw225/E9eUoP9nNp/vPTNhBlpucubBJJF2EnoYT6NBV4U6m7IN4jiS0ubMsyb62bx11hQ+GTEX4SU1wxiPDwvStuyS2c0Qsvl5WivhemtRLHPMrrQ5QdMDlCAFmkVl9bPqMgr7LZ1X/1ieWv9GaEIHk4/wfKQixGT8TvG5kebzF7S1NFn2jN7+GSw1vJMCM/6pL0xMPtAu+cEXNQtqUoy8yqn3/BR80PeGBPVmugKegJY0bdY8dakvq66HUcHfKQxoSjGQNl6RvqXngmkEPle8j2pJHL3QmNpUK8t31WtnTF9sJo4+oBRunrHnT/D8Bw0mxk0NCd4yiUivnKZoGvqQX8EjOWm7qL3YUP0UnlgNfb1KjW/BjXnxWbS+xSkC2qq0bF27OS6BQFO7FOLHYcoufrS3LQzEKMtjRZhRA4s0U26EuJKKJ02wi8LqUSaY3NGDTKScMTowND3GJFPMqZHIMC+gp2TP4C4vqX0QlBIf124GyX7Pc694eITgqlnl8Y5NmtF5kBboj+lKkDjqTc26y+rPno1T2bvGD4qIPOP9VN8sGrBCBmaDQuWq3B8m1994pKecMfGcVskRRdIxX50JH09STVqmGqZ3+zyhnS0ung07Mt9zJpMHOTZh+bTIsCz5CfJf9k0/nYWIDRFDfDbcvp/KXNPMLA5rdiPrj+b7/mJx1Z85Be0AqZ5/laCoAr2w0DuNULOaDISOSybRlTeoSj6eWEFfpkz5hoTloPZxdQdIKL5Vr92KvcjBKYPB37IY0GIWsO8/8CKwicPVILkwz7XPt3BqdXEsWO9DB99weKLP6q3yVGHzqkt+LsYwaSzORjQGwz326unnBlLUQZk/wJsEro9QHaDPecX0HegtLyo/It1k4UjIEdQPiTKuKDHS4oiqmveFrLyUBM3BY4ou85P8isipNaZ/WMtwuK4oNZN0V9Qd8Mzt98OHXu/GwwDP21mocPbwwNFtP21AOUX9dGzA0/eWHdlRpvnsU3UepWxiUEePZuz9Y3ph4At+TLwgNCnctc8zRekmFyhUbb0ZPGflRJy7SEcnY+1sTiVKld5tkxO9eJfKyUXTqlxG8+/R4duulmCFWAuR/dE4rOgYZq+VOnfZZZZ7ZR/sWUk2mfCh0TSOy2j6rcZ0T292Fjvz604+m3xmiUbT95Hw7Mvk88NvJ586jOf5ynxZ4NPveFhbqvDIzI/U7yo94znE6HpRXDdNNvmYYlNf4f4kP84LMOTFmLjeTu14fG7kLxNHVcmpMAIbuENLzNkSJj6VZEm+P1ZKlcxrd3ZWTAf7Lh/su+lgMbypj/Vd00egUgeWO7ybb0fje7cBZvQ9pkA1JW0eTYkX2hT0XarOaMJbVTCqUITWOOKZ9ZVyBWYjAgGaLJtCPbHQgDmzmcDbTs8rozlYE4SqYCPdTLy+luVcfuUpGc3YIvu6KU/i9frpFTVz1S8l51YT+haeqOk46YnWNIhenzxu8OtbZGi8eGvL7Dpo/jBvacq1nRDSyR8pZRpbHztVupjH4Pcqf5zaJGTKEzoyAhN6Dx+Z6Bz0CyJ3e2IHnZjhbdOc6myavMQ4T7OEsUsZc30ztmbP9qCoLG2974toq0qzTdpQySX2Ps8KeW7wpj2nbfQZvTrITrRgEQBX0kQIxbZYx1l+rlydDb6pEK8QggdqV5Q6+nXCmRQp/4LSybGauB1Clbhyqrkq04TttDnzbz6nqdW6sbF6NRgNgDw6PM2j1OaQLR+SbDWI21xqDRfBKx6fymK/X69mP8iW4rrmslDyfLnfQFHsC/q8JsCaLHewvszdOuXQvAyPFVJXlXuR8VOUmDta7Si7EQze/T/qu4WzWyA8RBEKIl5ZiFzhy5IDaNCJRah4a8HiulKnkquyRlXwHPD9LUDqW96Wt+PQy7rs/jWYiums6tmBsz7qdr04LkEWYiUiKhs4r0fhaBjfnb8n2wGSuLeMu8rUGpT3POW+QECssfmFas2t0VCF3HZZ5sQwdzZXrTN5NjvCY5xK+DElnfI4IJ32U+n1aGSvZU5zL2xGUtIFW5Ga0T07heD4qcQK7pTcPT9Hm5yotnMCTDmuAEM52WSMaxZyNGhg5hhoIT1jbKi7XgAGf8rqjHmdcQWnrHYUtBz9zdwFW03J41PWhYc7T2BxeLcCUE09eX0b/Xt421d6cdAMAoBEmohMcN+LyhRZpxSWqOxXF64kixMdx5tBzue9qsI+w17DIfkU1pVRagNsVFhv5TTutNUmd7xMzJi21jO54MwXeBUdcGjX5dxhqKjLQSnFKGPPtvUBzub0+lL58Bp+2k18jo3Sfp5yM1D51rKIvIkDYZNP0HSsVTmIZTqlazmcW/nIjhGo5lmwVstrdItUnsV63V5vXRiIxS1eKRRW5JUKeddxxTO3XKvkKgQo3/gD1O8L8/Sz+ufDc5vDyYkNy86hdXDnJDqY3S5WJFpxl9/JZFm5ezu3pcnIqiad+NaWBlSnAhrbAI1nBDTEIbWajC7Ladmr805u39kI8dx8faeJR4IxljrcEX/HJSc/FB9alQt5Yr+nqXviIp4d9p/Y/CXnYnoZz1i8YHuN0/ItpIaEzYIlvBjchpKp61oNYcPOkh1xXP9lOhCD4/LIXktBPVzlMm+AdE5TUZZN1Ep1UmIVq6niJme7l/eWftbtAdoT2LehM2nqAfqoWv6OxPTftMvWKaNkMKiZhiu/zSlTF7Qx48B0O0IzTrEBNxkBct4g4C+tHa65ceJFKAJsXcrXg9TLx9sspD77VGnAIYAiKUc3cBDurZJBWY0u7WtD+sCOY2fxXBTlvhfez4kaVvlvJdmpz54nCttDDPv1dhgl7IEfr3PRh4OHRZi/OG9Vo4Xo4PX5rOs6AL7/8HogXUVJrlJjSgdVcap0hKTQAwldGE7Nshx2xdzWo8aqtXdq8sutq5RqDs+qgFKWMLsfxnP7Xo91+24cs6s9PwkjhAgkjX/O6OskFz3y3F4Y9Mdyj2L3QX76StikUBH5dSncYffjxE1GcUnN6+hh9Lu3hiv43fT7vZ0Z6o6r1+3MALczA9xkBrjJDHDpEIpyV+MQZDhwWLZi8gpERkth4zK+UJiQri8Y/iOZ2i5ehUX5Lh9gzB2/kZBeKPG2H/thznb+hd9L8CDOxfmclvSG529tI/SXXsmVrPmBPxgN1v2/k8c68Wf9wsugb73UahWPdUbJzTD2xX0BOHPtHTAMkvZ6N/K83Pyw7lKIKfWUDCdaK28c6Bl92xvA9SYfNV4/thpsuPF7HbpIxnAd1rUwkGYQ/qzX1r2t0GO3VoHBX7mWm8xGOFwLY+ViLb3U7WBwI4LdIXE7Mn6gvN3Fi0PwYCv+4RMAiM0M1xdfaeU1I2iOqinJCPidASWFVfveS94ZK5tueaGp5d9TaiilVlByxue29t1tr/ueCULOKM63RyQ4onac3nkBL2AbK5bxURqL5AAaRYT3vTfdMSjqN93A66cfQKGn+bz1Kr8XQYvBIfPL4eo142dUf/jofwIR1OOm12hfeWsU1Ovwl/OjszIaAjcD/9OtB+fnGo1Gs9VsHbvHLyr2SB3OzdSh+SOvZZPEu821+c2dQHdfTO9OTG6W3rQbMTAsiZ9a/0y7T8Par/qteZrmvLFj1JnC/mgQrA/dQHzB5HV8R+PBsJUUaXUEYYQCFKtPgMDk6fpaP3yokjVGYPgvIahy5Qa5shQCYgaKaJmbB/GMDVf8KL28RXtGWYRbVxPYB/GyJXoTT/W5ViMvnNKBmVYFthZP3v2I65+7Hmnyobyr0bwqygXqeI9fo3Bzc4XOlXsSf3j/H6t0RXK92Jdx7dIBTJVLINsy4akXGdbumo9GH6c1cRiGXSTPgXx6ZYY1AtOaW9bt1oL/6sUFsp5hQI4gZp5mnvkw0pd13NY3xqDS3vSiLmzSzflLebzcp49PgOZTP3+p1Wrif2ik3KePR+Rf66tHI1CwSY5It+P1d1Gtadf++Xe3m+I+1MVREuJg2kgIe1zOFgHAWAwSsUI/dyz9zNv6GTcvFPrhZMfCzc3Y4zm2Cg/gRslzJJ/Lo0iPjJ+mt5Lo1R23m9wg4OkhBpiwiDFmb8b8TZFZ8rPgA+UynUp18SaKL5pn6e60Vcmb+zrm7VrTPAn+0dbaDt3CnsIal8G6MwXWuDZ9qu4Ol+mGaULRvGmN3TGsvqXJmCS7zgadnTZR+3wLSJ3+R2zQGRtfJ+baian2bMR8+Fv6st8TXIMC11wwUnMHucZYZAV+x8AqFuDIKhdmngXl8nNKKsziorGjBGdxsdIsJHDTLCzAcRYWVuh026UqnfqF5n0bMS+5sUc+443IDWJMsKA9L+PrToHTO+P8m6RQJ7FJAzn2QXuKunbU0dM2emrDL6xQpwuEccnIrlBk5PDOAJbb0mRg4HAy54k/52g/u9iqRGz8Y5HZx0itW9pLRsqjXoGyXzIv4IB/ADZbxd+nn1FVT7yqC0cHxcWHY+uKGMajrhkcy2fCbBSQ//hmuoT8ez0VV1HMBtbFiAwcIfDhS0UwRc3MC6fp1GRTxtUVaq6UHU+Bvthosl9E7hDHCvpU3CY2yStsfGQlGrVqdotlljdx2Y0ceZ90UbU1dJeSMWBCo9QmW3N3pPennfl+LuFe1WSc6LVLUhkM8Tf8aAgKRyQrcd/pByCFP6TE6gPTVbYYPpeX2YpjJl/BHL/Nf03hm/Q22wMlO5vfYZYzOSw3rTq1QqRNehxyxhqhqiAauIdUKvjCb8pJqJ0noLVRP/H7fiDR+Zbn9vA6fvG43oXO+ktuFLezn87bXpSA6Q/Nl9zueyCpwqi9Po4Tb0C/Y4f7viT+VXcgood/4VpcG5n7GpN2AZyat07oPDAfy9FP4NDH6T853Ec06ljkzMTRo9qvKpMVMCS4pa1yzssFq0YBmhOZvCS/SFodpXFu3bVq6IiyJW2ECT+ShxdfRsCWPKxyI0AH5XI/jHHUyu+rD4DfF6OtmHllqaeeg/U9IIoYxUubKY8OBhQEOAx8QV28mqBPlLPA3kDZ0JDxrnycqANbtKOPzquQDoQy5Noo6KaXuLul6dM8vCVWwBHead6kbg5dFW5dzTWmS5cxRHIt8r2g1x/XoVqVAFdhpzvywXQRC6OoKqbDCl+V9ul1w0Fer+sP3D6ePYi9njkdfoXXyc6EP+AJo9r5b9hh3KTK6W/eU6PB1E1X3uWB11eI90KAN0WBu5MWcL9+M4VUHHVhdfCLf7/XPt0uLNpPsm/2ccxV+wrfqRGFWMW0hdaFhTayOt1R1MaLgOk6SbzpEdYAhGxa4WxbHAiFesVSYzYCVhPfIinlw4LDSPq2LYMu1B+2TX6n3ZzsxTgE9xW2515uNRXnU3u+KT1P7QtNk3SeazVy0nl4BOfSpRZqo0duafzafD6WqiJW6L1C5ZU5pEBhTUbS+g0XCMWL2DZSoDSYaN78gWv41MC0jwlkXni5ueZGW36gYewSIIyBctH3u++da2+nWQqdhWkDJRXwWIOliF/7woVW+RAvzjJEPfSJRpKUfwMf1OH0wd3JHtJsFiXDXoOzKwRSG2EIqdVGECTZ2lxYChl6s+92vRhIdTXoRqB8Aq22nEtrppXZW0gD63tn/j9l937ICb4AAA==")))

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

            clsid = "{E31D0F45-8A5A-47D7-A4A3-CFB7F0C8B731}"
            progid = "EnergoLogic.VisioEditorAddin"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddin, Version=0.1.0.0, Culture=neutral, PublicKeyToken=null"
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
            progid = "EnergoLogic.VisioEditorAddin"
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
    def uninstall_energologic_editor_ui() -> str:
        # Disconnect and remove only the EnergoLogic editor UI registration.
        try:
            import winreg
            progid = "EnergoLogic.VisioEditorAddin"
            clsid = "{E31D0F45-8A5A-47D7-A4A3-CFB7F0C8B731}"
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
    def get_energologic_visio_crash_diagnostics() -> str:
        '''Read bounded Windows process/event diagnostics after the fixed add-in probe.'''
        try:
            import json
            import os
            import subprocess

            if os.name != "nt":
                raise RuntimeError("Visio crash diagnostics are Windows-only")

            ps = r'''$ErrorActionPreference='SilentlyContinue'
$procs = Get-CimInstance Win32_Process -Filter "Name='VISIO.EXE'" | Select-Object ProcessId,Name,CreationDate,ExecutablePath,CommandLine
$since = (Get-Date).AddMinutes(-20)
$events = Get-WinEvent -FilterHashtable @{LogName='Application'; StartTime=$since} -ErrorAction SilentlyContinue |
  Where-Object {
    $_.ProviderName -in @('Application Error','.NET Runtime','Windows Error Reporting') -and
    ($_.Message -match 'VISIO.EXE|EnergoLogic\.VisioQolAddin|EnergoLogicVisioQol')
  } |
  Select-Object -First 30 TimeCreated,ProviderName,Id,LevelDisplayName,Message
[pscustomobject]@{processes=@($procs); events=@($events)} | ConvertTo-Json -Depth 5 -Compress
'''
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    ps,
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    "PowerShell crash diagnostics failed: "
                    + (result.stdout + "\n" + result.stderr)[-3000:]
                )
            payload = json.loads(result.stdout or "{}")
            return ok({
                "processes": payload.get("processes", []),
                "events": payload.get("events", []),
                "powershell_stderr": result.stderr[-1000:],
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def launch_energologic_visio_qualification_copy() -> str:
        """Launch only the fixed EnergoLogic qualification copy when Visio is not running."""
        try:
            import os
            import subprocess

            if os.name != "nt":
                raise RuntimeError("Visio qualification launch is Windows-only")
            target = workspace / "KRU-35_normal_scheme_v2_energologic_qol_host_v1.vsdm"
            exe = Path(r"C:\Program Files\Microsoft Office\root\Office16\VISIO.EXE")
            if not target.is_file():
                raise FileNotFoundError(f"qualification document not found: {target}")
            if not exe.is_file():
                raise FileNotFoundError(f"Visio executable not found: {exe}")

            ps = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "@(Get-Process VISIO -ErrorAction SilentlyContinue).Count",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            running = int((ps.stdout or "0").strip() or "0")
            if running:
                return ok({
                    "launched": False,
                    "reason": "VISIO.EXE is already running",
                    "document": str(target),
                    "process_count": running,
                })
            proc = subprocess.Popen(
                [str(exe), str(target)],
                cwd=str(workspace),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return ok({
                "launched": True,
                "pid": int(proc.pid),
                "document": str(target),
                "visio_executable": str(exe),
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def get_vsto_build_capabilities() -> str:
        """Read bounded Windows/.NET/VSTO build capabilities without mutation."""
        try:
            import json
            import os
            import shutil
            import subprocess

            tools = {
                name: shutil.which(name)
                for name in (
                    "devenv.exe",
                    "msbuild.exe",
                    "dotnet.exe",
                    "csc.exe",
                    "regasm.exe",
                    "gacutil.exe",
                )
            }
            program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
            program_files_x86 = Path(
                os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
            )
            windows = Path(os.environ.get("WINDIR", r"C:\Windows"))
            known = {
                "vswhere": program_files_x86
                / "Microsoft Visual Studio"
                / "Installer"
                / "vswhere.exe",
                "framework_msbuild_4": windows
                / "Microsoft.NET"
                / "Framework64"
                / "v4.0.30319"
                / "MSBuild.exe",
                "framework_csc_4": windows
                / "Microsoft.NET"
                / "Framework64"
                / "v4.0.30319"
                / "csc.exe",
                "framework_regasm_4": windows
                / "Microsoft.NET"
                / "Framework64"
                / "v4.0.30319"
                / "RegAsm.exe",
                "vsto_runtime": program_files
                / "Common Files"
                / "microsoft shared"
                / "VSTO",
                "office_gac_pia": windows
                / "Microsoft.NET"
                / "assembly"
                / "GAC_MSIL"
                / "Microsoft.Office.Interop.Visio",
            }
            known_result = {
                name: {"path": str(path), "exists": path.exists()}
                for name, path in known.items()
            }

            vs_instances = []
            vswhere = known["vswhere"]
            if vswhere.exists():
                try:
                    proc = subprocess.run(
                        [
                            str(vswhere),
                            "-all",
                            "-products",
                            "*",
                            "-format",
                            "json",
                            "-utf8",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        check=False,
                    )
                    if proc.returncode == 0 and proc.stdout.strip():
                        raw = json.loads(proc.stdout)
                        for item in raw:
                            installation_path = str(item.get("installationPath", ""))
                            install = Path(installation_path) if installation_path else None
                            candidates = {}
                            if install is not None:
                                for label, relative in {
                                    "devenv": Path("Common7/IDE/devenv.exe"),
                                    "msbuild": Path("MSBuild/Current/Bin/MSBuild.exe"),
                                    "office_targets": Path("MSBuild/Microsoft/VisualStudio/OfficeTools"),
                                }.items():
                                    candidate = install / relative
                                    candidates[label] = {
                                        "path": str(candidate),
                                        "exists": candidate.exists(),
                                    }
                            vs_instances.append(
                                {
                                    "displayName": item.get("displayName"),
                                    "installationVersion": item.get("installationVersion"),
                                    "installationPath": installation_path,
                                    "isComplete": item.get("isComplete"),
                                    "isLaunchable": item.get("isLaunchable"),
                                    "candidates": candidates,
                                }
                            )
                except Exception as exc:
                    vs_instances = [{"probe_error": f"{type(exc).__name__}: {exc}"}]

            reference_dirs = []
            for root in (
                program_files_x86 / "Reference Assemblies" / "Microsoft" / "VSTO40",
                program_files_x86 / "Microsoft Visual Studio",
            ):
                reference_dirs.append({"path": str(root), "exists": root.exists()})

            reference_candidates = []
            search_roots = [
                program_files / "Microsoft Visual Studio" / "2022" / "Community" / "Common7" / "IDE" / "PublicAssemblies",
                program_files_x86 / "Microsoft Visual Studio" / "2022" / "Community" / "Common7" / "IDE" / "PublicAssemblies",
                program_files_x86 / "Microsoft Visual Studio" / "Shared" / "Visual Studio Tools for Office",
                program_files / "Microsoft Office" / "root",
                program_files_x86 / "Microsoft Office" / "root",
                windows / "Microsoft.NET" / "assembly" / "GAC_MSIL",
            ]
            wanted = {
                "extensibility.dll",
                "office.dll",
                "microsoft.office.core.dll",
                "microsoft.office.interop.visio.dll",
                "microsoft.visualstudio.tools.applications.runtime.dll",
                "microsoft.visualstudio.interop.dll",
            }
            for search_root in search_roots:
                if not search_root.exists():
                    continue
                try:
                    for candidate in search_root.rglob("*.dll"):
                        if candidate.name.casefold() in wanted:
                            reference_candidates.append(str(candidate))
                            if len(reference_candidates) >= 40:
                                break
                except (OSError, PermissionError):
                    pass
                if len(reference_candidates) >= 40:
                    break

            return ok(
                {
                    "path_tools": tools,
                    "known_paths": known_result,
                    "visual_studio_instances": vs_instances,
                    "reference_dirs": reference_dirs,
                    "reference_candidates": sorted(set(reference_candidates)),
                    "process_architecture": os.environ.get("PROCESSOR_ARCHITECTURE"),
                    "program_files": str(program_files),
                    "program_files_x86": str(program_files_x86),
                }
            )
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def get_extension_host_capabilities(page: str = "", doc_name: str = "") -> str:
        """Read bounded desktop Visio extension-host capabilities without mutation."""
        try:
            page_obj = visio._resolve_page(doc_name, parse_page(page))
            app = page_obj.Application
            document = page_obj.Document

            try:
                vba_enabled = bool(app.VBAEnabled)
            except Exception:
                vba_enabled = None
            try:
                document_macros_enabled = bool(document.MacrosEnabled)
            except Exception:
                document_macros_enabled = None

            vbe_accessible = False
            vbprojects_count = None
            vbe_error = None
            try:
                vbe = app.VBE
                vbprojects_count = int(vbe.VBProjects.Count)
                vbe_accessible = True
            except Exception as exc:
                vbe_error = f"{type(exc).__name__}: {exc}"[:500]

            com_addins_accessible = False
            com_addins_count = None
            com_addins_error = None
            try:
                com_addins = app.COMAddIns
                com_addins_count = int(com_addins.Count)
                com_addins_accessible = True
            except Exception as exc:
                com_addins_error = f"{type(exc).__name__}: {exc}"[:500]

            return ok({
                "application_name": str(app.Name),
                "application_version": str(app.Version),
                "document": str(document.Name),
                "page": str(page_obj.Name),
                "vba_enabled": vba_enabled,
                "document_macros_enabled": document_macros_enabled,
                "vbe_accessible": vbe_accessible,
                "vbprojects_count": vbprojects_count,
                "vbe_error": vbe_error,
                "com_addins_accessible": com_addins_accessible,
                "com_addins_count": com_addins_count,
                "com_addins_error": com_addins_error,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def get_undo_status(page: str = "", doc_name: str = "") -> str:
        """Read Visio undo-state diagnostics without mutating the document."""
        try:
            page_obj = visio._resolve_page(doc_name, parse_page(page))
            app = page_obj.Application
            try:
                active_document = str(app.ActiveDocument.Name) if app.ActiveDocument else None
            except Exception:
                active_document = None
            try:
                active_page = str(app.ActivePage.Name) if app.ActivePage else None
            except Exception:
                active_page = None
            try:
                current_scope = int(app.CurrentScope)
            except Exception:
                current_scope = None
            return ok({
                "page": str(page_obj.Name),
                "document": str(page_obj.Document.Name),
                "active_document": active_document,
                "active_page": active_page,
                "undo_enabled": bool(app.UndoEnabled),
                "document_undo_enabled": bool(page_obj.Document.UndoEnabled),
                "undo_levels": int(app.Settings.UndoLevels),
                "current_scope": current_scope,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def keyboard_undo_once(page: str = "", doc_name: str = "") -> str:
        """Send one real Ctrl+Z keystroke to the active Visio window.

        This bounded qualification tool accepts no arbitrary keys. It exists only
        to verify the exact user-facing Undo behavior of QoL transactions.
        """
        try:
            import ctypes
            import time

            page_obj = visio._resolve_page(doc_name, parse_page(page))
            app = page_obj.Application
            window = app.ActiveWindow
            try:
                window.Page = page_obj
            except Exception:
                try:
                    page_obj.Activate()
                except Exception:
                    pass

            hwnd = int(window.WindowHandle32)
            if hwnd <= 0:
                raise RuntimeError("Visio active window returned an invalid HWND")

            user32 = ctypes.windll.user32
            GA_ROOT = 2
            root_hwnd = int(user32.GetAncestor(hwnd, GA_ROOT)) or hwnd
            SW_RESTORE = 9
            VK_CONTROL = 0x11
            VK_Z = 0x5A
            KEYEVENTF_KEYUP = 0x0002

            before_count = int(page_obj.Shapes.Count)
            user32.ShowWindow(hwnd, SW_RESTORE)

            kernel32 = ctypes.windll.kernel32
            foreground_hwnd = int(user32.GetForegroundWindow())
            current_thread = int(kernel32.GetCurrentThreadId())
            target_thread = int(user32.GetWindowThreadProcessId(root_hwnd, None))
            foreground_thread = (
                int(user32.GetWindowThreadProcessId(foreground_hwnd, None))
                if foreground_hwnd else 0
            )
            attached = []
            try:
                for other_thread in (foreground_thread, target_thread):
                    if other_thread and other_thread != current_thread:
                        if bool(user32.AttachThreadInput(current_thread, other_thread, True)):
                            attached.append(other_thread)
                user32.ShowWindow(root_hwnd, SW_RESTORE)
                user32.BringWindowToTop(root_hwnd)
                user32.SetForegroundWindow(root_hwnd)
                user32.SetActiveWindow(root_hwnd)
                time.sleep(0.15)
                focused_hwnd = int(user32.GetForegroundWindow())
                if focused_hwnd != root_hwnd:
                    focused_pid = ctypes.c_ulong(0)
                    root_pid = ctypes.c_ulong(0)
                    user32.GetWindowThreadProcessId(focused_hwnd, ctypes.byref(focused_pid))
                    user32.GetWindowThreadProcessId(root_hwnd, ctypes.byref(root_pid))
                    if int(focused_pid.value) != int(root_pid.value):
                        raise RuntimeError(
                            f"Could not focus the Visio window for Ctrl+Z: "
                            f"child HWND {hwnd}, root HWND {root_hwnd}, "
                            f"foreground HWND {focused_hwnd}"
                        )

                user32.keybd_event(VK_CONTROL, 0, 0, 0)
                user32.keybd_event(VK_Z, 0, 0, 0)
                user32.keybd_event(VK_Z, 0, KEYEVENTF_KEYUP, 0)
                user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
                time.sleep(0.25)
            finally:
                for other_thread in reversed(attached):
                    try:
                        user32.AttachThreadInput(current_thread, other_thread, False)
                    except Exception:
                        pass

            after_count = int(page_obj.Shapes.Count)
            return ok({
                "page": str(page_obj.Name),
                "window_handle32": hwnd,
                "root_window_handle32": root_hwnd,
                "shape_count_before": before_count,
                "shape_count_after": after_count,
                "keyboard_chord": "Ctrl+Z",
                "keyboard_undo_sent": True,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def undo_once(page: str = "", doc_name: str = "") -> str:
        """Undo exactly one Visio user action on the resolved page.

        This is intentionally narrow and exists so compound QoL commands can prove
        that their UndoScope is exposed to the operator as one Ctrl+Z step.
        """
        try:
            page_obj = visio._resolve_page(doc_name, parse_page(page))
            app = page_obj.Application
            try:
                app.ActiveWindow.Page = page_obj
            except Exception:
                try:
                    page_obj.Activate()
                except Exception:
                    pass
            before_count = int(page_obj.Shapes.Count)
            undo_enabled_before = bool(app.UndoEnabled)
            try:
                current_scope_before = int(app.CurrentScope)
            except Exception:
                current_scope_before = None
            # Execute the same built-in Visio UI command as Ctrl+Z.
            # visCmdEditUndo = 1017 and is documented as Automation-safe.
            app.DoCmd(1017)
            after_count = int(page_obj.Shapes.Count)
            try:
                current_scope_after = int(app.CurrentScope)
            except Exception:
                current_scope_after = None
            return ok({
                "page": str(page_obj.Name),
                "shape_count_before": before_count,
                "shape_count_after": after_count,
                "undo_enabled_before": undo_enabled_before,
                "undo_enabled_after": bool(app.UndoEnabled),
                "current_scope_before": current_scope_before,
                "current_scope_after": current_scope_after,
                "undo_command": "visCmdEditUndo",
                "undo_command_id": 1017,
                "undone_once": True,
            })
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

