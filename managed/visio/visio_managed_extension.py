from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.91"
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
            build_dir = workspace / "energologic_visio_editor_addin_v25"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV25.dll"
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

            clsid = "{1A2F95D4-3B13-499E-B87C-503D2B32F3E6}"
            progid = "EnergoLogic.VisioEditorAddinV25"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV25, Version=0.2.5.0, Culture=neutral, PublicKeyToken=null"
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
            progid = "EnergoLogic.VisioEditorAddinV25"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV25")
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
                "progid": "EnergoLogic.VisioEditorAddinV25",
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
            progid = "EnergoLogic.VisioEditorAddinV25"
            clsid = "{1A2F95D4-3B13-499E-B87C-503D2B32F3E6}"
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

