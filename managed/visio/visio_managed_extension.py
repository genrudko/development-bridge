from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.112"
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
                ("EnergoLogic.VisioEditorAddinV313", "{1A6AF8E1-2576-4EF3-96EC-676904B6DA57}"),
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

            build_dir = workspace / "energologic_visio_editor_addin_v314"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV314.dll"
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

            clsid = "{6989E63C-E667-4B14-B85B-210710468940}"
            progid = "EnergoLogic.VisioEditorAddinV314"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV314, Version=0.3.14.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.13 -> v3.14",
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
            progid = "EnergoLogic.VisioEditorAddinV314"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV314")
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
                "progid": "EnergoLogic.VisioEditorAddinV314",
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
            progid = "EnergoLogic.VisioEditorAddinV314"
            clsid = "{6989E63C-E667-4B14-B85B-210710468940}"
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

