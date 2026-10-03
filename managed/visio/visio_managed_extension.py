from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.96"
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
            build_dir = workspace / "energologic_visio_editor_addin_v30"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV30.dll"
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

            clsid = "{B66D6B8F-7388-4DFB-AD57-64E4D02856AE}"
            progid = "EnergoLogic.VisioEditorAddinV30"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV30, Version=0.3.0.0, Culture=neutral, PublicKeyToken=null"
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
            progid = "EnergoLogic.VisioEditorAddinV30"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV30")
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
                "progid": "EnergoLogic.VisioEditorAddinV30",
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
            progid = "EnergoLogic.VisioEditorAddinV30"
            clsid = "{B66D6B8F-7388-4DFB-AD57-64E4D02856AE}"
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

