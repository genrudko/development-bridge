from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.123"
CONSOLE_SOURCE_B64 = "__CONSOLE_SOURCE_B64__"
TOPOLOGY_HELPER_SOURCE_B64 = "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"


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
                ("EnergoLogic.VisioEditorAddinV315", "{E82068B0-D05D-4646-82B0-0CA923733CAF}"),
                ("EnergoLogic.VisioEditorAddinV316", "{89DDBB87-8513-5078-9BF3-1DA6D75B2454}"),
                ("EnergoLogic.VisioEditorAddinV317", "{D0F27C51-9E15-4C2D-A584-170EA8B7F317}"),
                ("EnergoLogic.VisioEditorAddinV318", "{6BC8DE0D-79B4-4E0D-9E0A-C6E6A7E0F318}"),
                ("EnergoLogic.VisioEditorAddinV319", "{A2ECDF6D-77BB-4B3A-8B29-3B736850F319}"),
                ("EnergoLogic.VisioEditorAddinV320", "{08DA44F1-A58D-4E53-8F2F-A1107D57F320}"),
                ("EnergoLogic.VisioEditorAddinV321", "{9D1B5AC1-0C47-4C18-BB03-7ED263E8F321}"),
                ("EnergoLogic.VisioEditorAddinV322", "{D65447E9-8176-4EBB-8CC4-4DAA1C3AF322}"),
                ("EnergoLogic.VisioEditorAddinV323", "{3C74BB1A-284A-414B-BAE0-5D413682F323}"),
                ("EnergoLogic.VisioEditorAddinV324", "{7F0BF42E-719C-4A53-9926-DFE2B0EEF324}"),
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

            build_dir = workspace / "energologic_visio_editor_addin_v325"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV325.dll"
            helper_source_path = build_dir / "EnergoLogicTopologyRestoreHelper.cs"
            helper_exe_path = build_dir / "EnergoLogic.TopologyRestoreHelper.exe"
            helper_source_path.write_bytes(gzip.decompress(base64.b64decode(TOPOLOGY_HELPER_SOURCE_B64)))
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

            helper_compile_args = [
                str(csc),
                "/nologo",
                "/target:exe",
                "/platform:x64",
                "/optimize+",
                f"/out:{helper_exe_path}",
                f"/reference:{framework / 'Microsoft.CSharp.dll'}",
                str(helper_source_path),
            ]
            helper_compiled = subprocess.run(
                helper_compile_args,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
            if helper_compiled.returncode != 0 or not helper_exe_path.is_file():
                raise RuntimeError(
                    "EnergoLogic topology helper compilation failed: "
                    + (helper_compiled.stdout + "\n" + helper_compiled.stderr)[-6000:]
                )

            clsid = "{8E9D3160-A441-4944-9471-728178F5F325}"
            progid = "EnergoLogic.VisioEditorAddinV325"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV325, Version=0.3.25.0, Culture=neutral, PublicKeyToken=null"
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
                "topology_helper_path": str(helper_exe_path),
                "compiled": True,
                "connected_before": connected_before,
                "connected_after": connected_after,
                "load_behavior": 0,
                "toggle_present": toggle_present,
                "ui": "modeless WinForms panel + Visio CommandBar toggle",
                "tabs": ["Ячейки", "Геометрия", "Проверка"],
                "removed_legacy_versions": removed_legacy,
                "migration": "v3.1-v3.24 -> v3.25",
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
            progid = "EnergoLogic.VisioEditorAddinV325"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV325")
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
                "bind_cell_identity": "ApiBindCellIdentity",
                "capture_replacement_sample": "ApiCaptureReplacementSample",
                "replace_equipment_from_sample": "ApiReplaceEquipmentFromSample",
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
                "progid": "EnergoLogic.VisioEditorAddinV325",
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
            progid = "EnergoLogic.VisioEditorAddinV325"
            clsid = "{8E9D3160-A441-4944-9471-728178F5F325}"
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

