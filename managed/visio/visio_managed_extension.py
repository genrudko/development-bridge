from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.79"
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
            build_dir = workspace / "energologic_visio_editor_addin"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddin.dll"
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
            helper_path.write_bytes(gzip.decompress(base64.b64decode("H4sIAAAAAAAC/6VW3YrbRhS+11MMupKpVtgthWJwCKTeEkiXkGy7FLMMY+nIO6k0I2ZGuzalsE0hN+lV6VWeohQCuejPK9ivkCfpmRn9WGunaVpd2NKZOed85/vO/ORKloTSvDa1AkoJLyupDGFCSMMMl0IHQWNLzaYCPfxKbrgYmJ9pKdp3venMhpcQ5DZXxcxVwZdtosf4GQRBBjm5UdwAVaDrwkR22tSNxuiyKSTLpiTjqVloo2Iil88gNZcjcnKPnEkB04DgY50SH8bA2kQWTJLVZaWjJkZMQGhbKdMp57NTVmgYWWMqMy5Ws7A2+cln4aiBVDIuIpcEy/Q5PD5qU5GZAxhhnQlTq+vF5HK0N+cIXvT4zs2wT6gNUwaycErOVQ1xP4CkZvKG5rIWdtSh3Bte1sZI8c7htODpt3BsBJSSCu1h6I3fu98B73vlxU0dviarYKILgCqaJGMkyBnVZtqFrzWoTz7GEvvWyIoi8eZu1rKkDiDOG6/H49NPuxHDTQFoDucC1Eo+kiuekre3v5Dtm+0fux92z3e3ux+3v29f49fz3UvyNddchn1gz4oV3gbZvtr+uf1r+2Z3i/+/bX9Fl5/I2xc/h0Hn4ZrOU+3a5epGYJOh0k5x1K2vzT4FiJUTHWdEvqrkCzAXLsI5BnjkJly4OKPRwHdZ5z0xqQKGjNeCY9cBxbEcVFSydTSJ2ywfkcmdEMcy+lyxDe88I3y546YAV7awM5JrVtTQl18pmfagLh6enX519uD8m8fzqMVJl1IWcQebXkue0erA0Cf0bOopKbg2C+TJdvziss953yYdCACiLqn3a4qhRcUUK0dD9nlOLJqW+Ifas2CbYFlAwznuW9mBpCMym/nmGkbcA5ywqgKRRVbZI+o1HNpVGtxp92SO+D0UHe3VEpNxHwOx43basTOMzbgG8qQWdoHN7QKNBgsAMm6kanxdGL/u++h+lS6Gu4Yl3uHtZklp10WDYXEyuXxXAEuA87cuvbTv3SXurMQP74L0ihfZ+5rgqLp7a/9Q4wbO/9T4gQXXCm2ZifdAH1O7ZeGD1P68rnBzxN2BPOGrqzbIP8o+OA0OZG8CtBQdF74J0Qnvv/+L9A1hT5HoL0FrtoKLyEeLu50fyRrw1aJoz61BDbBOoTJk7v7wOkKYtrbpgbc/26wvbtwRTvEJci5YUeydUv/utGu6YYz3AJSTUsFKezvCVgsptbcCSsPmPuAUfbrRBsr5mpvI3xlGwd+iIgk8WgkAAA==")))

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

