from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.03.89"
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
            build_dir = workspace / "energologic_visio_editor_addin_v23"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV23.dll"
            source_path.write_bytes(gzip.decompress(base64.b64decode("H4sIAAAAAAAC/+19a3MbR5Lgd/2KEiZiAzhBfQAp+SEa8pGiZHPPtHQi5ZFCViiaQJNsC+jGdDckYDmM8CPGnjn57BvvfNiYmAvP3V5s3LeVHxrTtqT5BxvEX/Avucysqu6q7qpGg4/ZpyJsoruqsqqyMrPyVdWj2A922MYkTrzB0pmR8uRcCft9r5v4YRA7b3iBF/ndXI3VyH0Ej7m3b/TDLbfv/42LTXNlb/nBL3Kvbnrbopt8wShI/IHnrAWJF4XDDS966He9OFdr0xsnAGNn1Hejq+Nh5MUxjjhX6+d+0Asfxc61MBqkZVfHiRfE/pbf95OJfLnud6MwDrcT5/r2NvQHaIi8pTNn7rpx7A22+pNL7Eo4eMeHdn2vnkQjr3FPLVwWvzb9BMprVwFvO+Fb4Y7fZdgoZFd7fhJGNXOrd7wIh1+vtZwFZ9FpYbUzgTvw4qHb9ZgCjYBxWGf2zjD45yOeArfPYs/tez3W7QN89kZ/5G260Y6XUCVeFf8NR1t9GBS0Yrx8rbdkKrwZPiq8j5OIEBj0hiHU4eX7Z0qGccXr99eC7dA+iOWguxtGlkGsjGJ7yaYXDXzo0VJjox8mxoIrYRBwyqs8R6X8LT9OXoOCywwpZK0Xsw4LvEfZ+3qjpM06LLcXlbQqx2Y68hs4tnLEbuy6Q2+Oxe2F8NdjtwcDW9Ede9EqzMMNut76IJ0G/b1bZBp6/cbI79VrKxcXr76y8Orq+fbC4vL5C8vtl8+/cu2V1fMXVtsLF1aXW6svL7ZrsgnJg21gh83J0KsDXO2Fkz6txasjty9aZXPmhWxN4SXORstDP4dEQQJQsDoaQnM38d7ythN1YQ1Vbvo7u5Y66+HDEghYWtJ4w0M5iYxkLr/pDV0/Qn6/EXkPfe/RrGrLw2F/YplM2AWMWMaxGz664QaeZRhXx243AdkZe0ldEEVvvD5oSgrpTdYHxobLfX8nuF23l90xl624sXclHE5kb1vjtK+tSfozyd4mEyscXILjwln33HgUeTf8pLtrwa6Pv7dGiagk4A3xwYIcuTHo0qGcq15+ZeFqa2H52vmLq+0LwFUvt84vv7qwer51tf3SyxdXVhdebWVcdSMKd9Z62oblKHvMcq/nB+8sLKb1r6AgSnmtrj8SIy6PkrDIgSY5xi6xtdVNbTteaFbi0GHkPwSWY+HWewjnvjvkTEjahLVSr7cWrAVcUBWr8b5QU2D3t+H/xRqA9YEb9FbciN3fcqOyCiujJAkDdj8Jd3b6Hn8q1r+fb3D1oRck8f0rMJkH9PtNKO17kQQkHouQIs/thUF/wkAl8sbs/g7wOf/J9xn6XU+b4b//UtvY9bzkXaf+bu9c42y2t8T11y+969ym178UxfDcqDW19gTy+pArims7AeyGV4CV2C/1Epji0IelBwrO7x0PQ7/HrgdZz3WxVMvZcjYZKHr3RZX1sOcx5XdTru2yXNomYGKbLUeRO2HdUZyEg0ba6542fJVmAEnLJgri9VSywZryWa+XRBO2B1IOtDaY2m4YJ1pdeuNc58PtsGTXj5fYPoMeu7vQbl+DRb31+5sK8agSBf8ZpfG+DcUgeboZlhGj2RtC6k1vACKQ47QqBvmM/W1WJ35hZ4HURv0++6u/YmfpjQNbsR8PwxhWn/OUc6UPTzBk69Q5KA4ptxAqL5lrAFMaC5SR6qsphtworlxOWuSWj7qAOVhnkScaw2B1+tMrWBeSCCq+NewB09cLC6WNQ2+4kbhRMhoiN/a9OduueDt+sLE7SsCWCiwtCxJJ4hMYy0I/0jYxl5IWTCum4kmuV7IbhY9Isq0FD8Hq7F0fehHVuTrueiR66jVueB0+P3zKDv98+OLw28MfDn+cfjb9ZPrbw+e1HEPhv8hLRlFg2U74uphWSMyYsGVkXQsCJIqgOy6B9M6yzSFmW/i/Dqsr7xrQzFGe9cbA3EDHQpGA1m+DMQkA1H2+ZmISwUPY313R7N5SjrolzSt1HSDMuqjfZOtxCCO6EcY+otAZ0ONmOIQSP0Zz23nHhQ2qyUh5WVKRWY3TQUiwOhoyPhS3l+DPax0aDiAkSKKwj/vOCKw35p8715hBZRkORWPWZTlod/17S0bq3CAEO1d/AQpPXO86m+5OU0Oyw9UKhxNErcl4C+RDN/JjwM71qIdWbKNR6KA4VBN2gH7iguaxZGy6BWrCg2LR/hn7E7Gg3qPgwTOzBlbPD6qhrxCSDFCKeCbdcZA+8hYFgil/5ORUQkzOFXcoBG4JJ+hNYElz1XNrWtZ4I5n0ke+QI+gNvSCOoEcxntL+w7Cf+EN0eOE4Dr8ESfbD4ZPD7w6fTD+cfoqi7QnKOBBtn7KqkxLWA2oigDNjTal6cgWysqpavx5wvFBJo2wQVIOd61i1W7mpW4drk8LaGAp0yK4kUZ/rOVuAXHYFN+n+qrftjvqJTVhrlWAg28Dw3tF1MqWupcNMsRIcx375S1bQq4pcKBUoWLTMpKmjwplbDOxAKGoCv1JLw8HlFU5esoLCazO8FgGXmmssg46JC1GOA6uLBbYVsQunBeT6ON9uLBUVFLsbxgZnBpjMU5MBwHeVxqA4cgytZzRW3TxZa835U9bc4AXKoGSF9XTHrQBJOIqMcIj8ZyyJcCYpSyHdS6WIyDgDWqo8JcHUfvrD3zKQg0axx1U9ISChwhOnVtpdJb9VNgWtOq9Hjq2yLqSHK4NCb+q1ca1CwzuGhpMZDY/iG8s6wdbkYN6M3CDeJvER4f6KYLA9NkQv2KwhzOtWKx0CUdx8Y9BdcgpP6q66UiIu99kptJ2rmHr1yqCn7r0MDg8B1TSlOIsG8Ja6SEM9uOdH3Lg/oq0hi4fuDu6yaFqQIPduwIucWSJCOgy2wz7UJU/CQy/C97AvDLjIwlkhsIa5nzgcRV1PRnAACtZ1KGQRO2uJN0BIa6t17MPRYj0WgAnFshSAb3iJ0m5lguEgGlGTSaBrPfEby9g5BYm5jRIQzOFTRYJN4PROc62uBkhjsvBa5Hmie1ywht7UWVtt0o79phvvbngyJJSfqxRPfAjrg9wAwPK44Qe3aw12XpTraE7LzWAnpWDvzAB7p5bXvLOoF6/Po16E8DQMhtaPF61M6jCny2zcAG0XmxW8XURTUF+gMAWYq0dd8vncvSf7JTmiBdzSGnVTe85ksvW6GwPzac1FhQqNUWmv0hQEnOeCTc1t2h5QnDLFGearzlLEQnZ+8nsGt4eKJrLKcLgSRyCZ1EUnkCkhNW1lSC371q4ETrkFSL/Rb6BCaVjbEkqp5Ya7TU9l7XKeBUQvSCvCELEhCjpyb90KeuEGltRTKcAusxZ7XbP8LrHD34N28efDg+n78PdrYYJNP59+AprI94c/TD9i8PbPUPoE/r6osUtHaf8jPGDr3GTIWOmCMeNbDJAkmswgFpzvanhl0Ku3WwsXDEiW1NSTW0xP2w54QoWTynizV4RQm0Hgvhh0tqZEzV/N58f7+vApYO359KPDH8mpR4rej/hi+hkDjY/jFX5+PX18+C1qhvDfc3j1ucnXl0kn6J2LpnRWKGiy4dsaZ3IGIMwhZCwMz4dR1Qsk1wlaHYXl8V86ajvPS+gFhtcLbNy+b5p35rhrkeMuTxQGn50dDUhtigSxoICj9q5/r9HIqFAIIXiLhnUqTOYBQbII3xnHRhw5B30fgMXyjJMsUjhQ9/T96edAyWDOsOn/IHKm8umHKDsYiZmDjPKFRKH2B0uM3iLHPJl+jEwAL6Ah7wD/e1KrtGJCOwhcZP9VEU+UdANqH6CrPsTNe3i3dQ9VBH03KdRYmtHDpKyH9swe2sYeMlHETZIxQJEzQgsuewTLojYYFHQZuXm4PFsp6FFkNaNcenN9m+urMqWpYZaOKozXWKuiEDz8XxjGgGWDbQKF23MxFmXzQGL4OqWHw4NaiXyH3vgw7YJDkLwyXBNuhUkClckwwO2ihli4VAONGhMSnLe9R5SYgMod937Xa2/X5hKKIJoTDt4LEj+Z1O2yrpkNxdAF+i5kalc9xYEwA2RBk+UVYCrW8sYMsMGY87cn5B2xQ7Yp/5V6SPf+otNWCV+JmAS6/dykfmXUh7ceWmzOlVEUAQLFq6ZRanHnyj+mNPWETT8wiJgnbK+177DDP4CI+QAFEttr77OfPv6C7S3sL2Gbb6HmweE3bG/xUstptfYZyJ5nS7QCuJe/gGbYEIG9EDrPc5D9YoURwgsQiN9KJ455tAVlraB9KeqUYu01FYMOBMC4sVQSA9nGVepXUa1gnTNFkhTNpli0RoVAYt7MT12H/2Hhn7KFr5rdLHwUCD1Os8Z1w/W4xj508q/buj8BU+pLUk9IqSFRcDC3MVUNwumZUynPzdhKZ6kFq14CG1+6MbmmvcPQLO8WKSVRKaPMhpxUjFAbSlWg0t3TPZ2t0/03s28K9ZtT52+4zn28XfPPYgPmYJ+f/KZocWxW3SHBbpy1C1bb+dSw14ztTuxny6e1n83FY1qA6gvNDfEE/RIfgBmm6OtPYClgV8q5RLm35BwUFY2+Jktl3Qs2/TWQyvPp4wyI2OZqTm2pCpqNsS8l8lUWml53k11neSsGmdEAM6btnX8VM/+y1xP5uqqB878VRjngxs5TnO6Lwz/B+w/Z4VfTxzzjgXxASL+A4Wc1i75wfD0ocxH55B8SYmAzHL7lPfT6pWTDFYK3Q8xuRpSTbOMU5BfIpspemtv5/g8o0J/g4h9+r4iNU9ji8vTvn8bGcsICWjCgGUeX2G2QwiBdf/azn3Hx2mR3QA6rb0Cyck6Y/EXFniHqKVZwmIVMqwRSbTJTUTET9IFsje3KYoJeka3J0l+A839L0XruD/+cHR6w6cdCbvI3KO1gJdHBQWbh15TzBKbh9LPph/9O+B9poGI04gMQlSlGXyDxS/zBQ3UtuhzMP5ekQQpEXFT1EOdDglG3spPe4pPyTV56+wBOJkaXutui7imH6Mxu4ErBo1wAac7IUT56lIWN/DkDRugrldEhLlKkA+vzitGhihGispZKeAhGfEyaswWHqpFd6v8+DuXBLOyUp/dQID5T8fz0JwMFtH/RcIzxB+SQCmEHDeLEDLFtg9i2QgS6VWIMvTS8UKL9KG707nF96DP86Mhfb7pxRV96Yz7He9fmdS8upwf7w79IpXEPTW4QHda97+kl9k+/u53TF5vwDnTIhbwOKTft/D7NLRxuin9Z8BJg0T+L/smzC8WDO/bj0/c1H0fHQmJOtwZQOReqbg+/O/xR7ATCK4I4F8sit4ivaFlAFeJG6AHVeQaG5zNGlsSTvHVeiKfOpQJKlG37EZ0/s/JZXJRmUu8np03q5iVITVpGzCCvjWtIiSSXke6kU3dePTQHT9ckvyCMIok/n34uTye8YLcNSqel6p1TUCyr6nDlmRbxEffODa5+8Y2vdDWk87SSBK2mLZ+OYa2sHQmsFyQ2jSkKwsXZMQjHlHU5WmBnuzUEbkXGjXwXzxdYEHK6QlBPDj6+95EknHRBXqZNMlMlvR6WxDbpRpUzPXheAScySri3mETb9Ncg5b7hzkhdxumrN33M0hV+QQJv+tH0V9J3+fTwB5vVnbTLoyAovqqF+xZmAWqXA0rxJ3oEteosTz+VTaFJRXz+o5pioR0lJXQ9Zpih8z4pDOhueiZcs/DimSUeR+nheDBMek1EbG6hGOZL2uk7s7uZYCmKIfEZMJjKyClXiZeNSg7isuz3Mucwn91rnerZLf8P6ZJRstOP6O89fK74e7/Ct9NPAalPhfO3aLWdsEpyBIblzLoRRkm9B3V38BBUGnroe9sg59LHCI8JVc3sxbazA+lYq5QhVJDU/2yYVG0mUEGGnFrVwaZ06/Dzrt5mKOhc699G3vszJOLcGh8lw31AsbCnug+gms73VEu2MmlPWyRnpJiRgsc2jeVgUu+iQdnNBBRBaFSd1xcwnadi8CSAnpMAeprLCpNsRaIqC6PgPoCy7Dk3cbjMemrUCvH6AHH6gY993Q/k2PG9KRd+E6x+L+WkpiS+y2BA991AdYlYa9bLEjViwZE8dBbbkjZiYVeuuxm6swBeo+RkuUhQVWiu0oFyPWOlPFNliyepZPg9x3yL19PHcO68Wusw8h7OPwLYe9rlLhO3m4xIcuQ3MJpzcRPDcdj43BhcEB2cF5sNzt1ZuHi8TNs59FzYkA44gxyQToQBSK48FYJHWOk7Ho+AXUt3DMAuzCfSFPOopNtXySai7IccBxiAI6eR245YzLkClhBsS1w8+fdSBfv4xyZy5t0fC5I2n5tTFKAnaerZJApDKgEDEPFSlZfy+QMAgjbJdrkHPGV/WX9hhs87XVi0EA15cXipR+IHJkPuVDLvZmWmHTEjbVZm2hwZaWVoOG5O1jHyso6Um3UCYfT5crQqJk/tV0o7K99kHTQk/KCb1LMTfkf2VuQzrQ4seh3qOuh/oLdP0ICQxpn05T5JLbXpY4dxG4Sn5FQxqfQ9o0EZO9y38Zd0Vyhn8kl+Dvnx/+tBf/KvyXsLmm97PmWeT1zmk+e1d1RrYV1zbg2b0TjTt2fwunIzsXgjK2i38iwYSK/lfj9Xx2g7KlowX1eZzSH/gtLsCf6Ni5qzrY31nKkgHglShIgooFfbwo0daL0GpTUwwipc0nUWlO5U6AhXp4TdKNu3sPFmNAFEZRcWFwBk17TZAaXIKSo7Xir33lBdsenc0R3L54wuWVJrpMO6pwbQZze7I5vB5tQodVrivLMhcxbozOEu+fuczQf0/g2KulxIgnLoUHP9gMJYX6XWHlZOZwLvhHX8lNLt0mjGLBI1UT8Ifjfo+XhBXQmhGltaqfWhGzFviESa4qxRVRE09MQIlAlO+UHDoSPuVMalEjJhlk4mdBxpKG38Ikq4jXMjfAQAbw8GoOV4Q64fNtGhcY4p5XfU8kUsL7GdeuhxazutedMETCiiyCVfPlPxHktRwVK0NPFeaXoBf5t4kzQ9wN8m3h1ND3fwIbstGt712L496SCjJQNfc6y0eZi1UTmVoOy6M412lc7lNQVCs6HVcrJp2O4tIFdPBmV+Pv+jOAD6TGTDKuf/0C//HJ07igdH0XToRXbpJyd3Vv/pN/+XtUlNadSqDPYy1FaT+7IK6N3K4wFoVanQLlbAzMCW0zLY8VUTe3LzfypOp+Gcf8BXYuOHej/w4D26j3+kUAioitNfFXHy0/u/YxgFppjVM0yig3qfCMgHEq1CMHJTnzTN6W9M90iirNryKIar4UqvJfbfnhd3I19eSTeHe2KvtX9JaC177X1VnsbO3gK84CoxTxQHGuIZ1XSoQPVN4EAlE6W/FzJ+Vt4RSyvPypoWyUhVQlO1/fD3tFfh8mDq5oeqBse1bgUdOsxV3+2HOze9GO9ec4P4Ed1Lt+7FMahSK+GY31imkQcj/V7p7tK7wbtBrhfU2fH14d8J8wGTAbijAkf1ek2/zJFIRRk1FGdj4HfLxc4dL347VAvWgOKc/zYC1BmulqHzwDSfsx1tmggnw52m7KbnuJH+eDwKyV9m0H4oDKCCITK/G0ed68k7azRTVahXKkVatPEioTbylFp+xMjQ1WziP565Wnrq1Skn/tO1H+WdbCcV6D5Jg4gsyy23V/aJjcLNOwPOeBWv3SleI0ucoZLe/I5/mzlZN7r2eVKK6JiaOmurJafjpe02rG61leu1Rutt2MBrMay22bCSVaaowJnzMAUxy/IqhTepBk81yczwcMMOPLrJWJhjP9/1Ipnpmar8lIacqkJmPX5sU+AnpLlTQNx5xaYsqkuCA0o1sLkVemAZUpdL83kln1DNGs8MRjkEs0RPFv4ElMLPS4wOznw3/SjTLWl3hT3zCZqXdKwtr1Y1GdVLdyyo9BH9/0PMJcFmtRPR2BFbON8MWQX/JBbPdkAioBQnqqauyvGN7q438ITQvMRAs8L8tcegVgJXjrpQ0e2fF+c0v+K7sEBBUX3Pb89pP7//Y76fvN6vdcB1p9zQ8RAgO/xSrScjw/lEHz0jfvrYeTfiipLQR/8alrNeo5fNrJtN94FXJ1qmy+A1dBqu5c0lVejJFOomY9uIlNvkpFdxTofjqk9FbjR5jegzG80o8H8x8sSGYa1W5dI22f/MO8dLjqSmCX2WOPBZPly6SNv1g/i/epNcMKMhZkSsrRVxZ32pa0qQoYBAN2vHBollWON0UvYDtn+ZlU4tRtZ348R2g/yRF4/flJ/d+2laOYMU49fm17PBeWO891MM0Rsvlco5sevDqGPCB28mbobGFHNMxUQr92txikucfKFLosCcJZsYN0Ns6AjrJKexV76HCAQ4Rrt/JH32U7pqqiTSi7cwUEp9/ujNZ0JEpePjoozPsUkjPQLFaUTW5FaPEDdrPRvR5bme6K+76/d7N1ykO8D4ygiermSv1t2hifi0FJUkxBCLJFq5Jc0QTCqEy2wncoe7Ftmk1awgn2A4DQ7wrt+7Z0qYqQbjmHpwWcr06ai5mQabheVLdFu7YiZaK9+6AXykolgUO/LLio15Nbd0bUh056EtzWiXq3+vXAmcX886q81VYarq6Wp6ntr3KDq+mv53zChG39pzylxDuxj+LzVL6PR8H9mnmGH+jEGNX+Gr6eNaGR92gaoqkPtG4nYfiL0Hf4om2et8A6rl3BjFuyo69DqPQGR4SM9Y1aLT7xnNwu4IrRLRRzis2xQCnB3f60dRabhNY+cAGYsTDrS711BgpWscADhljkF5npAS6OHxtpS3uEC9LJIyDIEhc/0K4gjH+x/ySJFHyqalqYjVRBNlofBFKkZc/J6SO5J1U5A7s7Pc9g1eUN7p/OkAf29JdtVyyNXTDDI3gJ9fmf6avOPfCzvthzQPdilndnHlRBunwfefph2JigXXf5oeNjNBi0MQLkjLJkDaTe5WcvN95DJxk4DeTr0ns/tuN8qvFoPO7qAJQ08O/+rTQ4xb+AF9YNnUxB0rTd7GXHlrk6PyfN5NVHZy1ZpQhpQ5Ya/RHBtyphNbvcs0sYac3qTMzCJY54HMW05Lr0etz5lKcmdH3vaA/WJM7BWfHCB9V1m5Re3JSkMC7K7b30ZiJOj/mS3ke8/ssoGWcJ25ZWldTkKB5LlBaN6osynb2Y4j4m0eSmv2os0FaSUjmQbgpx8ETAOqeExc8KSF/rKLVWTz87RWwp/YogAtEF+H0xQ9QAmR4pmjpkrzOxRkaPk7siY/kTblN0KFO5h+jOdgFekrg5KKI5FUtj+hUagJ4Wf09luwDfFKFzzGQH1htvWBdkcWvrCxZoqR1zj1np+BD/o2paDeTMnBk+6Sps0qc451RVU66mM+kkV5E9I4LdK3dMcwjcDbxevcVsR5Eo2pTbWyJF69dsb0xWbiPAduH80z9qQQntShwcRgsCFrXWZG6ZXTvFNDH/IL6qR12r4FUWyofkZdrIa+XqVeA8GNefFZdBuIoxG0x2opyHY/ggQCTe1SiJ/xKbs31d62MBCjLI8VYUYNLNJMuZDkciqeDNfYzxE6g8kdPXJGWiWjU1CzA2cyb54aibT5AnpK9gzux5NqE0EpcdztZZDs16T3iidiCK6aKh+PbdKMDrm0QPFNV4LEUW9mKmFWf/4Uo8r+PH76RSRPP00V5aLlLWRgNig8K1buyJPrbzynVM6YePis5CgqKcevzYWPJ6kJIPMn06uxntDOFhcPvB2Z7zmTydMp27B8WrhblvwL5L/sq8o6CxEbIob4bLhjYiZzzbIPOaz5rcM/mK/LjMVNmea8ugOkev6RkaIK9MJC7zRCzdwzEDoumURX3hIs+dB2BX2Z0v8bEpaD2sfVMZBQfKteuxV7kYNTrjWBEcxaoZgF7PsPvQiM+XAtSBYXuPZ5E6dWF8e/9T508A2HZy+t3SrPfzavuuTnYmCWxuJsRpMbbhR72ad/UtRBmT/AGyPeHqE6QJ9Zxc8yJN6OF5UfhW+ycCTkCOqHRBmXlcBvcURV/RKFVMOUBM0RcQqZ8xsbFJFTa8z+4KnhxGBRaibprqhHDpjb74ePvN71RwEeIrRQ4fxxjaPbftqAcor66diAp+/mO7KHTws2pOo8StnEoI4ezdj7h/S+zRf87HtBaAKF/gmL6KuaeGMPFKq23hwuv3Iizl2YpJOxduCoEqVKt7zJ+1+8M+fkwoBVLh369+ip7lTLGkOshcj+aBxW9Giz10u90uwSy72yD/asJJtM+NBoGsdlNP1ScLrmOjtgnjmkp59NP5Phrh9gk3g/S0mnz53hgZ7p54ffTT91GE9elknAwKff8yNwUoVHZv5Q/UzaM54Yja4XxXXTZNNPKKj2Fe5PpBXRJ6jSe2VxvZ3a8fjcyF8mjqqSKGIENnCHlmC5Jb59KhmgfH+slP+Z1+7srJgO9j0+2PfSwWJcVh/re6ZvqGUe5uHdfDsa33sNMKPvMQWqKRP1aEq80Kag71J1RhPeqoJRhSK0xhE/LlApyWE+IhCgybIp1BMLDZgzmwm87exkOZqDNeupCjbSzcTra6nb5VfxktGMLbKvzvPMZK+f3rvTrn6nP7ea0LfwRE0ASo/pptH/+vRxg99JI2P6xato5tdB8yeUS/PI7YSQTv5IeeDY+tj538UEDN8UxDWLDpOQKc9EyQhM6D18ZKJz0C+I3O0ZKXQMiLdNE8WzafIS4zzNEsYuZcz1zdiaP02Fwsm09b4vwsQqzTZpQyWX2Ps8neW5wZv2nLbRZ/TqIDumg0UAXMlvIRTbYh1n+WF5dTb4pkK8QggeqF1R6ujXXGdSpPwDZCfHauLKC1XiyqnmqswStrPmTHZHli+uGxtrV4PRAMhji+enlNocsuUjkq0GcZvLCeIieNXjU1nGD91Ush9kSz7m0qD2QrnfQFHsC/q8JsCaLHdbQJm7dcZNADI8VsjHVe6/xi+5YkJstfP5RjD46YxR3y0cSAPhIYpQEPHKQuQKX5YcQIOOYULFW0sW15U6lVyVdaqCh5vv7wBSb3o73tihl3XZ/eswFdMB3LMDZ2PU7XpxXIIsxEpEVDZw3ojC0TC+u3BPtgMkcW8Zd5WpNSiZe8a9kIBYY/PFas2t0VCF3PZY5sQwd9au1pk8cB7h2VQl/JiSTnkckI4wqvR6NLLX0sG5FzYjKemCrUjN6J6dQXD8qGUFd0ru8qKjTU5UG58AU04qwFCOaxnjmoUcDRqYOQZaSM+YGOpuFIDBn7I6E15nUsEpq51vLUd/M3drWFPy+Ix14eHOE1gc3q0AVFOPk9+mlHzYctLbkOYQACTSRGSC+15Upsg6pbBEZb+6cCVZnOg43gxyPmFXFfYZ9hoOyaewroxSG2CjwnorR4xnrTa542Vixqy1nssFZ76VrOiAQ7su5w5DRV0OSilGGXu2ow9wPqfXl8p3C/HLiOJrhpT28yM3A5VPlYvImzjlNv01mo61KqfLTEePLSeOK59DMgLVPAvWanmNbpnKs1iv2+vJ77EUt3ilUFiRlyskjMcVDxJzrZKrEKB84w9QvxcX6KfJc7RX9tGS8YmLDcvOoXVw5yQ6mN8uViRacZcfZ7Ks3L2d29JkZFWTTnxrSwOqMwFNbIAmcwIa4pBaTUY3ALVKvkVFndy+sxniZQD1cRPPOWMsdTgWfyclR1YUH1qVW4Ziv6epe+J2oTH7T2zhonMhvWFoIl7M+W2heXwLqSFhs2AJLwa3oWTqulZD2LDzZEcc13+ZDsTguDyy11JQj/jik3EDpMOnirJsolaqkxKrWE0VNznbvby39KuID9GewL4NnUlTD9BH1fIXP6b/Zl2qTxklg0HNNFz5aVuZuqCNGQem2xGacYoNuMkIkPMGAX9p7XDdjRMvQhFg61K+HqRePt5mKfXZqwdNUZGUoxs4CPdWyaCsRpf2VSl9YMexs3guinKJDe/nRA2r/Dex7NRnzxOF7SGG/Xo3jBL20I83uOjDwcMiLFxYsKrRQnTw+nzWdR0A3394PZCuoiRXqTGjg6o4VTpCUuiBhC4Mp2ZZDrtibutRY9XauzX54eM1SjWHZ1VAKUuYXXrjuX2vx7p9N47Z1Z6fhBFCBJLGP2f0dZKLHnluLwz6E7lHsfsgP30lbFKoiPy6Eo7Z/Thxk1FcUvNt9DD63VvD1fBRwO73xnPUnVSvuzUH3K054CZzwE3mgEuHUJQLKIcgw4HDshWT9zoyWgobl/GFwoR0fcHwH8nUTvF+L8p3+QBj7vjhh/SWjHf82A9ztvPP/V6CB3EuLOS0pDc9/L4FlLz0aq5k3Q/8wWiw4f+NPI+KP+uLr4C+9VKrVTyPGiX8RBUd+seZa++AYZC0N7qR5+Xmh3VXQkypp2Q40Vp540DP6NveBK43+ajxTrW1YNONH2zR7TiGO76uhYE0g/Bnvbbh7YQeu7UGDP7qtdxkNsPhehgrt4Xppe4WBjci2B0Sd0vGD5S3e3gbygM6NdZ9wCcAEJsZri+82sprRtAcVVOSEfA7A0oKq/Zdn7wzVjbd8UJTy7+l1FBKraDkjM9t7bu7XveBCULOKM63RyQ4onacXuQBL2AbK5bxURqL5AAaRYT3vbfcCSjqN9zA66cfuqGnhbrx6zZiMThkfuNdvWb8CvFPH/9PIIJ63PQancs3R0G9Dn85Pzqr8nOgdF3D+Xaj0Wi2mq1j9/hFxR6pw/ZcHZq/kVw2SbywXZtf+wS6+2J2d2Jy8/T2hRqWx7Dk19DpZ9oNHtZ+eSCKeubTXDB/Fgl0prA/GgQbQzcQn2V5A9/ReDBsJUVaHUEYoQDF6hMgMHm6vtYPH6lkjREY/ksIqly5Qa6shICYgSJa2gsgnrHhqh+lN9JozyiLcOtqAvsgXnZEb+Kp3m418sIpHZhpVWBr8eSFlrj+uTufph/JCyjNq6LcCo+XEzYK11FX6Fy5/PGn9/+hSlck14t9GdcuHcBMuQSyLROeepFh7a75aPRxWhOHYdgF8hzIp1fnWCMwrbll3Wkt+a9dWCLrGQbkCGLmaeaZDyN9WcdtfXMCKu0NL+rCJt1cuJjHy336ogZoPvXzF1utJv6HRsp9+iJG/rW+ejQCBZvkiHS3vP4eqjWd2j/97nZTXPK6PEpCHEwHCWGfy9kiABiLQSJW6OeOpZ8FWz+T5mKhH052LNzejj2eY6vwAN0QxDUxeRSJn0HiN4hMP6Bvcx0cfmMl0atjt5tcJ+DpIQaYsIgxZm8m/E2RWfKz4APlMp1KdfEmii+YZ+mOO6rkzX0F9XataZ4E/zhvbUxXy6ewJmWw7syANanNnqo75jLdME0oWjCtsTuB1bc0mZBk19lga9whal9oAanT/4gNtibG14m5dmKqPR8xH/6WvuD4BNegwDWLRmreQq4xFlmB3zGwigU4ssri3LOgXH5OSYVZXDB2lOAsLlSahQRumoUFOM7Cwgpb3U6pSqd+ifupjZhX3Ngjn/Fm5AYxJljQnpfx9VaB07cm+TdJoU5ikwZy7IPODHXtqKOnbfTUhl9Yoa0uEMZFI7tCkZHDtwaw3JYmAwOHkzlP/Nmm/exCqxKx8Y+CZh+dtW5pLxkpj3oFyn7JvIAD/qHfbBX/Lv1crnriVV04OiguPhBcV8QwHnXN4Fi+fWajgPxHVtMl5B8hqriKYjawLkZk4AiBD18qgilqZl44S6cmmzKurlBzpex4CvSFRpP9PHKHOFbQp+IOsUleYeMjK9GoVbNbLLO8Qsxu5MhLsouqraG7lIwBExqlNtm6O5ben07m+7mIe1WTcaLXbn5lMMTf8KMhKByRrMQlrh+AFP6IEqsPTPfzYvhc3tArjpl8BXP8Lv+JiG/SK3oPlOxsfvlazuSwXB/r1AqRNulxyBlrhKqCaOAeUqngC78pJ6FOnoDWR/3E7/uBROdNz+3hNwbE40YXOuuvuFHcyX4673hRAqY/NF9xuw9AUoVRZ2MSJ96AfscO931J/KvuQEQP/5K5w3hSsP6JKe3mOjVvndB5YD6Wo5/AQaTjd40RjUsmzDgy9q0MbINKaub6y5QF6IMEMbRksakp51tepJrKKj8XFkMwZkdl0lcKBpQCNCedeUmeHrQ6SuMciWnV0Odlyw8JE376Dy8HjUAC8AjO9QB9oVf6YYyjVn5ffQiiZTnaiZlXluXqOVjfuykuY+0w5dHB2IUAhzE2qIu3IPSJSJfYmyiGGjK0lg9JbYE24Oij8ypkHqG4ujYKuukl+G5ppjaPpEmCEY5w3qRujpIVbq3NNaZLqzEacy3yvaDXn9ShWpVYWmFTPfIZeBF2owAuZt4KtxiHy3dW081MXtcfuH085hB7PXPm/Sqvkx0/f8hzU7Wj5rCZuUmVg+a8p0aDqfu7vDYEb8oQ78Ve0RQF7jgt4CGEZgqpOOrC6uAXEzP15ml6/SZXcfjNdhxz1b5ieGpEIVYxbaF1YaGNrE53FHXwImW6chNvw4Q1AOGXVjjbEWdPoV6x1Jj4gNUKtyUbBl7wTUk3umXQhfrDjsnFtZeTvRjy4G7JTvuVVlPxc3UWmtLJ1VlsmqRzu9XISefhEfxYF1uo+B65pQnHw3zYVkWsULGFdi3TVYHCmoyk9ZsuEIoXsV2kQGmb0bz5AzcmqIFpHxPIXHylue5GO36gYexio6lvpwRnf4mBbtP3uw/OdXbTJImtpVmDJw30WBOggGNncbFVPuwLxx22Ho1Fu03KyYEPGnr64I6zhzTBRkn61+DsCcHVQRhCunUQBEnADheqQtbe6LswfiDptaAbgT4MNN1yLq6bVnB/KY3175/5//1kglTYzAAA")))

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

            clsid = "{782E02AF-5D14-4A70-A92D-0E1675BD2901}"
            progid = "EnergoLogic.VisioEditorAddinV23"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV23, Version=0.2.3.0, Culture=neutral, PublicKeyToken=null"
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
            progid = "EnergoLogic.VisioEditorAddinV23"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV23")
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
                "progid": "EnergoLogic.VisioEditorAddinV23",
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
            progid = "EnergoLogic.VisioEditorAddinV23"
            clsid = "{782E02AF-5D14-4A70-A92D-0E1675BD2901}"
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

