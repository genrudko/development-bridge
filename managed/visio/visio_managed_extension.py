from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.90"
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
            build_dir = workspace / "energologic_visio_editor_addin_v24"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV24.dll"
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

            clsid = "{31E49DF3-9BE0-4FF6-AC9A-D7268E7829AA}"
            progid = "EnergoLogic.VisioEditorAddinV24"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV24, Version=0.2.4.0, Culture=neutral, PublicKeyToken=null"
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
            progid = "EnergoLogic.VisioEditorAddinV24"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV24")
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
                "progid": "EnergoLogic.VisioEditorAddinV24",
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
            progid = "EnergoLogic.VisioEditorAddinV24"
            clsid = "{31E49DF3-9BE0-4FF6-AC9A-D7268E7829AA}"
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

