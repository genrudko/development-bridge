from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.93"
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
            build_dir = workspace / "energologic_visio_editor_addin_v27"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV27.dll"
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

            clsid = "{1DD57883-7CD6-4C5F-BAEA-8383F4D41CC2}"
            progid = "EnergoLogic.VisioEditorAddinV27"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV27, Version=0.2.7.0, Culture=neutral, PublicKeyToken=null"
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
            progid = "EnergoLogic.VisioEditorAddinV27"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV27")
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
                "progid": "EnergoLogic.VisioEditorAddinV27",
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
            progid = "EnergoLogic.VisioEditorAddinV27"
            clsid = "{1DD57883-7CD6-4C5F-BAEA-8383F4D41CC2}"
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

