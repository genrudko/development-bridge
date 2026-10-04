from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.113"
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
                ("EnergoLogic.VisioEditorAddinV314", "{6989E63C-E667-4B14-B85B-210710468940}"),
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

            build_dir = workspace / "energologic_visio_editor_addin_v315"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV315.dll"
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

            clsid = "{E82068B0-D05D-4646-82B0-0CA923733CAF}"
            progid = "EnergoLogic.VisioEditorAddinV315"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV315, Version=0.3.15.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.14 -> v3.15",
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
            progid = "EnergoLogic.VisioEditorAddinV315"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV315")
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
                "progid": "EnergoLogic.VisioEditorAddinV315",
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
            progid = "EnergoLogic.VisioEditorAddinV315"
            clsid = "{E82068B0-D05D-4646-82B0-0CA923733CAF}"
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

