from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.108"
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

            build_dir = workspace / "energologic_visio_editor_addin_v310"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV310.dll"
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

            clsid = "{D1C940D2-5A7E-4B4B-A92A-2D443A0DBA85}"
            progid = "EnergoLogic.VisioEditorAddinV310"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV310, Version=0.3.10.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.9 -> v3.10",
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
            progid = "EnergoLogic.VisioEditorAddinV310"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV310")
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
                "progid": "EnergoLogic.VisioEditorAddinV310",
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
            progid = "EnergoLogic.VisioEditorAddinV310"
            clsid = "{D1C940D2-5A7E-4B4B-A92A-2D443A0DBA85}"
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

