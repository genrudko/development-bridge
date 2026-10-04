from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.143"
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
                ("EnergoLogic.VisioEditorAddinV325", "{8E9D3160-A441-4944-9471-728178F5F325}"),
                ("EnergoLogic.VisioEditorAddinV326", "{B0DB7395-E237-4F35-BED6-AE59C2C5F326}"),
                ("EnergoLogic.VisioEditorAddinV327", "{9A7903D3-1371-4AF6-B80A-01F6C039F327}"),
                ("EnergoLogic.VisioEditorAddinV328", "{8E75F86D-AF28-455B-B20C-62492D9BF328}"),
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

            build_dir = workspace / "energologic_visio_editor_addin_v343"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV343.dll"
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

            clsid = "{8A0C9D8A-956F-4E64-B991-9A88F39AF343}"
            progid = "EnergoLogic.VisioEditorAddinV343"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV343, Version=0.3.43.0, Culture=neutral, PublicKeyToken=null"
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
                "ui": "native RibbonX + drawing context menu + modeless WinForms parameter panel",
                "tabs": ["Ячейки", "Геометрия", "Проверка"],
                "removed_legacy_versions": removed_legacy,
                "migration": "v3.1-v3.42 -> v3.43",
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
            progid = "EnergoLogic.VisioEditorAddinV343"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV343")
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
                "insert_equipment_into_connection_from_sample": "ApiInsertEquipmentIntoConnectionFromSample",
                "repair_glue_preview": "ApiRepairGluePreview",
                "repair_glue_apply": "ApiRepairGlueApply",
                "doctor": "ApiDoctor",
                "visual_diagnostics": "ApiVisualDiagnostics",
                "bus_diagnostics": "ApiBusDiagnostics",
                "extend_bus_right": "ApiExtendBusRight",
                "trim_bus_right": "ApiTrimBusRight",
                "reconnect_begin": "ApiReconnectBegin",
                "reconnect_end": "ApiReconnectEnd",
                "align_x": "ApiAlignX",
                "align_y": "ApiAlignY",
                "measure_pitch": "ApiMeasurePitch",
                "coordinates": "ApiCoordinates",
                "nudge_left": "ApiNudgeLeft",
                "nudge_right": "ApiNudgeRight",
                "nudge_up": "ApiNudgeUp",
                "nudge_down": "ApiNudgeDown",
                "show_panel": "ApiShowPanel",
                "ui_status": "ApiUiStatus",
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
                "progid": "EnergoLogic.VisioEditorAddinV343",
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
            progid = "EnergoLogic.VisioEditorAddinV343"
            clsid = "{8A0C9D8A-956F-4E64-B991-9A88F39AF343}"
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

