from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.105"
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

            build_dir = workspace / "energologic_visio_editor_addin_v38"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV38.dll"
            source_path.write_bytes(gzip.decompress(base64.b64decode("H4sIAAAAAAAC/+19a3Mcx5Hgd/2K5tjhmFkOWgAIyhIgUAsClIw7geQRoE0EyWU0ZhpAWzPdo+4eErMQIiRz/Tp6pbXsi3NseM+7txcb+20pSrQoiaT+wQbmL+iXbGbWo6u6q7p7BqDWjltGSJjursp6ZWXlqzKHSRDuOZujJPX7Sy8NlSd3Ner1/E4aRGHivuWHfhx0ciXWYu8ePObevtWLdrxe8NceVs19ezsI3829uubv8mbyH4ZhGvR9dz1M/TgabPrx3aDjJ7lSW/5BCjD2hj0vvnQwiP0kwR7nSv0oCLvRvcR9M4r78tulg9QPk2An6AXpSLzcCDpxlES7qXtldxfag2mI/aWXXrrpJYnf3+mNFp3VqP/DAOr1/GYaD/3WbfXjCv+1FaTwvXEJ5m0vejvaCzoOVoqcS90gjeKGudYP/Ri732zMuufcV91ZLPZS6PX9ZOB1fEeBRsAYrJcOX3LgX4DzFHo9J/G9nt91Oj2A77zVG/pbXrznp1SIFcV/g+FODzoFtRz2fb27ZPp4LbpXeJ+kMU1g2B1EUIZ9P3qpohuXunv+ergb2TuyGQ3jjm/oiLHBqUZR2stVv9fbiO76m6mX+uZuYhEcBP0o6ceWH/cDaMDQn24Ef31n7cD6ZVT48naQpK+rk3jBWedDwLfOshP69wylmq2awy5fmJWwsx/Flrm9OEzsX0rmgVa8F5lXczUKQ0YWaiNgfrrgwwUHt+96N1EnCN+LeTHW2YC96McltcpnU/b8KvatAuP3vYE/wc7jGHKj37d92rZ/WoNxeGHH3+jLYdDfm0WKRq/fGgbdZmN1YWV17pW1hZm1iwtvzizMvXJx5uLFuXMzc2uvLlyan7/4/VfnVhuiCiHlLtCqrdHAbwJc7YUrn9aTtaHX47WyMbOPzrpC6BiNWxkEuUnkKAAf1oYDqA479m1/N1UX1lDkWrC3bymDG98OAb+WVN708RDDjWT+fs0feEGMW/Nq7N8N/HtVxVYGg97IMpioAzNi6cd+dO+qF/qWblw68DopHGyJnzY5UnQPNvptgSHd0UbfWHGlF+yFN5r2b9vmbxe9xF+NBiPR2s6BbGtnJH+m2dt0ZIWDS3BSOBu+lwxj/2qQdvYtsxvg751hygtxeAN8sEzOahTFXSByqZ+YYV4eAj224xZ9LkEu+n59UPJxLboX2jAqHCI1I9Tkr4GmrfkJLBqxaMZqVwZ+TF/xKBxahiW4FZ0qllOT1177/sLFtdm1mbXzr1yaWTj/5nmgJq+uznx/ZX5u4dXzq698/9yspCZX42hvvatxUa7C+Kx0YdZ/eO5VWX4VCbCkMU39kQjQyjCNipTHRL+dRWd9bUvjEefbtSjTIA7uAi440c6PEc4db8CID7G41kLd7nq4HjICXSzG2kL21bmzC/8vloBZ73th96IXO3d2vLiswMVhmkahcyeN9vZ6Pnsqlr+Tr3Dprh+myZ1VGMw79PsH8LXnxwIQfyxCin2vG4W9UTbYZBR2NuE/fsCy99qZzKvuRFGPl7/qh11EvGVn1+slhjniiMlKb0Xv+CGUbTQqChKvhwUD6HxV4Q0QL7w9Kq5y9sefHj8f/+T4+fEjt1EyfBBT/APnzh6Qd/aTjZ5+N2U1/PeXjeYbr6fESF64+Vdnmq327bOtMxlnkTTfWLzl3oBCcXTv4MKt7tnWe7dc9khP8LHVaGswqZkrAybQre+FwBitAlV13tO/wKoPAtgNreqBdGR/kLpUDumviv0XHRdd/u6J+5xnfe5GQde5EmZNNzkSrmS7su2AEHmHF9mIur6j/G4LrF0RO7QNE7HrrMSxN3I6wySN+i3Z6qHWfXXrw8ysmAgBK6fufiwpnvVyaTxyDuGQBokQhrYfJalWlt64V1h3l510P0iWnCMHWuzsQ70jDRa11uttKTRA3YD4z8hMHNmmGA7ODCGaOKPZG5rUa34fTnA2p3VnEEasPetfiQnfdZoaJXPOAA4Oez3ne9/LUSbxpVUAQougAnGJyjkzy1bixuZCfTLPM1sz6iUSbrV3Z+iNC7xwkAyiBPCXEXeXP8O0W5dPAQvUXo6MaL+7BtxoWlqd9YVVyuGiPmUlRfh0G0tgn0wflG7rOC8HUMDv3NGYQ3JqAoZpHWh+axk6q+9SvYAV3WnbJdcHXaCMzQI6a/3QK8KBE6fDAdIsWqVJ6l7094Jwc3+YdpHhM9cskG0xn0B+LLtMaIcqdpk2T2K90n04c4jor4d3vV7QlazjpYOOTwS62WCqr+Nnx4+d46/hnPzs+Mvjr8Yfjn8+/vXxs0aO7OC/2E+HcWjhnfStZxgxzZaRwFkmQEwRNMfotN5Yxgklzg7+b9lpKu9aUM1VnvXKQAIBjzkbAbUve/08A9EwbRK+h7C9m7za7SULyVHKuoCYTV6+7WwkEfToapQEOIVunx63ogF8CRJUeLo/9IAdaTvEqS+pk1lvpwMdcZqorQjg89wS/Hl9mREhOEPTOOrh6TwM4XAKzp5tVWBZNoe8soMcogbtZnB7yYidmzTB7qV3gbtPmh13y9tra5PsMh7aZQjRaDusBu5DLw4SmJ0rJMX1WsXz4bD6xICOAv4kBTZ7yVh1B3ipd4qfjkqOl+JBt2w7zvIda+Y71dJXCFEGMIU/k6DUl4+sRgFhyh8ZOpUgk7vqDTjBLdkJehVY0lzx3JqWVd5MRz3cd7gj6A29oB1Bj7w/pe2DMJIGAzQ5YD+O/wCU7Mvjh8efHz8c/2T8KyRtD5HGAWn7lVN3UFxURn4N5qzqLAYyW1sua14J2bzQl1ZZJxi3c7ac2yGcsXXXRoW1PhTw0FlN4x7jBknSW8VDurfm73rDXmoj1lqhojg4KeeqlLU0mDFvfMc5773nFHi34i4UPBYsWia/N5Etzy0GNsCZQT6/ghPEzuXZcvblIhKvrejNGHapucQKcOK4EOVzYNWjwrHCT2H5gZRIM3OtpSKDYte12uBUgMnUsRkAfFerD4q21lC7orKqy81qaxresuoGVW8GJftIurE2Q966ALlS2AiOANWCJ/THysIIjXLptGT7BGqqO0yAaXzz+984QBWNRJAxfpxcQoGHbqO0uVqq6mwIWnFWjnTZZU0IpXYGhd40GweNGhW3DRVHFRWnUYdnjWBtsiltxV6Y7BIxISRCMFgfK6Liu6oLk2rSS7vAEW+SPuhaeGWH6tr5UiQuV9MruJ0rKBX5ZdA1jX4GS1f0lwFQNP5mHJ2Zc2fbzqw7WwNOgZKpgCaAgyYEM5BZBDJXCwgzNZSAmamEU8MmoZI4pXDeclHWSsGEYTndexGwPs1MJ92yCaONBFXFyw3nrKY6PusAIUtR3ax8Yupn+tRnOmPlI9ciq6eydRTSxpLNCHMOaWjCWmaKZjX1oxbls24QM9XclDKw+Dxg+m8UeYnB8K9qQyEGTfhIAJvWg7KkB7zLlhD4lT47SnFUCKxlbichXxDhPgBQsKxL9vLEXU/9PkJaX2tiG67maGABmGp+GQDwLT9V6l0coS8C9ajtCKDrXf4bv8H6ZZOYY+Bgghl8KkiwCZzeaK7WpRCpnfj4Zuz7vHlcsJZe1V1faxMn+QMv2d/0hT9CfqzioGRd2OjnOgAS8dUgvNFoOTP8uz7N8rsZ7KgU7HYF2O1GXiLMXC4S7vmDqhWacOmDgVK5H18cNWFMF5yDFkhhWC3P8hocZDhM3U0GxTyYdPUtn3TZhbwWnLAV3leUox6wmbp5W7ROZ6XmRyJLGEfAtq+oveEl0E2tOi9QozKKqXWqwiHue519rsXpAi4rQ6xQ2OiblTanfacGXYOiT50m0kNgd8UcAc1T0YlAShRt274hHh5Zm+JzynQe9Bs1ZSqUlrUuTSnV3PR26amsXk6XhtMLdJBmiDY4klBS6F4Pu9EmfmlK+uJccGadNzRdx6Jz/PfAQX99/GT8PpoaudJh/NH458Btf3H85fi+A2+/hq8P4e/zhrM4Tf2v4AFr5wZD4nkHxPfAInJXW2pwvGvRar/bnJudXzBMssCmrji8utpBw5w4XXl6mPWANLUZBKZ9RPOCRGr2ajLN9aPjxzBrz8b3j78iNTYJM1/hi/GHDkg1bF7h56Pxg+PPUPqB/57Bq49M2u2M7kHrjOjJUSGhybpvq5zRGYAwAZGxbHjWjbp6T7FOUGuaLY//ZK/te15AL2x4/YNttx+Zxp2pqmdJVZ1HCoOW2j4NiG0KBbFMAZvam8HtVivDQk6E4C2qkiQxmQQE0SJ8Z+wb7cgJ8PsJSOVPGcoihgN2j98ffwSYDCK7M/5bQmf6ztwcHCIzTzLM5xSF6j9Zcugt7piH45/hJnDIP4I1gP89bNRaMc53ILd/11/jzgUCb4ChhOlqDpAtGNycvY3Mh36aFEosVbQwKmthrrKFOWMLGSliYvcBQBEjQi1F9gjSc6PfN00NMHxpz6e1WtkFzHnLj/o+UNzVfS/cIwVfkRYConvMbTfskmNGhuv05sou452Fb2/LTE9VGK87szXJ5vE/oKkPFhoOFiSHz3hflOMG0eeRxKDjJ42SEwFaY920kxq+SZTumlYjkzZJSMEDpoGzsIjSGXqouZf9e+SphowmsxA1G5cbE5FRXC4G3g/TIB017dSxnXXF0ATxs9zHuSnngIsk4kPbyTPj9FlzoDbABsEy2B0R/2uHbBNEarVgYMnlZqjNlfMpNeOmEVzhxC98M5PMOnhtpbWCjn5NhO4xEc+vkG1ADuEnQAiR6iFxfEyLWk4/tU1Sh5gau2WYM8m/FU1Nip6DW1LRWOGlzdVhjy3NbuSuDuMYUJq/ahubZUrgf5MDeOiMPzAM86FzOHvkOse/h5F9gIeKczh35Hzzs4+dw/mjJazzGZR8cvypc3hucdadnT1yYMhPl/j0AYcK1bAiAnvO+dZncH7zPYcQnsOh9plQNpt7W2C4Cxy0whIruoC2Iu4DET9olTkG7eK+6dVhj2HnZcIACQttvmitGu4PeSWQNHj8l/7nBet/VKWME90LOS+u6Wp0tcZJVUHQyJ+d7iePI/KqlZNwJ1ycNP2LwUmEIRVOZ3FP5y9fCVm7OIOFqsRfdg8MH3Do3VHxQ+1DLLf0+k5eOnU1wR/otCCGnUjkk4kVBfUglKkK9gSHeiKVgaRJFcxfFSO75qfAqklWyjNxO0a2W1f9lW5hQcPNygrB/CPHb2XzC5NWPKdP82TRm6vQXqGLQq7CS1NJnBpy/ZLLnI9zggF5Cn4yfgA49twhizFpYMa/oPLPC5rkagFpQq9i2IWxn6TA43fFhob1uMZeIQnaigZRL9obUXO0uFw9jGTrNHDpBXFjnJdUp39qXqyCv33O1WaoNnjQtjJtx88XncOFo9Nn0SxGGOTX2oXVbVW7djclFjspX/1LcRzFVVpyzo4BIzfww0T4Ga+KR1+ceEkm8zDhSTsKLziH/Jw0qbumll5s+zEnZMAa0aYc3yeW+itayl+Z1pSfFUxn9CUhxxPEPxIDaKd/cPwIxKPPcZ+jvPQBlsQ7NI+hPnZCr/Icb9coSAjMvAPSunEw2hSfhWLHf+CwniCeL2JFfe1cbow1455W9KUKCasWT666EVUw4pzTXnlRnPZEFElz8flYU3I/RK33ByCXKiScT3XOlMckc1yXokqx7UhuA1b7F7hg4wcZEM6AN9QLViXTbPQeUnyHylz9Nrx0313ZSeC0bjmvO3P+zGt4WyN7PRKv6yrD/im/t+h4ewrD/iOiO510zIOULAxIy2CGnzYskszJJbTMABGQ9YEfJXCmve3f9XulaMNElcsRXo3M8bmB2Siq64CCulxzEVod3jjHyf5fIDA/R1Q6/kKhIS/AupXfTcGLYBAnY3OqGRnTrCuvrGrDyeudsuqJEyLz6i46N4CjAU7lO9/5DmNV2s428DTqG2B3Pj415mUemRdHrN1EnAXn4OFsr9L/1DtfDA56HLkHmXdfHZ8/2+GkaBlSNGXsHNj1BSkaN3ZGS98Cif01OZYys/ZHDupQf8YPKPYGjxVAFRQuSDP4iJz1gZUZfzj+yX8R2ikILWJUTReFD+CEk+vzHPeqWA14qK9+KAfzn0XSEZ9xLuqajfN+QnGntuXeYnYKTKZ7ewdOx3FHCjdx5wX77Zhtw4ZRiM00oddIzvVEWkqzo1l6U9oWhRujsluRDM6kvVD9VzIzVjChywraXoV/CqOGwvzyUU3/lJo+KmU1FQcV6PEJEdzmnlIPx6WV8CRoDqOwo7neQgHTTZ+nQHbuqkBHL3XH6AGB27GG44MGcWSGOGeDOGeFCHireDl0pYNDCU87HV+r6lVOasmvsObjrvyBl9S06LcmM/93bLb/Kgv69JbzgvVct5oHNe3lk7oYnY5pHMFY2YDHp+Z55AO7UPM8P6FINz36Ty3DnUSOO/p2JLtD1DGXLvWi8++/vZET6trwDgS9eU3QQ50wZ1Xz3ClDO6ZDNmpBpVT3rcpw2jWjkysJTyKDaH7lsNendCgPJnAln8aJnM1bz9vxUbmROWeTW7a7FQf9Zqs0bMB6chn4tivxj/YDOKYx2GqToAE1F1BXoxBOwTQ7TAi6y+Is2BHaZNnBULTkRX4y2853cJcczh2RvkND+iXUd5xT31iMK0G3zQYouXIzr64xLq3S3SA0xbTZnsOe+owp34HWPzDwn4u34lshntl8Mv5bFMCZQS/bbKa2Igpyol12Kdk9NW6XWfYUL3zXY0dr7raZ8wZQkIYZmxCTqJr7th/upfsoCNR2lfwYNU04S3g8Oly59JxMMED90IkJZ+/nRktpo6ojF5xXFup25P9UNsc115+RcPFH7Kqiu/4M3j2hs/wxFHplARUtTwD3HlFpGJSps2cokBfsvw00sbG+tzFY2M1bg8O3j+B/l49uK79vJe6dl5uts7dmbh/Otl85d/TdRmtaQ/TH5hl+wgb4NbAnpHw4foqI+8n4PszAI9QFEmfxN8DIoF6Q6Qo/QZRuZ8fTwzYCeTz+Gyj5Qdt5uQ0IzlRPX1JpvnR/yg5YJ/G54Dsp6nXVDaRQZgbcvpnsZFmHOfXa/7MYH1GkT8ie/Iz23hc5jAf+EfDgPv3/J1D6PplscK8ef8nMVaXbtWEfHY9Vo4+o7fA9UAhPkztXph35P1TSF00/ykb7gRjwfWCOnjDTlN0Drp8LoFzfDy67o8Gd1jGkEPM955pIFRvFnQ0sUB1dSCB2xwu7QZc5nOVxu0mwLHYUWTHzK5Ov3PU1M4PRV6yfYeoFYdJU4AB/0YHXQWhinfkuSlm8Gbl3ZPVanA1HMgRSF7WyQIut6V2lbcfJrQYe9uyMPes0bjXQpeCPiI1AKZnaavyr48/ZNiOzMuMIyRKsTFypt1JGfzZhj9Ps4V9lm+XpiJF+0U0jS30awcntk3+QRqb7JHrYruZNrN4mhCX5sUvXnSbUfRuY+DIvxurLYsmUyjfLJmCsvV25kTtALvUH6Yg2QemOUxocUmQ/nDusZW+Il5N3avLUvIqMOxeQVbRqWLJuiIau+YNe8SDke9syI6jOYOxW6cFKSN5yvvc9a3eYukKjLKJfjBa15aab5gQrjvpq7Cd+fNe/MgQun3pLqTBEq225R0tw4Yyxw22H0cQJwsCV65uZPMijg/FG7AplvjfPnq2rAz4yW57EFrdiUV1eGI99bt9+ZGb7letc6KOjcUDE/qO67esCQSNNnPl+l2F1LCziCdiiSTxTpTeadRiSb5TBLL8Cpujn7N7kswmZwakcQ/9zbvEYZkTe5VkkfR05jM6hIyme/JqPhIj6+TUd8gCSOU046+ptnfFPORf+uOzGjoVb5vvgherpciHBCywBf9+t1jSQsOv06f/LLJa1ywTgbl7hQMJw843Xd4Adu+Cebc3A77tRLwVcwUjfzTcWb7rt2xhA+43Wdxtmrz1qyN0cdjp+kjhv8Oe34mg4SG42EHLjNovc6Cyq3V+qMQs2Ai1YsDjYY9dA+IuYHV99P7QG+CM2CqPkFhmXe/tBz3ea7OvrErrQdnzve87qvhfD8aYebLzQTaqFl6jpR57yYqt+iGdOHuoMSCGmXmBpOL1ZZ8qbhqLYMPyZmTGymoPY3w0O1MY3hzvsW3O2zdowM6nJcJfVxO6cdeYM0/KGCSov3kLtd8OINrxPZ9U1gyfWYC1dHAuLxh+8gyB58ZfPTqLtxuNIWtthHufras5+y86+R+MH3DEdqT03MAir+ydEM7mS7ylpylC1BMTUIce1h3mn2IKp6j/RIUgswG4QU1BuKxefFM3NwqeMvPDlLTKC1CakQOalcdBACw2pnREjTXfG6ohXOXi6sPUxrc9zsj1+JEK2PnduGFyQLEW3X4CbUV2PnhcjX22qCv7S1RB3XmtZBSc3aX7rLqn13LtejOOqgl6cQ0IOyhhog1/HWTbYNSWtYivnbkXXB0CekFLFgYdxYS1r9mLtl3oYx1MyYAqd9gVikDN3JL+LXxIbOafCmXPDpBSdx0XhXgpIy8e/ALL+Kbv0oBN1ffXGDxy5ws+JwoOY8FMhVoHkZHM6TefKde5IYetdeJ6vAjRXDkjOH29xvYtTqFaFKjXn899UaVJLAcA8rB2MM/M+2frRnfspvwICL55abiRTIE8M6C2chvnt5PniRed0Tr4zM8gES3ETon3W0M26clcVDbtlgRhL4pSWXUJho3t9AjPivyJeZrY5jLmS2eY+YXpVvD/JL5kUPf9OmQebYsOyzboJYhXIQT1/Dz0upS2r5+8CnZOPMQZFravyx7rVoQSwVOmGUEFS+9UwqVglUI6GDFvVzkq8dZnGw9+KOJ5r7dvQ+6iCIk7M4pIe5AMyej7W7fj1mNwK6zV0aYfojCAzgvDYhrESjpoddErsZASKILRqW99RIZGzAsLvvAJMmryZLVhc18JzAGkZNxwymvXYyLiiBMejg7K+bwSh6Du+b1n2kHIBFKSwUHXA0T83y4JSJHzvMcWS1TCXcO+1DS+b2EwX1SrJ/cEDqinYVS/lR85UzZbdlORDj+NRHr9jh4XuyOb8rBNY1I8BXiuelNkGyfju5D1ARUK5K67XSYdETfKHGo25eLBhP2x733jfhjcwww8gHLs7f/5kDp4T8L5wSD1hm+YJ8UlkWyaGqnBhCwt9zk3Qz3J+fnAys4G0+ThqiSR1YqxQbJXcXmmVBJqUtVBqMoSiKbE1nXqgG1LOAYWQfupVkVQqo6lUR1QxRlKR0VTKkdcSfsYCb2SEVyPujBneqcRuMR2xhrgZtCjswC2aaQ5rGQTK6TImjAMswxSaMjyyncvI6/afCAu8+XDHAw+FUHr7kKzznEOXzk6SXR8/cB3GiLL733X46rw9lK7tk4B74nC6OZ3Ob3IRBkrZGbugdorxbaTqxxQOKQhpO096NlX5bRFwd7UiYk5J1BwFQEnsHBMmKzXLDFx1vOoZKIygyX/ZPeyP/j+NszMlumvBdx4Wg+88LAnjTvOk3sObjnZZ7BxkvroqDCXTGzgNBPBUKZ/OyriO4W4B3hqfOzKYOIlitp3syDArLDY7+3532PNFFCKeTVLYNRiAdm492voc1nWnlimGiPANWFKjK2EPdhy9if13h0Hsr0bhboBr8a3EGDw9Mw9IjHOTCcFsSkQkyrzU+5w5vOfUgTZlS6Xa3mBQYbKfjL5K1/2ZpmUgIoEDR7TS6+XKGHUuQgQUlzx4xl6/K2g7grs4DHrd1fwXcnmy3hrZGgJGcrAisID4e+ECWisHhbjl5XWsF004qgqQ/PIeXdBs7CBLACxHA742gFurkej0DMyJPPW4ZUTALnUfY1fB8/OXOX6KV//dHzHxgbkMocyRwS9rQE4a8fg0W+4qTELqN30ZtFe7siHnBK06bC7QskOMkrB7dYs3PcqqbYtqlVdBcD58ZRokB1zbSbvgnU2xoHJ2UjqxyEuZnG8+kRoZLCxHwh2UOCF+nplYq1DXtNMuZL6oJQhsrGnF4rte7PgDRF45Z63a/GOxJYdAmeDYeUiSVhgZWiefMk5/KlwmRcwPobjYfDdOmc7hanQPAN7o90FK8wdE2ebbqHQ86yjft9Xv5/B72bVV1IpjjqkJ3fNMU0QXA3nYUcNnTHPHp8KR09J2rtGN9oELf9sOjg0f4G/b2eYP2/iAjA2mqtzAd10M9Gn1BZS4ZNjXbFbm2C3GVms6d8F8ODsFd5XGRaodzqTRarnZMGwMGpG9DMrk+/wfeaqBp0ZHQ+RQNS2rwo7RiyztPEN3p/nNL/+fM0fcV6tRp7MXoLQafyYrgBro/DwArioF5ooFMHjNrDt7vmZgQK+/E+wN0Q1uWb8Ft+Tg5dWss1veO37zlRbnp9ky6WywWcdTYsWyuP8dzh7NXGC8CfCpL2ebI3EP54/+Ut4tBInLDKEjsZbPjtw94gXtHgOStYwX/ia945JDIBFKEJHmS3z1XFxLpNeP2E3jr8jeCwLB+KdFpPrm/d86KAqRYf4puuhrcQ2/0E4WJjaRPDH+JSY5Z/oQudKlxyYeBDs++dloiGgUi7p+0okDkUt5Al0sLPGiI5dYPaxojdtcKGIOvrBB2fWN/K1S6qhYa/lbWW7lHa248qwsenGPKnJGS71TiowALh2GbvqJyoqzGVamowizVFIxb9G1wAP56pqfYK5hL0zuUR5mHjTyYnTAMvRqGOeQYKj0cvFWyK64qmuFd1/g9fHvuNz5UIbOxMG80dCTlxP2KYOFz1kfWC7lxN32k8uR+mEdkNj9H0OY8eIVFzEnfExnlrWhIqxs2jWBR8ZTQLR2shs74uIKl54N+ruTqe/U0Z++E5aWaoMzwSpqW+SzIsa38ihfnnvD0FT1LpraTYk0H6UZFNzyXfRiHYdEHuLTchn6UxeRSX+x43VVCYLldSyJwsDzidaMxJAZaOfIQFtyi7L+DUqb0qIZWG5OBtJsJCTeknw6Qpof1JfjyyUaozw/aGHqrbrSOsZJgCqtmpJQZvySzVUJ4KXwRvXgqZK5GR6yFqHvkXmADfdH+34sAjtJyY+ijkmO2CzOHdjkuBEJcOS75L5qkxnU9cEOSUZ8YrkO9g9JTaXhu8SmoZKNTXmjNOiSvQl/wpTCz0WHYoji/VMpYtCBDsf0Q3klNc8ctunqT3ZAFi+MN05FcMPZwvFmk1WwseDnanMgu5nM50QV2NSDApXMfZ9T5UUHeED0hn4AzDFs0WEHCnq9GRkAgQ59PgVFKc5tWOJJ//0/5tvJi39aA4zLy3Ud40KzUN+ynHDiyftk6gFIxg/csvAjshkSvF5tVYUiEVdjcv5vut+beorZTjolMa5iTJlEx70W0CcvHr1O+Jn1ZhgG7w5FshVrsTpZYkX7k/r4qOEopO+17XYg666kykiM9cgTLT4i2traJ2Y6rxOshkOgK1CJgWIZ1lgOyh5c49tZ6SwpQc8jmREjUJ7e4gHrnKUet6ycKSpYPmOCf4ApzHkX/YOlUjon74p5Cc0Hq8aGRoG80GseZfVHPEIsD3T5tRrtHw9DrOgW8q1Pokgopjx4rtkJTalxKHBZPtLRh64xGwEbY5t6OgXGaUjWZmIVJzewNyxIl9/1hH+dfWBgr3qId5KdzV5teIMy1pggpBFa9QTSiiOpgjCpEC44e7E32LfQJq1kDfoE3WkxgDeD7m2Tx2M9GC8wcNmL4XnxDGZuW5mz5FY8AgYy+6LwwXbGjNc+wzce8IMwHxmDzF3AGECkxBNybnJtiHTnoS1V1MuVv13OBE7OZ53RxqpsqvqexbpL8Rd0KXz8P1laFJ5OBXmqr+D/grOERmd6uH2Kl4GeOlDip/hq/KBRtg87gFU10H0z9Trv8LMHf/Iq2euiIwZ8ca8Ok311OmwXdKGohac3p1vqDFEq4W1EA1tYmzM4OnbWD+NSeUzbziFuLIY4UO92S4El1zhkV4PFGMNyTx3F3sfMrnJvMYJ6gXtiGeyD5vI1yBH297/okUKPlENLYxHrkSZy2mKLVDS8ocgvXE2VZgp0p9r5uEhbRKOTe6D8s+VegnbdR714JtxR2FXD8S9Ij/8Fl9O+lFcWlnJiF7dXqP3MjRNVCdLXkBcsGCmk036lezODwHWclkOAuBt2hULm9hJZvYx3xBjQG1J7Ut32XKs8DyY0to0iDD0BnUoCVEACWxaEQToyV/EOlCqX8VqTtcq0ez6vJioLOW28Wy0wc+S8TmNsiZGObOUu0MBaYnijMjGLYM0Ams+6uYAOVPus6Uvumt9l38PEKheHCbtIx/hdZeXOaU9WHOJg973eLiIjQX/Zmc+3nsllfe3GTKajpXU5DQaSuaOheKOOptbVgSlIvE1DaUT6MhWkFY2ENwi37qm3WTAqPN+TFvzLUsCI6jO0VlyfOEt2+hGG3SCcogf4Qqh4gsg//0C+sszDQMTs4TLlp5yFezL+GcZoUKjvohKajisSiWX7IwqFGhF+Sm8/A9mQRVki6ZGuxunZvh/iC9vWlDPyOsPemYr5wIczHHszJgdD1AucNrPMua3Li9KtTLMzqrhrwnxmCn0X6hhHQ/C5ot/ARX71T9vUplLabRTjpi9W41fv8PgoftRS2edhotnacJlIOMjphcV7Uxuxz0JiEtcpfG0OUPN+kClqixU3lGiafDXyGYRLtAZ8N+bJZ1FtwG+s0Rmr3aSx6xEEEKhqp0LsOmZZku+Suwr5jhhpeaIQM6pgoWZK/pELkjwlxeQkE9jRYHDTm9GIq3Towmq1FU3cOKNK/MJZYXpKzgymxxNsE0EpUdwdZpAMZfL+ftlFRYKrXvVKDmzUjO4ezgLjK1eCyFG30qM0Kz+5p1ltfR67lMgd/R9LRrkoeXMamHUKr/WWK/LE+huvj5ZvTLwnXBI1gJjj1yeaj4dSBBButDLt1kM62ZLi3eSp9z3bZKz2BdhWw1CzfYsvf4L7j20fnGN9C9E2xBlio2GKicrNVSUfMliTS4e/N2dQTXjyVLN75RPEevpkYIGeW/CdeqiJewZEJ78c5AwuHcDyZqYvzkEq+Xswi4INsaudd6KdH8Pp7cQent3MwyBr9XpTNNCGfWF1jcnSO6yH6bn5JgCriP+BKzNbnTVaGk+YX1J5aEFEcoFgedl5+vlBlFKWIc2uyF5P/NhF9GhYVCSW2SGyfw1xoMlDmrQEVJp6mHUVtsu8ytavt1p1JuzIKPUXLdjUF3crHl314sTPQofKGZPBQy9TSojNdNTDTR6m/p4fly9v24mGnOAiI01b6IJiIS/2qK4Cp+BZKveqJdY8bUmKQqTQ5kb5GXM3AonEcOO9eLykkn3QTSyO1+tF9/zulXshXoK3IN/kBqDphWStQzmJ5sUIyy9eHzq1KlSzyki5B4+j1MC3TycV/4tMofqcxXMpnC4idjt6O1OgPPioCsUT6EbLkTgX9VBHY+0yYC1MFfYLk5mkGAfu9Oyl335upD8Plb5MnFnuXoezFuH2Rym6purfeaNUfe8sOrlXJYHEBdpkxId60zrpRvtY9xWgbAgyQEqmuR9/OP5Q2AW/5Le6+Q0EODQ+pAtw44+OPx//ynWYY7mSTuELdj1VyDp0L5xy8H3Icu09ZU7rqKNSdFxtZ/xzsj5+gueTiHkNMESSAkoT2DjZPjfuL9OOquNRYwTW9wYWrwKLI8AL8Ztl52Mtr9k8U2ffirKzP2ad/bHsLBqw9b7+ON9XXRU/uJmvR/37cctdX7vtKFBN/rvTSTsyQvWglJ3RiLfKYNTBCK1yzK5y1PIGmQwJOGgSAQvl+ELDzJnlKVa32quQxmB1D6szG/Iwoax2KzVTFJN2AWtwruO997g/t9+TseRqi6n/xMXLhyzCROYpJa/QSzeJ5vhBi8VZE84PxfBqk/Og+egBpd73dkSQg5/Kex5rn9hrvuipEpis3WbSYSIy5S47GYJxvodL26xx4C8I3e2uO3Szi9U9I478bJjsi3GcZgpjpzLm8ubZmtyfh+zudPS+z+3pKs626UAl3eH7zO/nmUHt+IyO0af06kl2fYpl0nuuOALRFFuzZwTdvCiEb2oYdjjhgdI1qY6e/jujInk/0sMXtNV4+B+V4oqh5opUEduqMZPckTnW68LG+qVw2Af02GGOPKUyh6h5j2irgdzmnKcYCV7z2VBWer2auVVFTX4xuMz6P1+uN1AY+wI/b1bfycgVJXrpiogawo5YcFwWoX/IzrHK1Xgs1UGdqBa52A4vv+xcjYM+sH7C8BTt4n25dH/RYUmqQ3LNEObABKSRnsAp54dba1A+9cM8zMSPAyAaf+0n2YU2mvzNfR+mMfZ3fSBraGnaGXHiT8MACrMPkky67xVAUk0WizBCWpvgLOCl3mHPu+54vSj0nSBxwihFOkERgGYSb9d3J1QMSk24GLBC0OmFUZ6syNAngJWm57MfM7k+kb2UAyzN0Kfgyy7gO05xeUaxyF6E9GKl4uDkR6folCmVMB+hixuVwqNhwetV+mfKD2M/a9kAy5rbik6vMamAKuiKs9YytK4ZWLv+6V9mrpRUSM80JRaknaMv9pRgamLECk0Fy/CDlocNnuXnTqb3xZbUpD9spcoymElAIotPHU1JTEdOVpUn/Jm7LYBYV/MNh6nWmV7dBOGHLO1S6TpawS+Wg5+vB36pzGCBbIZylh06mYZU4qqI5BJjXALFoUOeLkdLE4ZVEZxonp6/6fV6O+hijdTTD+8GcRRiNp3EuYfXL7MDJ9rBZEoev86zBydKv+93AziZc9EHAaiHeTXYICPXueZ7XThLfHG0KSfQLjs4nG4QQyO9kWviifKnPZIifuIUTuxpOQgV5p8hM2E6adhoCtEGAAvErFszx3M7md6fliuO+XoEudzkSJOQK8JzjyFF2oOVUekQ77IpTXc/IzzWCcY53OWYznZWXyYZgz120LATHp3gFKpNRW0W7TAb01AYwTcQKl/zd7XxsbcCrjmvtTI9CjXKmZDZ8iS4cTcM+eFk65QXjvb3LbeJ6d++22izklcGLIiLcloZdDmyAbmwVbHGil1X51cBONkpUSajYt7SmixsjaAQOb9e7KtfKZLW43nrZqWuwfZOk51aQc+QETUbr6aUul5SjJGw0MY/yqzXjF+qR6hKNDV6k9er27x+So0WE2WHNCJlm9VgBp333rPyOkXo1ycFX6ayJxwmHUiB7VZSk1fMVq2gyRQygLeneiZZjwML0eAwCldFjl6akI3LwxbsnHIEVbJ1NqcllcWYjlMRjjOZ282EETnrJN8sCQNssJDnsolQ4OykbQ3f3DZGXraNV0rV7/h4Y7sh9BKL6Ajw1jDoupf9e/iXglKIgPCX83rNXgRccvOOl4zCzib8V8cvhJW+ChMLME+U/5fZRtEcMb4//iXz/3/OM99S/l94oUblYtHd9BjZMkqISWWrddUarYmV2uJTSVNqK8QCxsN8DxjMhq0gvwSPRY//t6m71pBQZI82W50pUp6wOqPJ+Jv3/6VRGd/8DvKZqiWJXrjryVqQDKLE77Ywt+69q17oFxSgrChtFlhJmJlmc8NP96Mue4pbInFUvdCLhPHG+AD5QjTRJ7HTTp4RUcrxLDNiV2SnKDKNBfWwJZ8A2/L286TQ0tllkZcRIQoyQ/2nMPxKXH/LAFisMyzM4p9wEqVVTWrmD9Dpk6VStlqI65x2NUrKZjtDDzF/1gEGgkLe3Cesf0whiBHjSyOoibuTxbl0Gm6jvt1ciZ0haOmlOI7iugyl8K6F+fbDxBORRcSjL1AkqbMS2qSqIN1NzHCU/ChI94GA/o6MtMyLGIhnw87eoFtOY9cLen73Toxa9u4dPLPp/OOvQ9/vJne8NMUc4VFYbwkpoJDRzV+l0dzJ30LTsLKgaU9YQDxtFsmT2hDKQ1sm10pVchSx+tSzr3H+ODGEPjQfF2UkzXRmlNPJoxJ3eUbsFWfFM0Vqz94AgcQeDZOm2lrLzsQf5YN3y6BSH31qyvZCjgbkEiWTzOuneeEYdyhbJb/Jh+8/YoHG6yAOHIXs6F5muKEd4jajo5Va2m2QRq7OxqVNc0CUBHQC8sZj0ZArpSE8UL1sMyw4awYryw+SiRqm5DH8YvrULJ/1IARekO5pfsUc3vLpOyhjCt3kJOr/SL+UT1cuiuN2ztqbk5lmid36CvmxRZGD5XkeYH5ySuC2Hd5FAaZslo1grPoZy+2FUnZBx2IDDlr1vgob5CyX5Ipm07Ruz/x8emmSCgkJSyHl86jlgGnxZ0syLWUxKZSP2vXVHGAl1mwpWHMvJ2xmmgXJHOBodeuIvSYmJkcg7QJvqaOKCLKKLMgwnjDIKlcOsmb43pzJdIUXWJJM/D0zU4fE5umzAH2TYNw+iTBy+snC2Ik/ScqwSuXcCdKHrVSkD5vJ8ofNVCYQm156OwGdyq9UFAd7uCerE0Uq01SVLnIyypPvQm3iMB0tKo5gygannf56UQ3rumlzisIi0KoxH+z8AoajpdC0B67khieONSQbNoV5zUtszvGnRbb5SbnAO35gC+56/DFIYr87/v3x39Hf/7VoT6BAF4zKFFBQNusppQGRwdDY3VXB2AMkNmtaRFfnPWSG5FxkgVzzYrndHbCcAFhOlZdfRsexl5l7WccLneGAjDtSC8xtrolDEhfwrGE0THojbt3XyZZbcGcb9gdk9L++7rw79GGRduLA34XqOz6y+rASM95g0Bsxmw85t9GFjco8zgu1XJo3RwnQHZfR2IRM14Dg0GDQYdqBtejSXfRzMBFIXnlrH0QSlF/5L3ez5/uD5vz5SThPOqCJknX3fBbn1pTSdXpPTs3HvG9Pov0iL48ZBqndZih+L3UfZY4H6+REykdU24W9VtyO9Vr30SZO2nbSW2k8RIhfnrv0z+9yWiHUD7+bVtFt5daKsLYJ/CnxZtwUyLMs8ahtLWwwwtkLFxy1SoL6SD6LDH+8ODyYHQgnPDzr38xR5N6a5EbfxT78SmqKvrOWHa2tGwKkRHI64JNtagTmbtp3trL7OuyCUun2Q2gl+YMpTxcHowZ8ZK+0C88ESr5QChFa8O/IJJo9SCtvjlcJ+Fr7lonJHNZM48+ketnX8qwxZiBaR0phCYQ6e3ap1g6oFs0V9eXp74E/ISw/rVWovviek6Wnc0PgxQ5OwddxVAOGkoHEGKqrEHbwwOD5bIs4ODKU3SwAgz9lZUaszKhG+Axt35ZPfztHLNrCAbtiXRgKncLisGY5oIaay+0GqX2je5nXxQTueMRYqKFj+Oiy5lr1I9dyOmqJckJWkgxsbpRFj1nmLcvcnwVfxQuovatLtDRiZVtk9V5I5RIr5yETvbYqIyWYj0PKkaNCUM5D9b0eBUQ5D7VC/FDEjnMCX7wmtZ55nWtu5k4mx/oHaLxzPNRc9IxXplgs8DxolFYNvukBCMA9FP+gwWG6H8VBSp12nZUO4pAThdgXbNfrZNXImcy1TTsvZZ33ej7uUpGiQVPWQPtgXQS9VOUqaBJage1j2lble977L8ssXb7brUrYgrf86XjKG3xOp3WXn9xVvnyofJf4ByRPazs2yzwSRqGPIzXvu7NO42WkY/kNVzYjvMEcrhZbtGCZaLKAXpMHp7InD63OGtvg6ZfITE5aTSUTFFnQx7/A2/6LggE7nD3CvKNLSEhYKJ7D+aOXD8/BG66oOlyA3/q0HJ6HV2LVlw9fOTJkn5XiqEK3M5pNd32ylW6rqyAfWrWcL7X8cLhbRbLGyTxEebWaxzMphUknzKFj4Njonh/LkhXBJ/PJDMvyFk4SXKOQHDGnHRPWM9UhyI8N3s463q7QUZLFjAzCZMBuhZrun4hvgsm/UCPvhMAXW8zHMiJLn2pRWWtwFE78TV5BeVUZa+7Si1GY4V0g46zqs8GLWcV6vY+tpYprm2qrJS76rFhRDWcT6BkGkk5L3aUZach1s7V0yvExqlQGe3RJqDrVTU58KzL2BOjalNx9iZCntbR9qi3ZZAomCqI/sOnriAsbFYuvyI+9qOP1MPeDjFCpCQmsORmZcqkWuG0ruNGE4BAxsHOzLLfwtt2pN7te7d7Y3orwXlOTja3NO8ViVRLE7Od2q7oPiPw3OJbecP7CmT/vLtSrtc1rbVfWylMxNpTpqFj1BjReEtWl1mzXV2jGc+MWJ26WTsQMd7pMr5bGtqdorDoNbK6x7oHIB3vDmcnGWa/uSNTdVupuL1WuUJZaFpr/C+zDWQQGv0Yi2cN8qxRKObHXSGxx7e0dPDql4EOnEdNNhKieW+I/ZTwcxnroVw6pSFmIN84hNfXadLWQBa1unSCuW44in+6lSdFzy5VIs0+ZRI4a2VpNucItKcJr5/U0Ai2abE3FmhV8sNftbvI4YkWWTfnIg43VYoRrZulmq8qCS8Ca4g9Y0XPz9LP+hddK1iY+Ia9RydGctIHJ2cM866MpwescR4oaXbAhmnZkUqZmZAM0MTtzwHmZUTkjwxqRfMxBG9OFE8tywP+OSkhzzlZt2DhAlkQS82XEaC3GByYuX8auMp6l7WyzFyP+wmgino74m6WnkvhmNC+GoJJiLze1EjzC2SRJBk4a3VJ2xBDWcuqYlhx7GIdjTw/QykJaGLGVykhkFSypMgN5V67S1tqiW3cxfAG2bWhMRuNaZsWUS62z7neUf40q7SReJ+r3G6buimu+IrC91mfsmJadmXPYfGpIr1jQfArXPHppbXDDS1I/RhJga1K87suQYazOkozoquowkSEVveuzC/wlnbJeyaZ7J128DpaOch2b9BY2y06g3P5hsOtE1Qf0sXdEQyR75iSg9AlqDKM4de4GySajYtgnmM/5hXl9P/H8FgkrxQZyTUl2sal+aOrwikkvKBtEXpOVA12Fs8yLlLUO1Ji3l2u6wpZYtRIKfMSYLhDywtgaxXrFAWu719qcuqMbtxp0648+4Qa91dBcRBX0kCH/Et/r+V2n0/OSxLnUDdIoRoiA+fjnJR0HBEKhxYssW/woc+4AmQ2Ui2KFgritL0YHzp2E7sqVlLyMnhZB5/pgLboXOne6BxOUHdUvuzMB3J0J4KYTwE0ngEspH+tMcOyHlDVEkWsGcCzATs9WtynWjZbNttvZomKqOH1xyd2NmX9URHa+ef+3DiVY+ACdsMf3RRLo8QNmgM0Z0H4UdFOME7Qwn2O8fuAHe/sI/ZXX8lGGgjDoD/ubwV+LTNH4s3nuVWDhXpmdLWaKjlOW65QuEePItXewuXAbbHZiPx+qAMtejDDZHWVf4bWVNy60jP5AW0DkTUFRMRTAerjlJe/seLH5juubUSgEKvzZbGz6exE6RQMxeO3N3GC2osFGlKQZJP2rt4P+kzEcOKm3I1x8lbeHzlpEubLxDxsAQGxnc73w2mye2YLqyO0SPYHfGVDigRvH/5ZdHsxrbETVPT8y1SxccrXV7+z7GCmlCCFntsvXx0lweWl2d4EPAljP4jfWS+Mn0YFWccJ7/tveCHh/CvhAk4TzTk/zeTmYvrp8MRjki8M0JQ+Tv6dYHU/4gFgs5W9+9neABM2k7beWL1wbhs0m/GX70V0bMkd1siY3Z+ZarVZ7tj174hY/rtkiNTg3UYN/UK6ifkAXKKoGifcGtPHNnUJzH1c3xwc3SWsfq3Hg8cr+I2j0Q+Vu7fi+tV12UYJaZsOcNzaMvFvUG/bDzYEXNtm7t/Ad9QeNM4KkNRFEAYo8FMQ+4ocFowrLGU14M0A5YsOL94JwGUtepX7uNc+32uTSkiQBID4yNsuYhu+5SLLz/PgTJQGbDL+i3C9u5MmLYU5lP2Emzk2x4M/YoaMitnXqr/GmaPJlwyR/MBwwdQC2vd4F6lWeOLzZi+6ptAF1uuwXp/a57wbifDGCofUV+jw3D2ccVlyjcJj8RFOfkaAjr9AWi8ZbE0s4B6xvbglkx0zzCuezz3ItUhIWGVLgE7re9HR8n+ywJfM78IKY/NMwXFCbnVswta2J+8BAUXMYqadGi9RWm+IUFVs0LqTsRiWlh9MiO470T4aFZDuK7V5+lc1ZIPWOeHptggXbjWKm/lieXQpeX1giFQd0yOXkgWWKyxRN8mUTGaWtEQgUV/24A2xPe/58fl7ukEEF+M7mzPnZ2Tb+B0Qe2WrDa30NqQfKbJKS2Nvxe4e4n5Yb//7bG23MxPW00V4ZphF2ZhkX54idXEUA0BfDGVOjnW1LO/O2dkbtc4V2GPI50e5u4rObTsqGoBAqIugBi8jC8q0+o6wJ4w/gNHgEJT61IuoldAa8QsBlHkIYMI87mb0ZsTfFLZMfBesoOyXpq35g8M8L5lF6B8vqWSYSgGNaNBjbjUbbPIiVXrAHVQ4a2D0Ja1QGa7sC1qhRPVTvgJ2ShmHCp3nTGnsjWH1LlRGdlfo22DlYJmyfnwVUp//RNtgZGV+n5tKpqfRkyHz8ayC9nx8/xDUo7JpzRmzeOWAH1wTAtw1bxQIct8q5iUdB6fgYJhVGsWBsKMVRLNQahQBuGoUFOI7CshV2OsulTDLe1nXgAMSZe2xD5ote4pNifyv2wgR989gBKPf1TmGn74zyb9JCmdRGDUTf+8sVDPC0vWeH6YvqfmGFdjqAGOeN2xU+GXf4Th+W21Klb9jhpEyh/TlH59nCbC1k+1eWXZsxtY+Pv7Qeaa8YMY9aBcx+xbyAfd/DlJHZKv6OxdYhCTnL7q0u3FWEuMHqNRUyjGm9Mzj/CNj7QTFbuA0D1gLUBe8MU5/AZycU9b/uKvLRwLoYJwN7CPvQMhVhdiSBkOjM8XmuPk1nkGewbJBBBpQBZBJhNdASmOFI6ehvJujobJsEW3NHVaC/ngjoXPXChHiAft+0JgMku8YvIZ6g5jpITb9vHkcniuJusqwzT0BNv2QnD6NJGEMBM0p9xkLSkbZQSa3Gw1bZRr+KTQQhhpdpVg+ddQiG/6qRVPDPC0UwRWnBj6qEPtIcJfUlPiYonEzCWwAp/UexN8C+YvyCZSLdBcGbelYi8qnKNU56RNQKuyoDRpKCdGIQtwzNSdIKM6FRT1Q+HAgd73Km4T2P/FPbYYQY4wf3fYe1iCE2fsmi3uGBjaQOGXGKaffV+D7l63uy6BBLjglFH1Jq0WdMbfEllX8ognV8AmP83CFCmRX7FE5NdivgiYKZPKaeLhOLlv+WP3L1t9somOiFXjGHoDRVheOK2Uxq6m6GvTToBaGYTkywcSXsjfjjZgfDVl704mQ5++n+0I/ToIOhcS56nXdgS0TxMotzQb8THipDzL8WffBTljPu+JHrsFxzAm1yKRHz6RBpOp+Ys73qiV1x0uHse+wWVEh8ZlzhK6N0jMVkbJjL65qsvB0jMVVl+5Z9UnU56n4uLAbfmJom7dWCUK8AzXEM7EseH7QySuUcimnFULNtMxJHKbv5gOH1YqAAzF58JUSLx2ovwixeTeU3hUZZifcSxy/Ld+K7WN4H/EuQki07yqOL1kwODo3zUNYLO36PkHTJ+QGSodaScslABb4DHKqr9863DI3ZvYT5m4fp5JZu5iVRMgAWmvma/+4Q6G+36qJ2jdjO6OQje8GaXzL67oibdXbfHIHI3AxHwPK5rmyOAEi33xyGHXn3xSvNhMgcJ3INsirNljGRix5oqliZgt2iofrNOPDDbm/UxOwQNa6WFzhee5frxdFm87bsCCsAg8vYXsO6dP1O0Pd6lNrO75qDP6yxMu5WPGIZRu6yZCKXSb3MFXRwqntpubOC8IjHllotR2W+ocPkhbwRhFyocPmh2eYfvAP5gVlM2xKSIdB6fnV+/xtHkT0ofjTTbJH8waJUsZmjkMLAnLqNpaoEUy8CKfgqyhrmAGf66mdlOsN42T9YYvd9MWgHrAGcArLAmWV+bwfKFb+aPXeHhgDKho4XFMfCamjpdKH8YNmkfz7MHUJo4WUGhOX5+dm2ooRenm8LDfTyQtt0TM3NtnLH1GAKJfP5WZRKp65pmuNB3qNFnVgueXDxSVzdoEuSdGz9wANE8WNnHzFQKE5o3OyBSfpUwXSg88k892rbbCLLWcgQztGSA0weHEPvnF3el25mO0tVnSdW/EQDIP+K5XPnZsu7vXDSbuuOKqhUEXSyH4CoIh+8g+xBuigqCVM0OIeccC0jDE7dlhEEUcBlRlQ5rb3a86D/gNLrYSf2MUHd8qx7fsO0gkdL0g3q6KX/AOuqJaBGQgEA")))

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
                "migration": "v3.1-v3.7 -> v3.8",
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

