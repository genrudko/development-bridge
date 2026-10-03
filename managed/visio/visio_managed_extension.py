from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.109"
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

            build_dir = workspace / "energologic_visio_editor_addin_v311"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV311.dll"
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

            clsid = "{6D8D560D-1F9F-4CB8-BED7-5FCBB70B1F2C}"
            progid = "EnergoLogic.VisioEditorAddinV311"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV311, Version=0.3.11.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.10 -> v3.11",
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
            progid = "EnergoLogic.VisioEditorAddinV311"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV311")
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
                "progid": "EnergoLogic.VisioEditorAddinV311",
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
            progid = "EnergoLogic.VisioEditorAddinV311"
            clsid = "{6D8D560D-1F9F-4CB8-BED7-5FCBB70B1F2C}"
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

