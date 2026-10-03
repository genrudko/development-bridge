from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.110"
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

            build_dir = workspace / "energologic_visio_editor_addin_v312"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV312.dll"
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

            clsid = "{2F8B22F0-0A1B-4E30-B850-09B1F7197D3D}"
            progid = "EnergoLogic.VisioEditorAddinV312"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV312, Version=0.3.12.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.11 -> v3.12",
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
            progid = "EnergoLogic.VisioEditorAddinV312"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV312")
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
                "progid": "EnergoLogic.VisioEditorAddinV312",
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
            progid = "EnergoLogic.VisioEditorAddinV312"
            clsid = "{2F8B22F0-0A1B-4E30-B850-09B1F7197D3D}"
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

