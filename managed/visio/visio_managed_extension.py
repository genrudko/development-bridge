from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.52"
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
    def install_energologic_qol_vba_host(
        page: str = "",
        doc_name: str = "",
    ) -> str:
        """Install the fixed EnergoLogic QoL VBA host into a macro-enabled workspace copy.

        This tool never accepts arbitrary VBA source and never modifies VTD stencil projects.
        It is intentionally limited to *.vsdm documents inside the approved workspace.
        """
        try:
            page_obj = visio._resolve_page(doc_name, parse_page(page))
            document = page_obj.Document
            app = page_obj.Application
            full_name = Path(str(document.FullName)).resolve()
            try:
                full_name.relative_to(workspace)
            except ValueError as exc:
                raise ValueError("QoL VBA host can only be installed in the approved workspace") from exc
            if full_name.suffix.lower() != ".vsdm":
                raise ValueError("QoL VBA host requires a macro-enabled .vsdm document copy")
            if not bool(app.VBAEnabled):
                raise RuntimeError("Visio VBA is not enabled")
            if not bool(document.MacrosEnabled):
                raise RuntimeError("Macros are not enabled for the target document")

            try:
                project = document.VBProject
            except Exception:
                project = app.VBE.ActiveVBProject
            if project is None:
                raise RuntimeError("Could not resolve the target Visio VBA project")

            module_name = "EnergoLogicQolHost"
            components = project.VBComponents
            existing = None
            for index in range(1, int(components.Count) + 1):
                candidate = components.Item(index)
                if str(candidate.Name).casefold() == module_name.casefold():
                    existing = candidate
                    break
            if existing is not None:
                components.Remove(existing)

            component = components.Add(1)  # vbext_ct_StdModule
            component.Name = module_name
            vba_source = """Option Explicit

Public Const ENERGOLOGIC_QOL_HOST_VERSION As String = "0.1-probe"

Public Sub UndoProbeDuplicate40()
    Dim app As Visio.Application
    Dim scopeId As Long
    Dim sel As Visio.Selection
    Dim dup As Visio.Selection
    Dim sourceCount As Long

    Set app = Application
    Set sel = app.ActiveWindow.Selection
    sourceCount = sel.Count
    If sourceCount < 1 Then
        Err.Raise vbObjectError + 701, "EnergoLogicQolHost", "No shapes selected"
    End If

    scopeId = app.BeginUndoScope("EnergoLogic: Undo Probe Duplicate")
    On Error GoTo Failed

    sel.Duplicate
    Set dup = app.ActiveWindow.Selection
    If dup.Count <> sourceCount Then
        Err.Raise vbObjectError + 702, "EnergoLogicQolHost", "Duplicate selection count mismatch"
    End If
    dup.Move 40#, 0#, "mm"

    app.EndUndoScope scopeId, True
    Exit Sub

Failed:
    On Error Resume Next
    app.EndUndoScope scopeId, False
    On Error GoTo 0
    Err.Raise vbObjectError + 703, "EnergoLogicQolHost", "Undo probe failed"
End Sub

Public Sub UndoProbeDuplicate40FromShape(ByVal triggerShape As Visio.Shape)
    Dim pg As Visio.Page
    Dim win As Visio.Window
    Dim sel As Visio.Selection
    Dim dup As Visio.Selection
    Dim ids As Variant
    Dim item As Variant
    Dim sourceCount As Long

    Set pg = triggerShape.ContainingPage
    Set win = Application.ActiveWindow
    win.DeselectAll
    ids = Array(66, 69, 71, 73, 113, 117, 119, 247)
    For Each item In ids
        win.Select pg.Shapes.ItemFromID(CLng(item)), 2
    Next item

    Set sel = win.Selection
    sourceCount = sel.Count
    Application.DoCmd 1024
    Set dup = win.Selection
    If dup.Count <> sourceCount Then
        Err.Raise vbObjectError + 704, "EnergoLogicQolHost", "Duplicate selection count mismatch"
    End If
    dup.Move 40#, 0#, "mm"
End Sub

Private Function EnergoLogicSelectionIds(ByVal sel As Visio.Selection) As String
    Dim i As Long
    Dim result As String
    For i = 1 To sel.Count
        If Len(result) > 0 Then result = result & ","
        result = result & CStr(sel.Item(i).ID)
    Next i
    EnergoLogicSelectionIds = result
End Function

Public Sub CustomUndoProbeDuplicate40()
    Dim win As Visio.Window
    Dim sel As Visio.Selection
    Dim dup As Visio.Selection
    Dim sourceIds As String
    Dim newIds As String
    Dim unit As EnergoLogicUndoUnit
    Dim sourceCount As Long

    Set win = Application.ActiveWindow
    Set sel = win.Selection
    sourceCount = sel.Count
    If sourceCount < 1 Then
        Err.Raise vbObjectError + 705, "EnergoLogicQolHost", "No shapes selected"
    End If
    sourceIds = EnergoLogicSelectionIds(sel)

    Application.DoCmd 1024
    Set dup = win.Selection
    If dup.Count <> sourceCount Then
        Err.Raise vbObjectError + 706, "EnergoLogicQolHost", "Duplicate selection count mismatch"
    End If
    dup.Move 40#, 0#, "mm"
    newIds = EnergoLogicSelectionIds(dup)

    Set unit = New EnergoLogicUndoUnit
    unit.Initialize win.Page, sourceIds, newIds, 40#, 0#
    Application.AddUndoUnit unit
End Sub


"""
            component.CodeModule.AddFromString(vba_source)

            undo_class_name = "EnergoLogicUndoUnit"
            existing_undo = None
            for index in range(1, int(components.Count) + 1):
                candidate = components.Item(index)
                if str(candidate.Name).casefold() == undo_class_name.casefold():
                    existing_undo = candidate
                    break
            if existing_undo is not None:
                components.Remove(existing_undo)

            undo_component = components.Add(2)  # vbext_ct_ClassModule
            undo_component.Name = undo_class_name
            undo_source = """Option Explicit
Implements Visio.IVBUndoUnit

Private mPage As Visio.Page
Private mSourceIds As String
Private mNewIds As String
Private mDxMm As Double
Private mDyMm As Double
Private mUndone As Boolean

Public Sub Initialize(ByVal targetPage As Visio.Page, ByVal sourceIds As String, ByVal newIds As String, ByVal dxMm As Double, ByVal dyMm As Double)
    Set mPage = targetPage
    mSourceIds = sourceIds
    mNewIds = newIds
    mDxMm = dxMm
    mDyMm = dyMm
    mUndone = False
End Sub

Private Function SelectionIds(ByVal sel As Visio.Selection) As String
    Dim i As Long
    Dim result As String
    For i = 1 To sel.Count
        If Len(result) > 0 Then result = result & ","
        result = result & CStr(sel.Item(i).ID)
    Next i
    SelectionIds = result
End Function

Private Sub DeleteCurrentDuplicate()
    Dim raw As Variant
    Dim item As Variant
    raw = Split(mNewIds, ",")
    For Each item In raw
        If Len(CStr(item)) > 0 Then
            mPage.Shapes.ItemFromID(CLng(item)).Delete
        End If
    Next item
End Sub

Private Sub RecreateDuplicate()
    Dim win As Visio.Window
    Dim dup As Visio.Selection
    Dim raw As Variant
    Dim item As Variant

    Set win = Application.ActiveWindow
    Set win.Page = mPage
    win.DeselectAll
    raw = Split(mSourceIds, ",")
    For Each item In raw
        If Len(CStr(item)) > 0 Then
            win.Select mPage.Shapes.ItemFromID(CLng(item)), 2
        End If
    Next item
    Application.DoCmd 1024
    Set dup = win.Selection
    dup.Move mDxMm, mDyMm, "mm"
    mNewIds = SelectionIds(dup)
End Sub

Private Property Get IVBUndoUnit_Description() As String
    IVBUndoUnit_Description = "EnergoLogic: Duplicate Cell"
End Property

Private Sub IVBUndoUnit_Do(ByVal pMgr As Visio.IVBUndoManager)
    If mUndone Then
        RecreateDuplicate
    Else
        DeleteCurrentDuplicate
    End If
    mUndone = Not mUndone
    If Not (pMgr Is Nothing) Then
        pMgr.Add Me
    End If
End Sub

Private Sub IVBUndoUnit_OnNextAdd()
End Sub

Private Property Get IVBUndoUnit_UnitSize() As Long
    IVBUndoUnit_UnitSize = 1024
End Property

Private Property Get IVBUndoUnit_UnitTypeCLSID() As String
    IVBUndoUnit_UnitTypeCLSID = vbNullString
End Property

Private Property Get IVBUndoUnit_UnitTypeLong() As Long
    IVBUndoUnit_UnitTypeLong = 46001
End Property
"""
            undo_component.CodeModule.AddFromString(undo_source)

            return ok({
                "document": str(document.Name),
                "project_name": str(project.Name),
                "module_name": module_name,
                "undo_class_name": undo_class_name,
                "host_version": "0.2-custom-undo-probe",
                "persisted": False,
                "note": "Use SaveAs after qualification to persist this in-memory VBA project change.",
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def run_energologic_qol_undo_probe(
        shape_ids_json: str,
        page: str = "",
        doc_name: str = "",
    ) -> str:
        """Run only the fixed in-Visio UndoProbeDuplicate40 macro on explicit shapes."""
        try:
            import json
            raw_ids = json.loads(shape_ids_json)
            if not isinstance(raw_ids, list) or not raw_ids or len(raw_ids) > 100:
                raise ValueError("shape_ids_json must be a JSON array with 1..100 items")
            shape_ids = [int(value) for value in raw_ids]
            if len(set(shape_ids)) != len(shape_ids) or any(value <= 0 for value in shape_ids):
                raise ValueError("shape IDs must be unique positive integers")

            page_obj = visio._resolve_page(doc_name, parse_page(page))
            document = page_obj.Document
            app = page_obj.Application
            if Path(str(document.FullName)).suffix.lower() != ".vsdm":
                raise ValueError("QoL VBA host can only run in a .vsdm document")
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

            before_count = int(page_obj.Shapes.Count)
            document.ExecuteLine("EnergoLogicQolHost.UndoProbeDuplicate40")
            after_count = int(page_obj.Shapes.Count)
            if after_count != before_count + len(shape_ids):
                raise RuntimeError(
                    f"VBA probe expected {before_count + len(shape_ids)} shapes, got {after_count}"
                )
            new_ids = [
                int(window.Selection.Item(index).ID)
                for index in range(1, int(window.Selection.Count) + 1)
            ]
            return ok({
                "document": str(document.Name),
                "page": str(page_obj.Name),
                "source_shape_ids": shape_ids,
                "new_shape_ids": new_ids,
                "shape_count_before": before_count,
                "shape_count_after": after_count,
                "macro": "EnergoLogicQolHost.UndoProbeDuplicate40",
                "executed_inside_visio": True,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def run_energologic_qol_custom_undo_probe(
        shape_ids_json: str,
        page: str = "",
        doc_name: str = "",
    ) -> str:
        """Run the fixed Duplicate + IVBUndoUnit probe on an explicit selection."""
        try:
            import json
            raw_ids = json.loads(shape_ids_json)
            if not isinstance(raw_ids, list) or not raw_ids or len(raw_ids) > 100:
                raise ValueError("shape_ids_json must be a JSON array with 1..100 items")
            shape_ids = [int(value) for value in raw_ids]
            if len(set(shape_ids)) != len(shape_ids) or any(value <= 0 for value in shape_ids):
                raise ValueError("shape IDs must be unique positive integers")

            page_obj = visio._resolve_page(doc_name, parse_page(page))
            document = page_obj.Document
            app = page_obj.Application
            if Path(str(document.FullName)).suffix.lower() != ".vsdm":
                raise ValueError("custom Undo probe requires a .vsdm document")
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

            before_count = int(page_obj.Shapes.Count)
            document.ExecuteLine("EnergoLogicQolHost.CustomUndoProbeDuplicate40")
            after_count = int(page_obj.Shapes.Count)
            if after_count != before_count + len(shape_ids):
                raise RuntimeError(
                    f"Custom Undo probe expected {before_count + len(shape_ids)} shapes, got {after_count}"
                )
            new_ids = [
                int(window.Selection.Item(index).ID)
                for index in range(1, int(window.Selection.Count) + 1)
            ]
            return ok({
                "document": str(document.Name),
                "page": str(page_obj.Name),
                "source_shape_ids": shape_ids,
                "new_shape_ids": new_ids,
                "shape_count_before": before_count,
                "shape_count_after": after_count,
                "macro": "EnergoLogicQolHost.CustomUndoProbeDuplicate40",
                "undo_unit": "EnergoLogicUndoUnit",
                "undo_description": "EnergoLogic: Duplicate Cell",
                "custom_undo_added": True,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def install_energologic_qol_action_probe(
        page: str = "",
        doc_name: str = "",
    ) -> str:
        """Create one bounded ShapeSheet Action trigger for the fixed VBA Undo probe."""
        try:
            page_obj = visio._resolve_page(doc_name, parse_page(page))
            document = page_obj.Document
            if Path(str(document.FullName)).suffix.lower() != ".vsdm":
                raise ValueError("QoL action probe requires a .vsdm document")

            # One small temporary trigger, isolated from the electrical drawing.
            trigger = page_obj.DrawRectangle(0.25, 0.25, 1.65, 0.65)
            trigger.Text = "EnergoLogic Undo Probe"
            section = 240  # visSectionAction
            if not bool(trigger.SectionExists(section, 0)):
                trigger.AddSection(section)
            trigger.AddNamedRow(section, "EnergoLogicUndoProbe", 0)
            trigger.CellsU("Actions.EnergoLogicUndoProbe.Menu").FormulaU = '"%&J EnergoLogic Undo Probe"'
            trigger.CellsU("Actions.EnergoLogicUndoProbe.Action").FormulaU = (
                'CALLTHIS("EnergoLogicQolHost.UndoProbeDuplicate40FromShape",)'
            )
            trigger.CellsU("Actions.EnergoLogicUndoProbe.BeginGroup").FormulaU = "TRUE"
            return ok({
                "document": str(document.Name),
                "page": str(page_obj.Name),
                "trigger_shape_id": int(trigger.ID),
                "menu": "J EnergoLogic Undo Probe (forced bottom)",
                "action_formula": str(
                    trigger.CellsU("Actions.EnergoLogicUndoProbe.Action").FormulaU
                ),
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def trigger_energologic_qol_action_probe(
        trigger_shape_id: int,
        page: str = "",
        doc_name: str = "",
    ) -> str:
        """Trigger only the fixed EnergoLogic ShapeSheet Action cell."""
        try:
            page_obj = visio._resolve_page(doc_name, parse_page(page))
            document = page_obj.Document
            if Path(str(document.FullName)).suffix.lower() != ".vsdm":
                raise ValueError("QoL action probe requires a .vsdm document")
            trigger = page_obj.Shapes.ItemFromID(int(trigger_shape_id))
            cell_name = "Actions.EnergoLogicUndoProbe.Action"
            if not bool(trigger.CellExistsU(cell_name, 0)):
                raise ValueError("trigger shape does not contain EnergoLogic probe action")
            action_cell = trigger.CellsU(cell_name)
            formula_before = str(action_cell.FormulaU)
            before_count = int(page_obj.Shapes.Count)
            action_cell.Trigger()
            after_count = int(page_obj.Shapes.Count)
            if after_count != before_count + 8:
                raise RuntimeError(
                    f"ShapeSheet Cell.Trigger probe expected {before_count + 8} shapes, "
                    f"got {after_count}; formula={formula_before!r}"
                )
            return ok({
                "document": str(document.Name),
                "page": str(page_obj.Name),
                "trigger_shape_id": int(trigger_shape_id),
                "shape_count_before": before_count,
                "shape_count_after": after_count,
                "action_cell": cell_name,
                "action_formula": formula_before,
                "launch_path": "ShapeSheet Cell.Trigger",
                "action_triggered": True,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def mouse_run_energologic_qol_action_probe(
        trigger_shape_id: int,
        page: str = "",
        doc_name: str = "",
    ) -> str:
        """Click the fixed EnergoLogic ShapeSheet Action from Visio's real shortcut menu."""
        try:
            import ctypes
            import time

            page_obj = visio._resolve_page(doc_name, parse_page(page))
            document = page_obj.Document
            app = page_obj.Application
            if Path(str(document.FullName)).suffix.lower() != ".vsdm":
                raise ValueError("QoL action probe requires a .vsdm document")
            trigger = page_obj.Shapes.ItemFromID(int(trigger_shape_id))
            if not bool(trigger.CellExistsU("Actions.EnergoLogicUndoProbe.Action", 0)):
                raise ValueError("trigger shape does not contain EnergoLogic probe action")

            try:
                app.ActiveWindow.Page = page_obj
            except Exception:
                page_obj.Activate()
            window = app.ActiveWindow
            window.DeselectAll()
            window.Select(trigger, 2)

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            hwnd = int(window.WindowHandle32)
            GA_ROOT = 2
            SW_RESTORE = 9
            VK_SHIFT = 0x10
            VK_F10 = 0x79
            KEYEVENTF_KEYUP = 0x0002
            MN_GETHMENU = 0x01E1
            MF_BYPOSITION = 0x00000400
            MOUSEEVENTF_LEFTDOWN = 0x0002
            MOUSEEVENTF_LEFTUP = 0x0004
            root_hwnd = int(user32.GetAncestor(hwnd, GA_ROOT)) or hwnd

            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long),
                ]

            def chord(modifier, vk):
                user32.keybd_event(modifier, 0, 0, 0)
                user32.keybd_event(vk, 0, 0, 0)
                user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
                user32.keybd_event(modifier, 0, KEYEVENTF_KEYUP, 0)

            foreground_hwnd = int(user32.GetForegroundWindow())
            current_thread = int(kernel32.GetCurrentThreadId())
            target_thread = int(user32.GetWindowThreadProcessId(root_hwnd, None))
            foreground_thread = (
                int(user32.GetWindowThreadProcessId(foreground_hwnd, None))
                if foreground_hwnd else 0
            )
            attached = []
            before_count = int(page_obj.Shapes.Count)
            target_text = "J EnergoLogic Undo Probe"
            menu_items = []
            clicked_rect = None
            try:
                for other_thread in (foreground_thread, target_thread):
                    if other_thread and other_thread != current_thread:
                        if bool(user32.AttachThreadInput(current_thread, other_thread, True)):
                            attached.append(other_thread)
                user32.ShowWindow(root_hwnd, SW_RESTORE)
                user32.BringWindowToTop(root_hwnd)
                user32.SetForegroundWindow(root_hwnd)
                user32.SetActiveWindow(root_hwnd)
                user32.SetFocus(hwnd)
                time.sleep(0.2)
                focused_child = int(user32.GetFocus())
                chord(VK_SHIFT, VK_F10)
                time.sleep(0.5)

                menu_hwnd = 0
                hmenu = 0
                root_pid = ctypes.c_ulong(0)
                user32.GetWindowThreadProcessId(root_hwnd, ctypes.byref(root_pid))
                target_pid = int(root_pid.value)
                EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

                for _ in range(30):
                    candidates = []

                    @EnumWindowsProc
                    def enum_popup(candidate_hwnd, lparam):
                        class_buf = ctypes.create_unicode_buffer(128)
                        user32.GetClassNameW(candidate_hwnd, class_buf, len(class_buf))
                        if class_buf.value != "#32768":
                            return True
                        pid = ctypes.c_ulong(0)
                        user32.GetWindowThreadProcessId(candidate_hwnd, ctypes.byref(pid))
                        if int(pid.value) != target_pid:
                            return True
                        if not bool(user32.IsWindowVisible(candidate_hwnd)):
                            return True
                        candidate_menu = int(user32.SendMessageW(candidate_hwnd, MN_GETHMENU, 0, 0))
                        if candidate_menu:
                            candidates.append((int(candidate_hwnd), candidate_menu))
                        return True

                    user32.EnumWindows(enum_popup, 0)
                    if candidates:
                        menu_hwnd, hmenu = candidates[-1]
                        break
                    time.sleep(0.05)
                if not menu_hwnd or not hmenu:
                    visible_windows = []

                    @EnumWindowsProc
                    def enum_diag(candidate_hwnd, lparam):
                        pid = ctypes.c_ulong(0)
                        user32.GetWindowThreadProcessId(candidate_hwnd, ctypes.byref(pid))
                        if int(pid.value) != target_pid or not bool(user32.IsWindowVisible(candidate_hwnd)):
                            return True
                        class_buf = ctypes.create_unicode_buffer(256)
                        user32.GetClassNameW(candidate_hwnd, class_buf, len(class_buf))
                        length = int(user32.GetWindowTextLengthW(candidate_hwnd))
                        text_buf = ctypes.create_unicode_buffer(max(1, length + 1))
                        user32.GetWindowTextW(candidate_hwnd, text_buf, len(text_buf))
                        visible_windows.append({
                            "hwnd": int(candidate_hwnd),
                            "class": class_buf.value,
                            "text": text_buf.value[:200],
                            "foreground": int(user32.GetForegroundWindow()) == int(candidate_hwnd),
                        })
                        return True

                    user32.EnumWindows(enum_diag, 0)
                    raise RuntimeError(
                        "Visio shortcut menu window (#32768 with HMENU) was not found; "
                        f"pid={target_pid}; drawing_hwnd={hwnd}; focused_child={focused_child}; "
                        f"visible_windows={visible_windows!r}"
                    )
                count = int(user32.GetMenuItemCount(hmenu))
                target_index = None
                for index in range(count):
                    buf = ctypes.create_unicode_buffer(512)
                    user32.GetMenuStringW(hmenu, index, buf, len(buf), MF_BYPOSITION)
                    label = buf.value.replace("&", "").strip()
                    menu_items.append(label)
                    if label == target_text:
                        target_index = index
                if target_index is None:
                    raise RuntimeError(
                        f"EnergoLogic action not found in Visio shortcut menu: {menu_items!r}"
                    )

                rect = RECT()
                if not bool(user32.GetMenuItemRect(root_hwnd, hmenu, target_index, ctypes.byref(rect))):
                    if not bool(user32.GetMenuItemRect(0, hmenu, target_index, ctypes.byref(rect))):
                        raise RuntimeError("GetMenuItemRect failed for EnergoLogic action")
                x = int((rect.left + rect.right) / 2)
                y = int((rect.top + rect.bottom) / 2)
                clicked_rect = [int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)]
                user32.SetCursorPos(x, y)
                time.sleep(0.1)
                user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

                expected_count = before_count + 8
                for _ in range(100):
                    time.sleep(0.1)
                    if int(page_obj.Shapes.Count) == expected_count:
                        break
            finally:
                for other_thread in reversed(attached):
                    try:
                        user32.AttachThreadInput(current_thread, other_thread, False)
                    except Exception:
                        pass

            after_count = int(page_obj.Shapes.Count)
            if after_count != before_count + 8:
                raise RuntimeError(
                    f"Mouse ShapeSheet Action probe expected {before_count + 8} shapes, "
                    f"got {after_count}; menu={menu_items!r}; rect={clicked_rect!r}"
                )
            return ok({
                "document": str(document.Name),
                "page": str(page_obj.Name),
                "trigger_shape_id": int(trigger_shape_id),
                "shape_count_before": before_count,
                "shape_count_after": after_count,
                "menu_item": target_text,
                "menu_item_rect": clicked_rect,
                "launch_path": "real Visio shortcut menu mouse click",
                "ui_action_launched": True,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def msaa_run_energologic_qol_action_probe(
        trigger_shape_id: int,
        page: str = "",
        doc_name: str = "",
    ) -> str:
        """Invoke the fixed EnergoLogic ShapeSheet action via Office MSAA accessibility."""
        try:
            import ctypes
            import time
            import uuid as _uuid
            import pythoncom
            import win32com.client

            page_obj = visio._resolve_page(doc_name, parse_page(page))
            document = page_obj.Document
            app = page_obj.Application
            if Path(str(document.FullName)).suffix.lower() != ".vsdm":
                raise ValueError("QoL action probe requires a .vsdm document")
            trigger = page_obj.Shapes.ItemFromID(int(trigger_shape_id))
            if not bool(trigger.CellExistsU("Actions.EnergoLogicUndoProbe.Action", 0)):
                raise ValueError("trigger shape does not contain EnergoLogic probe action")

            try:
                app.ActiveWindow.Page = page_obj
            except Exception:
                page_obj.Activate()
            window = app.ActiveWindow
            window.DeselectAll()
            window.Select(trigger, 2)

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            oleacc = ctypes.oledll.oleacc
            hwnd = int(window.WindowHandle32)
            GA_ROOT = 2
            SW_RESTORE = 9
            VK_SHIFT = 0x10
            VK_F10 = 0x79
            VK_ESCAPE = 0x1B
            KEYEVENTF_KEYUP = 0x0002
            root_hwnd = int(user32.GetAncestor(hwnd, GA_ROOT)) or hwnd

            def chord(modifier, vk):
                user32.keybd_event(modifier, 0, 0, 0)
                user32.keybd_event(vk, 0, 0, 0)
                user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
                user32.keybd_event(modifier, 0, KEYEVENTF_KEYUP, 0)

            def press(vk):
                user32.keybd_event(vk, 0, 0, 0)
                user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)

            class GUID(ctypes.Structure):
                _fields_ = [
                    ("Data1", ctypes.c_ulong),
                    ("Data2", ctypes.c_ushort),
                    ("Data3", ctypes.c_ushort),
                    ("Data4", ctypes.c_ubyte * 8),
                ]

            def guid(value):
                raw = _uuid.UUID(value).bytes_le
                return GUID.from_buffer_copy(raw)

            foreground_hwnd = int(user32.GetForegroundWindow())
            current_thread = int(kernel32.GetCurrentThreadId())
            target_thread = int(user32.GetWindowThreadProcessId(root_hwnd, None))
            foreground_thread = (
                int(user32.GetWindowThreadProcessId(foreground_hwnd, None))
                if foreground_hwnd else 0
            )
            attached = []
            before_count = int(page_obj.Shapes.Count)
            menu_hwnd = 0
            diagnostics = []
            target_diagnostic = None
            target_acc = None
            target_child_id = None
            try:
                for other_thread in (foreground_thread, target_thread):
                    if other_thread and other_thread != current_thread:
                        if bool(user32.AttachThreadInput(current_thread, other_thread, True)):
                            attached.append(other_thread)
                user32.ShowWindow(root_hwnd, SW_RESTORE)
                user32.BringWindowToTop(root_hwnd)
                user32.SetForegroundWindow(root_hwnd)
                user32.SetActiveWindow(root_hwnd)
                user32.SetFocus(hwnd)
                time.sleep(0.2)
                chord(VK_SHIFT, VK_F10)
                for _ in range(30):
                    candidate = int(user32.GetForegroundWindow())
                    class_buf = ctypes.create_unicode_buffer(128)
                    user32.GetClassNameW(candidate, class_buf, len(class_buf))
                    if class_buf.value == "Net UI Tool Window":
                        menu_hwnd = candidate
                        break
                    time.sleep(0.05)
                if not menu_hwnd:
                    raise RuntimeError("Visio shortcut menu did not become a Net UI Tool Window")

                iid_dispatch = guid("00020400-0000-0000-C000-000000000046")
                raw_dispatch = ctypes.c_void_p()
                OBJID_CLIENT = 0xFFFFFFFC
                hr = int(
                    oleacc.AccessibleObjectFromWindow(
                        menu_hwnd,
                        ctypes.c_uint32(OBJID_CLIENT),
                        ctypes.byref(iid_dispatch),
                        ctypes.byref(raw_dispatch),
                    )
                )
                if hr != 0 or not raw_dispatch.value:
                    raise RuntimeError(
                        f"AccessibleObjectFromWindow failed hr=0x{hr & 0xFFFFFFFF:08X}"
                    )
                dispatch = pythoncom.ObjectFromAddress(
                    int(raw_dispatch.value),
                    pythoncom.IID_IDispatch,
                )
                root_acc = win32com.client.Dispatch(dispatch)

                visited = set()

                def safe_call(obj, name, child_id, default=None):
                    try:
                        return getattr(obj, name)(child_id)
                    except Exception:
                        return default

                def walk(acc, depth=0):
                    nonlocal target_acc, target_child_id, target_diagnostic
                    if depth > 5 or target_acc is not None:
                        return
                    identity = id(acc)
                    if identity in visited:
                        return
                    visited.add(identity)
                    try:
                        count = int(acc.accChildCount)
                    except Exception:
                        count = 0
                    for child_id in range(1, count + 1):
                        name = safe_call(acc, "accName", child_id, "")
                        role = safe_call(acc, "accRole", child_id, None)
                        state = safe_call(acc, "accState", child_id, None)
                        default_action = safe_call(acc, "accDefaultAction", child_id, "")
                        shortcut = safe_call(acc, "accKeyboardShortcut", child_id, "")
                        row = {
                            "depth": depth,
                            "child_id": child_id,
                            "name": "" if name is None else str(name),
                            "role": role if isinstance(role, (int, str)) else str(role),
                            "state": state if isinstance(state, (int, str)) else str(state),
                            "default_action": "" if default_action is None else str(default_action),
                            "keyboard_shortcut": "" if shortcut is None else str(shortcut),
                        }
                        diagnostics.append(row)
                        if "EnergoLogic Undo Probe" in row["name"]:
                            target_acc = acc
                            target_child_id = child_id
                            target_diagnostic = row
                            return
                        child_obj = safe_call(acc, "accChild", child_id, None)
                        if child_obj is not None and not isinstance(
                            child_obj, (int, float, str, bool)
                        ):
                            try:
                                walk(win32com.client.Dispatch(child_obj), depth + 1)
                            except Exception:
                                pass
                            if target_acc is not None:
                                return

                walk(root_acc)
                if target_acc is None:
                    raise RuntimeError(
                        f"EnergoLogic MSAA menu item not found; nodes={diagnostics!r}"
                    )
                target_acc.accDoDefaultAction(target_child_id)

                expected_count = before_count + 8
                for _ in range(80):
                    time.sleep(0.1)
                    if int(page_obj.Shapes.Count) == expected_count:
                        break
            finally:
                for other_thread in reversed(attached):
                    try:
                        user32.AttachThreadInput(current_thread, other_thread, False)
                    except Exception:
                        pass

            after_count = int(page_obj.Shapes.Count)
            if after_count != before_count + 8:
                try:
                    press(VK_ESCAPE)
                except Exception:
                    pass
                raise RuntimeError(
                    f"MSAA ShapeSheet Action probe expected {before_count + 8} shapes, got {after_count}; "
                    f"target={target_diagnostic!r}; nodes={diagnostics!r}"
                )
            return ok({
                "document": str(document.Name),
                "page": str(page_obj.Name),
                "trigger_shape_id": int(trigger_shape_id),
                "shape_count_before": before_count,
                "shape_count_after": after_count,
                "menu_window_handle": menu_hwnd,
                "target_accessible": target_diagnostic,
                "launch_path": "Office Net UI / MSAA accDoDefaultAction",
                "ui_action_launched": True,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def uia_run_energologic_qol_action_probe(
        trigger_shape_id: int,
        page: str = "",
        doc_name: str = "",
    ) -> str:
        """Invoke the fixed EnergoLogic ShapeSheet action through Office UI Automation."""
        try:
            import ctypes
            import importlib.util
            import time

            page_obj = visio._resolve_page(doc_name, parse_page(page))
            document = page_obj.Document
            app = page_obj.Application
            if Path(str(document.FullName)).suffix.lower() != ".vsdm":
                raise ValueError("QoL action probe requires a .vsdm document")
            trigger = page_obj.Shapes.ItemFromID(int(trigger_shape_id))
            if not bool(trigger.CellExistsU("Actions.EnergoLogicUndoProbe.Action", 0)):
                raise ValueError("trigger shape does not contain EnergoLogic probe action")

            try:
                app.ActiveWindow.Page = page_obj
            except Exception:
                page_obj.Activate()
            window = app.ActiveWindow
            window.DeselectAll()
            window.Select(trigger, 2)

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            hwnd = int(window.WindowHandle32)
            GA_ROOT = 2
            SW_RESTORE = 9
            VK_SHIFT = 0x10
            VK_F10 = 0x79
            VK_ESCAPE = 0x1B
            KEYEVENTF_KEYUP = 0x0002
            MOUSEEVENTF_LEFTDOWN = 0x0002
            MOUSEEVENTF_LEFTUP = 0x0004
            root_hwnd = int(user32.GetAncestor(hwnd, GA_ROOT)) or hwnd

            def chord(modifier, vk):
                user32.keybd_event(modifier, 0, 0, 0)
                user32.keybd_event(vk, 0, 0, 0)
                user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
                user32.keybd_event(modifier, 0, KEYEVENTF_KEYUP, 0)

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
            menu_hwnd = 0
            menu_class = ""
            diagnostics = []
            uia_error = None
            target = None
            clicked_point = None
            try:
                for other_thread in (foreground_thread, target_thread):
                    if other_thread and other_thread != current_thread:
                        if bool(user32.AttachThreadInput(current_thread, other_thread, True)):
                            attached.append(other_thread)
                user32.ShowWindow(root_hwnd, SW_RESTORE)
                user32.BringWindowToTop(root_hwnd)
                user32.SetForegroundWindow(root_hwnd)
                user32.SetActiveWindow(root_hwnd)
                user32.SetFocus(hwnd)
                time.sleep(0.2)
                chord(VK_SHIFT, VK_F10)
                for _ in range(30):
                    candidate = int(user32.GetForegroundWindow())
                    class_buf = ctypes.create_unicode_buffer(128)
                    user32.GetClassNameW(candidate, class_buf, len(class_buf))
                    menu_class = class_buf.value
                    if menu_class == "Net UI Tool Window":
                        menu_hwnd = candidate
                        break
                    time.sleep(0.05)
                if not menu_hwnd:
                    raise RuntimeError(
                        f"Visio shortcut menu did not become a Net UI Tool Window; class={menu_class!r}"
                    )

                modules = {
                    name: bool(importlib.util.find_spec(name))
                    for name in ("comtypes", "pywinauto", "uiautomation", "PIL")
                }
                if not modules["comtypes"]:
                    raise RuntimeError(f"comtypes is unavailable on the Windows agent; modules={modules!r}")

                try:
                    import comtypes.client
                    uia_module = comtypes.client.GetModule("UIAutomationCore.dll")
                    from comtypes.gen import UIAutomationClient
                    uia = comtypes.client.CreateObject(
                        "{ff48dba4-60ef-4201-aa87-54103eef594e}",
                        interface=UIAutomationClient.IUIAutomation,
                    )
                    root_element = uia.ElementFromHandle(menu_hwnd)
                    condition = uia.CreateTrueCondition()
                    scope_descendants = int(getattr(UIAutomationClient, "TreeScope_Descendants", 4))
                    collection = root_element.FindAll(scope_descendants, condition)
                    length = int(collection.Length)
                    for index in range(min(length, 200)):
                        element = collection.GetElement(index)
                        def prop(*names):
                            for name in names:
                                try:
                                    return getattr(element, name)
                                except Exception:
                                    continue
                            return None
                        name = prop("CurrentName", "currentName")
                        control_type = prop("CurrentControlType", "currentControlType")
                        enabled = prop("CurrentIsEnabled", "currentIsEnabled")
                        rect = prop("CurrentBoundingRectangle", "currentBoundingRectangle")
                        rect_values = None
                        if rect is not None:
                            try:
                                rect_values = [int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)]
                            except Exception:
                                try:
                                    rect_values = [int(value) for value in rect]
                                except Exception:
                                    rect_values = None
                        row = {
                            "index": index,
                            "name": None if name is None else str(name),
                            "control_type": None if control_type is None else int(control_type),
                            "enabled": None if enabled is None else bool(enabled),
                            "rect": rect_values,
                        }
                        diagnostics.append(row)
                        if row["name"] and "EnergoLogic Undo Probe" in row["name"]:
                            target = row
                            break
                except Exception as exc:
                    uia_error = f"{type(exc).__name__}: {exc}"

                if target is None or not target.get("rect"):
                    raise RuntimeError(
                        f"EnergoLogic action UIA element not found; uia_error={uia_error!r}; "
                        f"elements={diagnostics!r}"
                    )
                left, top, right, bottom = target["rect"]
                x = int((left + right) / 2)
                y = int((top + bottom) / 2)
                clicked_point = [x, y]
                user32.SetCursorPos(x, y)
                time.sleep(0.1)
                user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

                expected_count = before_count + 8
                for _ in range(80):
                    time.sleep(0.1)
                    if int(page_obj.Shapes.Count) == expected_count:
                        break
            finally:
                for other_thread in reversed(attached):
                    try:
                        user32.AttachThreadInput(current_thread, other_thread, False)
                    except Exception:
                        pass

            after_count = int(page_obj.Shapes.Count)
            if after_count != before_count + 8:
                try:
                    press(VK_ESCAPE)
                except Exception:
                    pass
                raise RuntimeError(
                    f"UIA ShapeSheet Action probe expected {before_count + 8} shapes, got {after_count}; "
                    f"target={target!r}; clicked_point={clicked_point!r}; uia_error={uia_error!r}; "
                    f"elements={diagnostics!r}"
                )
            return ok({
                "document": str(document.Name),
                "page": str(page_obj.Name),
                "trigger_shape_id": int(trigger_shape_id),
                "shape_count_before": before_count,
                "shape_count_after": after_count,
                "menu_window_handle": menu_hwnd,
                "menu_window_class": menu_class,
                "target_element": target,
                "clicked_point": clicked_point,
                "launch_path": "Office Net UI / Windows UI Automation bounding rectangle click",
                "ui_action_launched": True,
            })
        except Exception as exc:
            return err(exc)

    @mcp.tool()
    def keyboard_run_energologic_qol_action_probe(
        trigger_shape_id: int,
        page: str = "",
        doc_name: str = "",
    ) -> str:
        """Invoke the fixed EnergoLogic ShapeSheet Action through the real shortcut menu."""
        try:
            import ctypes
            import time

            page_obj = visio._resolve_page(doc_name, parse_page(page))
            document = page_obj.Document
            app = page_obj.Application
            if Path(str(document.FullName)).suffix.lower() != ".vsdm":
                raise ValueError("QoL action probe requires a .vsdm document")
            trigger = page_obj.Shapes.ItemFromID(int(trigger_shape_id))
            if not bool(trigger.CellExistsU("Actions.EnergoLogicUndoProbe.Action", 0)):
                raise ValueError("trigger shape does not contain EnergoLogic probe action")

            try:
                app.ActiveWindow.Page = page_obj
            except Exception:
                page_obj.Activate()
            window = app.ActiveWindow
            window.DeselectAll()
            window.Select(trigger, 2)

            hwnd = int(window.WindowHandle32)
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            GA_ROOT = 2
            SW_RESTORE = 9
            VK_SHIFT = 0x10
            VK_F10 = 0x79
            VK_END = 0x23
            VK_RETURN = 0x0D
            KEYEVENTF_KEYUP = 0x0002
            root_hwnd = int(user32.GetAncestor(hwnd, GA_ROOT)) or hwnd

            def chord(modifier, vk):
                user32.keybd_event(modifier, 0, 0, 0)
                user32.keybd_event(vk, 0, 0, 0)
                user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
                user32.keybd_event(modifier, 0, KEYEVENTF_KEYUP, 0)

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
                user32.SetFocus(hwnd)
                time.sleep(0.2)
                chord(VK_SHIFT, VK_F10)
                menu_class = ""
                menu_hwnd = 0
                for _ in range(20):
                    candidate = int(user32.GetForegroundWindow())
                    class_buf = ctypes.create_unicode_buffer(128)
                    user32.GetClassNameW(candidate, class_buf, len(class_buf))
                    menu_class = class_buf.value
                    if menu_class == "Net UI Tool Window":
                        menu_hwnd = candidate
                        break
                    time.sleep(0.05)
                if not menu_hwnd:
                    raise RuntimeError(
                        f"Visio shortcut menu did not become a Net UI Tool Window; "
                        f"foreground={int(user32.GetForegroundWindow())}, class={menu_class!r}"
                    )
                press(VK_END)
                time.sleep(0.15)
                press(VK_RETURN)
                expected_count = before_count + 8
                for _ in range(60):
                    time.sleep(0.1)
                    if int(page_obj.Shapes.Count) == expected_count:
                        break
            finally:
                for other_thread in reversed(attached):
                    try:
                        user32.AttachThreadInput(current_thread, other_thread, False)
                    except Exception:
                        pass

            after_count = int(page_obj.Shapes.Count)
            if after_count != before_count + 8:
                raise RuntimeError(
                    f"ShapeSheet Action probe expected {before_count + 8} shapes, got {after_count}"
                )
            return ok({
                "document": str(document.Name),
                "page": str(page_obj.Name),
                "trigger_shape_id": int(trigger_shape_id),
                "shape_count_before": before_count,
                "shape_count_after": after_count,
                "launch_path": "Shape shortcut menu / Actions.EnergoLogicUndoProbe",
                "menu_window_class": menu_class,
                "menu_window_handle": menu_hwnd,
                "ui_action_launched": True,
            })
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
    def keyboard_run_energologic_qol_undo_probe(
        shape_ids_json: str,
        page: str = "",
        doc_name: str = "",
    ) -> str:
        """Launch the fixed EnergoLogic undo-probe macro through Visio's real Macros UI.

        No arbitrary macro name or keystrokes are accepted. This is a bounded
        qualification tool for proving true user-context invocation.
        """
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
            document = page_obj.Document
            app = page_obj.Application
            if Path(str(document.FullName)).suffix.lower() != ".vsdm":
                raise ValueError("QoL VBA UI probe requires a .vsdm document")
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

            hwnd = int(window.WindowHandle32)
            if hwnd <= 0:
                raise RuntimeError("Visio active window returned an invalid HWND")
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            GA_ROOT = 2
            SW_RESTORE = 9
            VK_MENU = 0x12
            VK_F8 = 0x77
            VK_CONTROL = 0x11
            VK_A = 0x41
            VK_RETURN = 0x0D
            VK_ESCAPE = 0x1B
            KEYEVENTF_KEYUP = 0x0002
            KEYEVENTF_UNICODE = 0x0004
            INPUT_KEYBOARD = 1
            root_hwnd = int(user32.GetAncestor(hwnd, GA_ROOT)) or hwnd

            class KEYBDINPUT(ctypes.Structure):
                _fields_ = [
                    ("wVk", ctypes.c_ushort),
                    ("wScan", ctypes.c_ushort),
                    ("dwFlags", ctypes.c_ulong),
                    ("time", ctypes.c_ulong),
                    ("dwExtraInfo", ctypes.c_void_p),
                ]

            class INPUT_UNION(ctypes.Union):
                _fields_ = [("ki", KEYBDINPUT)]

            class INPUT(ctypes.Structure):
                _anonymous_ = ("u",)
                _fields_ = [("type", ctypes.c_ulong), ("u", INPUT_UNION)]

            def press(vk):
                user32.keybd_event(vk, 0, 0, 0)
                user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)

            def chord(modifier, vk):
                user32.keybd_event(modifier, 0, 0, 0)
                user32.keybd_event(vk, 0, 0, 0)
                user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
                user32.keybd_event(modifier, 0, KEYEVENTF_KEYUP, 0)

            def ascii_text(value):
                VK_SHIFT = 0x10
                VK_CAPITAL = 0x14
                caps_on = bool(user32.GetKeyState(VK_CAPITAL) & 1)
                for char in value:
                    if "A" <= char <= "Z":
                        vk = ord(char)
                        use_shift = not caps_on
                    elif "a" <= char <= "z":
                        vk = ord(char.upper())
                        use_shift = caps_on
                    elif "0" <= char <= "9":
                        vk = ord(char)
                        use_shift = False
                    else:
                        raise RuntimeError(
                            f"Fixed macro name contains unsupported character {char!r}"
                        )
                    if use_shift:
                        user32.keybd_event(VK_SHIFT, 0, 0, 0)
                    user32.keybd_event(vk, 0, 0, 0)
                    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
                    if use_shift:
                        user32.keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0)
                    time.sleep(0.01)

            foreground_hwnd = int(user32.GetForegroundWindow())
            current_thread = int(kernel32.GetCurrentThreadId())
            target_thread = int(user32.GetWindowThreadProcessId(root_hwnd, None))
            foreground_thread = (
                int(user32.GetWindowThreadProcessId(foreground_hwnd, None))
                if foreground_hwnd else 0
            )
            attached = []
            before_count = int(page_obj.Shapes.Count)
            macro_name = "UndoProbeDuplicate40"
            try:
                for other_thread in (foreground_thread, target_thread):
                    if other_thread and other_thread != current_thread:
                        if bool(user32.AttachThreadInput(current_thread, other_thread, True)):
                            attached.append(other_thread)
                user32.ShowWindow(root_hwnd, SW_RESTORE)
                user32.BringWindowToTop(root_hwnd)
                user32.SetForegroundWindow(root_hwnd)
                user32.SetActiveWindow(root_hwnd)
                time.sleep(0.2)

                # Close a stale dialog left by a prior failed qualification, if any.
                press(VK_ESCAPE)
                time.sleep(0.15)
                chord(VK_MENU, VK_F8)
                time.sleep(0.6)
                chord(VK_CONTROL, VK_A)
                ascii_text(macro_name)
                time.sleep(0.15)
                press(VK_RETURN)
                time.sleep(1.0)
            finally:
                for other_thread in reversed(attached):
                    try:
                        user32.AttachThreadInput(current_thread, other_thread, False)
                    except Exception:
                        pass

            after_count = int(page_obj.Shapes.Count)
            if after_count != before_count + len(shape_ids):
                diagnostics = []
                try:
                    process_id = ctypes.c_ulong(0)
                    user32.GetWindowThreadProcessId(root_hwnd, ctypes.byref(process_id))
                    target_pid = int(process_id.value)

                    def window_text(target_hwnd):
                        length = int(user32.GetWindowTextLengthW(target_hwnd))
                        buf = ctypes.create_unicode_buffer(max(1, length + 1))
                        user32.GetWindowTextW(target_hwnd, buf, len(buf))
                        return buf.value

                    def class_name(target_hwnd):
                        buf = ctypes.create_unicode_buffer(256)
                        user32.GetClassNameW(target_hwnd, buf, len(buf))
                        return buf.value

                    top_windows = []
                    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

                    @EnumWindowsProc
                    def enum_top(target_hwnd, lparam):
                        pid = ctypes.c_ulong(0)
                        user32.GetWindowThreadProcessId(target_hwnd, ctypes.byref(pid))
                        if int(pid.value) == target_pid and bool(user32.IsWindowVisible(target_hwnd)):
                            top_windows.append(int(target_hwnd))
                        return True

                    user32.EnumWindows(enum_top, 0)
                    for top_hwnd in top_windows:
                        children = []
                        EnumChildProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

                        @EnumChildProc
                        def enum_child(child_hwnd, lparam):
                            children.append({
                                "hwnd": int(child_hwnd),
                                "class": class_name(child_hwnd),
                                "text": window_text(child_hwnd)[:200],
                                "control_id": int(user32.GetDlgCtrlID(child_hwnd)),
                                "visible": bool(user32.IsWindowVisible(child_hwnd)),
                                "enabled": bool(user32.IsWindowEnabled(child_hwnd)),
                            })
                            return True

                        user32.EnumChildWindows(top_hwnd, enum_child, 0)
                        diagnostics.append({
                            "hwnd": top_hwnd,
                            "class": class_name(top_hwnd),
                            "text": window_text(top_hwnd)[:200],
                            "is_foreground": int(user32.GetForegroundWindow()) == top_hwnd,
                            "children": children[:80],
                        })
                except Exception as diag_exc:
                    diagnostics = [{"diagnostic_error": f"{type(diag_exc).__name__}: {diag_exc}"}]
                # Best-effort close any macro dialog left open by a failed qualification.
                try:
                    press(VK_ESCAPE)
                except Exception:
                    pass
                raise RuntimeError(
                    f"Visio Macros UI probe expected {before_count + len(shape_ids)} shapes, "
                    f"got {after_count}; windows={diagnostics!r}"
                )
            return ok({
                "document": str(document.Name),
                "page": str(page_obj.Name),
                "macro_name": macro_name,
                "launch_path": "Alt+F8 Macros dialog",
                "shape_count_before": before_count,
                "shape_count_after": after_count,
                "source_shape_ids": shape_ids,
                "ui_macro_launched": True,
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

