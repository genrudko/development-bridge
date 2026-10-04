from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.147"
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

            current_progid = "EnergoLogic.VisioEditorAddinV347"
            editor_progid_prefix = "EnergoLogic.VisioEditorAddinV"

            # Keep early known CLSIDs so partially-unregistered historical builds
            # can still be cleaned. Later builds are discovered dynamically.
            known_legacy_clsids = {
                "EnergoLogic.VisioEditorAddinV31": "{F2236480-88B8-42B3-AEC4-0707D59A14FC}",
                "EnergoLogic.VisioEditorAddinV32": "{9B2D0D65-A68C-44D0-A523-612148808DBD}",
                "EnergoLogic.VisioEditorAddinV33": "{54D4E77E-73B0-4D45-94E2-B138DF35D1A3}",
                "EnergoLogic.VisioEditorAddinV34": "{A6E63A2D-0DA5-4E84-9B2B-5B3E6944B5F4}",
                "EnergoLogic.VisioEditorAddinV35": "{D93F00C2-1C95-4D0A-A0A9-609E25B9794C}",
                "EnergoLogic.VisioEditorAddinV36": "{81705A73-9C25-4E72-84A8-F58E4C818AAF}",
                "EnergoLogic.VisioEditorAddinV37": "{3D58EA6C-A51F-41B9-A46D-BF0FB3BA7C5A}",
                "EnergoLogic.VisioEditorAddinV38": "{9974BD0D-D56E-45F5-BB8C-7A21485C6730}",
                "EnergoLogic.VisioEditorAddinV39": "{B42A3C6E-8C1F-44AB-A486-93C6AB3D8F39}",
                "EnergoLogic.VisioEditorAddinV310": "{D1C940D2-5A7E-4B4B-A92A-2D443A0DBA85}",
                "EnergoLogic.VisioEditorAddinV311": "{6D8D560D-1F9F-4CB8-BED7-5FCBB70B1F2C}",
                "EnergoLogic.VisioEditorAddinV312": "{2F8B22F0-0A1B-4E30-B850-09B1F7197D3D}",
                "EnergoLogic.VisioEditorAddinV313": "{1A6AF8E1-2576-4EF3-96EC-676904B6DA57}",
                "EnergoLogic.VisioEditorAddinV314": "{6989E63C-E667-4B14-B85B-210710468940}",
                "EnergoLogic.VisioEditorAddinV315": "{E82068B0-D05D-4646-82B0-0CA923733CAF}",
                "EnergoLogic.VisioEditorAddinV316": "{89DDBB87-8513-5078-9BF3-1DA6D75B2454}",
                "EnergoLogic.VisioEditorAddinV317": "{D0F27C51-9E15-4C2D-A584-170EA8B7F317}",
                "EnergoLogic.VisioEditorAddinV318": "{6BC8DE0D-79B4-4E0D-9E0A-C6E6A7E0F318}",
                "EnergoLogic.VisioEditorAddinV319": "{A2ECDF6D-77BB-4B3A-8B29-3B736850F319}",
                "EnergoLogic.VisioEditorAddinV320": "{08DA44F1-A58D-4E53-8F2F-A1107D57F320}",
                "EnergoLogic.VisioEditorAddinV321": "{9D1B5AC1-0C47-4C18-BB03-7ED263E8F321}",
                "EnergoLogic.VisioEditorAddinV322": "{D65447E9-8176-4EBB-8CC4-4DAA1C3AF322}",
                "EnergoLogic.VisioEditorAddinV323": "{3C74BB1A-284A-414B-BAE0-5D413682F323}",
                "EnergoLogic.VisioEditorAddinV324": "{7F0BF42E-719C-4A53-9926-DFE2B0EEF324}",
                "EnergoLogic.VisioEditorAddinV325": "{8E9D3160-A441-4944-9471-728178F5F325}",
                "EnergoLogic.VisioEditorAddinV326": "{B0DB7395-E237-4F35-BED6-AE59C2C5F326}",
                "EnergoLogic.VisioEditorAddinV327": "{9A7903D3-1371-4AF6-B80A-01F6C039F327}",
                "EnergoLogic.VisioEditorAddinV328": "{8E75F86D-AF28-455B-B20C-62492D9BF328}",
            }

            legacy_progids = set(known_legacy_clsids)

            # Live COMAddIns discovery removes loaded stale Ribbon providers from
            # the current Visio process, not only their registry entries.
            try:
                for index in range(1, int(addins.Count) + 1):
                    item = addins.Item(index)
                    candidate = str(item.ProgId)
                    if (
                        candidate.startswith(editor_progid_prefix)
                        and candidate != current_progid
                    ):
                        legacy_progids.add(candidate)
            except Exception:
                pass

            # Registry discovery makes this future-proof for disconnected builds.
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Visio\Addins",
                    0,
                    winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                ) as key:
                    index = 0
                    while True:
                        try:
                            candidate = winreg.EnumKey(key, index)
                            index += 1
                        except OSError:
                            break
                        if (
                            candidate.startswith(editor_progid_prefix)
                            and candidate != current_progid
                        ):
                            legacy_progids.add(candidate)
            except FileNotFoundError:
                pass

            # Also include orphaned ProgID class registrations left by interrupted
            # historical installs. They do not create a Ribbon by themselves but
            # should not accumulate forever.
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Classes",
                    0,
                    winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                ) as key:
                    index = 0
                    while True:
                        try:
                            candidate = winreg.EnumKey(key, index)
                            index += 1
                        except OSError:
                            break
                        if (
                            candidate.startswith(editor_progid_prefix)
                            and candidate != current_progid
                        ):
                            legacy_progids.add(candidate)
            except FileNotFoundError:
                pass

            def read_progid_clsid(progid):
                if progid in known_legacy_clsids:
                    return known_legacy_clsids[progid]
                try:
                    with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER,
                        "Software\\Classes\\" + progid + "\\CLSID",
                        0,
                        winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                    ) as key:
                        value, _ = winreg.QueryValueEx(key, "")
                        return str(value).strip()
                except (FileNotFoundError, OSError):
                    return ""


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
            for legacy_progid in sorted(legacy_progids):
                legacy_clsid = read_progid_clsid(legacy_progid)
                try:
                    legacy_item = addins.Item(legacy_progid)
                    if bool(legacy_item.Connect):
                        legacy_item.Connect = False
                except Exception:
                    pass

                legacy_keys = [
                    "Software\\Microsoft\\Visio\\Addins\\" + legacy_progid,
                    "Software\\Classes\\" + legacy_progid,
                ]
                if legacy_clsid:
                    legacy_keys.append(
                        "Software\\Classes\\CLSID\\" + legacy_clsid
                    )
                for legacy_key in legacy_keys:
                    delete_tree(winreg.HKEY_CURRENT_USER, legacy_key)
                removed_legacy.append(legacy_progid)

            removed_build_dirs = []
            current_build_dir_name = "energologic_visio_editor_addin_v347"
            for candidate_dir in workspace.glob("energologic_visio_editor_addin_v*"):
                if (
                    not candidate_dir.is_dir()
                    or candidate_dir.name == current_build_dir_name
                ):
                    continue
                try:
                    shutil.rmtree(candidate_dir)
                    removed_build_dirs.append(candidate_dir.name)
                except Exception:
                    # A DLL can remain locked until Visio finishes unloading an old
                    # COM add-in. Registry/Ribbon cleanup is authoritative; the next
                    # install can retry filesystem cleanup.
                    pass

            try:
                stale_bar = app.CommandBars.Item("EnergoLogic")
                stale_bar.Delete()
            except Exception:
                pass
            addins.Update()

            build_dir = workspace / "energologic_visio_editor_addin_v347"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV347.dll"
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

            clsid = "{C44C4B47-8A58-4E17-9D14-661C91EEF347}"
            progid = current_progid
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV347, Version=0.3.47.0, Culture=neutral, PublicKeyToken=null"
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

            addins.Update()
            editor_addins_after = []
            try:
                for index in range(1, int(addins.Count) + 1):
                    item = addins.Item(index)
                    candidate = str(item.ProgId)
                    if candidate.startswith(editor_progid_prefix):
                        editor_addins_after.append({
                            "progid": candidate,
                            "connected": bool(item.Connect),
                        })
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
                "removed_build_dirs": removed_build_dirs,
                "editor_addins_after": editor_addins_after,
                "single_editor_addin": (
                    len(editor_addins_after) == 1
                    and editor_addins_after[0]["progid"] == progid
                    and editor_addins_after[0]["connected"]
                ),
                "migration": "all legacy editor registrations -> v3.47",
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
            progid = "EnergoLogic.VisioEditorAddinV347"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV347")
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
                "start_base_copy_interactive": "ApiStartBaseCopyInteractive",
                "start_base_move_interactive": "ApiStartBaseMoveInteractive",
                "cancel_interactive_mode": "ApiCancelInteractiveMode",
                "interaction_status": "ApiInteractionStatus",
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
                "progid": "EnergoLogic.VisioEditorAddinV347",
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
        # Disconnect and remove every EnergoLogic editor UI registration.
        try:
            import winreg
            prefix = "EnergoLogic.VisioEditorAddinV"
            discovered = set()
            addins = None
            try:
                page_obj = visio._resolve_page(
                    "KRU-35_normal_scheme_v2_energologic_qol_host_v1.vsdm",
                    "MCP-v2",
                )
                addins = page_obj.Application.COMAddIns
                addins.Update()
                for index in range(1, int(addins.Count) + 1):
                    item = addins.Item(index)
                    candidate = str(item.ProgId)
                    if candidate.startswith(prefix):
                        discovered.add(candidate)
            except Exception:
                pass

            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Visio\Addins",
                    0,
                    winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                ) as key:
                    index = 0
                    while True:
                        try:
                            candidate = winreg.EnumKey(key, index)
                            index += 1
                        except OSError:
                            break
                        if candidate.startswith(prefix):
                            discovered.add(candidate)
            except FileNotFoundError:
                pass

            def read_clsid(progid):
                try:
                    with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER,
                        "Software\\Classes\\" + progid + "\\CLSID",
                        0,
                        winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                    ) as key:
                        value, _ = winreg.QueryValueEx(key, "")
                        return str(value).strip()
                except (FileNotFoundError, OSError):
                    return ""

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

            removed = []
            for progid in sorted(discovered):
                try:
                    if addins is not None:
                        item = addins.Item(progid)
                        if bool(item.Connect):
                            item.Connect = False
                except Exception:
                    pass
                clsid = read_clsid(progid)
                targets = [
                    "Software\\Microsoft\\Visio\\Addins\\" + progid,
                    "Software\\Classes\\" + progid,
                ]
                if clsid:
                    targets.append("Software\\Classes\\CLSID\\" + clsid)
                for target in targets:
                    delete_tree(winreg.HKEY_CURRENT_USER, target)
                removed.append(progid)

            return ok({
                "removed": True,
                "hkcu_only": True,
                "removed_progids": removed,
            })
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

