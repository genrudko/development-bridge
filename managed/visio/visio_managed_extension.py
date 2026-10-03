from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.94"
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
            build_dir = workspace / "energologic_visio_editor_addin_v28"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV28.dll"
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

            clsid = "{A57C645D-EC43-4DFB-89CD-4FF056A4C4C8}"
            progid = "EnergoLogic.VisioEditorAddinV28"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV28, Version=0.2.8.0, Culture=neutral, PublicKeyToken=null"
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
            progid = "EnergoLogic.VisioEditorAddinV28"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV28")
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
                "progid": "EnergoLogic.VisioEditorAddinV28",
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
            progid = "EnergoLogic.VisioEditorAddinV28"
            clsid = "{A57C645D-EC43-4DFB-89CD-4FF056A4C4C8}"
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

