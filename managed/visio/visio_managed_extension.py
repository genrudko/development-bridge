from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.101"
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
            build_dir = workspace / "energologic_visio_editor_addin_v35"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV35.dll"
            source_path.write_bytes(gzip.decompress(base64.b64decode("H4sIAAAAAAAC/+19a3Mcx5Hgd/2K4tihmFkOWgAI0hIgUIsHJeFOIHkEKBNBchmNmQbQ1kz3uLuHxBhChB5ryz75pLPsDxsO78l7vtjYb0tRokVJJPUPNoC/oF9ymVmPru6u6u4ZgLIdYUZImO6uynplZuWrsoaxH+yyjVGceP2F54bak7MS9npeJ/HDIHZe8wIv8ju5EquRew8ec29f64Xbbs//mYtVc9/e8IOf5l5d83ZEM/kPwyDx+56zFiReFA42vOiu3/HiXKlNbz8BGLvDnhtd2h9EXhxjj3OlfuwH3fBe7LwaRn317dJ+4gWxv+33/GQkX677nSiMw53EubKzA+3BNETewnPP3XTj2Otv90bzbCXsv+lDvZ7XTKKh17qtf1wSvzb9BL43LsG87YZvhLt+h2GlkF3q+kkYNcy13vQi7H6zMe2cc84701jsucDte/HA7XhMg0bAOKznDp5j8M/HeQrcHos9t+d1WacH8NlrvaG36Ua7XkKFeFH8Nxhu96BTUIvx72vdBdPHa+G9wvs4iWgCg+4ghDL8++FzFd241N311oKd0N6RjXAYdTxDR4wNTjSK0l6ueL1eeQ+Xgs5eGFkaWR7G9i+bXtT3oUVLiY1eaB7WShgEnD5qr4T2/Q0/Tl6GDxcZ4vFaN2aLLPDupe+brZI664CUXlRSq3w2Vc+vYt8qln7PHXhjoGA3hL8eu9Hv2z5t2T+twjjcoOOt99Uw6O/NImnT69eGfrfZWJlbWpm5sDo3tbo89+rU3MyF5anl5ZlzUzOrL85dmp1d/tGLMysNWYW41g4Q7eZo4DUBbuaFo57W4tWh2xO10jHzj2xNo3hO7EsDPzeJAgXgw+pwANXdxHvD20n0hTUUuebv7lnKrId3SyDg15LKGx5ycyQk8/dr3sD1I2QHVyPvru/dqyq2NBj0RpbBhB2YEUs/9sJ7V93As3Tj0r7bSYDDx17SFEjR3V/vtyWGdEfrfWPFpZ6/G9xo2r9tmb8tu7G3Eg5GsrXtfdXW9kj9TNK3ycgKB5fgpHDWPTceRt5VP+nsWWbXx9/bw0QUEvAG+GCZnJUwjLrA5BIvNsO8PIQ9wI5b9LkEuej79UHJx9XwXmDDqGCI3IxQU7wGnrbqxbBoJKsYq8kdOcvwyhnF6kvnXp2eXpmdmll56fzU3Or00tTS9NJLUxemX7o0e375pR+9NJcyiqtRuLvWzUgKjra5L3VhQt88d16VX0HeqthHM/tIvGVpmIRFpmJizWyera1uZuSg2XYtpjOI/LuwzCzc/gnCueMOOF8hMc5aqNtdC9YCznuLxXhbKKKxOzvw/2IJmPW+G3SX3Yjd2XajsgLLwyQJA3YnCXd3ex5/Kpa/k69w6a4XJPGdFRjMW/T7dfja8yIJSDwWIUWe2w2D3oiBLOrtszu7wLr4T7510u+mqob//rHRfOXlhKSWizf/6Uyz1b59tnUm3TXj5ivzt5wbUCgK7+1fvNU923r7lsMf6Qk+thrtDExq5sqAS+1ruwFs+ivAMdjb2S8w7IEP6NCqHkhH9Qcpp3JI/1Tsv+y47PIPT9zn/LZ+N/S77EqQNt0UKLeUomWbgaZwRxRZD7se0363JY4uSRRtw0TssKUockesM4yTsN9SrR5kuq/jPszMkokSeDkd/bGkfM6WS6IRO4ANCMR+GNpeGCeZsvTGucK7u8iSPT9eYIcMWuzsQb3DDCxqrdfb1IhA5474z7hRHtqmGDaFFCGaOKPpG5rUa14fdic+p3VnkI/Y32FNont2BvBr2Oux559nZ+iNA1KSHw/CGFaf8wZnpQdP0GXr0DkoDim3EDpPMJcA5mL8oPU0u5qiy63iyuW4Xm75qAkYg3UUeaQxdDaLf9kC1oUkhIqvD7pA883CQmX6ka24ARwrGQ6QGnvemHWXvV0/2NgbJl3cps01CwxJzicQlgV/pHJr/koKCq2YPk9yvZI94KbEztaCu27P714ZeBGVubTf8Yj1NBtccz96cvSQHX179PToi6Ovj745/uj4g+PfHD1p5AgK/0VeMowCy7bI18W0QmLENFtG0rVMgJwiaI5zoGxj6SYXs2383yJrau9aUM3RnrOVgbgBj4VABLUvu33EQ11eaZiIRNAQtndTVLu9kMNuifNaWQcQsynKt9l6HEKProaxj1Po9OlxMxzAFz9Ge43zpgsbbZuRELagT2Y9SgcmwZqoY/rweWYB/ry8SN2BCQmSKOzhvjMExZr5Z8+2KrAsnUNRmXVYDtpN//aCETs3aIKdSz8FwS1udpxNd7edmWSHi0cOR4hGm/EaSIdu5McwO1dI9u61WoUGil01zQ7gT1yQoBaMVbdBSnir+OnwOfsTkWC2RUGDz1V1rJnvVCu7QogygCnimWTgvnrkNQoIU/7I0akEmZwVdyAYbgklZKvAkuaK59a0rPJGMuoh3SFF0Bt6QRRBj6I/pe2HYS/xB2gxxX4cfQqc7Ouj+0dfHt0/fu/418ja7iOPA9b2a1Z3UEILQkkE5sxYUorQXGqsLXI3rwR8XuhLq6wTVIKdXbRK6XJTt3bXxoUzfSjgIVtJoh6Xc7ZhctkKbtK9VW/HHfYSG7POFIKO7ADBe5PLZFpZS4OpYCUojr39NivIVUUqlAIULFqqmjVR4MwtBjYgBDUxv1JKw87lBU7+ZRmZ12b4agRUai6xBDImLkT5HFitX7CtiF1YfSDVf2qmtVAUUOwWMhucCjCpES0FgO9q9UGzsRlqV1TWLXBp7Yxdrqy6wUCXQkk/ktmjzZG3LkBhyjOCI0C14Emrn7Yw0g5YOi0pnUBNncIkmMZ3f/gtA65oZIJc8BPsEgrcdxqlzdUyMKZDyBTn5cgCWdaENEWmUOhNs7HfqFFxy1BxVFFxEiNm2gjWJk/AZuQG8Q4xE0IiBIP1sSKaK6u6MK79s7QLAvHG6UPWdqpRaNamWorE5cZVDbdzBZX5tQx6xg6bwsqaZ8sAaHZaM45OzTjTbTbtTNeAU+BkOqAx4KDh1wxkGoHM1ALCDcQlYKYq4dSwJOssTiuctzeXtaIMzyks7hVuZNSc1PXGa2Y3KdRsun7EzTUTao/y88DdRbkJlUXamr2r8CKnaAr/KQMBpwdlyTZ0lw8edvo+34RwVAisZW4nJiewdJcCFCzrkH8wdtYSr4+Q1lab2IaTcaxaAHITqwbwNS/R6i2P0PdKPWozCXStK37jN3ZWm8Sc6AMTzOFTQYJN4LKN5mpdCpBPyI+vRp4nmscFa2WrOmurbZLBXnfjvQ1P+l/zY5VbDO/Cej/XAdAlr/rBjUaLTYnv2WlW381gR6VgtyrAbjXyulTqYo6Fyx+NEjThyueM+qwXLY+aMKaLbL8F+gtWywuLBEoPL1AwBWXgNwCOChJMuv5WTLrqQt4yStgK7yvKUQ/4TN28LVunXSbjN1cljCPg5Ctrr7sxdDNTXRSoURkVvDpVYfvz3M6esH90AZe1IVaYOrLESsRpp1S/azCR6dNEGjx2V84R8DwdnQikQtG27Rvi4aG1KTGn3FpAv9HGpENpWevSlFLNDXeHnsrq5axQOL3AB2mGiMCRhZIp9HrQDTfwS1PxF3aRTbNXMlaCeXb0e5A9vz16dPwO/H0g1PXjj48/ADn1q6Ovj99n8PZb+Hof/j5tsPlJ6n8DD1g7NxhSbDug+PoWZTWJRhXIguNdDVf63ebM9OycYZIlNnXl5tXNbDQ8estRu4fZgkZTm0Lgdjs0zCuk5q/Gs/k+OHoIs/bk+P2jb8gATGrAN/ji+CMG+gCfV/j54PjDoy9Qb4D/nsCrj0124ZTvQeuc6alRIaNJu2+rnPIZgDAGk7EQPO9GXYuhXCeoNQnJ4z/VazvNS+gFgs9+sFH7oWncqZF3moy8eaQw2Hft04DYpnEQyxTwqb3p3261UiwUTAjeohFGMZNxQBAvwnfGvhFFjoHfj0CffcxRFjEcsPv4neOPAZNB2WXH/4vQmb4fv4e8gxGbeZRivuAoVP/RAqO3SDH3j3+BRAAvoCJvAP+736i1YkLuQDn5rrcqHM4Sb0CghOlqDlAsGNycvo3CR3Y3KZRYqGhhVNbCTGULM8YWUlbEFdZ9gCJHhPp9+gh6Z6PfL0hJcvNwedBh0CXXe4q59ObKDpeEZWRiy8wddRgvs+maTPDoX9HlBcsG2wQytyeiL9rmgcjwQOHD0aNGCX+H1ng37YxDoLzWXdPcploXqRy4XTRwFuYbIKtjEI5z2btHwTgoNnJPSbNxuTEWUwTWnHDwXpD4yahp53XttCuGJkg6FRGaTTUHQsGQH9osL1rT50z4pwE2qIn+zoikWTtkm1pRqwWDgK1Qu7aMLabUjJtGcIX9u/DNzADr4LWVc0qu+C2xrYfECr9BIQD3+/eArSEPQ1b3kBa1nBtmiKQOazR2yzBnShorulw057PwKKLR3k2aK8MeX5qd0FkZRhGgtHjVNjbLjaH/qQZwnx2/axjmfXYwfeiwoz/AyN7FLYIdzByy737xCTuYPVzAOl9AyUdHn7ODc/PTzvT0IYMhP14Q0wfyJlTDigjsqZBCn8BuLGgOITyFLeoLaXQ197YgPhfkYU3A1TT7tqa8A0veby2UeDB3kG56dYRdoLxUtCfRvy0WrVUjDCBv0lGG/79bc56xNUc3sbDwXiAk64zlJWukOKlhBxr5m7PkVGwOft09oTCTp601f0rsluRX4jGPxtab60F4dpqzIuYKqalKAlz1EpBxlAzimsQEQ7W8BawU9yXzM+vsUgZGwVdJuyZhN/LiBESyrkQYGPQ1/sqAQjquVQle7rORutxnIHJx8OOP9y8jGAixhlPJr7gsM6lYUCFqPRX2GNRHP2xb5Yejp/PsYO7w9KUFi3UfRYd2AXPrCBPsoFJgqCck6P79CslAbP1Lz2rrH4trZHzvn2RsaPfRqPYuCMqaHH0fFgc28JyngKsKZ+FT0WLRZop7P2XHvwSEAtRJgQiJoOE0FupMs9Gtrzn1y2Jw1t1kz1najoELtkAHn/GmXsIQ5/T1SL6uq53/m0Zyj7im/hCH+/Toz/D+PXb02fGHPLSLDJiI0TDDjxsW0erkImNq3/TJuCkYymY4eMO76/VK0YbLTpdDPI6SZ3tmn8uEckcRWh1ZIycZ/F/gPB8gKh19pbGzZyAC5KnJ/1vYeP9KNjDBVsxrNc9uwC4Fu88PfvADvv202RbsU/ob2MI+ObUNaRY3JCZX4i+6WxjiYASqDtIgmjqhNbatRlNiErR7bu/b1ZEELaHbo4XvgWH+huK3uA/sY4Ymml+I7Ya/wU0CUAWNmmR4eEAxsV/At4+O3/s725yAbSJG1fRnvgv7lVqfp0ircjXgob5yVg7mL8WgEZ9xLur6mPJBBVGntpvPYtX2TX4+ewdOx8uvDPZR5xk7+c2OJMMoJDGN6WLO+amVIybdaFXolW1RhK07PXzE4YzbC93ZnVrJ/TH92+jakc5szg2ldffjms7smg7tspqaNxt6fEIEt/my6+G4ckKcBM1hFHY0z7ZQwHTT5wmQXfg1aeul7hjdpUiONbykGYgjM8QZG8QZK0TAW80l2lXe0BIJVfP6dU7q8qtw+yF9ve7GNV1/rfH8hB2bk7DK1Ta5i63gZsu61/yajrVxIwtOx4eGYKwb+sNTCzjwYOOvuTOfUNXiJ94n1KtOolsdfj/a1gHa8koXbZ791+9u5BStNrwD5Ws2o3yh7U2Ij3mJkSMQt9V9WjA/4iepaX2velUmwv7kZriT6AWZwFCg2gkjQv0xYkEniQLl89Zztz00OKTRlRRX6WxGfr/ZKj0xuxZfBlnqSvTjPR+2TkyT1iRowJcl1JUwgJ0pSbcFgu7wI8Z2hDad68YkchQGejIb+g+QSg5mDskGkUH6BbRBnNPfWIzYfrfNB6gkZbP8nBEmWqXUIG2xRGxPgaa+QGspqWcfGmTC+VvRrQB3XzEZ/y30gfvTyzafqc2QzvdnotVLqKfGwQoLTYnCd12+SeYOWrBXgIM0zNiEmETVnDe8YDfZQ+G8dnTUJ2j9wVnCjY4Jg89T/PkUuB/GLeDsfaDss3pASKOqIxfZhbm6Hfk/lc0J2/AXJPD/GbuqWYe/gHePaFd+CIUuzKHx4xHg3gMqDYMydfYMZWcB+lvHU/y8723MAHPz1uDgjUP43+XD29rvW7Fz54Vm6+ytqdsH0+0L5w5/2DAcVa858eYZfsQH+C0IGmQQOHqMiPvZ8fswAw/QPkcywj+DSIK2Om6/+wxRup1uT/fbCOTh8T9DyXfb7IU2IDg3B31NpcXS/TXHXJzEWywoKex1dQLSODMHbicmO1vOwpx47f8kx0cc6TPy2z0h2vsqh/EgCQIevE//fw9Kv09OEaTVo6+5Q6iUXBv20Yk0DdkRtZmggUJmhty+MunI/7WSv2Rslny078oBvw/C0SPu/LEHvfRzGR/rh76kQdYiThWzafBwU2Ed1LFRBl1jgerEGhKxO27Q9TFjjQG3mwTL4ttQFUlvpN6oV87aqlnA6Gv+xSBx/SBuanBAvujAaz8wic6CihKeakHRjqpeS7IRSIZA6qJWmj2rNXl0pG07udXAzZ7vsWdZ41aDAUX9GbEROCU3JR3/+uhLTmbkuOUSIflatYkrPSyT8p8NoHGaPfyrkVmejxj5Fx0VsNSnEZzcA/ipcvy8T6qH7WzN2CZnQtg9N9ilYzDT49qjDUJ8jnDHPO0RT2gQsxABF+3tZorcBnKpP0hGRASlFKc1OKSkVjh3WMvekCinwujz3LyKjbOLKCpabSVpN2RD17xBr7gRCtq2zAgaJri4VbqxEpK32PPPW7vDfRUZziL7xXlRWxHdJDtYcdRXIy/2orvelSFI+dRbSmItW20rGi3BhTPGDrcZ54ljZEAqtwFzfVAkxhGN2I28gjbPnq1rlz00e4MkiVuxqK4sjNu+8Dk/MIv92gkOjILJSEAk/qPh7NsCQyObmvlIh2F1LCLiCcSi+pPwKc4AqqYlw1Byo8rj9g0IRR/wg09PxhQGJwqP/AvH5+V2KhzgPNnrKDBvBgP2cOfPxC3IhHff0iYPIHkgA1vTA/SPfy6k8IdlQfoWaVnQwTO108mcTjJYLi8SiPfdaksDKbusT/9f5AlKHa4Ad/MGB1KGm6+8vA3i2EXnbGsKft8NewngCqZvbb4yf9Np38asqK+0ftgwx8VRQ87GsNPx4pi9Ip5fi8LhIL7ZQMiN2zxpGZvXu79QYxZsDFqKYJG/y0NixYuIb199L7DmtiIxChNEFgWXe3t+z2NN/vVlBV1aO55/nq3suRFsb/rGJgrdpFp4CpJ+5DkvtuoFuOfkoU6BFmLqBZaG3Zt3prxpKIoNw5+pKaOoOYi8HX9fb3xjuM2/NafbvA2zkBoPd3hN7M5ZNmOYlldMUEXxFlq/G0a0EX06q68ZPPEGa9nieEYg8eDu+/GzP29yEms3bkfKAw7zOFvXcvY7vvc9OP5QBAAjtxcOBukJ/4x4pjDyPSZLGZqWgJkyCia7nw87LTid/oJBOnIBdvyI8tFapfi46AKWcV4U7awOjhCkNiEFCi+N/QZ6aMjsjBhpOiZSR73KwcsqW5/Q+jwlL+LHMlvhU3bDEBZkKbr1DEJ/6kbZPBv9akM38JeuhjzlUMsr+L0HfdYLoHo2oaEasgh5B+Uh47l3cYhh0eClVJyHr4OzGV4fALNBvhP5LiY4tKzAs/VGZvORnZI7UlqoL5K4mwb8eF38EtuYMxVOgw7G5c8iTYGIHkDOfPxLYNKf80MCWRadXb3jD5la4afEr0Ho/7lUkkAPsoV1JjPlFnTkl/VOLM5WAZopB6TmT7S41sUp1KtClZrz+Z+6bpjJZc1jmBmmfXiHPPcYMP1YHJmAF48tRwopIx1mppVhueJ44WzxpGIyo96ZxV2CpYXvEJ01sk5aRVVFN21ZXrSShHtlhzb46F4ewyn4H4iXqacNkyaknrbPuJUUJvWhOJRRjK07ZYlqAoLlxLoBShJoNT1vF2MalWeq5+0An1OPEWb3q2vAx7rVZ4GxVClB6CCp/WqYVKwSqEBDjq16ZxXeOtx+4W2GAs8z7dvQ+7CCI44tsJJV411yYT7MeuXriawVvmjo0jbxGclmJOOxDWMpGDU7GPbXSRkUQWjV9qWjeSHn04PfeXOWcmBzz6483oT7APIy4QbkPOuhUQxFfUwk6+N9X/cD2Xd8b5LGN4eDnqcoSd4WcvEiA+0q0ANrbAXzrp5Vn1QZNxq9TMdFizJ/VuhfHqnEKdhWjerW2J6si1l4BwxCq6n5mxnX8e3xjndbnY6x4Ee8sNX1GItIu3U3RbYUfqsksb/I+aRRXK18/tmUA+WpBrZ5loEUu84y32I29fHY6bhKAmj0d8fvARpAysN63U4yJL6Z375pzMUtHPth43LGszuigSmx1eLYndnzJwsxHUPKh+34EWcPj0giJJ84iY6Fw19Y6EvhOn+Si08EGYQPpC3GUUuVqpMOgk6F5yjAABwZjQott3AZIST6t6EB/kq0cQoJCnNK9h8L208+NUJxVzlNhdsyAxh2hiwNZ6suheVDbgAECQ4z5WdAFFOQ5WcrTmuo5UY13ZDupMK5eeoJVaoSjkyYaKQq4ciEiUZOOyPGCbJiTOT6+V4jxy3btQVm/SwZNdNXjJ0ho35mjNp2pvpTcFjLr1cufDioXvpBJ2mmaYontmHlPXiPLNI+SsBolaK39yn4RqjsKpZR6e/HHzqMa6Y8gUIdRTsf7oD5FbjF6/s0Yml3RNAGMuC3UlwJekAp9Cbyfjr0Iw9QZ8dHgeB7SY51es4K0JRmxlP++JTIFGp5be8pD9vOmcFsRoZK47PBLcDNCsXbnUEdkglpgbMv9Xq5MkZbgxTz5VEFcZmg15WcAsEtD/1edyX/hQJ3rGcfuIjAwcoj6/IvaFeeBj6nvtnqWFUqgaoSpDhMRkf/GtsoRwFlNeBrgx22atxUdwbmRDFkYd+XsEuDoPgh4/z8peGL8tV/90ZcJuGBL8h9U/hlDahJI1GUZstZgUlIvKanGHvm4IGaE/RN8LlA/wRJl9J70y2eVyirtiWrVR5owPnwtGkYcoC1TXl/KsYYf44MN+fto4gSirWlEJLPlCUCC6uRiDAbcVTpaeoorEJdE6VdTCMqSxDYWNOKxXfdiHkDRF41Z6268rihJUagTHDssjhZXB1xFzwuleA/VbKxkDWlGrvx0yjhGujV8B4AvNHvg7TpDbic3kZj21mmfd/Sv5/D72XHKNEajJeEjBlkZpoiOt7Gl8/0Ge8pElPB1LS02TU6Kz1w4G+b4djwAf628c57etjCh/SWe3jXZYclEW0Klwx0zWdlhp/Fa7UmC3rL3/uo4a7WuLzxQchXtFpOOgzbFRDE9lIo49P5H0XG68fGcDm0nWasi5q8RS/SG3E5urPmd7/6f2yGhKVWo05nL0JpPbNJWgAtr/l5AFzVCswUC2BalGln+nwV+crwjv62vzvEYK7F7FmuBYZHMNPObrpvec0LLSEK82XK2mLMGnaJ98YSxHYwfTh1kcsmBzOHL2iXSjsHs4f/qE7IgaZkhtBRWCtmR1GPfEHUY0CylvHY2rgnNXII9FCcH0Kk+RpfPZWH6+j1A35e9hvyc4LEf/zzIlJ9987vGEaokEP6MQaaQ7kPBORHEi/FzsItWaQwHP8Kb6nlYr9a6dJtEzeCbY+iRTKIaAxi6npxJ/LlZZhjWOZgieeZWmJ9s6I1bguth4epAoHyQwj5s5HUUbnW6re23No7WnHtWVv0Io1qekZLPxmJggAuHSYFek8XxfkMa9NRhFmqqZhJdNV3e+EuqP14WaQbxPfoIs11L45B7F0O9/kVixmMY6T5ab2cvxXwg5r6WuEJDnh99C9CscTYJ27Dw8G80sjePkvYpw0WPqd94Jdhxs6WF18O9Q9rgMTO/xjCjBcPasg5EWM6s5gZKsJKpz2j8Kjz/YjWLD13Io9fCPW4Qk0d3+apj/70LZsZI4wQgnXUtuhnRYxv5VG+PH2poalqKjqZaaM09bdTTkXP1tYgL5I8rVCZv3YVmewX225X1yD49WIluQT6nLxr5hMo3q5tPQtY3yFnM1o0fcv5P18d+5Mab8lFEFKbH9TX48s1GqM+P2jhDTB1tXU87Q9VWjU1odSWr5qrUsBL4Y3qwdM1czM8FC0Cj257F8P98Z4XyZRBSvOjfFZKIjarc/s2PW5EChzF7Dgv2nQGfX2wQ0oQH1uvA/ohrak0MZQkGirZ2FDnIv0umVXxJ0wp/JxnlJ0ST1EqFYM2dNim76uDlXnhsE0HWNINsnjsuXEqihvOFo43nayCsRw/V1vD+flaMSe6wqZvFBudPa/vCa48z0AGxJjeD0E4BhIddqCg25tSx/hp0xdTUNTinIYl7/Dv/5hvJ6/+ZRrgUl6u65g/mB19qpeTwSv5WMRsGo3jD52yJBqqGVK8XmxVJdSQBzxycV/ZeC99F7PtdNr9jFq6vHFs3PkIlbQ3w8D/KUWxmwJZVLE6lxXK9qu2jbKkCirm2HbGjXdXcWVkxlnfYkuMiEg784l7juqkXBEQ6CBPbOBYhjVWg7KniPh+Vlrpvaznks6IuQ1Pb/FAdM7chmxaOVNuKzqh1Uw75+3jTbqii97+QimfUyee3Jjmg1fjQ6N0VBgtjrr6A5F7VKRQpFRmdKQQM4/BZogVHaEQ5VSC2vdvAQPHkJRvSGD+NWU8K4m7wCspKP1WPl/PR4JFqf5xVsbH2KaeToBxGSRrc7VKsBugDQvS5ame8K+zBwLsVRfxTomz6at1d1AmGhOEJESvnkRauSVVMCYdwkW2G7mDPQtvypSswZ+gOy0O8KZPsXLFW3xrwXiG6beejcyLe/AmD49RUTKb0QgEyPSLJgfbBTNR+4wgPJAHYT5SAVkED3CAyInHlNzU2hDrzkNbqKiXK3+7XAgcX846kxmrRlT1I2qzobRf0dHm4/9Jh7/f40ISyVTfwP+lZAmNTvWQfIqHYB4zKPFzfHX8YaOMDjuAVTXQfSNxO2+JvQd/iirp62bh2CR8ca4O4z19OmzHTKGoRaY/MOeIGaJWItoIB7bkLGdwdHyvH0al+liGnAMkLI44UO92S4Ol1jjgB1zlGIPyqD3N38fdroq2OEO9KGKkDP5Bc/ka7Aj7+3d+pPEjbdPKiIj1WBMFhfFFKjreUOVXYVdpMwW+Ux2KWuQtstHxI1D+ZInHzxxz0Q9cyXAUfsTu+Jdkx/9K6Glfq1D9hZzaJfwVej9z40RTgooCFAULTgoVrVkZL8khCBunZRMg6YYfHVA3Ack7gIxnozjQG8p6Ut32TKv8AjdobAtVGHoCPhX7aIAEscwP/GRkruLua1Uu43Eea5VJaT5vJipLgWyN70TMHLGXaYwtOdKRrdxFGlhLDm9UpmYRrClA82knl5aAap81fckdb7vsuXhlx/Iw5gfIuLyrrdy5zJMVhwTYPbe3g8hI0F9gs/nWU72snzkVkdpoaV1OQ4Dk4Wio3uijKdvZTsLibRZKazCxzQRpRSMZDSK8e/rZBsw3LmjSgn/p5SKy+hStlbAnTpOffoTJIwin6AG+ECqeIH8NJuOXEQYy84zQKT8XItyj419gpgGN+85rCdaEIZFEtj+jUphhwo/p7RegG/JcQaQ90pGw7DW19/GFjTTVjLzMsXeqYj7w4YzA3lTIwZTpEqfNInOOdEVROo1oPjVK4TNSOS3itzTHsAyCzxTjBpbFkbcMUZtKpTH12dIp0ReriSNnuH0UP2bCnvMw0W1tOFoiA+SyhVV8taGNyOOJHUnqlLE2+2h5308NtcWK61pOSLEa2fUqtRoIasyzz6LZQJxfoj02cyLAbkeQQKCqnQvxY4hlt9Pa6xY6YuTlscbMqIKFm2k3W1xU7CkuXnsxhh8NBje5G42kSkYHNau9aPIYC1USp1gK01OyZ3A7nhSbCEqJ4e4ghWQok4/3S4+tEVz95Eq8b+NmdBJtGgRftRLEjrqVEaVp+fEjzWrb8/gRNRHJ/1AJykXNW/DAtFN4nLXckCfX33iYsJww8XxsyWl5Eo5fHms+7isVQIbRqgud7tPOFhfP5E5M95zIeO2LQFbDIOP7ll/+CumPkw/OcZaEiAxxhvhouGGikriq9EMOa3zt8A/mmzZjccmmObzyEWI9fTKIQE8t+E49zKh7BkSnuByUDC7tw/Kmri8hQWr3yeBdADbErg7e4acPWeTi3s0jDNJWrzdlA22gC2toTHpJwVqQnJttArCKvBe4MtMLpWG2fLXllFFcUnmCPERyiWB53Xny+UGU0pYhSY/6XY+9yEH0aFhMJJbZIbZ/DXGgKVJ5tCRUmnqYdR22w6PK1q6Xnxcwk4dkfEUPNvXF2YxGV90o9tIEmGrGVArMy3SxwUYy6iGRB4m360Xly9tm4VAwXBSkiYQuah7yYo/qGnAKkaWKVi0Z04kkKfuOxpsb5XvM3RA0EsP55+L2kijxIetiYW6vF97zulfuBXgk2oJ84zuAJleSMx3KaTTPRll+9vbQiU2hGa+M0ntwO0oMcvtkWvG/q8s5n/I8JoXdRWYgx2hnSvcGH3WleAzbaDkS53L3ZdE4cxiwFqZK/4XJTVLMf3Z6/tLv/4afvw2TvrqSsTy8DmctRPJHLbqm6Z+9Umq+Z/Ms96okHbZEm5T5UG9aJyW07MXrdJV4mi4jtdwff3T8kfQLfk13uakTCLBpfEQH4I4/Pvry+NcO44Hl2qUAX/HjqVLXQWJ+j+6E+4jf/faYB62jjUqzcbXZ8QfkffwM9yeZuRlgyFT7dG1d42R0bqQvE0XViagxAuu7A0tUgSUQ4JnEzfL9sVbUbF6os5Oi6uxPeGd/ojqLDuxsX3+S72vWFD+4ma9H/ftJy1lbvc00qKb43cm0HZVneVAqzmSYty5g1MGITOWIH+WoFQ0yHhII0KQCFsqJhYaZM+tTvG51VCGNwRoeVmc21GZCd7Mt1bz8lqwLWENIHW+/LeK5vZ7KoVZbTf03oV6iEea+HimljtCrMInm8Yctnl9MBj8U04qNL4PmsweURt/bEUENfqLoeax94qj5YqSKb/J2m1mHicmUh+ykCCbkHqFt88ZBviB0t4fu0MkuXveM3PLTYfIvxnGaOYydy5jLm2dr/Hge8rvT1vuO8KfrONumDZVsh+/wuJ8nBrPjE9pGH9OrR+nxKX4f3FMtEIim2HoHhN/Nq0L4poZjRzAeKF2T62Qvlk65SD6O9OAZkZpI1aNzXDnUXJEqZls1ZtI70sD6rLKxdikY9gE9tnkgT6nOIWveI95qYLe54CnOglc9PpSlXq/mDaGypjgYXOb9ny23G2iCfUGeN5vvVOaKErt0RUYN6UcsBC7LRP3k51gRZjyesL9OVotcbocXXmBXI78Pop90PIU7eF4u2Ztn/NLkgEIzpDswBm2kJ3GKvbm5CuUTL8jDjL3IB6bxMy9OD7TR5G/seTCNkbfjAVtDT9P2SDB/GgZwmD3QZJI9twCSavLMdCHy2hhnAQ/1Dnvudeb2wsBjfsyCMEE+EfbC3dFU7O54zpiGQWUJlwPWGDq9MOqTFffMSWCll8zZt5lcn8hfKgCW3jOn4csO4DtOcfm9WKG9CNnFStXB8bdO2SnThbhihA4SKqI53Y17vcr+TLec2PdaPsCy5jbD02tMGaAKtuK0tRStayaUrr/7l7krFRfK3pckF6Sd4y/2i6306/0qLBX8nhr0PKyLu2rupHZfbEm/uoavVNk9XAqQvIumjqUkoi0nrSqurZm5LYFYV/MVxk3r3K5ugvAmvzyodB2t4OfLwc/WA79Q5rBAMUPbyw5YaiFVuCozuUSYl0AL6FC7y+HCmGlVpCSa5+evur3eNoZYI/f0grt+FAZ4J0zM7uHxy3TDCbfxSiBXHOfZhR2l3/e6PuzMvVEeqAubET8Pvxk67JrndmEv8eTWpu1AO3zjYF0/gkZ6I8ckE+V3e2RFYscp7NiTShA6zL9BYcK00/DRFLINABbIWbfefy78ZNn+tBy5zddjyOUuR5qEXBFxgxZypF1YGZ0PiS6bLpvup4zHOsE4hzsC0zll9dVVWUBj+w0748kynEK1ibjNvB1mYxIOI+UGQuVr3k5mfPythGu+nVmbHo0b5VzIfHliJNx1wy1nqnW63Yzo+5bTxEvMftho85JXBjyJi7ZbGWw5qgG1sFW5xopd1+dXAzjeLlGmo+LtmzVF2BpJIXJxvdhXr1IlrSfz1r1buYbYO8kdyxp6Bpyp2WQ1rdT1kmKchQU2+VHd3czlpXqMqsRSk23yenWb10+p0eJ1zwGNSCOzGsIge/ttq6xThH59XPBlJnvCYbKBFMRu7YLtitmqlZWXUgaI9vTIJOt2YGEaAkbhqMjhc2OKcXnYUpzTtqBKsc4WtKSLGJNJKjJwJg27GTMjZ7VVLntHnekmiMktV4Zb6ePv21luGGTGe1P8Xmou44LWGhnNxIhqm+xrxSmv1fK/j52k9qReeBES7ZVnVP/bc8YXjjYIX3xFtzUvneQuEn9KrDcbEnkWFR61rYUNTMdeuKCYlhxikP84oxPF4cFsMBnzYGJ9TyQOzZQJ385uslTswa+47A7biAM3iMeKnDLrhgApcW4W8MmIGoE5G3bK1qivwx2ypeSH0EpuNaC8pAKMfsCVv8oEeBEo9UIrRGghvmOaOLPFrDJSTvGSsokpOaefzaVnGn96slb1tTxLnhlIpiOlsCRC5a8utlEAFa72ERmuQjgVGvgrwvLTWoXqQL/cdSCTiV2i2P4p2HZGNWBoGdeMR5MKxyz3DZZe2wnLkaHsRgEY/CkrM+JlRjXChTN0Wz797RyzaEuDc8W6cBQ6hcXhzQpADT137Q3KqhPeS1XHMcwPJFjoofJidGlzrfon9QUftUR1Yzc1sLlRFi2E3DrIzb1SrhIF9N7VZVoZZmVbZN0PVrnE2n7I/aiblZGh5u2QcgLqELT9UH+fjXrW9sNMIbEpYscFgy+6hddSK3vGrC7cwqBKM29/EMYeczFDSM/oIua5T/Kg0SRvsMX7MXN7wOS70OAw2QsjP6FOO2ypgzjEwgD7gu26nbQaKc+ObdpFKeu817Ppp4eQdGjaGmQ+WBchW6pyFTIaWkHs48Yh7Xve2pHepFFO7VaLUME7cDqeAYONbVL3wPiugfKhCirx9kmfzlBsmmktCAMPR2qmu7Os8QLysTzBlc2IaDCHq8UWLVgmmyyg1/iHcezJ0quz5DdEuskHFAP29dF9PfMlZaw8/iVGN85LAQzvNT+YOVxARsKPHhzMHr5wcA7eiKiTgzn4nZ2Wg/PwSq764sGFQ0O2faWOanw75dnk20xXuq2vgnqo2DXE+mXy4SK1yuTU41nERLWa2zPlZKX0rAI6HpQP72Uud68VOSzTJ5flaR4nmLiQDDpnHZMpmXX7rhcZrLtZvF2irSQ9I+sH8YBHwZj8bfKbFPIv1sizJfHFdsa1jMnSp1pc1hoMLph/3kluMpXx5i49G4MZ+j6Ns5qdDVHMqtZn+9haqAhT0VstcUnwYkUznE2h5xhINi2dSlPWkOtma+GU44GrTAa75BStTu2XU9+Kgj0BujahdF+i5GVa2jrVlmw6BVcFMZLe9HUklI2Kxdf0x17YcXuY60qdyM0oCbw5dRJ3oRa4LSu40ZjgEDGwc9P8LoWtooxXDCdzbmxthujHbfKxtUWn+Nlcgpj+3GpV9wGR/4bA0hvsH9jseWeuXq0tUWurslaei/GhTMbFqgnQGBST1Vov1bm6zjBuuePeKNwgmxvSRJntLY1tTdBYddr7fOKSfZn//gbeOybHWa/uSNbd0upuLVSuUJpKH5r/B+zDWQQGv0YyudVsqxRKObPPsNji2ts7eHhKhy1O4wybTMkxsyB+qvh/LnpkQyyoSNmRNiEhNbO1KZSCJ+loneAcW44jn26QiOy5JQTEfK5BIUeN7PSmu1EsV6LUzmNuBFp02ZqKNSvkYLfb3RDnpooim/ZRHK6qJQjXvJWEryoPpoU1xR+woudm6Wf9AJ9K0SY6oaxRKdGctIHxxcO86JMxgtfZjjQzuhRDMtaRcYWakQ3Q2OLMvpBlRuWCDG9EyTH7bbwehUSWffF3VMKac77qqjsqYz8b0yzuptwXMou6n3IkXhhdxKdz0k4ZuWznuWheDIdoJS03MyXEia5xkiqd9DSv6ojhGO/EZ3gF9nAJx54OqZWG8BqxlcooZJUiqTYDuZNs5a3JG5bZXQzXxLYNjanTR4u8WP7ycvWvUWWdxERU/X7D1F3RKZXIJ9Nn7FjmNgohYYupIbtiwfIp75mhl9YG19048SJkAbYm5eu+OiLF6yyoE+y6DRMFUtm7Pg9YLOmUNQSNkmp2PWCSySjXsXGjzng2Ju1CPQ67ThYhQB97RzKIZM8UCZw+RothGCXsrh9vcC6GfYL5nJ2bzdKTyOcV81J8INe05F4b+odmFl4xyRdlv8pbsnKgq3CW5xjkrQM3Fu3lmq7wJVathAYfMaYLjLwwtkaxXnHAGeq1NqdTdONWAwUEvoZ0NaXutOBkI9AjvbPPc3tel3V6bhyzS10/CSOECJiPf57L4oBEKPR4kWdLbGXsDrBZX8s1UCiIZL0c7rM7ceImw7ik5GWMtPA71wer4b2A3enuj1F2VL/s9hhwt8eAm4wBNxkDLqW4rjPBkRdQljRNrxnAtgCUnq6uvGic0bLZqJ0vKqbGzS4uhbtx90/hclNKKPUuJrU5fl+7r4scsDkH2o/9boLnIuZmc4LX656/u4fQL7yUP1XhB35/2N/wfyZvxsCfzXMvggh3YXq6eDNGlPDc7nT9EI488w6IC8lgoxN5Xm58WHY5xOS+lG1O1NbeONAyxgNtApM3HQLHC2XXgk03fmub7ukzXGf6ahhIhQp/Nhsb3m7osetrwAxeejU3mM1wsB7G2sWo2a/uNsZPRrDhJO62DPHV3h7gvWxvUf76zlt8AACxnc713EvTeWELqqO0S/wEfqdASQZuHP1nml8ob7GRVXe90FTzt5SkknIXUfajj231O3seRoYXIeTcdvn6OAmOKB2rK8XgBYiexW+8l8ZPsgOt4oT3vDfcEcj+V93A69Ek4bzT02xeD6avjlgMDplf99vEy5CfHn0Lk/COljviu1/8b0CCZtz2WosXrw2DZhP+cnp0VocDoGYgfro4amqm1Wq1p9vTJ27xk5otUoMzYzX4Ka3TQ5V67lHlINfDu9nxzZxCc59UNycGN05rn+h5bzDvxwNo9KPMXWLWdnmmB2qZD3PW2DDKbmFv2A82Bm7Q5O9ew3fUH3TOSJbWRBAFKGpTkHQkNgvOFRZTnvCqj3rEuhvt+sEilrxK/dxtnm+1KaQljn1AfBRsFjHt8FOZVBBvbEwTzsr0Z3oKskaevRjmVPUTZuLcBAv+hG86OmJbp/6aaIomXzVM+gfHAVMHgOyzXaBe5ZnDq73wns4b0KbLfwlun/tuYM7LIQytr/HnmVnY47DiKh3/FTua/owMHWWFtlw00ZpcwhkQfXNLoDpmmlfYnz15JToSUe4Kz+P35RXmtvnFi74pPg0vs27zfQumtjV2H7Q7w79759/rtEhttekW7WKLxoVU3ajk9LBbpNtR9pNhITlFceoVic7ZHJl35NNLYyzYThhx88fi9IL/8twCmTigQ45gDzwzbmpoUi+bKChtjkChuOpFHRB72rPn8/NyhxwqIHc2p85PT7fxP2DyKFYbXmfXkHqgzSYZid1tr3eA9LTY+K/f3Whj5tHHjfbSMAmxM4u4OId85yoCgL4Y9pga7WxZ2pm1tTNqnyu0w5GPhTs7scdPOmkEQbc/ctlWppnn+eX57XDH78JugJcPf25F1EsYDHiFgKu8yzBgcc42fTPib4okkx8F7yjfJelrdsMQn+fMo3T3F/W9TF54gmlgYWw3Gm3zIJZ6/i5U2W9g9xSsURmsrQpYo0b1UN19vksahgmfZk1r7I5g9S1VRrRXZslge3+RsH12GlCd/kdksD0yvk7MpRNT6fGQ+eg3wHq/PLqPa1CgmnNGbN7e5xvXGMC3DKRiAY6kcm7sUVD6YY5JhVHMGRtKcBRztUYhgZtGYQGOo7CQwnZnsVRI5lfCfkYz99CGzMtu7JFhfzNygxhj8/gGqOh6u0Dp26P8m6RQJrFxA9n3/mKFADxp7/lm+qy6X1ih7Q4gxnkjucInI4Vv92G5LVX6BgonYwrR5wztZ3PTtZDtP/htIlyofXj0tXVLu2DEPGoVMPuCeQH7nospstNV/BdYJy7N6reZ6AtHlwCt83pNjQ3jNSYpnD/StfeF21FsGIDXzkf+9jDx+B1Dagmp/3VXUYwG1sU4GdhDoEPLVATplgRKIpsR81y9m06hzGAhkEEKlAPkGmE10BKYwUjr6G/H6Oh0mxRbc0d1oL8ZC+hM9cIEuIH+yLQmA2S7xi8B7qDmOshNf2QeRycMo268mBWegJt+zXcezpMwZzVm0PyC36ZN1sLCpdsf20a/gk34gZt4cbN66LxDMPwXjaxCfJ4rgilqC15YpfSR5Siur/FxReFkGt4caOk/jtwB9hXzUi0S6y4o3tSzEpVPN64J1iOvLLabMmAkCWgnBnXL0JxirTATGe6Jxod9aeNdTC2851F+ajPOiDcAZN9jvEUGXfwVz7COGzayOhTEH6Ig/s3x+5Sf+NE8I5EcE6jfp1TqT7jZ4msqf19ma/8MxvglI0aZFvscdk1+KuCRhpn8suecTixbztz5fPyh0yi46KVdMYegNFWF7Yr7TGraboa9xO/5gZxOTCh2JeiNxONGBxrrLbtRvJj+dN70osTv4FUyy27nLSCJMFrcGMWJ16ffscMt3HL+daM/Tg9lln/gMJ5bV6JNLgV0Pv0zTecjc3b7bCJ7nHTY+x46BROSmBlHxspoHdugLw1z+awlK+/HiE1VOd3yT7otR6fnwmIIwsxY0l4sKPUa0JzEwL/k8SFTRqucQ7FMMbRs25zEYcJPPoR3vSgCDsD9xVcC9His9ELMWtrUfl+6C6xlKdqNmVeW381zsLwH+BcjJ1tk2qOD3kwBDp3zUBZvXesRki6w15ENtRa0QwY68G2QUJ1s77wa/m9kV68Og4468uGWJjzm8QISYYS7i1dptoz52prqSBLz9lvFyo3vfv9HOi76auR7Qbc3amISqBonqguC3sQ3SAknP0V+YOY4YfzmcLm0Z7oJ1uv4fbdHGWy9rjnnwSovk97idJfnDMvc2ASbmZvUua+Jt9RqMV3mlNcU4s184r3YK9rig7uvPnBHYVtBKva6sDp/+C3TRG4UPIRBh8RufpM2nzm6gw1kMqdReQ3Ws0AKsYqqRqYJC26kZTrDaNHbX+DHXDFXBawBMD9V4MyiOK4C5YpfzQGrUGwdGGomVZuh4wV7qXSWWTpdKD9YNJldD3K8Fx2b3G6+ODs73dZsr4uzbWl4XZxrm7jzzHQrx50HE9hWz0+jMjZxTdMcD/KBHPrECoFbaA3yxAKdDSRu/boLiOJFbA8xUNoLaNz8gSu4VMG0j4nJPPdi2+wZyjmGEM7hAgPZpud33jq7uKeiq7YXqjpPEuiJBkBhBYvnzk2Xd3vupN3OxmegLUHyyb4PErp6cPfTBxWZp+VFy8A5EIxrEWEI7raIIIgDLnKmKnjt1Z4L/QeUXgs6kYd5aBennfPrphU8XFDRP4fP/X8xS3igrSABAA==")))

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

            clsid = "{D93F00C2-1C95-4D0A-A0A9-609E25B9794C}"
            progid = "EnergoLogic.VisioEditorAddinV35"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV35, Version=0.3.5.0, Culture=neutral, PublicKeyToken=null"
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
            progid = "EnergoLogic.VisioEditorAddinV35"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV35")
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
                "progid": "EnergoLogic.VisioEditorAddinV35",
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
            progid = "EnergoLogic.VisioEditorAddinV35"
            clsid = "{D93F00C2-1C95-4D0A-A0A9-609E25B9794C}"
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

