from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.131"
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

            build_dir = workspace / "energologic_visio_editor_addin_v332"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV332.dll"
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

            clsid = "{4AD14F1D-A796-4E3E-B386-6E9DB2E9F332}"
            progid = "EnergoLogic.VisioEditorAddinV332"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV332, Version=0.3.32.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.31 -> v3.32",
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
            progid = "EnergoLogic.VisioEditorAddinV332"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV332")
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
                "progid": "EnergoLogic.VisioEditorAddinV332",
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
            progid = "EnergoLogic.VisioEditorAddinV332"
            clsid = "{4AD14F1D-A796-4E3E-B386-6E9DB2E9F332}"
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

