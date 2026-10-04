from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.125"
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

            build_dir = workspace / "energologic_visio_editor_addin_v327"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV327.dll"
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

            clsid = "{9A7903D3-1371-4AF6-B80A-01F6C039F327}"
            progid = "EnergoLogic.VisioEditorAddinV327"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV327, Version=0.3.27.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.26 -> v3.27",
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
            progid = "EnergoLogic.VisioEditorAddinV327"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV327")
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
                "progid": "EnergoLogic.VisioEditorAddinV327",
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
            progid = "EnergoLogic.VisioEditorAddinV327"
            clsid = "{9A7903D3-1371-4AF6-B80A-01F6C039F327}"
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

