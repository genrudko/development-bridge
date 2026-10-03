from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.102"
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
            build_dir = workspace / "energologic_visio_editor_addin_v36"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV36.dll"
            source_path.write_bytes(gzip.decompress(base64.b64decode("H4sIAAAAAAAC/+19a3Mcx5Hgd/2K5tjhmFkOWgAIUhQgUAsCpIQ7QeQRoEwEyWU0ZhpAWzPdo+4eEmMIEXqsLfvkk86yP2w4vCfv+WJjv5miRIuSSOofbAB/Qb9kM7MeXdVd1d0zAGX7woyQMN1dlfXKzMpXZQ2TINxx1kdJ6vcXnhsqT+5y1Ov5nTSIwsR9xQ/9OOjkSqzE3j14zL19pRdteb3gpx5WzX17LQjfyr265m/zZvIfhmEa9H13NUz9OBqs+/HdoOMnuVIb/l4KMHaGPS++tDeI/STBHudK/TgIu9G9xL0cxX357dJe6odJsBX0gnQkXq4FnThKou3UvbK9De3BNMT+wnPP3fSSxO9v9UbzznLUfyOAej2/mcZDv3Vb/bjEf20EKXxvXIJ524lei3aCjoOVIudSN0ijuGGu9YYfY/ebjWn3jHvOncZiz4Ve308GXsd3FGgEjMF6bv85B/4FOE+h13MS3+v5XafTA/jOK72hv+HFO35KhVhR/DcYbvWgU1DLYd9Xuwumj9eie4X3SRrTBIbdQQRl2PeD5yq6cam746+G25G9I+vRMO74ho4YG5xoFKW9XPZ7vfIeLoWd3Si2NHJxmNi/bPhxP4AWLSXWe5F5WMtRGDL6qL0SyvfXgiR9CT5ccBCPV7uJs+iE/r3sfbNVUmcNkNKPS2qVz6bs+VXsW8XS73oDfwwU7Ebw13du9Pu2T5v2TyswDi/s+Gt9OQz6e7NI2vT6lWHQbTaW55aWZ86tzE2tXJy7PDU3c+7i1MWLM2emZlbOz12anb34wvmZ5YaoQlxrG4h2YzTwmwBXe+HKp9VkZej1eK1szOyjs6pQPCP2pUGQm0SOAvBhZTiA6l7qv+Zvp+rCGopcC3Z2LWXWorslEPBrSeV1H7k5EpL5+zV/4AUxsoOrsX838O9VFVsaDHojy2CiDsyIpR+70b2rXuhbunFpz+ukwOETP21ypOjurfXbAkO6o7W+seJSL9gJbzTt3zbN3y56ib8cDUaita092dbWSP5Ms7fpyAoHl+C4cNZ8LxnG/tUg7exaZjfA31vDlBfi8Ab4YJmc5SiKu8DkUj8xw3x9CHuAHbfocwly0ffrg5KPK9G90IZR4RC5GaEmfw08bcVPYNFIVjFWEzuyzvDKGcX5mRemzy69cGbqxeXZs1Nzl16YnTo/t3R+6vLZ85fmls/PnF9auiwZxdU42lntapKCq2zuS12Y0DfOnJPll5G3SvbR1B+JtywN06jIVEys2Zl3Vlc2NDlotl2L6Qzi4C4ssxNt/QTh3PEGjK+QGGct1O2uhqsh473FYqwtFNGcO9vw/2IJmPW+F3YverFzZ8uLywpcHKZpFDp30mhnp+ezp2L5O/kKl+76YZrcWYbBvEm/X4WvPT8WgPhjEVLse90o7I0ckEX9PefODrAu9pNtnfS7Kavhv39sNF9+KSWp5cLNfzrVbLVvn26dynbNpPny/C33BhSKo3t7F251T7fevuWyR3qCj61GW4NJzVwZMKl9dSeETX8ZOIbztv4Fhj0IAB1a1QPpyP4g5VQO6Z+K/RcdF13+4bH7nN/W70ZB17kSZk03OcotZWjZdkBTuMOLrEVd31F+twWOLgkUbcNEbDtLceyNnM4wSaN+S7a6r3VfxX2YmSUTJbByKvpjSfGsl0vjkbMPGxCI/TC03ShJtbL0xr3CurvopLtBsuAcONBiZxfqHWiwqLVeb0MhApU74j/jRnlgm2LYFDKEaOKMZm9oUq/5fdid2JzWnUE24mDbaRLdO6cAv4a9nvOjHzmn6I0LUlKQDKIEVp/xBne5B0/QZevQGSgGKbcQKk8wlwDmYvyg9FRfTd7lVnHlclwvt3zUBIzBOoo80hg6q+OfXsC6kIRQyfVBF2i+WVgorR96xXXgWOlwgNTY88ese9HfCcL13WHaxW3aXLPAkMR8AmFZ8Ecot+avpKDQiqnzJNYr3QVuSuxsNbzr9YLulYEfU5lLex2fWE+zwTT3wyeHD53Dbw+fHn5x+PXhN0cfHX1w9OvDJ40cQeG/2E+HcWjZFtm6mFaIj5hmy0i6lgkQUwTNMQ6kN5Ztcomzhf9bdJrKuxZUc5VnvTIQN+AxF4ig9uteH/FQlVcaJiLhNITt3eTVbi/ksFvgvFLWBcRs8vJtZy2JoEdXoyTAKXT79LgRDeBLkKC9xn3Dg4227ZAQtqBOZj1KBybhNFHHDODzzAL8eWmRugMTEqZx1MN9ZwiKtROcPt2qwLJsDnllp+PkoN0Mbi8YsXOdJti99BYIbkmz4254O21tkl0mHrkMIRpth9VAOvTiIIHZuUKyd6/VKjRQ7KppdgB/koIEtWCsugVSwpvFTwfP2Z+IBPUWOQ0+V9WxZr5TLX2FEGUAU/gzycB9+chqFBCm/JGhUwkyucvegDPcEkrQq8CS5orn1rSs8no66iHdIUXQG3pBFEGPvD+l7UdRLw0GaDHFfhx+Cpzs68P7h18e3j967+hXyNruI48D1vYrp+6guBaEkgjMmbGkEKGZ1Fhb5G5eCdm80JdWWSeohHN60Sqli03d2l0bF9b6UMBDZzmNe0zO2YLJdZZxk+6t+NvesJfamLVWCDqyDQTvTy6TKWUtDWaCFac45+23nYJcVaRCIUDBomWqWRMFztxiYANcUOPzK6Q07Fxe4GRfLiLz2ogux0Cl5hJLIGPiQpTPgdX6BdsK34XlB1L9p2ZaC0UBxW4hs8GpAJMZ0TIA+K5WHxQbm6F2RWXVApfV1uxyZdUNBroMSvaRzB5thrx1AXJTnhEcAaoFT1j9lIURdsDSacnoBGqqFCbANL77/W8c4IpGJsgEP84uocB9t1HaXC0DYzYErTgrRxbIsiaEKTKDQm+ajb1GjYqbhoqjioqTGDGzRrA2eQI2Yi9MtomZEBIhGKyPFdFcWdWFce2fpV3giDdOH3TbqUKhuk21FInLjasKbucKSvNrGXTNDpvB0s2zZQAUO60ZR6dm3Om2M+1O14BT4GQqoDHgoOHXDGQagczUAsIMxCVgpirh1LAkqyxOKZy3N5e1Ig3PGSzmFW5oak7memM19U0KNZtuEDNzzYTao/g88HZQbkJlkbZm/yq8yCma3H/qgIDTg7JkG7rLBg87fZ9tQjgqBNYyt5OQE1i4SwEKlnXJP5i4q6nfR0irK01sw9UcqxaAzMSqAHzFT5V6F0foe6UetR0BdLXLf+M357QyiTnRByaYwaeCBJvA6Y3mal0KkU+Ij5dj3+fN44K19Kru6kqbZLBXvWR33Rf+1/xYxRbDurDWz3UAdMmrQXij0XKm+Hd9muV3M9hRKdjNCrCbjbwulbmYE+7yR6METbj0OaM+68cXR00Y0wVnrwX6C1bLC4sESg0vkDA5ZeA3AI4KEky6+pZPuuxC3jJK2ArvK8pRD9hM3bwtWqddRvObyxLGETDyFbXXvAS6qVXnBWpURgWvTlXY/nyvs8vtH13AZWWIFaYOnViJOO2UGnQNJjJ1mkiDx+6KOQKep6ITgZQo2rZ9Qzw8sDbF55RZC+g32phUKC1rXZpSqrnubdNTWb2cFQqnF/ggzRAROLJQMoVeD7vROn5pSv7iXHCmnZc1K8G8c/g7kD2/PXx09A78fcDV9aOPjz4AOfWrw6+P3nfg7bfw9T78fdpw5iep/w08YO3cYEix7YDiG1iU1TQeVSALjnclWu53mzPTs3OGSRbY1BWbV1fbaFj0lit3D7MFjaY2g8DsdmiYl0jNXo1n831w+BBm7cnR+4ffkAGY1IBv8MXRRw7oA2xe4eeDow8Pv0C9Af57Aq8+NtmFM74HrTOmJ0eFjCbrvq1yxmcAwhhMxkLwrBt1LYZinaDWJCSP/2Sv7TQvoBcIXv9go/YD07gzI+80GXnzSGGw79qnAbFN4SCWKWBTezO43WplWMiZELxFI4xkJuOAIF6E74x9I4ocA78fgT77mKEsYjhg99E7Rx8DJoOy6xz9L0Jn+n70HvIOh9jMowzzOUeh+o8WHHqLFHP/6OdIBPACKrIG8L/7jVorxuUOlJPv+ivc4SzwBgRKmK7mAMWCwc3p2yh86LtJocRCRQujshZmKluYMbaQsSKmsO4BFDEi1O+zR9A7G/2+aWpA4Et7Pq3V0jZgzit+1PeB4y7veuEOmcaKvBAQ3WNhimGXnPUZrtObK9tMdhaxjC0zP1VhvORM12Sbh/+KTjJYaNhYkB0+4X1RthtEnwcSgw4fNUp2BGiNddPOajiRKN01rUamp5GSghtMA2dhvgHSPYbtuK/79yh8BwVN5ltpNl5vjMVGcbkYeD9Mg3TUtHPHdtYVQxMkz/KYzqacA66SiA9tJy+M02ctYNQAGxTLYHtE8q8dsk0RqdWCQSSXxFBbKudTasZNI7jCjl/4ZmaZdfDaymsFH/2WGN1DYp7foNiAEsJ7wAiR6yFzfEiLWs4/NSKpw0yN3TLMmZTfik4axV3NfZBo5vfS5vKwx5ZmO3KXh3EMKM1ftY3NMvPpn+QA7jtH7xqGed/Znz5wncPfw8jexU3F2Z85cL77+SfO/uzBAtb5Ako+Ovzc2T8zP+1OTx84MOTHC3z6QEKFalgRgT3lcusT2L85zSGEp7CpfSHMtObeFgTuggStiMSKLaCtqPvAxPdaCyU+z22km14d8RgoL1MGSFlo80Vr1QgcyBuBpKvg7/afZ2z/UY0yTnQv5LK4ZqvRzRrHNQVBI39ztp+KzSGouycUZvKk9exPid2SxEs85tHYmnY9CM9O15bEXCE1VUmAK34KMo6UQTyTmGCUV3WbWSnuC+Zn1vKF1Iyi8jHkY5N4HPtJCkJcV6AYTNM19sqAdCp2Volq3rOR07xnIKQx8OOP9y8jSnBBiNHVL5n0M6kgUSGcPeU2H9R5P2xbJY7Dp/PO/tzBycsXFg8CChvtAubWET+c/UoRo55YocYQVMgSXFhYelbCwlh8RvPvf6LZ6e6j4e5dEK0Vyfs+LA5s+TlvBFMuTsOnolWk7Uh+/9Q5+gUgFKBOBoTLEA23sVBnmo2hA0rgQFmcz5qX7rpLWwnwzRZo7TP+1IsYRp29HonXdfX5f1NI7hHT7R/icJ8e/hnev+ccfnb0IQsfIyMpYjTM8OOGRRg7vpCZ2VADMqByhrIRDV7z7/q9UrRh0tbrER55ybM9s19nQkmlCK2OdJKTJf4vcJ4PEJUOv1LY2TMQGvLUFPz/uVX/lWx5nBGZV3feuQH7GuxXP/jBD9iG1XY2YWdT38Cm98mJbWGzuIU5Yu3+ovuLITqHI/cgC+2pE/Bj25wURSlFa+zWnl3lSdE+uzVa+B5Y7K8pqox55j520Az0c75BsTe4rQCqoOGUjBsPKFL3C/j20dF7f2e0EzBaxKiaXtZ3YYeT6/MUaVWsBjzUVwDLwfylWDriM85FXc9XPtQh7tR2Plos54HJ+2jvwMnEHkinQNx5xqEHZveWYRSCmMZ0fOe859LZk23NMiDMtijcnp4diWJwxu2F6oLPLPHBmF53dB8JFzvjhsKC/HFNF3tNN3tZTcXHDj0+JoLbPOz1cFw6Oo6D5jAKO5rrLRQw3fR5AmTn3lbaeqk7RicukmMN360GcWSGOGODOGOFCHirOGq70kdbItNOJtcq/sjOcZ2RFQ5JpMpXvaSmU7I1ngezY3NfVjkBJ3f+FRyAuuMvqOnyGzdK4mS8ewjGKgY8PLHgCR/EhZr7+TFVusnRf2Id7jh63MH3o9nto6WxdKnnnf/87Y2cUteGd6DozWqKHloGuaial04Z2jFL4qcF4yh+Elrd96rDaWcMjm8kPI4OooXGAq1PGBMbjBENO0kcLJu3nrflo3Ejiy+lyFJ3Iw76zVbpmeHV5HWQ267EP94NYJvGRHFNggbcXEBdjkLYBdNsMyHoLjtkbUdo08l2TKNHgbDHs/D/AKlkf+aA7B0a0i+gveOM+sZiYg+6bTZAKZWbZXVNcGmVUoOwFBOxPQWa+gJtuaQKfmiQP+dvxbdC3LP5ZPy3KIA9g1622UxtRJThQIvXL6GeGkdLLDTFC9/12NaaO2rivAwcpGHGJsQkqua+5oc76S4qArWjvT5BSxPOEm6PDjcuPcWfT4H7YRwGzt4H0nqsBrg0qjpywTk3V7cj/6eyOW65/oKUiz9jVxXb9Rfw7hHt5Q+h0Lk5NLQ8Atx7QKVhUKbOnqL8NEB/a5jHgPW9jTlwbt4a7L92AP97/eC28vtW4t55vtk6fWvq9v50+9yZgx82DIf1a068eYYfsQF+C+IJGR8OHyPifnb0PszAA7QFkmTxzyDIoF2Q2Qo/Q5RuZ9vT/TYCeXj0z1Dy3bbzfBsQnJmevqbSfOn+mmNIjuP95pQU9boqASmcmQG3E5OdLeswJ177P4rxEUf6jLyKT4j2vsphPMiPgAfv0//fg9Lvk8sGafXwa+auKiXXhn10PFGFPqK2w2mgkJsit69MOvJ/reQvmn2UjfZdMeD3QTh6xFxT9iCefi7nZf1QnizMnMfdYj4RFj7LLZEqNoqwcyxQnVpEIHbHC7sB5uwx4HaTYFn8KLIiaZvUG/nKXV0xCxh9xfsZpl4QJk0FDsgXHXgdhCbRmVNRypJNSNqR1WtJNhzJEEhd1Mryh7Umj/a0bSe3GrjZsz32tNO41XCAov6M2Aickpmtjn51+CUjM3IrM4mQPMHKxJUeF8r4zzrQOM0e/lXILM9HjPyLDktY6tMIju+f/FQ6md4n1cN2umhs8zYhLOmPXTqxMabt2yDE5wh3zPMuyYTGNwsRMNHebtzIbSCX+oN0RERQSnFKg0NK64Vzh7XsDfFy8lhAnptXsXHnAoqKVgtL1g3R0DV/0CtuhJy2LTOC5gwmbpVurITkLedHP7J2h5krNM4i+sV4UVsS3SQ7WHHUV2M/8eO7/pUhSPnUW0rjLVptSxotwYVTxg63HcYTx8gBVW5vZvogTw3EG7EblDltnj5d1wZ8YPY8CRK3YlFdWRi3fe7ffmAW+5UTKRijo0lAJP6jue3bAkMjS5z5iIphdSwi4jHEovqT8CnOAKqmJcOQcqPMZPcNCEUfsKNfT8YUBicK9/wLRw/mdioc4DzZ6yhscAbDCXHn12IkRMq/b2mTB5AsaMJZVQ8cHP2MS+EPyw4dWKRlTgfP1E4nslqJUL68SMDfd6stDaTsOn36/yJL0eoyBbibNziQMtx8+aUtEMcuuKdbU/D7btRLAVcwgW3z5fmbbvs25oV9ufXDhjlqjxpy14edjp8kzsv8+ZU4Gg6Smw2E3LjN0rY582r3F2rMgo1BCxEsDnZYwC5/EbPtq++H1uxeJEZhisyi4HJvN+j5TpN9fUlCF9aOH/3IWd71Ytje1I2NF7pJtfAcKP3Ic15s1Q9xz8lDnQItxNQLLA27N+tMedNQFBuGP1NTRlFzEPvbwZ7a+Ppwi31rTrdZG2YhNRlus5rYndPOjGFaXjZB5cVbaP1uGNGG9+m0umbwxBqsZYtjOZH4g7cXJM/+/MxxrN24HUlvO8zjbF3L2W/Z3vfg6EMenozcnjsYhNf9M+KZ3Mj3mCxlaFoCZupQ4Nr9fFBswVX1FwwIEguwHcSUkdcqxSdFd7OIKaNYbHkQhiC1CSlQeGnsNdBDQ2ZnxEjTsZc66lUOnq5sfULr85R8jx+LfI1PnRuGECRL0c1nEGZUN6Ln2ehX66qBv3Q1xBmMWl7B8V2a33tIar3wrmcTuKqgF5eQUIIy5grghzIWDX5NyavYyrkb0fUBsCfkVHHgYVJIy5o9W/+lnsPthByYwqZ9gQTkLBzJ7+KXxMbOqXAW3DAuR+epHXiUAvLyo18AW/+cHXrQmbq+ekcfOnKFnxKHBzXhZ0KtAs3JFnSazpTb3JHD1juzOVsFaKYckJw/3uJqF6dQrQpVas7nn1RtUsv/zSKsHUyV8Q75+jGc+zE/AgIvHlsOVVIWP8zmK4KG+QHL2eJZzXRGvjMLyARLCRMiOmvobl1JVUXHblkuuZIkhWWHUNjoXhrDjfgfiJeZbw7TRmS+uc+YXRUm9SE/ZFKM/DthGWwCgmXEug5qFehBPX8HIy6lL6vnbwOfk48xZkSsa/LHutWnobFUKUGoIKn9aphUrBIoR0OGrWpnJd66zOLhb0Qcz7X2beh9UMERxxZxyQ7yLjk9H+p+/HpCboX3Grq0RXxGsBnBeGzDWApHzQ4GJXYyBkUQWrW972iQyHkB4XfeACZd3swXLI5r4T6AvIw7DhnPemgUXFGD4wkOWd/XglD0Hd+b5PeN4aDnS0oSN6xcuOCAPhaqoTi2gnlBayUg5ceLRy/R8deilqCrCRdHMnUMtlWjujUaSHdKc3+CQcw1NX9TczbfHu+Au9VNmXB+xApbnZUJj+hb8zJky+C3Si5D4HmyFIqrdQeCnnShPNnCFsuzkGHXaSewGFoDPEY7rloxiP274/cATSblQcdeJx0S38xv3zTm4haO/bBxOePJIt7AFN9qcezu7NnjhbKOIeXDdvyIsYdHJBGSF51Ex8LRNCz0JXe2P8lFNIIMwgbS5uOopXzVSYhBp9xzFGAAjoxGBr5buAwXEoPb0AB7xds4gaSOObX8D4XtJ58corirnKSKbpkBDFRDloazVZfC8kE6AIIEh5nyEyqSKYjysxVnSeRyo2JvSPhS4Q498ZQyVSlXJky1UpVyZcJUKyedE+QYeUEmchb9DUSoWzZ5C8z6uUJqJvEYO09I/fwgta1T9afgoJb/sFxkcVEpDcJO2swSQk9s+cp7Ch9ZdASUm9GWRW/vU5APV/RlzKTU+o8+dB2mz7I0EnXU83xYBWaZYHay79P0pdzGQdvOgN3/cSXsAX3Rm9h/axjEPqDOdoBixPeSVOzknCKgX82MpzKyKRGp5/I64lMWHp4zntlME5VGboP7gRkjivdogxIlUv/CfrDU6+XKGC0UQjkQRyL4tY1+V3AKBHdxGPS6y/kvFCBkPWPBBAsGVhzDF39BJ/MV8Dmlz1bHqohxVBUg+VE3Os7Y2ELpCyirAV8bzkGrxp2Ap2BOJEPmfgQBuzTYih2czs9fFiYpXv13f8QkGRZgg9w3g1/WgJw0EmBpttxlmITUb/qSsWsHHOScoA+EzQX6QUgmFV6ibvFcRFm1TVGt8uAEzoevTMOQAaxtAPxjMZb5c2S4Oa8iRa5QTC+Fqnwm7RdYWI6Eh/PwI1FPM4dkFeqaKO1CFrlZgsDGmlYsvuvFjj9A5JVz1qorxRtacgiUCY5dgic7LWNDqxSBxflPlUTNJVSh/K6/FadMb70a3QOAN/p9kFH9AZPu22iiO+0o3zfV72fwe9khT7Qh43UsYwazmaaIjtGx5TN9xhuh+FQ4clrazjU6/z1w4W/bwbHhA/xtO5v8YRMfUCbBW93W8F3XOSiJnJO4ZKBrNisz7MxfqzVZcF3+hk0Fd5XGxd0aXL6i1XKzYdgu2yC2l0EZn87/wHOLPzaG5aHFVbNJKvIWvcjuHmbo7jS/++X/c2ZIWGo16nT2ApRWs7VkBdBem58HwFWlwEyxAKZ6mXanz1aRrwgj6W8FO0MMGlvUz4wtOHjUM+vshvem3zzX4qIwWybdgmPWy0t8PpZguf3pg6kLTDbZnzl4Xrm+292fPfhHeRIP9CszhI7EWj47knrEC6IeA5K1jMfjxj0RkkOgh/ycEiLN1/jqqTjER68fsHO535B3FCT+o58Vkeq7d37rYCQMubEfY0A7lPuAQ34k8JLvLMz+RQrD0S/xPmAm9suVLt02cSPY8ikqRUNEY7BU1086cSCuHR3DngdLPO/IJVY3K1rjNtd6WDgsECg77JA/g0kdFWstfyvLrbyjFVeelUUv0qiiZ7TUE5goCODSYaKj91RRnM2wMh1FmKWaiplEVwKvF+2A2o/Xcnphco+uLF3zkwTE3ovRHrvMUsM4hzQ/pZfzt0J2IFRdKzwpAq8P/4UrlhhjxSx/OJiXG/o9v4R9ymDhc9YHdu1o4m76yeuR+mEVkNj9H0OY8eKBEDEnfEynFrWhIqxs2jWFR2YfQLR2svMt4pgHV48r1NTxLaXq6E/eHqoZYbgQrKK2RT8rYnwrj/LlSVwNTVVT0fFMG6Up091yKnq2tgZxZedJBdj8tavIZL/Y8rqqBsEucivJWdBn5F0zb0HxHnPrmcP6bjyb0aIZWM4ZBvJ4odB4Sy7QENr8oL4eX67RGPX5QQvv2qmrrWNWAajSqqkJZR4A2VyVAl4Kb1QPnqqZm+GhaBH6Hpn72XB/vOvHIg2S1PwoR5eUiM3q3J5NjxuRAkeRPu55m86grg92SAriY+t1QD+kNZUmuxJEQyUb6/L8ZdAlsyr+hCmFn/MOZdzE05pSxaANHbbp+/IAZ144bNNBmWyDLB6vbpyI4oazhePNJqtgLMfP1dZwdo6Xz4mqsKkbxXpn1+/7nCvPOyADYuzwhyAcA4kOO1DQ603JdAG06fMpKGpxbsOSffl3f8i3k1f/tAaYlJfrOmZRdg4/VcuJkJd8BKOeruPoQ7csWYdshhSv862qxB3iIEkuWkyPElN3MdtOp9yEqaQAHMfGnY9ryXozDIO3KFreFP4ii9W5FlK0X7VtlCVvkJHKtrN0rLuSKyMz1j2SLT4iIm3tE/Mc1UntwiHQgaHEwLEMaywHZU9F8f2stNR7nZ5HOiPmazy5xQPRWbt32rRyphxadBKsmXXO38M7i3kX/b2FUj4nT1Z5Cc0Hq8aGRmmvMMYcdfUHPJ8qTwtJidbo6CLmRYPNECu6XCHKqQS17y0DBo6BLN+QwPwrysdWEq2BV3lQmq98XqCPOIuS/WOsjI2xTT2dAOM0JGsztYqzG6ANC9LlqZ7wr7MLAuxVD/FOirPZqzVvUCYaE4Q0Qq+eQFqxJVUwJhXCBWcn9ga7Ft6klazBn6A7LQbwZkARdsX7kmvBeIZpvp6NzIt78AYLqpGxNRvxCATI7IsiB9sFM177FCc8kAdhPjIBmQcPMIDIiceU3OTaEOvOQ1uoqJcrf7tcCBxfzjqljVUhqvpxuHoA7ld0hProf9Ih8/eYkEQy1TfwfyFZQqNTPSSf4tGZxw6U+Bm+OvqwUUaHHcCqGui+nnqdN/negz95lex1s3A8E764V4fJrjodtuOsUNQi0++bc9EMUSvhbUQDWxKYUzg6ttcP41J9TCPnEAmLIQ7Uu91SYMk1DtlBWjHGsDzWT/H3MberpC3GUC/wyCqDf9BcvgY7wv7+nR8p/EjZtDQRsR5rolAytkhFxxuq/DLsKmumwHeqA1iLvEU0On4Eyh8tUfza4Rj1mJYIR2EH845+QXb8r7ie9rUM8F/IqV3cX6H2MzdONCXI2EFesOCkkDGelVGWDAK3cVo2AZJu2IEDeR+SuAnJeKKKAb0hrSfVbc+0yi++g8Y2UYWhJ+BTSYAGSBDLgjBIR+Yq3p5S5XU8BGStMinN581EZQmarVGhiJkj5yUaY0uMdGQrd4EG1hLDG5WpWQRrCtB82s2lP6Dap01fcofiXvc9vIbk4jBhx86YvKus3BntyYpDHOyu19tGZCTozzuz+dYzvayvnaXIbLS0LichQLJwNFRv1NGU7WzHYfE2C6U1BNlmgrSikYgG4d499UQE5lDnNGnBv+zCFFF9itaK2xOnyU8/wiQVhFP0AF8IFY+RJwcvGBARBiLDDdcpP+ci3KOjn2NGA4X7ziuJ3LghkUS2P6NSqDHhx/T2C9ANWU4i0h7pIJl+ve99fGEjTTkjLzHsnaqYD3w4xbE3E3IwobvAabPInCNdXpTOMJrPmlL4jFBOi/gtzDGOhuAzxbiBi/ygnEbUplJZJL5eOiP6YjV+UA23j+JHLew5DxPd1oYDKSJATi8s46sNbcQ+SyBJUqeItdlDy/teZqgtVlxTck/y1dDXq9RqwKkxzz6LZgN+6on2WO0cgd2OIIBAVTsXYocXy271tdctdMTIyxOFmVEFCzdTbuu4INlTUrzKYww/GgxucjcaSZUOHe+s9qKJwy9UiZ99KUxPyZ7B7HhCbCIoJYa7/QySoUw+3i877EZw1fMuyZ6Nm9H5tWkQfOVKEDvqVkaUZuXHjzSrbc9jB9t4JP9DKSgXNW/OA7NO4SHYckOeWH/jEcRywsRTtSVn7Ek4fmms+bgvVQARRisvqbpPO1tSPMk7Md0zImO1LwBZDUPN9y2+/BXSHyMfnGOdhIgMcYbYaJhhopK4qvRDBmt87fD35vtGE37VqDm88hFiPX0yiEBPLfhOPdTUPQOiU1wOSgaX9mB5M9cXlyCV227wzgEbYlcH77Azi07s4d7NIgyyVq83RQNtoAtraEx2GcJqmJ6ZbQKwimwZuDLTC6Vhtmy1xZRRXFJ5Ij5EcoFged158vlBlFKWIc0OCF5P/NhF9GhYTCSW2SG2fw1xoMkTgLQEVJp6mHUVtsuiylavl58XMJOHYHxFDzb1xd2IR1e9OPGzRJtyxmSqzdfpAoX1dNRDIg9Tf8ePy5e37URDznBRkCYSuqB4yIs9qmvAKUSWSlq1ZGYnkqScPQpvbpTvMXcj0EgMp6aL20sqxQfdxeJ4vV50z+9euRfiQWoL8o3vAJpcSdY6lNNono2y/OztoRObQjWvjNR7cDtKDXL7ZFrxv8sLR5+y7CeF3UVkOsdoZ0orBx9VpXgM22g5EudyBOporB0GrIWpwn9hcpMUs6adnL/0+79J6G/DpC+vmSwPr8NZi5D8UYuuafp3Xi413zvzTu5VSdptgTYZ86HetI5LaPr183ShepZkI7PcH3109JHwC35NN83JEwiwaXxEB+COPj788uhXrsMCy5XLB75ix1OFroPE/B7dWPcRu5nuMQtaRxuVYuNqO0cfkPfxM9yfRIZogCFS+tOleo3j0bmRvkwUVSeixgis7w0sUQWWQIBnEjfL9sdaUbN5oc5OirKzP2Gd/YnsLDqw9b7+JN9X3RQ/uJmvR/37SctdXbntKFBN8buTaTsyn/OgVJzRmLcqYNTBCK1yzI5y1IoGGQ8JOGhSAQvl+ELDzJn1KVa3OqqQxmAND6szG3IzoTvglmpe6EvWBazBpY633+bx3H5PZl6rrab+G1cv0QhzX42UkkfoZZhE8+jDFstKJoIfisnIxpdB89kDSqPv7YggBz9R9DzWPnbUfDFSJTB5u82sw8RkykN2MgTjcg/XtlnjIF8QuttDd+hkF6t7Smz52TDZF+M4zRzGzmXM5c2zNX48D/ndaet9h/vTVZxt04ZKtsN3WNzPE4PZ8Qlto4/p1aPs+BS7d+6pEghEU2y9ayLo5lUhfFPDscMZD5SuyXX0y7IzLpKPI91/RqTGE/yoHFcMNVekitlWjZn0jiywXlc2Vi+Fwz6gxxYL5CnVOUTNe8RbDew2FzzFWPCKz4ay1OvVvIlU1OQHg8u8/7PldgNFsC/I82bzncxcUWKXrsioIfyIhcBlcSEA+TmWuRmPXQxQJ6tFLrfD8887V+OgD6KfcDxF23heLt2dd9iVziGFZgh3YALaSE/glPPGxgqUT/0wDzPx4wCYxk/9JDvQRpO/vuvDNMb+tg9sDT1NWyPO/GkYwGF2QZNJd70CSKrJ8tlFyGsTnAU81DvsedcdrxeFvhMkThilyCeiXrQzmkq8bd8d0zAoLeFiwApDpxdGfbLiPjsBrPQyO/s2k+sT+Us5wNL77BR82QZ8xykuv38rshchu1ipOjj+1ik6Zbp4l4/QRUJFNKc7eK9X2Z/pNhX7XssGWNbcRnRyjUkDVMFWnLWWoXXNNNT1d/8yd6XkQvq9TGJB2jn+Yr9AS71GsMJSwe7DQc/DGr8T505m98WW1Cty2EqV3fclAYk7b+pYSmLacrKq/HqcmdsCiHU1X3aYaZ3Z1U0Q3mCXFJWuoxX8fDn42XrgF8ocFihmKHvZvpNZSCWuikwuMeYlUAI65O5ysDBmWhUhieb5+WWv19vCEGvknn54N4ijEO+eSZx7ePwy23CiLbx6yOPHeXZgR+n3/W4AO3NvlAfqYdpCNsjIda75Xhf2El9sbcoOtM02DqcbxNBIb+SaZKL8bo+siO84hR17UglChfk3KEyYdho2mkK2AcACMevWe9a5n0zvT8sV23w9hlzucqRJyBXhN3UhR9qBlVH5EO+y6VLrfsZ4rBOMc7jNMZ1RVl9eyQU0ttewMx6d4RSqTcRt5u0wG5NwGCE3ECpf87e18bG3Aq75FmhlehRulHMhs+VJkHDXDLepydbpFjWi71tuEy9L+2GjzUpeGbAkLspuZbDlyAbkwlblGit2XZ1fBeB4u0SZjoq3fNYUYWskhcjF9WJf/UqVtJ7MW/cO5xpi7yR3OSvoGTKmZpPVlFLXS4oxFhba5Ed5RzSTl+oxqhJLjd7k9eo2r59Qo8VrpUMakUJmNYRB5+23rbJOEfr1ccGXmewJh8kGUhC7lYu8K2arVlZeShnA21Mjk6zbgYVpcBiFoyIHz40pxuVhC3FO2YIqxTpb0JIqYkwmqYjAmSzsZsyMnHUsVOUprC09A9HxjY2V55nFA7CE3+ybdYyLAYnjJaOwswuyajRMeiMucOqptt2ChWXYH5Acen3VeWvoD2FC48DfhupbPlqvYGKmvMGgN2JsiOwt5EOsvHRirpaVfX2UAKd0mXktIWkK6AMaDDokVrsr0aW7KHqbGD2vvLEbgzSNZMt+ues93x80Z89aNyub4VS/rtB0xcfkxkXN7dG33/jxLOMZDIPUHGzF76UWTSYLr5Jdk4+otlelVij5aq0QibHzCB83UIJHrfvlqfL/9uIlCqdPeLhERbcVR6rYAAT+lBjY1gXyLEo8alsLG/YFe+GC7aDknIn4x/YiXhwezDatMc+O1ncW49BMlxXY2Y1OxT78SsquM44ZcIMGI8lJWzcESLmNdcDHI2oE5q7bKVuhvg7zmZeSH0Irua6CUsdyMOoZZPZKi8EjUPKFUojQgn/HTH5mo2ZlMKPkJWUTU5JKQU93aBp/dvhZ9rU8kaEZiNaRUlgCofK3WNsogApXC0mG2ypOhAb+irD8pFahOhYzd8/LZJIxL7Z3Aua3UQ0YSlI84+mxwknYPYMx3nYIdmQou14ABn/KyoxYmVENkV+j2/Lpb+eYRVv4BCrWhaHQCSwOa5YDaqjphW9Q4qPoXqbdj2EhIsFCPc3AR5c116qfTIHzUUvgPXZTAZsbZdGIywy4zCIv5CpeQO1dXaalMSvbIquuysolVvZDpnptVAbvmrdDStuoQlD2Q/W9Hpiu7IdaIb4pYsc5gy967lczR4jm+XAyPdbfG0SJ73iYxKVn9OKz9DR50KitGtwlASjAPVT/oMFhuhvFQUqddp2lDuKQE4XYF2zX62TVyL7h2qadl7LOez23S3ZOTIWmrIH2wboIeqnKVdA0tILYx+x3yve8QSq77KSc2q1Gu4ID52ScNwYz6KQenPG9N+VD5VTi75E+rVFslgwvjEIfR2qmu9NO43nkY3mCK5sR3mAOV4stWrBMNFlAr/HPS9nz2VdfZNDgGUEfUJje14f31eSklFT06BcYgDovBDC8sH5/5mABGQk7HbI/e/D8/hl4ww1V+3PwW5+W/bPwSqz64v65A8OFCFIdVfh2xrPJ/ZytdFtdBflQsWvw9dNSFiO1ivzh4xktebWa2zOlzaUMuhw65jKI7vmxLFlxHjqfX7sslfY48d6FfN0565jImq2a4P3YYIDX8XaJtpLsGHMQJgMWqGRyiYpvQsi/UCMVmsAX2zHkMiZLn2pxWWu8Pmf++TgGk6mMNXfp2RjM0D1tnFV9Nngxq1qv97G1UBFJpLZa4jVixYpmOJtCzzCQbFoqlWasIdfN1sIJh2xXmQx2yG9dnX0xp74VBXsCdG1C6b5EydNa2jzRlmw6BVMF8bCD6euIKxsVi6/oj72o4/UwHZk8NK0pCaw5eVh6oRa4TSu40ZjgEDGwc9PsuovNooxXjPhzb2xuROhqb7KxtXmn2PFpgpj93GxV9wGR/wbH0hvOPzizZ925erU2ea3Nylp5LsaGMhkXqyZAY9ySrrVeqnO7oGHcYse9UbgaODekiS4fsDS2OUFj1TcT5BqjS5T52KaycdarOxJ1N5W6mwuVK5TddgDN/wP24TQCg18jkX9stlUKpZzZayy2uPb2Dh6c0HmYkzhmKLKmzCzwn/KIBhM99CgYKlJ26pBLSE29NkW7sDwqrWMcNcxx5JON4xE9t0TpmI+eSOSocYGA6foay601tVPNG4EWXbamYs0KOdjrdtf50baiyKZ85OffagnCNS+OYavK4p1hTfEHrOiZWfpZPwarUrSJjylrVEo0x21gfPEwL/poRvA625FiRhdiiGYdGVeoGdkAjS3O7HFZZlQuyLBGpByz18YbbEhk2eN/RyWsOeerrrpGNAn0sHN+fegel1nkFaIj/sLoIj6Zw5DSyGU7ckfzYjjnLGi5qZXgh+7GyXt13APXsiOGk9YTH7Pm2MMkHHvGqlYWZW3EViojkVWIpMoM5EO5SlsTl2A7dzGiFts2NCYPiC2yYvn75eW/RpV1EnOF9fsNU3d5p2SuJa3P2DHtwhAuYfOpIbtiwfIprgKil9YG17wk9WNkAbYmxeu+PMXG6izIJAOqDRMFUtG7PospLemUNUqQ8p52fWCS6SjXsXEDA1nCLOXOQwa7ZiSgvSMaItmTeQKnT9BiGMWpczdI1hkXwz7BfM7Ozer0xFOuJawUG8g1Jf/auvqhqcMr5mGjBGV5S1YOdBXOsjSQrHXgxry9XNMVvsSqlVDgI8Z0gZEXxtYo1isOWKNea3MqRTduNVBAYGtIt4eqTgtGNhw9smsVfa/nd51Oz0sS51I3SKMYIQLm45/ndBwQCIUeL/Js8a3MuQNsNlDSQRQKIllfjPacO0nqpcOkpOTrGGkRdK4PVqJ7oXOnuzdG2VH9sltjwN0aA246Btx0DLiUhbzOBMd+SInsFL1mANsCUHq2uuIueIeWzUbtbFExe7G+uBTuxtw/hftnKefXu5h36Oh95Uo1csDmHGg/DropHl2Zm80JXq/6wc4uQj/3Yv7gSxAG/WF/PfipuLwEfzbPnAcR7tz0dPHykjhl6ffphigcufYOiAvJYL0T+35ufFj2YoT5lykhIK+tvHGhZYwH2gAmbzqnj3f+roYbXvLmFl2laLhx9nIUCoUKfzYb6/5OhEHRwAxevJwbzEY0WIsS5e5a/au3hfGTMWw4qbclQnyVt/t4dd6bdMVA5002AIDYzuZ67sXpvLAF1VHaJX4CvzOgJAM3Dv+UpYDKW2xE1R0/MtX8DeURpfRSlKDqY1v9zq6PwftFCDm3Xb4+ToLLSyfy1jd4AaJn8RvrpfGT6ECrOOE9/zVvBLL/VS/0ezRJOO/0NJvXg+mryxeDQWY3Mjfxvuqnh9/CJLyjpPf47uf/G5CgmbT91uKFa8Ow2YS/jB7dlSELVCdvcnNqptVqtafb08du8ZOaLVKDM2M1+Cmt00OZHfBR5SDx3IA2vpkTaO6T6ub44MZp7RM1NRGmZnkAjX6kXfdmbZcdlKCW2TBnjQ2j7Bb1hv1wfeCFTfbuFXxH/UHnjGBpTQRRgCI3BUFHfLNgXGEx4wmXA9Qj1rx4JwgXseRV6udO82yrTSEtSRIA4qNgs4iZoZ+KvI94qWaWE1hkqFOzxDXy7MUwp7KfMBNnJljwJ2zTURHbOvXXeFM0+bJh0j8YDpg6AGSvd4F6lWcOl3vRPZU3oE2X/eLcPvfdwJwvRjC0vsKfZ2Zhj8OKK3RCm+9o6jMydJQV2mLReGtiCWdA9M0tgeyYaV5hf/bFrfVIRLlbVo/eF7fM2+YX72Kn+DS8b7zN9i2Y2tbYfVCudf/unX+v0yK11aaLzostGhdSdqOS08NukW1H+ifDQjKKYtTLc9E7c2TeEU8vjrFg21HMzB+L0wvBS3MLZOKADrmcPbDkxZmhSb5soqC0MQKF4qofd0Dsac+ezc/LHXKogNzZnDo7Pd3G/4DJo1hteK2vIfVAmU0yEntbfm8f6Wmx8Z+/vdHG5LCPG+2lYRphZxZxcQ7YzlUEAH0x7DE12tm0tDNra2fUPlNohyGfE21vJz476aQQBF3QyWRbcRMAuwKAXeB39C7sBng/9OdWRL2EwYBXCLhMjQ0D5kehszcj9qZIMvlRsI6yXZK+6hsG/zxnHqW3t6juZeJOGszUC2O70WibB7HUC3agyl4DuydhjcpgbVbAGjWqh+rtsV3SMEz4NGtaY28Eq2+pMqK9UieDrb1FwvbZaUB1+h+RwdbI+Do1l05NpcdD5sNfA+v98vA+rkGBas4YsXlrj21cYwDfNJCKBTiSypmxR0EZohkmFUYxZ2woxVHM1RqFAG4ahQU4jsJCCludxVIhmd3a+xnN3EMbMl/0Ep8M+xuxFyYYm8c2QEnXWwVK3xrl36SFMqmNG4i+9xcrBOBJe88202fV/cIKbXUAMc4ayRU+GSl8qw/LbanSN1A4GVOIPmdoP5ubroVs/8EufGFC7cPDr61b2jkj5lGrgNnnzAvY9z3MYp6t4r/AOjFpVr1wRl04uqdpjdVrKmwYb5rJ4PwBsPfd4gU2NgxYCdAWvDVMfXYNlFxC6n/dVeSjgXUxTgb2EOjQMhVhtiWBkujM8Hmu3k2nUGawEMggA8oAMo2wGmgJzHCkdPQ3Y3R0uk2KrbmjKtBfjwV0pnphQtxAXzCtyQDZrvFLiDuouQ5y0xfM4+hEUdxNFnXhCbjp12znYTwJ04pjktMv2IXnZC0s3Iv+sW30y9hEEHqpnzSrh846BMM/b2QV/PNcEUxRW/CjKqWPLEdJfY2PKQrH0/DmQEv/cewNsK+Yv2CRWHdB8aaelah8qnGNsx5xq7TdlAEjSUE7MahbhuYka4WZ0LgnGh/2hI13MbPwnkX5qe0wRrwOIPu+w1p0oIu/ZEnwccNGVoeC+EMUxL85ep9SSD+ad0gkxxz39ynb/RNmtviayt8XCfU/gzF+6RCjzIp9DrsmOxXwSMFMdh93TicWLWvXch996DYKLnphV8whKE1VYbtiPpOatpthLw16QSimE3O+XQl7I/643oHGehe9OFnMfrpv+HEadPC2n4te500giSheZHku6HfCU2WI+VeN/jg9lPz/geuw9McCbXJZuvMZumk6H5kvINDvGsBJh73voVswIfGZcUWsjNKxdfrSMJfXLVl5P0Ziqsroln1SbTkqPRcWgxOmZkk7X1DqFaA5iYF9yeODVkapnEMxrRhatm1O4ihlJx+iu34cAwdg/uIrIXo8lnsRJpZtKr8pNcpSvJM4flkKPt/F8j7gX4KcbNFRHl30ZnJw6JyHsngxXo+QdMF5FdlQa0E5ZKAC3wIJ1dV759fwfyO7ujwMO/LIh1eak5rFCwiE4e4uVqXZMqbUa8ojSY6/1ypWbnz3uz/QcdHLceCH3d6oiXm6apyoLgh6E1/yxZ38FPmByf248ZvBZdKe6bJevxP0vR4lGfa75pwHK6xMdtHWXZbWTbtUCzYzL61zpRZrqdVyVJlT3CSJlyfy93yvaPMP3p78wByFbQmp2OvC6vz+N44icqPgwQ06JHazy87ZzNE1eSCTuY3Km8qeBVLwVZQ1tCYsuJGV6QzjRX9vgR1zxVwVsAbA/GSBU4v8uAqUK341B6xCsTVgqFo2PUPHC/ZS4SyzdLpQfrBoMrvu53gvOjaZ3Xxxdna6rdheF2fbwvC6ONc2ceeZ6VaOOw8msK2enUZlbOKapjke5AM51InlAjfXGsSJBTobSNz6VQ8QxY+dXcRAYS+gcbMHpuBSBdM+xifzzPm22TOUcwwhnIMFB2SbXtB58/Tiroyu2lqo6jxJoMcaAIUVLJ45M13e7bnjdluPz0BbguCT/QAkdPng7WUPMjJPSV2nwdnnjGsRYXDutoggiAMuMqbKee3Vngf9B5ReDTuxj6mCF6fds2umFTxYkNE/B8/9F+aQwwa6IwEA")))

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

            clsid = "{81705A73-9C25-4E72-84A8-F58E4C818AAF}"
            progid = "EnergoLogic.VisioEditorAddinV36"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV36, Version=0.3.6.0, Culture=neutral, PublicKeyToken=null"
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
            progid = "EnergoLogic.VisioEditorAddinV36"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV36")
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
                "progid": "EnergoLogic.VisioEditorAddinV36",
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
            progid = "EnergoLogic.VisioEditorAddinV36"
            clsid = "{81705A73-9C25-4E72-84A8-F58E4C818AAF}"
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

