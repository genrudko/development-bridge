from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.106"
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

            build_dir = workspace / "energologic_visio_editor_addin_v39"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV39.dll"
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

            clsid = "{B42A3C6E-8C1F-44AB-A486-93C6AB3D8F39}"
            progid = "EnergoLogic.VisioEditorAddinV39"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV39, Version=0.3.9.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.8 -> v3.9",
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
            progid = "EnergoLogic.VisioEditorAddinV39"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV39")
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
                "progid": "EnergoLogic.VisioEditorAddinV39",
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
            progid = "EnergoLogic.VisioEditorAddinV39"
            clsid = "{B42A3C6E-8C1F-44AB-A486-93C6AB3D8F39}"
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

