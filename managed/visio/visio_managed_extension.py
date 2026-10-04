from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.138"
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

            build_dir = workspace / "energologic_visio_editor_addin_v338"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV338.dll"
            helper_source_path = build_dir / "EnergoLogicTopologyRestoreHelper.cs"
            helper_exe_path = build_dir / "EnergoLogic.TopologyRestoreHelper.exe"
            helper_source_path.write_bytes(gzip.decompress(base64.b64decode(TOPOLOGY_HELPER_SOURCE_B64)))
            source_path.write_bytes(gzip.decompress(base64.b64decode("H4sIAAAAAAAC/+y9/W8cx5Uo+vPTX9Gau0hmouGQlGVvLinSS5Gyo11L4hWlWISsNZozTbLXw+lJd49EhiZgW5uva699492Huwg2Xy8Piws8PKzsWLEsSzJw/4AH8l/wX/LOOfXRVdVV1T1DSnE2MWCb0111qrrq1KnzfUZZPNgK1vayPNqZPzVSfnWWk34/6uZxMsg6r0aDKI27RouVNLwLP82ncbg1SLI87mbGm0tXjQev9pONsB//MMRRjHevxYMfGI+uRZt8RuaL0SCPd6LOpUEepclwLUrvxN3IHP56tJtbHgHYrVE/TC/uDtMoy/B7jVavx4NecjfrvJKkO/Ldxd08GmTxRtyP8z3x8HLcTZMs2cw7Vzc3YQqwiGk0f+rUrTDLop2N/t5csJzsfD+Gfv2omaejqHVbfbnE/7oe5/C+cRFWfSt5LdmKuwF2SoKLvThP0oa91/ejFKffbMx0Xui88N3ODLY7NQh3omwYdqNAAUfQGLBT+6cC+CfGtRuE/SCLwn7UC7p9GCB4tT+KrofpVpRTI9YU/xmONvowK+gVsPeXevO2l9eSu6XnWZ7SCg56wwTasPcHpyqmcbG3FV0abCbuiawlo7QbWSZiHXCir/DOcjnq9y8nd6K1PMwj+zSxCX4E/eGZx/Uo3YlhAMt8egn8PwpWdp1v9kpvXouz/Ly6iIvBJf4J+DRYCAbRXUurZqvGZ1+Lhn1Ar51okANyD/sRnlDPGtCCFn3c+0WL1YPJNRqub725s+N6tW55hUPDOQciEvUuw5mJ0uVkZEEIWglovGi0vtTL1LXCFmKJ/KstwNRa7fJKrI26QM+y1TTajHeVBalER/+BWRp0t5PUgfMXRpn7jQc/6ST2E/spW04GA0bCaxMG67YgXR1jM6hP5Rb6V1POfBXnVkGJtsNhNAZFnAybxXmH7wgH3ejyjvwM+v+t8lVDj18dxb1mY/nc0vLsSyvnplYunHtl6tzsSxemLlyYfWFqduW75y6ePXvhr787u9wQXYhYbMKBvb43jJoAV3vQkb8uZSujsM97Fd/MXgaXlAuI3T1Lw9hYRI4C8GJlNITuQEVeizZzdWMtTa7FW9uONkiQ3RDwrafzWoQMBx4k+3sgY2Gc4iGGo3knju5WNVsaDvt7jo9JurAi9newjbCuCmdlbwYHs7IN8S09aOn57OtpvONvcS3qsvNwIdqKBxVt4Dw7lnc7ubsaDiLH6t6I8RYZOT8k7ObAZmVR3uQnobd7eactjkVv7/KOteNSP94a3Gy63607VjfMouVkuCdG29iVY23syT/z4mm+54SDeHdcOJejMBul0Wqcd7cdKBXj3xujnDfi8Ib4w7E4y0mS9oCy55Fj2a+M4LpyHyh67UEcen9j6Hm5ktx1ItRgRHc2nkf+GAj5SpTBppEMYV9vYN8ZKwHcBjDrduDL4TCH1VQYk7UQmRnnicZmF38wiofY9pU02fG1vzTIojSXzYFgJsWFUtX56jBKQ8FUuY4DZ72iVTjd8Oh6Mkz6yZbjY4WkoF98/gtj9sJfn11ZPjs79eLyzItT5158YXbqu//1r5emll584YUXX7iw8soLL3xXXhirabJ1qadJMB1F5ljqwRy/r3ZYxktW3iNN/SddMkujPCnfLrY7OpgLLq1c1wS0s2377QOPr8UbG8lAa21e7Gl8Bw5EkGz8A0J/Mxyya4cEUWejXu/SALadruZyMzYDlCiDNzfhv+UWsBk7IVDqMA3e3AhTX4MLozxPBsGbebK11Y/Yr3L7N80OF+8AKmZvLsPHvEV/fw/e9qNUAOI//VMDGp+DFH3BNsM0CnvJoL/HWC1z+MWiM/3W+LJSY421s8Kv/X3FwPwBjCxh4z9yFvVB2qbHUevGpeDNlP4qN9lIkr6czWWgb4QxfUTphWAz7GcW1OHHWO11MU2T1BSUzEWSmJntDbpr8C9fb/bc9gFsdtSek5XqWVHr68lb0cAxH60hiYnYMIZVrGp8GUSgcIuaq5qRw98fPj167/Dp4acdD4Qh+wDgskZIga+EO1HFBHmPVRgSW99wNGfoqor+i7Iv/SS8HmnivtqVZBPR4RUUqhjXCdTF2dGYoks8VLu4pXQJRmniHFkgUVq0vRxmQKcr51rqUWMLlD7sBmUqHiEgOnrjm3JXYEejGLj95C50myn3gisLF1GuhrhBvxf14f4Vb2vuiOi82g8Hq2G+XQ/VRK9rUTbq555+9IVGp+W9bp9wbcbfHvYcLvhVVB86WkuKcS3ainaDN7dAcGF/MoJBfzc1ivk3jebL53NSXS3e+vvTzVb79pnW6YLFyZovz73RuQmN0uTu7uIbvTOtt9/osJ/0C162Gm0NJg1zdcg00JdAqkmjZWCdg7f1N4jNMRDMVvWHdOV88LxWftLfl+cvJi6m/FfHnrMp1N9J4l5wdVAM3eRHbqngOtoB0P03eZPLSS8KlL/b4owuCQ6kDQuxGSylabgXdEdZnuy05Kj72vRV1gZWZsnG6LB2KneDLcVvvV2e7gX7IIkNwh34tG2QS7W29KRzlU13Ici342w+OAhgxO429DuwwOL343WF04Gby9dJ+61/Lv7DAS4Xl6l6E8oPdlzRyCb7W9uuZsZzq7/Y7JsXd7sRoQhscKti4jW5Bt+cot3Oq1GO8qgcuNnq8GvWNd0DF8qCtFkcsCZiaPGEkPRatANXJMPRuhhZvYHxZtDUON/gNCPSwbe+ZXCy4k2rBIRWSAXSIRYvmFpwMsOuTTRRELj7oIkEOCZqC/87bzK+HdJC43zVl4I5ZW+h45kzVTjBzogB/VZ8W/kaAzi8dJ8e2wGk5S6YfrmkqiTQWYlQFK04mAIYij/qnp2mJ51LGaDPMMmASjIRqcN/1wS7oU1uo9as2FzMO15BDoFIniYcCa0tcE7WFyY+9KMwNelQGS98rS64hmKiiHcaNUhKHRKnbIZ+X8htKd0NhthsXBA0Y9g85/aZ15LlE/UbTm/gJG10ZWU3hj3gKpol0qXNQ+8IzFaaj4ZCOTNWX1Ktrm2P8h5qxOw9SyyPWE+4uh0UVdhyKyiqtk5iv/Jt4NeIYbo0uBP2455UTRUXSINZqg+fHD4IDr8Cseyzw0eHXx59ePSTo58fPmlYLtc0ykfpwKFXcV8+/ItptaxsgWMBxBLBcIzH0QcrRP4s2MD/LARN5VkLunWU33pnOBWAx5yth95CxlHkVesh4ZQBx7vFuyFdtl4vStsOIGaTt28Hl7MEZrSaZDEuYWeHfoJ4AG/iDP0TOt8PgZVvE9eCVPDUmPRLu8pm6SpbYKQV2ac06Y9zVxVryDsHqJDQoOHlZMXONVrgzsUfjIAyNbud6+FWW1vkDtOvdRhCNNoB64HnMEzjDFbnKqm5+60yL7BfzR3ARAF/spIKbt7adQPkkLfKr3x3bZmpWXCxLubEmuakWvoOIcoApvDfpFrdkT9ZjxLC+H8ydPIgUweV64zgek6C3gW21Ghu7Kmv81q+18dzhyeCntADOhH0k8/HO36S9PN4iB5COI/DXwMle3R4//Dzw/tH7x19gKTtPtI4IG0fBHU/imvXrYJDmcMAMltbAdm8OmDrQm9avkkwXvCMn7Odng7+LoqGQPGjoB9thd29IIcVQdIDeB8Gg2QwdYd/TRp1ga8HOjYM8+1OcB26gOC7E/ZNiMM06Y3gJr9xKYizgGlHbwZnAs5LBDvATHRKHJOyagYj4roNtLUonYdgOU/7TAIhBecyMgv9lWgzHPVz16WhNbKzRFZrpmWKiur/4gAtePin87YqWGROAYK33w5KHHKZKghOFpCoGLCJIraBHOL21a0QZVaIX2ogMC4TA3LjkrDBsY28tOL6BD7C3zTOv7y70w/uMOPTQqMx25lpNIJo0E1QMQUPblx/Zeq7jcbLi6fOd/kgAXQZZPBuO8+Hc9PTWXc72gmzzo50tesmO9MJudtNn52ZeWl6ZnaadR7FAD0ZvJaEPeh/dcDmiT8bjUWY4XnGCi/SZM/n4Ua2yOeNP4IYe8Ef6uFuBP1wI+rDC/3pW9EeEAt8/BqDzeFspcloyCBtpUPWB3VPCqDD/zj6CZCRL5C6qH2h9wbDV+q+kQ8uvlb4I6gAPj56H5gsoESHD4k0HX0kIB7doxVYIpFcWQMNjpz7WqMx7R9f88lQp/ALoI5fwfDvoBqeU8ivf/w/7KObUOQEXqs/ATIxV8/g44oZCDByCtcqpyAcStTBf334AAZ+cPgY/v/u0Xt8H5wLUICoMVbpS12DfewejMNQRjs/TahZgarSYK2O/6vDTw6fHr1zdA+QjtYarsGHhw+qcJcb2JmhW4X3PwECygmPEQ67W58efgKfiJftg6Mf2z/LAFexkNy0YQ4LSygGtY8i+1XAZyYG/VDi3tyH9eHf9Glw9O7hp0cfHX7uGkwAGXubFD21OoXfwjo+gE16SHwKfudHweHD4Oin9KSS2BReSwpQ9jDgT+0rJntVborqRKQNwl8E4o11IL133cEuDnrWodhz30DUomIY6V6lbsRvgB69i8sOSM1JNO3B0T33sVUAVQzJvbWMI0okQjCrYjj7UBJAxUDcvUwd6F8A7v3D3wM6PWW0CG8xMdz79uF0L7UJ0P3VKNmJQG5WJ/LP8LVPiSS+R4v8URV2My8w4xrlt8cTuEFx2W7aP0B0na4xwrp/hHXPCOuVI5CzVmbegkCb+aHHzXdsguLnZQ6DXDgbBP+6+NpqGmVRrg3za8QuIGcP+ADy+lzVl902aXLyetG8QX8LUwZSefj74MUAtvGx+/JU+0/XG6x0hVpG+9g3Wvn+9A13Y1gx1s99Y2HvmgOhq1zFUP/sG4r1rxyMnAfPzagj/S889YLRfHD4KDg3QyPaR5MAdESbRvwa+67bjrpvmbiIRwqZohosdOFKq51MWLXPgaO5j+I8nRy4Kj+zETf7F5YcdNVDsVLN1pLvrzKhNZRyokA+t/Gw/F0FaJJIdfZR6i2+fuff4U0W/zCCF3203jv2j8OQX3TVR7XPT4PQxIWqaSFVnZ8Wwtb5aSHaLTZqqN4Loa1Z+FOl/A+nHVsaOUTLaqXBKg6bbd/IMCiENAbNV0aD7nkm5C4GIa2Ka0RFqOeStyrbz49p0+SCdUp+IACLjW0zTJMiYKmLynfkGDBugXmPNFnn1glbnWm8tSjnrqiNr3/xm6ARnPGbkltj25IVvBPbLrXE7P9o/1A1Lk4ziinxeuBZUKDZChYWAzUOoHIoPXBhgtEkABpwanaMIZnn9bHHrDGkjKuYYDDsW/vbihCN44xUYyBNopxkMLcLeeXYvM8ko/pc0SvHZSLnJMPW9miv8+1cYpzw80Vv0slyc0SNUbUIlolGLuRCckdsNjZIFB1jcAyNOZmhQVisMbCUKicZ1QwdqhyNC5aTjKWHIFWOZEQ+TTCgGTtVOSQPI5pgKOrZbOw2ag6yfoxB9moMosb8TEL21JChysEK8W0yFCyCvqZe7My0g5nOTN1BJ75F1FHHHfTG8LgjzuCIL9YfkQKoTmLMqVqDcuFuIqbDiE87V2tdy8GQEwxtiais5rJYhOYkH8pjO3WnC5sHi+aH+sd2YOF2WYsTS4fPszGuZKOEDkW7sP0spoT8XpTRHG4fsod0IBNPCt++Wv6ZHo856VZTmoEyv3bppdX3ZjUZjoaWtpr7hMWJcxRpD42PEts/ROjBgj0Ei/ALG4idwg0825hHM/ydOLtx6erGP4AYx1O46AsCX7+s+iPqiUi+fudfAlOJ0A4aTEfQDrjAVEhmbWYrNz6iPIbfjAkjKEZLMUw9gU16qFRMwGZCVCdBWkKYiGE9rJxMSbaqvSR2U59tToWVr3I6qkxUdya6mQTG04wilUM6+dW6WzOGfg4mV9bGVc7Qdh+UJuei3aUJn7Ioc7rM56hte5eHW2ujzc14V3/LFHFc+6O/Is8VEjdeRd2b023F9H3Z8LiJKQ7cmreYjdh53cfGpXjHe11FLzdMH7Suzftrw+l2xre2g2ouuVHWzhO5nfG+F+Re4iUkf1jbmm5k+nVWO8x3W7ialZa0F6HPVx5N6jvld6Ws4Usl/nErPg/smyx827ZtTm2mmz15zzLkr3C1x5YcpJ0eFElj2Ikuclc4TiYt3xCvSKd7W+EebLSrDpmg2Bd6xnu5Yx64dxZ3qUV9dZiXj/wybNUopTxFneVRmmIYKXtUPpANxiAv7M8czAcKQ7uwPwsPiC1Y2D8Lf74CDO9G2H3rOvMsXNiOe71osP/CQaMMVKj0xVe/HDT6SdiLeo1gLmgMkvxN/rNdM1IKAMTih4RRPCmD0TYBenP3R+rLZm7pxJf1UnYFJn01fX07zqM1zMbWLEVQ2KOSYKCG9QWMKleX+i8ggSpBdVFGh+pdYdxOwNKBTPtpFQ1b3IAAo5ht6cWFlCJaX0nhK6wN8ErEi7fZquGrWM4iBNjP8b2kZLdIf+5MQy44FWCKZEQFAFUZXtm5NLzCzHk7qwxx0VvLb+Trbkl0VEBRVLB4H0mesh5AnhLJCo5rdGvAExK2sjEin5Kvm4XtKyDYsi75gJkqxAJSKTGTD4ypZi3AlHI3+cDoGtQCiJHcyb9JepYndY9cuu96ACkllBccyQd+lC5IlWkL5GAbX//bP2uyaqDljfiqcOlHkaLT8A5X3OjFvJUMVf4drZGqSt1mpTlrR7msfEOIpFYFlELLXN1x3dJxr6LjJOmwlBMBvSmR3vU0HGSb5JtOtAPBYH/siImvqqYwbiYt7xQ4vRlnDnoWLoUw69m5vLTLn6ZLIWlGQ5nIywddU88XsPREXz4ASsYvO45OzQqdeDUcC00rAI0BB1OI2YGQ6nq2FhCWaswDZqoSTo2cZCqZUxqbmcu8iF5KYaagcTm9mRcdnEZqBTfcudAq7nSnJVq73t2p03zga1uci7Hqp13zDVzKv+bgjPsJyJ7NIr9SyxXp2sgw7w7j15U0SGeQo88xdZLyiqVSolc7zJtGeVlK1eClA44EcSpNcOWQ8/JQIplcAYhnoG7M+0RknXPGsNJenEZeL6sKy4fUjLMsUWjoIHkhWi3ls5CJmLvwB7SlVBV32NEkxBA5mJrDsgOTGCejbEQiFy5AwbYdSv6adS7l0Q5CurTSxDE6WtZcB8BcS/4MANGnquh3YQ8T69KM2oEAeqnH/8Z3gBnFIhqyGCwwg08NCTaB0wc1ejHZTrx8JY0iPjxuWEvv2rm00qaAs++F2fZaJJLrmt8qGCA2hcs7xgTQlhAPbjZawRR/ry+zfG8Hu+cFu14Bdr1hBrIWOboynl4cDWq04DKhMAYTR+mFveYuqpJ3W53rCXYzBVhLXmgOU8/Fzcmv+pQvupyCAZlhKzyvaEczYCt167YYnXggLfmebGH9AuEQyXqzXF5ad96gRmeMrq3TFZizKERXRQo+7wEuK59YYXHUDysdTvdJjXsWVaO6TKQJxOmKNQKip6ITgZQo2na9Qzw8cA7F15SFastcaSqUlrMvLSn1XAs36Zevn2EKxeUFOkgrRAccSSgJfzcGvWQN3zQlfQkWgxlUTyky1VxQbUSDp19RcNenh09JdzZ+/y/hB/Y2Ff0JmeN3duLcqUytQBb83pVkeafXnJ05e86yyAKbeuLy6mkXDSsV0ZG3h92OTUtbQODpf04vFEjNHo2XcIO5wD85unf4JWXfIPn2S3xw9GEAgi5bV/jzU2lo5VFhtqQcBd2D0RnRk1+FhKaYvqtzQWcAwhhExnHg2TTq2hjEPkGvSY48zwJadeYF9NKB11+4TvuB7btLyaIMpLAk13AvA2KbQkEcS8CW9lZ8u9UqsJATIXiKEeeSmIwDgmgRPrPOjU7kGPj98PBzEbCJGP4VBaF+REGoj4KjfyJ0pvcsGWhAZOZhgfnvKNGqD+cDeoon5v7Rj1loJGYRZQM8oPjIWjvG+Q6U4u5EKzyfoMAbYChhuZpDZAuGt2ZuI/Oh3yalFvMVI+z5RpitHGHWOkJBipg6ZRegiC9C7VPxcw8wemfHtjTA8OX9iPZqaRMwR0TpLW+Hgy3S15dpISB6yGpQDHqUi7HAdXpydZPxzqJQRctOT1UY54OZmmTz8JeYoQg2Gi4WJIdP+FyU6wbR51OJQYcPG54bAUZj03STGn5IlOnadqPQIhQFUHAV5lDuw1zcnSvRXcrJjYwmMzA1G1caY5FR3C5Na+Cmju1iKpYhiJ8VWlu5BlwkES/agcmM02utGogFNkiW8eYe8b9uyC5BpNYIFpZcHobaXDlfUjtuWsGVbvzSOzvJrIPXTlor6OhXROgeEPH8MqBg1HsUNYtUj0L5aVP99FM7JHWIqXValjWT/Js9tabVWj2OcZpWguwCSt4NDM0vf+b9YH/moBMc/hv3vnoa7M8eoMNVQNZr6CPCLfdfmJvpzMwcUAzkPF++T8ktiWUBeEJAieGC+5ufOYTwFC61z4T9wT7bEsNd4qAVlljRBbQVcR+I+K7XN3ITz02/DnsMJ68QBkhYaPNNqxPmZSqBpP3yL/qfZ6z/UZUyQXJ3wHlxTVejqzWOqwqCQf7kdD8mjsik7kHGU9XjoulvLF7ODKlwOctn2qzwJmTt8gqWuhJ/2du1vMBP7+21LemNa15ixtafMnytTlpNUMOztUJRUA+CT1WwJTjUY6kMJE2qYP6qGNmVKAdWTbJSoY3bsbLduurPe4QFDbcrKwTzjxy/k80vLVr5nj7Jm0UfrkJ7hd5GRodTE0mcGnL9jMucDwzBgBKcfnL0PuDY04CcCEgDc/RTav+0pEmuFpDGTHwNpzCNshx4/J440LAf19gjJEHCgEPD0eZy9TCSrZPApWfEjXFeUl3+iXmxCv5WZI5AtcH7bSfTdvh0Ltg/d3DyLJrDCIP8Wru0u+MF8+d89y3Ohc6MA8DIDaNBJtIjL4ufkbjxskLmsVY+2ef3pE3dNbH04jqPhpABe0SHkjKT3cdjCRv5gW1P+V3BdEaPeMqgn1BKm0fspPNUXXjOUV56F1tipRk9y5Do8hRr0ChICMw8ZkWwfoy2xGegGWUwQViUsmeO0iloeyfSKNhxT2t6qkLCqsWTq16BFYw457SXnhWnPRZF0ry+PtaU3PdR6/0uyKUKCedLbZjymGSO+1JWKbYDyW08lUmuCiCcAW90GrVcxMuOG99sqUdICsKEp8TvqYKEMOGpGZejVORbLmqiVJv4fCypk4JJ4ZpEgZoqLofu5rTbe1sM01JiENFMIJ/PV2R3lr0Ywi0Gs62TJJgfk3JB5iAs8y5S6wkYTBTsydE/YugdkcN7Rx8CmUVCqPDcbC3nnISNL9bfAqPaxCisdrEyZfs4pbJvWrJvm1yTuJiEKtRYt4WFYPZU2WdetnolTtEQf8riPV9Tp1qWG8I+FhbaE94yVh742Ois4h/Pc+7U7I2B6G0nELbC7veuDOrKia5rlSovoCcEqGb29LEFVEOcxHSgj4jH+EqwB8oB0o7PM7A7j4kuikhRW4nfFRr8kxjcvq/8rIbdfCS0V5MTYMchYMDF57QnQ8sT0aczQvtLC8NJVS8AcZho8RnHpxIphX5BRsZppEJxzzmS1RB5fOltElW7PaBvTInPOP/O736Z83K/dRxEXPg/IF/+uXJ4v8QyI3MoLlo4OEX5DvJjp+Eceq5q6MnHtK+JjQ11t7zUq8/pK0oYEM+qVPj1RAS3h/DxBYbC8yQmtxOOUdeT4WvRnajv5VGRYMSSiz+9MClXhZltvyQzlshEffRjFCI+F0mjkWtCP5pP6Ig/RINaIHK7ojroKUvBaqBDiZ+QloQqH5Ws7Bsg+u7Y628W0aOyAY3SYY4d7oBQXEPRxVV0pN4a/o6vEa3gE5K9SU7Wj8h9ktqP3hPzpAQTD+H2Jf+low9g0QtXMOiDIChu55GRKDwQYT6wWx81HIzkgCUzUd3qyDGujEdu5h9htOrVYuPDLScDELPygrdk39phhXvc9LMVvIwBoHVLtI097fp7abvnnpKS64GWtQOw/jEcHL6XqITXjlBpW6yVZFnv+YqGPC8Nfpa7aY26sfYuZr3YMTk6VDEySw+L5gcg19M94IiKFwzzQFISoXM+INGg5wPBwuXs3oZ8fJEzB6hik6DxB7UrIFWvKhtJCdFmX4a3KU5w3sc1pmy9FWjVAy7IEV5mI+BI7Ml8zW/QtvkVVMlIlxHyoIIXS0VYopNfYPvgfG18nLvhTGd25lRtHrBCG1xVQXT8Y1LvqHgYVaGloX6rabIZY0aD0hgezUvVrFvBt7413pwXgxmLCuEZ8L1c1/v06B/RhZFU01JDAzwlYyDRpqEUdOh4eMaqpWiPfQbKXKVNc+L/DG4Z0y4H5I/nS9f1Z4y5hmvlK/K/I34Z7+9HeMV/xjgwheXqNDwK31/psDVO7XOlxMgD5NRR4KKrmdS1KH2pCFlLfeuLY/PVcrLcd8fjsn5L+ZB+QhfzfQtXqnFbU+YecGXgH6ABa/+//5/Kiiz/+0snI3t8HfU3iv0/aX4fqWrS75EmkzH1Pkcgt0BAMIyPNzWlpvaFwRyL0eU6o9azMOV9pqwuLN8XukTNV9ilgmsHRz8havEJbIwW1P8YhQzdtstQWNjJNIOe5rZ4+LBRqY72WVC43sW2N8x3ipMMxrqhR72iqSn62TYV3mk8ryK+WLe16MYLGEr/fWtz7kAFzW8aLlR+jyvosG7tsG7VkW6HmbiahPOD5e7/XtGqgMlZZNvdbm1v4YeLOZMmGL90pjPjbbPubwPD3qxsYYWBx86yGlUypTp3Y9HZc5sMoH6MrdO6oxP/OqMLPnV3WLd2KI1gMIXFei0NtijDVWnBBP6IBnjeLqKRJytGoneNlnWl6V09kV2ZRiG2r9AU+VgdHD270RQjdljJhUs3dFEeSWMah4UwP2+JHxFivfJtzILgZe+LFXs97uXbvhUTDWwrRu8cK0bvaq+YGMXYfDGA/8NFZ8eHVwXRxhP6OFrWi038ddwL7s3Hb2se8iv89+ZPxN6klJ8jDstWVo+uK02JcnTvGRigBOOhcKfOyBRM2Qb0tfx+ejq4QmFCAXEsHX7fsQC8OMO0gvEG8glRfy+4cvU6VZft8TyAwNwNgmRgA8oCF87OzL5wphNcHQRYxTT4/vWVqZ1wABvbC4gnTOMucOc9ltE2iHFHtqPeqB9lQWiDCrMJ96BzLxrC10SD7h58/d0UmB8YIMxhQdN0NMyh9yAYDVJojdGeAtlsECMhODfPnjuHWvZWEKLrHX4bHBRAihBZWfj4bj8KCw+toItFjTo2kFhMt5cmw2mYWpzCzDBXDcuKiCsKW53QKqYRyCEpzE+u1QyV423bgEKfZIArn5O/GZrKu2JXEeowjTZhm5DChFhlFccBuWc0HCYprIF7i3hp16xTFA9mcWOwmL0o2Ii2YxghxEIzGBUDe7Q5wrMaYLLJ8vcTXo+yiCGVhk1OkzFSL3uXb30rWGOfkJXfNmurwZQTgqYzdiFooMoiXhsEEYd1m6/6QtDgK6WCatSJQIxgHcYIBzVInNs4ajgkC5pe5ZBcXiOSYVYAia0rQ0zndHD2xc65NmMo2Y/qBVPPBXrVwfptxH0QdWotG66FNk+XFD5unCppP9RgbHUU0hM2XMGQFEmm8R1wi71wVp0nRVb4uQzHLa0C4VIBlw/c5gWbk4ECx+dVAEThFbhBZ6dWVPJMNBCz6BBxiAZwRUYR3SrCcRsJELzz0ldMENgOBgmWDE/xMkEZZRrljk6wRPRyCKSQ2yB2QiCwYYoE2HoNxJtA7HBvxE3Uh2kBP0IX0t1t+E8Ml0BGqp2AEoQOunSdMbMufJWVcl8Gkgb70o9/GNG3svPz7QxoH9Dv4lu6RSIuIJDoiyHvBRtY5hPMvEeBjhOTMQ3Hsc2n3QbyimxkCGekC/MDcHDpIEnPovRO1OtYD4JNMrOIWqa4paGCT0bzd2S5wGvSsDXiMHUAXPhpFwKSg3o4O68rndfH6EziUFuIS+N1XJcd11t1Cb0mz+CVprD1+gBcNpngWiuJN6gDH/XDGxZhXRH/qLXiPTfT+S/KP40KqkUut2nYa9TydeGcEfCAwcYom8pFxByzozcxjQIcMzqxa9sRXNCzMy+1gAoMkGZsWIkLO59ANoCgxMD77AUbe8wAlwSbabKDbEsyyqeSzalhmnQj4IqWr14GTi6GJZtz80RMSZ0xVyHi7b86usfz1T8+eh8VX+h++VlAJlRSdjU65BzMGTu5L7YxeNTR3W20owAfB3wakCigTNQ57PWm0JuL51luIzlL2SugZ9ZlICEKOUfGCCZIBGEhZLIuQrgOrX7ECw4G21EfrkMEa2Xf72AYdxxl00A68YL+YcSof1f4/0k+eGMEFH2U5UTa4WKAJUhsELtpFBKbDnOE/WeTpk3KuileZHYqV8n6+HOJbBSRmMeI9bQGznsMh8WZ9rpudqpti8r8K2BpYfN1zZFGxP5z+aTyaj+LL7MQIPJMtMoZdbGKMWVcfpDlayxk3xrcY1bq9I91LDcP+VM4eMDTH5HB4wmRL0ZzFa26ypcrm00O4Q68Oai75sBVbXeWNrLmq5Y7VcYOo0zRQrtuZzZ4+23riFWA1gWgdQ7oGILB4a8Li4NmUdJS2lB8isoRc9pu1wzZszapujsvd8AVcy5ezbs6ou+UVPw9ryU6vE8YqS4SZ9bHXSTDq/hVt4zTOgFf4+MtgZqwA0OZivwRhlN6nfQm0e4Q6B+lLbswivs9xYXzIn/lJt/MUKXqW7nZiidBOVWDmBb2XTEVppEtp1W0ToGHKzfjHsaSxKSaZTral7n4PAdP7dvQWaGokK4tIITeizgVAdzRrEjvWHqvLCd3b+Z5Y4GpYllVebiUp6GdhisdSEdAH2u/7WTeIF9Mx82dHaYBuGl/vy7er9vfX9R2j0fjjOHGrPdnGeYMjPB35Op+0cfeeG3URVZ9NY02Y0yeUMOrZxLPniKO+VcuNX5h7BbxxNzZBx18ggtMrTWH4cyNqiAcm6lesxC34DA0G0VsATMtw8nQWrmHsftaejhLNns7P2Ur3VMZvADYTXn22JE+mDx6gdsA4GRt9CMREF+cOD4cP5vP1Ye+dnLqPwtvovpOKdUOgBaWz+sAeH4hmDlRH5fflQIHntR1n4bFJof3r5DX4Rw2qjnQboHyODlMCt84ze/OHXIu3JmO/ol8ZtCBnutGNRc85C10F7yCZt13clidaqeZ/6TOYYbXY5V72JOje6QNF7kFjj6wuod1JQ2o9BIrmnr0EQo4W3UmVStbtFW0uW+/HbgbOTS39ZbxYzU2hGnC8NT8d5aTgZ+ZjzBzBvwXUy6ggKSv4NGH8KNQgjeqoodNPr/4mOfnF6e5wKk4NK4TXGMC57QKdNCRz3B6OFES+csiVCfghPIdIn0szge1upZ0nPPlY2YmeDn6EJDCOGeVFMqM1rgu/C9LARe2MzJ/yh20UROSxV8N90ObDA+rgAOpwD3Obe+9LKzkTUZyYQHWYoHpHoE77A/spnjIU6R8wBPtFNcH7NmPRLoBuBePflS9Nc/M4YfuAzXx5tJgrxn18A4C2RT+32FrzE+CenBOdLl/UY6S+8JMQAPr+wh25UM6CaQU+Ixu4t+zbDUaU3b0PpwS2Da6yh/jedKS23yhHTcWM0fXE+WiZMwfwKlxq/NKS7pDoobVdqdEteO6p+O6o2OkOiZq3WzOiUWndWcn10iUqJCGm+Lf6U48SAPwZuvWZsWorzGl1QLTs639IMVCX8F3cLwzCA3+2vNSZw7gfHC2M3Mi1695oEkR9fDop3RWH9ORpZCP9zDykhVfLhOJhgNFRixtYTBdWgLrOo1YMsO6zdHKHaWIEU2Oi2doz1roSOJwzWV91mWfddZnXfY5rnvfx3Jdqtz7PjUYwmfk2McCXEjv5/fHEcspXHLEUjm9chgdFdCfmReNgmpf8pteWh+sWl5MZsGnZXWqES/reNTYdcgqWyygeThnpYmDbz7WTUK3CdvFKUtgdJmVpvTDnxYJNMkc/Zh4Jxe6Hj6uncjZFdY5YWzpWKGe2KNPdrlxgjuL/THDNSks04H6xjinF7y6hmex56uqakAI9mXTkmKhw8PvYRLum5Qd2TdLUkR3Vm9/EQMjhkE5F+4ohjKAdSeA9UoAWmyD0t0V3WB2Xnd0rh7ZcvW7LXCryd2mMuEpbf3awdmWQ+FT7ryud17HznWsNXADZ7n4gp0Y7uGwdxkNA7PmzSrOg/aZ5+HkvHgcm9jvJEIjn0pcCDGujwAZGdNCaRP/wBTreFlI9oTlU3QZALVpnsFLH7iu4gMXS7zHMzi5NY0RkxokmHjhNEg84cEFPKnmfXkvYMkLTSKhCkIFlzKnLK/Ynv2ZOfL3YmlX205VZDEvXfOI+VxVCJ3g8JeU3Ydkx09IunyAExYjl0VQtA8/LAQj0qag5hk1qRjh916n4V8rFSX8LU3ccGduqk0gp6cLn3m+pmFOnqcwrVEa9oWlGx07QyzRiyEOd2N4Qu5cpPm0++YXs+0wVVkwtRgATQg2k34/ucucsZI03iLPJkWpKNPadlw0bTvsb1IKDuUwWbhupQejl/IGENzmFAoJ3yF4dbquy65I2EZ79bpyqi/GPFN7TE7xxYhnfCOuOe60tvbprbod1/WO63U6cqfU4qNrdlpXOzlG0tSnRXevH/jasA+4Sg7fImcox7IkJY9qoLlBsokROVHOgncwzgewGh0Z34JjkdnA4uGQaMscqeYZLsN/UtaZe4aic3XIpiA90L9td68mTo3MLczLsWjP6z0Urtt5+BZ3ZUyGwySLc6tHpTHFTlXm92oNY1UnRzKYIsaLvlEE0ohNdEg5Y7DmdV3f6rk+SuRyc75sWHcDh01E0apKHZ8nM6bafEx/yHpfqmze5N+q7mo9y35l8o/n82GIrWNvodSA19nAovFYTp/HCLQ6MQz/hi7Oc8bt/0zn2L+jz+8U26MqmAM3D1gFsaa/NxWO8m2sQkA2ERGi1I/CO3hT4+V345KMMOj4UpgJdGf3h80kdmr8U1J1PdURclUNppjcsfWYY2SGZXzFFLl4lNWc3GNDl2Xsgq2y2BnyXBdcmefq8RgmuIv2HHR1eA9cYnVKhS2zgPw8l5wUnFT3DRNKFqkodVO0xRw3gZ+trJWhtbCVvRWdZMVZtYcrHo6XzAwMa73DebLI7VYjxKIwgNaOtGC61hqxFge+epXadxPdAaRRjbXjFMAlW26xTIYtF3+B0DFypB/XtgQh1WMVjreRhd2ichcnywGnbKxO+OQ96ttdo0vd3T0udiu7VrksXpZC+fqCJtX6cqX5N/Kr3cyF+c3Qq/4XY2PX9564gz+QjW5ItWTJA1ix4R38Gbj1Vx39MXz7uZ7L597PNVrH9fAPzgSzf/HyJ4u1wb091Q385PU/r8XQlTwvTA7kflvVt5tsoKE3b5ycU7+q1H0Gnv3auf5P4N4/TOM7eMyREo+XR1hLAt+2+a9G1sucq6jzpA+s8KAbXd5xhQpwMLu8Lmlkt6pzRTUrtdm72bCmFNyrAWNdwFhvuHyxqG9hguVprGmCLW+fdbPPnqUPXUHXR4AE58l8z2AsLmIGgF7cI3WwwpdbWprcue6ZLXY04y7FpRdEFa2Z5TE1ARVaSel6nZ2nP84v2KDTuzNnala+2uW5IRtq9uCbGP4DUIq8DGPmjhHbbgO+flzg5EWjxKgKNGAxTOg/U35JM2n52HbTKcotHXDc6ifdsE8OZOxBixVK4Gkw2Gxkjr/5SkjrLkh7Y0BCwsWTS7bphzWPpNwlGubm+vUEYyaa7IPafDptzFvBABZ/upKcqJ6PbA7fIcevYKo4tv6ee7znernnur9nzHPrjOMXqaKSBADHyUoVS5eMJAfEnRMd6CxTcokm4HVbTqlVS+qrW6JBGVZWMZtpiTvN2GKNZCk9JVObRzvE1sL/STl6tqVwspVDLwaztiBwGQBedLg1c5vBhw1Vns7ypy1y9pixBNXYv4s/LcOfnfddrxZVS/04Zi1AQr9ML10cjHZY0juPt3nbns25/JjiFl3X8aTqolOGsvbCKBNJAjaxzl2HIsUw35VIZChyG+ZF9OEmS+aT8dSEsWGQHFdcdamfbHHZFfqp+rqpMfVStXRSJVl2UmXU/kmrAEr6K3NdtQaVSgJqXVs9VAqEsA5eR5NADetoTQ5sdEKsoZc4iAK2VVKBM/xQn3+11F/BcPeS7gh7X3FUAWKe2LyRpRhQOUsWKwdkGwthIYQblrIdLNeM2sI+FXpbbwrW6tN1x5hoCP6defJWhDaNhsgaNW4NT2CK3gqab4bZ3qC7Bv/WqcTJWq+amz6+heLXLPAPixMf3UOvO1ZkTMlCDw+0hPYPjn529HO9vrx01bNZWpYxtexoKLD+e5SbaynN482wC1y0pcebHJnlQdnr9onbmHG3ZUdrNcwyZ0t1yZxyPGt1ne8p7a2rETt4sPF8Cg1XQ14uG5se/qt0g35QqGjeZ6XFRCqGDupz/gAvP1OcIKm4CcayY5AidypViwqgU7SrgPjRjwqD0YPDL75+598b7pVc0WmESjLcnVaVYyaPnHe3uMhbKhGnNrump21lD93NX8H7VoZcq5wLaX/3BYSOruM88MzT0OMJANrzGpdF4+uPfh/U3HvtsKmn7OHRezVLxDOvejrRrG7y44BOKTqhPobdZ3i9wAq7axhuucMo5seXqNhx5VSHAnECypM02wg0lmX8Pns9wUWkjLET/kOS8iSzfLwOeQE2v935dgs5ff6rTb/sERwExK40oAiezvV0bzVMs6gph2sHV0aoVF7L9/roKwJM2hYGNfm+hcnEBMIRksOxipoEiwvB7IvzVaW3SlIgh2HEcFn2/04S95z1QjRexRBnAuaSyN1gHFgiqrTTCd2Rdhm1gDu+anojZ1diOvFhuseUZgSsuw1S2ColOBe5pZaLR5fDoS0ng1Z6OBMsLrDXIqOD0BtXlluUSlThXOLwGRKD+KzPhtYV5yO01sKuyGOQDsZxeeSuFFvMolEu5Ucza8thPYoOBkIU9PMbsElIvTuguorKHqEklIfxIPu7aI/gFR5Unnq8CoBbWqfbnkq6WkOLhUD6hygiTu6djDvLIRUvZWgtv7BJn9+qWijRPVejvjWR1pEsT/yjfafsrcmmtUCQuGSTV1tVQQkVX3cC5a4/NiLVH3giWykNAFV2pTQoD+BOZNkZ1KiNT3lsopbjwUiCw7gvLRkNVXRDXhruW08omsel78CNiKdLGCSpBiZV5KepCklPaMUt6QEe87KqlnQ8HxrpArDwnrL8LP5fSxfwnLbgVO3T6l9rfKgftNPPaSOcNl+tVjG85hj/JTz6A49UxgAqJbCG6Pu8CKIng7GS/kUmfnzC6pvjDmLk/Wc8ZQoLfN4Jh0OS+1ngZ2O86vH2Xw5z5jXKOa9W+xaiYl1NynNWvLZP2eMeiqSerpxqaJhjX9uzlP3lacc3Cr0rZaveiALmJBvnrIYHaWPn3dpYE2hZOUt1ByhchY3T3Q4HW8DJlBT69vpErfrVidkArzqYklKxB1/pD5yPCk46eVpxs2ipnWXLpVkNgEde17kyqx32X4/z7WtYAuH55LCun0j8WWXtFhh/5sx4RYZLARFutjwU9bR8XyuxtzwNJbE4A2VgY9tmCLDhg7cQ3cmp/Mt+p6eF6hwuMF2pLt74GFRNPhrXJGAHl0+q5J+vFr5UVp7BeFkrgzM3gXhWqo2qMupjDSLZBa/Le5d5hHlFNdWU4iCIAoyoig7bzx9pK67yN+I9FwSE4cTO3bhxxk7TrHNvB6K8kxzM5nNlJxNWRYdoXK3rYEf7z4G5qHldG/TOfQVPSPSscWzKgLVI9ORTeVYU9y8UUtlD7ynHrXGc81qZiy9iBaurm5sZkELpL9QuHIB8B0A6lvR20WNkNpr6r0jyisd74nGrdsbix1IGLRJbPGbSF4pinxy9z2J+KJEUtEN5+nEp5ds3IkktU/xeSS7ulpIZxiU97HFSI5ahTZDl7P8CufQnXB4FIfgzTHd2+PtnkMXMdCIuz54EArkpr8cw5bsdudSdy8mdqElIutcOGjs7DXt2g7wfUf6xJfSNEZXQlkn2ajpyjImLTqwxfCKXl22rrhI01wEev19NZ2nNK97j/M6d3O27OxfcLGV7WS9nb/lYz8pKJ5NlA1WtqKToaKO2BKP1yhmmnlJC/E6jHYi9M5f7uaZsvxBmEXnnXscyrCisNzlyD/ck/dsoSOFG8TQvnuZOAqk6X+a7mE1y151wMt/DBnvzz4HE/pwyyZHSizIuBUc/ppzlD/gTzCIGqPKI2UKx3VfQ4zN49+HRe38htBMQWsQo9KfX6e0vSCH7kB8glin56F1U1or9oWBVsRvwg3viq0BE9mmZ968OmD8WSWdpT4d7dfU4tFPslNy6vRhkaVf1S5Avmg5NiGaPjMkSifMa0wilM3siz4qDn4tdBeLInJ52pdOgmDxQMx4AUYCXxa/arndYz+qgdvUty1cofh7ue3beC6k3GkrOt7iaZWnBps+1G7sKgyeDM+4sEAwdN+heFAGQFQFa9WPMpQsJUcNH/FB+xAw1n3HK6Cw/pVMu4v2ReMnZ45GAKfp6Fgg+INfKYyE4m8GkON4Tu3ccNIevcKO5PkIJ022vJ0B2nqORrl6azh3Ye+D6huhbP7w1cxvrndFxLL2Y90Pcs0OcdUGcdUIEvOV8LGZzZBwR/eXmaSfjaxVPHlk6oYF/1fC1HA/r6FR+L8y0tGJuFGq1SjnI3I2VrGTOk6Rf6hKXKm91Pn0vwSpAKeRGTTjP6M7xKjbydMlqjbgvSzURDO77YUG03lFMmSzVvJMNeDBf9lSlUQsfO2tSkmMlUjqmSDc5+k8swx1Hjjt4PpIdVh7zb/Vc8P/9y01DqGvDMxD0zmqCXqMdCFbV5E4Z2hEDqvGcUlMjpbrnKsMtF/XWnb6Uhgyy9IxkEOrLprWIcZRaUCp/3vR5zDk4VI933ASXNF+3frgRoXID/RDR1ZJHt3aup/FO08G5uyvoEDSg5gJqyRWVRTSWgwV0hLZZKWAdiZmofSjsdTn+C56S/dkD0ndoSD+P+o4XakTdx702+8C2HrJs8uoa49KqEw3DDttTltCIGNH30GGkxH/OvZG+McA7my/G3yYx3Bn0sM1W6nqylKbhXlMd1nN6rkUDcrClkkL8GaDsSpTFWwO6mypCYuAio6u1qfdi/sR2bEJMom4dkTybwiVrVrlATRNL+8R0w4zYCb81teQJc+s2Cix5J7IYvHSu7kR+VTkc11wXpXSeKrrrIu8xpkF+6RwqWtDB7lNqDR9lm+zpa9FWtAvn7zL6JLO5t4O/afz9rTeG+68dwH+uHNxW/n4j67w53WydeWPq9v5M+6UXDv7qGNW97Cv8kH3gV8CeyKID+Jn3YAU+RV0gcRb/CIwM6gWZrhB90b5sF9cTy4jxAEM0jt5tB9NtQHCmenpEra2lSE5M6+SrskVlG30k/yT8IfhJSvo99QAplJkBdx8mbxVR9ShPuve/k7WrLZWNNIx/SuE29+i/70Fr5j2HZ/XwET3yH1dP5Uhe2Vn/onbAz0CplLNxr0z65b+spC+afpR97bvig++x6JES8lq89pnSYDy/fZl7AljpaJdln2B/nueaSBUbSTrhDaqTUMiahCKe24LbTYLlsKPIjiRt0mzko86lFTuDsaPkIeLuowocr8u3CCdkQSry7MjutTgbjmQ5hZ7UQ60TKhZuv07eaOBlz+7YM0HjjUbAXEitTqoU51YUCVYXzuslVdCftW1MWQmrh/9XjplJR6z0C77Q2Z++4Pj2yV9LI9M9Ej00vbmkQ0f3xlZvE8KS/NgrRz9W674tTLxxcOsmMDkGX+85BLbENZ4L5OLOMN+jQ1AZZMEHHA0R0XDtsJd7IN6ucwkJx9XNEjWvIuMYrTXj1rAU0xADcTck+7XhWBFUZzB2y3uxEpK3qiJAAp2yiHkxWtSWh26SG6z81atplEXpnejqCLh8mm1Gs+Ut2vKMenDhtHXC7YDRxNIsr5Lw3W+Nq29m8iAPKeSDuBXK/GzaHFrtepYDu+VJHHEnFtXlhdUirna2H2ONvyDpDRl/nQOS5fa+KhE00sSVRRXH7jhYxGOwRWOEvsvyU+7PkHyjLE7zJTBFP8HaLtWym92nQ7cyevmjZ6Bws+sWyL3iPyQK3LetiNCh3aecgcHXP/4YtREdlntQ85EQIT9f0SUPIJnTRCBU5Az5fsS5cNLTukrhOLhlfg6eS/48kcPDZAlESo1qTQMJu8EO/RedcVAEZgJwz1Q4kDDcfPn8BrBji50zrSn4+07SzwFXFt/onWm+PHer074Nf7Vebv2ViV8yLBhAixD14GX++9U0GQ2zWw2E3Ljd+T6xZHPq9OtkMnERaMGC8dIi7aLaXq0QlywPie8yGJe721hBrsnenpfQhbbjW98KlrfDFK439WLjjW5Rr9vAANAfJuXFUSNKH25CnQpmrbPA1nB7s8n4h4amODD8b2rKnhtFJBSQg6+NNti75kybjWFnUrPRJuuJ0zkTzFqW5WUbVN68hdrvhhVt+JzOaF6fZ/iAtXRxS1gFSqBCuBtnVersP67HDWXZlxljz2P1unoXh6xH/T6RsE+J2ouAx48sFcEfk6YMVUv3sHYtOq7dN6Iey6aqP6JDkNgAChvzcfFZ2dwsfMpEUARTKROkNiEFJejcpeScqyK956qlRmId8cqAZ5a8fZ9fW0+AvXmP594PblpckBxN15+Bm1Fdj55nI1+tqQp+724I3+xaVsHxTZrP3SW1nnvXs3FcVdCLc0jIQRkEgNjqr6jw4AFMoGzXlLSK7VznenJjCORJpg9Bttm6Z8/Wfnk5CpFQrcbI0JyUAVPotBeJQS7ckaIepS51kXNqXDg3jEvReY1a7qWAtJynzblfJupmjftA7vBTovAgJvxIiFUgObmcTvNZv86dslDqUZcOQGerAM36Acn14yMW0a+iK0YE1lvP/1ClSS3+X4SSP+J5xcmdm9ITsexW5TAInn42ZtyzdBpm90p+VlovgXHjz2blMzuDTLAUNyE6Z43Kmts1zgIm/k/jDWCO2XFQJ+8LQmFfd34MM+L/QrwsbHMUky9tc58wvSos6gMeZFL2/DthHmyCA8sO61qCSXWh7RZ6XEpbVj/azJWEQsDQbud1Vf7YV6C5+1BgK++B0KLpcPxqmNSsEihHQ4at6mQl3naYxiO6nnA818Z3ofdBBUUcm8UlPci7LKmGbsevx+RWWK9hShtEZwSZEYTH9RlLg71mF50SuwWBIgit2tZ3VEiY1YTfLynApMmb2YJFuBbVHacaCWQ4ZDTrgZVxRQlurZ+I3LFZ53I8EHPH5y3HGUInMsqOtxiAFKYlsdNfm0yVZpIT1Xcv+xNqZdx77XJYLGyhi3Ia60hQh/+dDxTsggfVRjnTVM22Pb5dI7gazoFyri7s4SJyVo5QoK2s+ZkgdlVVCxZtmlM/sw2S8Z3xZ4CKBL8rbtjNR0RNzEuNhz6bFxvOw3X2rfE2fIApfgHht3fOvng8B88xeF+4pHiNkCLzEmOoSgFbIn8PmqCflEqI8JVq8++oJZIw8Vns1itpJOQEkiV56dtLK23zrDgQR+9lT6blszXpwQvVN4kFehkoUgjpp66RBwdGLxfHzpdoWUl1smCul7Xbyq6U9F3Iq3944XNmh7dnhbdeAW/dBe9SXV1IldXzwG+JJl4ON0VJoz9m2FE1XVbKS8nE+m4uw9TtPxQWePvljhceCqH09L5M7/RYcXaS7PrR+52AMaJzZLCvw1eb9tAz0JMJuP6FHd/W/s/wAU9JnGO5Ur3sjFtQI5XPltBnnIzqRz+qWc7yWtFxHvduqvLbIuBU78OXzYbOnF7AW2S1UQBc9CeCNDFZ6ekzcNXxqmegVnYF0BW3h335JihtXlm3Y9WQVOymS3uiD1dNL04bHSZ09JoQ3bllE3hceH1fTzgsIygcKvdNM9/yZLTLYefwVVAbx8BpIYAnSvl0VqYTWGILMGp89sBi4iSK2Q6KK8OusBD1A9z1xABA29iPtr6Gdd2ph2FMKcxYIDmynHF09+qgDyeOnqTRD0ZxGi0ng80Y98Jj9/wmmnlAYpwdTwhmS8KjlUpS71Pm8G6oA13Klkq1vcWgwmQ/vRgX07QQMeYlv5b6faONVeciREAR5MFzQEY9QdszmSvZfEMuTzaY1uzLKa3a8iQ5mJUSaGyaIlGBUjctUqZrlE1z9XEGrkycXdmeZe00rLG8RbmlRaZQ9qZUo9Bycz8KR1LxCBMkEw/EXJBQhing+waQi1YuLiUL+ukhIDUL87XG6KbU4qsILaGUdcoyFIWp6jp9l7y9sW65aXelG5C8nsmZ5xOp4cHG8ktEalRG2J8WJtsq1LWdXH/dP29PJxbfCdMgGiLyyjVr1eZHyyMFBMoGx82T4jpRj6uYJNetnxgy0sdyTTGa50qpif80S7SkwxLgkQ9LAY3XkpMT8Ls2Fu2KWXh8FP1epCINilYpjv5aTe7CDLH+7RRsD6tM1kY97JlAeb+uvn8B3/siedFQMNuZGddj0bbLFCvJMND2ej+QOxUo68zqJw0xXVeb1/alb2zzKr70QW2yhrCKd1hHxFZnQ66up+4dX5VZFtjZak3mQXkwVg07zrfSbnWKzxirkN04pOo3Rx+Rzvmx1fcSmXZN8axwqPTAzOQcNL/+2f8dzBJD2mrUr7rnrbKnrIO94J66UKz23os1K4WGOxvx1gg9Axf0wMD5AON5i8leD9+Kmi+1uIjBtqlGbWVvtQ27R+T+zMHUImPXgHWfVquM7p89+BsZbglCqB1CV2ItXx15esQDOj0WJGtZYyDHDfsxEOgBD0ZDpHmEj56KSE16/CkLvv6STOCsYlAJqb5+51+w2vOn5KvwmKo9qxVovtAuRy0dOyZ9ZyoiudPemx/vso2IXI80RLRKir0o66bxUMSc1VdPwxbPBXKL1fuW9rjN5UTm8wwHlEW0mIG2NFGx1/JvZbuVZ7Tjym9l08tnVBG9WmqYLfIyn7HiULDMinTCVlhZjjJMr/BmP6IrcQgiJysRG4SD7C4V7uAlrS4ku/ChcIVpGBeQrKzMcu6NAYv6VfcKw4Hg8eG/clEc9Q4s9RN+zMvIdKulkBD7lI+F18UcLozynOr/RtmVRH1xCZC4899GsOLlqB+xJvybTi9on4qwimXXZECZYoLVMpBBTCKWhysULCrN42k01a8/eb80R3JextCrOO6QXcuo3zJxf2J/K1LhcAHcnpiv48f9Z+sBtZJ08yQ9Od+nPzVZv0ffP7msT0A2wp5Zsa3pS0+xww55zRQVheV6lizXnvDS+qGlLm1OM3aElMbSniZE9xpFn4YnUe7JqZgYUlnzumoHTCABXSqj6rg8VFgF5XBVmgQvvL168FQVgx0eMhiDKCS7Cfvc17ejlGW8GrfAkyhn5S/iZMi8LUf9Nau8Zx4vn/ibCMm3qFQT9/x1murNhLcqxFsvzJLsu8uE3rqdmEC8h53cdWTIYa7zXYdA6BLW1KVFHJAS0NgCNZAsEle9qeQEnaKWjTUZ3Rz3yPaJfwIWw59zAeWzxVhoKdsRJwX8UVEG1OTK2xSGVnAm5eQFjRORmHG18HuLxSrZ+/B1tWmaRcnzNbFUm6e7Hg0eOxG/WOcCYL7RM/99kEqAKo660DDsT8lkHMRt8SUoi88de7hL4+tf/MYcx5S7tQEYe21MHfYNLT5qO+FQZvoH68lwjt7v+FLhyGFI4v1ua9y0OBdGGXCzW4MEtqN7InmlRFOsNUQZpZP+nUj4eMJwVtOL4uFXJFSiWplNeE6q65pOt5p+kaMN98halY8QqN99mPfAX3CLOJvfjXv5trxsoBlcuK/js5LGF91Xo56VLcq5b4rg2mhhFZeezDK+xuIUuF6DyaFKgQJyYewq1qtl075w+ESc7IoQVBBQXhxxAsUgdBzMEe0EHhCaEb6VMA8DSoQvixszzxE5y1J/Fy+XMedKYOfor/Pqp7JnJiMn+SB10kXNSeziUAAbC9UoURk2B/ySjPl2eplmyeAuBkm3OxqGg65QwrqbevOu0fDAJhZfBl9k0dvL4W5hj9s2hvubyTkrhTRMQlJYwcYgJQIX1KoXzJPYw9k+p3qs0uW1XObHsCa6GRsBo15JVvlhgDXEVa6GcapQMtI7qOg1SRVUBMLDjmV5oRo1XnW0JSAwy9t0ED2lR+pxOG7au5lGiKBy5BIoITHg0iywJWJf5/T9o15cc611g+8pvOa8SGwBaGdytW+hj4gpwcbk37NY43OsuzDmJ7qukK9//HGJWWo32upEFeZTGHJ28Vt2LevmXUlvyLZyGRQ7jbInMK4keAJj2bBqqlOmRF2oMlmM5d1EuVOFozWGDja5SvvsQWtO+C6ho9f+Cwfz0v36nJ4/kqrLvyOAvKg7NDUsW9I4/J+ogMNgWfRuurX/0sFtYIR/q5vQ8cVfwwub5xMtZ/m5TAiCvJHMfgNsMZLUoKE+GohHPGdICRbzyj9ltfyyQEqHQ1bpMfGDlsmWbFXiqCn8ekW3NnZDaqN0OeVhgOjWMlHQejg5up1ZCEiqWJOdmCRTnrwC1mWBKoqpAej5erWZcrivgO29hiFMzWfvK/YNEVSKan01pBS1Lt8icFozE3qBsgKvGeyACLv8jJzV/sATFFD5qcfE0r8rQ7VmZ1QyUQ7XFHUDbIJS0u+t1hStPJLSRoQcSIWYdFx/8N+QMY8TOpZxjfly3kPFi7BAPX0mlUXKCNCWCHLGGiZUHVFv5WetuEZxvMpok+dMUqQ44QgrUiOx6wOzvTOXKpkaiazOwlKMaimWTYrjmytPlBoSZaBVMCXRjoU0zcweKw0UJaDntl6GHjIz7BNyqhbS6hOmFeJR4tTmS1LK8VtVLEnDtjuCLMF0lOif6pgyP5rwIpA80hCgEQBlDMfyij4nhhks0SiV5pIKgnK+rAe8zBar4cVqx+ODQBb/sWbsd8ZymbRa+fBqmt0uB0W2bDvnIVwhHs0x1DvjCFuMKLbc5hwaXFNhCFabbDr0uhCYSBkkeeVjFnnwHhrtfFCDD4K4SP1FSWUfCA01XDLoI4++lnhhC9yxHqFJknNU+gPVz48mmOzSV9/XLhAtPZpC6Qrm20jezoglnQjS4wCj7kqHxs+q9yUeZGcytVU7f4v/cJJQpYB7tqZ0ZOX/wivW5hXREXTyzNAPePLdjwKW5A/I8geE1jpzVLx5oHkhFjX26vKMIj8DcKiT3IGWlVNBWXdEbTDu1jivHX3UOvfInx67/CtynH+Abnw6PijuWvefO7M89VyZ5annwixrh08WDS6zzfe/gWwzans4mjzipY5PimE+YbaLXP1KHJOgLCeSR5ZI40ONAxY5dtln67Y09Pb+qshBq66kNX2u0/Ql8NVt9vLwjGSwQn7xNCMr9peMmWRGI0y6Qk3Z75NhJU1E+s/ORCrfe59xlQpZ9bCQ9+hgfUmup3rEksJAnj0eAznlYiB5gz8ui3gt4j4whS+bbo5zsY1FVFoRV6aX+UETQHJXS6k37wxJw3MgPM++9a1Ae4y2Px9ftpRujTC/qnIO1EgzS04vGiigw/AwIPDPrJ7MCQfbTsieiuBbvtme0NvZqZWK8FvDgsyCvRwRutTMk0/BbnIs+1dSOzUyc+LSNWNFMUo0IseywlB8yu+eacx2PC/NsndmDXBuJ03FFF4IRmVbuLnANRyVu3VdlGs6ZdujOG1Nnd4bztBLn593ZRiy2ye15Isqz4UjArPZndjxVJ4VO4tQ+CQ4ah2MMW5dNwtT/qh2XSgIJ0cbB2Fg8/B78mIulIu7gCO4j3QPB43VNBl28mGDls7ZIM0bnuDUfa/3BHwzq10sBWvL9OWqtrR72B6siRLsfrF/wUEwPR1sxz3gz6bhtqd7JUBblMqNOWEejFEWWYxtc+045YrK3RXxqeiHPO9sticiV9Hz2N2Mx2xpob4wxHdwnDMI5TvlCqLSlVt09kXwGsGwzthc54LaYnadjdVYXmcjNcbX2UiN/XU20mOC+Q+HA7c3dU5VCG8MuI3OH/j/Y4XwTnRvO3wpizjfo3eV3AK2mF9FVKwR41vFknuCfk9Z3fDLQcCe8N+qwN/jrZrCAzL1AtNAKsVW5iwR08cPeLUu6qmqiPrquFVVgXuaOejZtoE3kS5y5KKI8XTieHv60KHmzTHw7nmLuZTenBd603TDLGTyUeCMrHYJrjJBifWtui6eFrAUlXs6SVymwE+D5z5hzagFb1pm1rYKrlhlaKSbqS+gUzAF83XjRY3xRUb6doGLrpT+lHSq3F/bWh+UCsVO4cZ3J07I3COFC7aWVrQBaWWQDKKG9eVc+YyeCRoaRlMdw+JQPnd9U4GbFO2O6iRSK501Dh75BlrD3c8ZZQgmOJ1izY97dj1vixvoj6uc+n6cjcL+CYfe/GlGBd+hpZgoKljLZT1ME+C7dxz1ZY8RIqx1BAGG7V2QJyMQMe4CSUPxEsT0PtG6zjc4pPjEQiKeZYRDZW40Xw6osQKUi2Rox0vnVA5fnkg9VhnEPJGWTGMs9FhmTJP/jYxkLpGEv0Qy14pk9gcwjxuMUxDUcaOXM2v0skBfFsMsApa5GfsTNHFZc5ZMGKUDhPoCsG/CVz0KQNAKuMpJ2l358Y7zvW8i2UZCqGj6OBlQNIFojXU1IE2gL4vkiV8KNp2pOwFgtDskQm1zZvKVcfaZ+9nuuuz9PqhEHVlqEQalsEyJiTpD4lxxprKj19xemNzFuGaoKZ+XXVwR3aHNczvfXpLWQF1ucfTnzDPHXmqL7KeRwEFIXCE6wn+4qeTktZOZ2rgpNU0wWF22pe5q6pTSXCz2gR2emaoybXmZ5q1GaQbEANYKk2y/CXB3Rhmyp+SyCEwrgIfFB1EGxFXSu/PM8EQeC/7JhLtDqbmDrTQcbneC76NiDrPRI5A0GmK1V0Bb2ughNBMeGB0X+y9yl3LzMWt9TQe0cMrieuoC0lQrQEepKNd9CeSrNFoOs+gbnevnxGgw58elBwzRQqqmw584qWBFHXgB0Zks9bR9FzV6JoE4PI/sENhxYq+wuqFfULd6zWvoJhzn7cNVbTSzkq3EIPbDluHSitzqhdP8/DMlLepANUgMlVCi5Ancxf8kKA1LPCin5YkuNLO/KL2kCaZHBpielgumVjKY560m46K/oreZ82SasSWZEUlgPpXlI58KSk3eXC7NmfN0OXJhOFPZ2D5hgnw25UhfR36bPBlO9dEfqH6mG38grDXzzezZytQ3okK5oNQWL35V1+bSxxVeT5lS0WJc3yfZt8Dm2dpXDJ+xx/lIQC9XCbC4GAh4HicDs4nbzYCjmujgNc2aVd5Uoopf4l1FPSSjojqW3Q9L+UCWuscpWSmv7Z9etxgnjwzSigg+Kaxf5Shc9I5QHMTz4TROwBpsDZP0Ij5yGyVRS1lGX+FRz1pN7rBWeLtbE5IFcghLJAzP7GQyTnYj9TVo3WvyKqstDL6hYqM3msVXdFg610s3LHH4Ph6sKgS/yytqzrL0idycPnOcYJxHsFzv0OWBlv8ndaJnHZE3cgcYje+6K8vQKz9ZZVpLPZ7geNh1nKNWE7uch8mJLNhDIkvwneDsi51z3oW5kwB/s+Y5d+0Co32LNAEmCffhq6P86uY1jHFRlohAlAJzrGcD+ahRP7xhEckal66sXLzZRPThM8RgmMlzuDTafFjOvLUa3sX1aIPsSqAaGOmBKTOz4Oq629VPLIvrPbGsSZ6PASWkqpccq5/k8w6BJtMjwwm0R47RvPqsDAZbqrqZ02pnq5fVdIPDz+Agk2cOUMN7MvGlmWGtzKDQvCgtFLQox4bTp1fL3l4ptDr9iUBgoyi2Xgz7+fCjJgYXsxkN4h9QIUxbyjnZzJtxDmhfPCimNm7hX4ucbdWs0S3CpqvHbWkFDVv8i2j3tVesnmadPeUQSP7OLE6Clj2WH+VmcJ/PThfKB4xMDZg/y8ltHqMkfJ0cO1dTMwJw+BSj3XlvwlmZMyvMaD1YN+4u93JAORjJee9TzhmhN+BHPLaSMk5g8cJgjjoKdYjhclWXNZNhVxTP9wH6EqrFA3nAtGT+MWgaKwnqcjA0+5DL0nJ+jD9j38jCiifAOA3JGNMhxDQ1sd7+CcZHOJ018gSjjwTSCu2QTUiDloUJX5nvpIzhx0ZJ9y9YiN1/Z+w0k8Yoj/CX8F9xqbiUGNxF9+hH+MgSnyrcI3aH/bgbc0WsRSnrlePZ51qWxq2t1QdsOfVkKnpc2NOm01aQo218QVvFgDauTlUqU3XzF5kVwXGtaC1rXC04OAN4K+7druH644BxTP2+rMzYel6p+sfKBDo8sRyguGq03IW/sZmk092RBas4W3iiebQheQU3Dqw1ruFzejpYgm9FgxbayYiLLrnNb0T9ZLCVocUs5HYywJXMBzTEq4v7+RH/soF6B8DsTrA02AuSfDtKHcP5wKozgRF+MIqHKNTBLiSj4XwwQDmpH/8wCuIc2+TbYV4QLB9g5i+TJbA13WQHMZNyozdRXIl2Q6wdG1y7EaxdCaaAYqfhIIM3O+IbWj7QsDc50IshxV3gCduOgizciYI++kLz9el4DeJI1tgWKQIcJ00aNrT8zj5+dMZ/THT2Y+mB+yCpV5U+RdSn6sOcdrsp7ftninSOOFh9iIrvu6W1vu03Uo+X81+72bss5UgVFV7Lw+5bnJvFP4VMLR+X6z3Dm87qKNtWr0W9zV3AywjJLDZ12KTsUZDdUUopW2mMZNh0iRj4dUx6GKWtWjmgKfMaHgG2C9DvdkuBJfFlAOCUbxz4o5qUMqCsGqsk+YxFW+RmfUvZUHv7Grdkt5Rm7M/nmlTuLug/U3mZFvE6getGMy5N407z1ST1UUYzX7abNnIEKRfSRN9YEY1R3LHzY5cBEQOMX1D7d4aFxJrpgJtRnygxWwH9fnD0U55fhZX6eCR1RvOGpZPXGlTnaXwnFgDiDjILoqEzJ0Be5Kpy4D2DwCudOSi34kwmtHG5PUkjV7kzoDelu3D12LMtVLGjL7IdIgy2jsoX+gX0MItRjwoCZTwA8cDeJdxVulyJtkJ3l0lpi+kX7SYu7PPWXdmP9oLz9I0t8aV7rnaL9GEt8Xl7PgURwZrCrLwdg0BQ7zO2N0bZkSsRnLdMWlD4mVZ27gXtlxOHONjtsL+JyEjQp4Oz5uiFRom5d2WlQg+0LychP7GEHyhkqF/ju0GPc5W4HPOtSO/zuXeikSPKG8Nhd4MpcSarsm/J7lO0V9y/e4Zq7O5hhmfCKfoBbwgVj6U+L0fFcm3Y77lG5OHRjw37tCh9qnhzkwbkD6jO0ojwY3r6GUv9humqRKKrx5gCtAB5Hx80KiPfGfZOVawH/jjNsbdgpmLU9YqnVk7XOLq8KZp0mnaDIIXXC7VaGb+FIjnQENySH+kCTwmpHWpbKy1dofXQWzLGs3uDDBtl3bqUOVksvwbTGjZ3sciEpDW+6AzjWwbiwCKwiLs1yitIdXm542XaAdaV74a+X+PrOxWFljOirl2+egutl02V12UKsLF0pG2vHrRa3e8izidCmMV3iTj0cfSTsZUvxGPMVZMXfzBCo6sCvC1WMFAdduMsGVhcdlsO98YTOdfMp1AQDlmgAz1/SvTk+HpnJRKca4GZphnJ7udU/fqnSvW+w085DaWkgJ+WUzt9odHokt5ZwzH2NWtRbhPL+adWmASfnfpWjF+pwv2ji79ipn9RFJcVxccUmr+JIvL+sxOc62kmD06dsP79RLXr4+tNC3oLx/rPRk9aRytykpmD/qNgszF3kAwEIf8+dvE4CmcVahbKO/qQSi08O0VLpdN6LdXL81Y9a0qUPxHlc7SbG/pnd9y9oZOGroZaGp94NdMnqwz7ExS+Skq7PytJjAJp7bevxf2EZw1ySEDVqY5qMluZMzsRxy+xZyw4Ds+tT6oQLpBaGgF73hfDO9rU75WXhFcyKDLRFphYlSHGGwmxYQmCGC+XrTIRq7IxK6eJtarbiBdnfRal/kxj1PnLb6IXLdBIGlE4iRbpS5Xl8VBmPcfm8bxshQpS1T2y9Se4cvmDKdgbl7pNZPgvdoJuGL9YrSrq9OLsJ+wqx9P/F3EMaiUAyzkuJnU5HjTrxYFZy4r4DyZ6Fns89UUCgDHWQ/VrfiLK7/FKVy5v5onPPTtkrPciHKvRoKcdP/7mG3j+2PHhNTmUI0THkGoQ0NcwJqnycFUZMBms8c2X/8Z37mkRgyK2kOnPbXk8WcZ2a+bKJ+Vqg+LqwRlqTLHrSlYibLRLs60qNq+EO9Hkl3Gy8Q+YQC4NkaVhEezFqDeaYoA2nAvnRWw64wOwCj983JmTvq15pJxGCSQ7N/H6GGGXAiDQ6RtZlHYQPSqiKs3VsQS3CagyikeBXcS4teos2MGpU9URJOSphZNBfcJqmGaRXTKV9XrlOjrL8eI/jH9cy/f6SA4GebQVpe3KOG4TORzlzUachNsUSHRIFz2h5WwJSjnheBJrXlR1mEZTXVIKZTzfteLxN8U4eaJPaTToBK9vR4NSHg8WBcUSpRCckOhOMsD7KM8CXEzU2gf9cKvNhU/a60E+DR8YGqGJ6J44ykFwiHl2jXhnJ+rFALm/J3O03IWJBKN84ZWl19YutulTFwb5mdnOyWI6hp0ZAcZmk5H1KOy7c/fwVVZYIf+JGGnngbigF916q9MMfGuCTGn1wlQrQlbt3zDI/XGrE8WweuJZzVVhRYhnZGY3VlPwJDwKHSSorvdQyZm3KhbUKLhUo+SoK9DTUguuzEvmSk04TYMV9vvJ3ah3FR1znfGJ4wdSTO6yoU3IsK8/G9eNZ28Dmdj8oXr16fm2c4uQPpmPxr/zMCBeFPlxmZUU+bKpINTRR/RSddEYw1PPj8RXkovcm51SLutorBX/qYWpStqKkoYWYcw/o7gjC/JrU/6LGa8y3oMn1tRcWdUoS9OiFrysNr1lvL4dzNW3WJ0WaFMQH1cll/HjwJSYO1ZLDl2Y6D6Q5o2jD48+FEFfcEXwoDwqGoD15Ki22tFHh58ffdAJDv8Vi7PxWgKfwzn9ghWgEooNMqhgbUzoRwkbHpM9nzymFGt+Ozj6CYWWfVIUgsSUD5gThNQilGa4cbxzbj1fthNVJzLVCmwnHDp8BMYLkT9ePjZ2P9bKxrbU661EWRdOJbBG7MbDkI42mwYGd2BQOHxWnTBhaFbNLNhGlGoRhu4g9jCWgd/w1Ar5BteaTy6fFluA+bv5NtCfYivknMz9wFa2BJd2SmZqfkpg2RYhUI8/PvUm+4ymkXWkRAuHt3gHdDAxVtPex7Y7XLNa2o0yVtRncT1Yol2gKpNX51RqnbXMFRXhkeMdRDWjQqkdP2ywL3YFVt0MCfQNzlD3OquhZM/S0ui/DniW3O1IYNZcXTKg/O232VrAM64YPF9fL/hbrs+7T+V8lahvWahQxiE3j95vBbzeJ4suPnzQOHZAtVmxscqd0IEI8uMnyoyJvaszYrKBeBpMhz1ci7eLe8+zuBtXb7LBgccjdK/Ihx7qFVmKz2RvnLRr/Apn9VZr/IB5chEh9ucd7vih4mybmBoy1rwjhOiynecJsTKP6RGmZXgq2RoErkTa0xK73MRPs+Kh6tfEvVouoZzwQOuaVEdSBpXuWnJi7D+jo6bmCeQUV3yq0aSK2FZ9M89UJfJ16gLfpYuD0Q6gxwbzofTKfaLnXaKtFnJreM4wEgyXLY291O8368lwoiebszce6Kxfd6MIVyWZym4vqaoiXFnGolCblZKw8CGYYXmZ200wF0q9uhJl9fRqGu8Apygs/ckmZhPPt+cwG2icBAOmEuZuKRkwZH2BU6TZTjbzsoY6i9KY4s6zoroNLf7adhRhxunNCMgamvY39jjxp88ACoNx8Pl2WAJJPYnLzhKktRmugkw+FvYx23ScBYOE+OGkn2ztTWXhZtSZ0G2kKz5YIej0YH4y5pj6Hpcp5nWYFuTsqtlhji+bgO+4xN5GeeJuQoKGVyQf/+oUk9K04Dw5HP/CDh5URPMONrxRZfCjUtzuu5Z9oG+468nJDVZ4v5byiMnRCrQeM5t39e3v8w+RVEgPxhAb0jboS72IjApt0WWaF5p62V8LwZuFMh5HuhZtYdZpfNlkO+XRVJ2WgDproy6QkqyOtiqlK6fo+irmyaD6kxyIczdfDpgpk9kxbRDIXbpiH53g5/zgz9YDP++zECObodxl+0HJSxylVeZ1COvUVh0L5e1yMH8Sxhqg56+E/f4GethSRpHBnThNBpi6JENLY6pcOMkG3CZ3Qp6abCtTrZMlM+YmWljpI5NOcC0Keyy7CLvalBtok10cQS9OI6x40LHxROZtj6SI3zilG3tSDkKF+SfITNhuGvY1pcqUgAVi1S30t/AJyW409fkUOUbrEWS/jwctgtGE0SOsJvzmFuyMSof4lG0ptnYKwuNcYFzDTY7p7GTtiCPdgDO223ATHp3glLpNRG3m3DAbk1AYwTcQKl+LNrXvY08FXO7S4V4ehRoZPjtsezI8uOLm0K4KMXo7+JvG39P5fqPTfKN3pvVXjTZreXXIalQ6S36QLkcOIDe2Sitanrq6vgrA8W4Jn4wa9bOoJgtboyykEUyKc40qRdJ6PK9NJTgh2ytCRK3a+mred8CImotXU1rd8DRjJGzg4h/FHDuMX6pHqDyaGn3IG9Vj3jihQcshugP6IuWY1WAGfYUYy9BvjAvezUhxHCYdSIntlgs2bgpft+5MjKe6gjqvAwfR4DBKEUwHp8Zk40zYgp1TrqBKts7lJaqyGJNxKsJTsVSVbvyamJZJ8kmswUr2Rn1gAJkSANGoH5VMAe0iu/Ll5E60lgMIivnKo0z1YKDivlLNJz81YxfEahptxruu7+Vte0mXMq27RE8iaSu80RjkwzYWwrriIGSMmqgt7FMZi5hYWa16Y0w0hNRUvEUefQ2h65lDB5dXR3GvcyW6i/9vKonmG1dMXXE/Acmj+WaY7Q26a/BvHX8n1noVkBVgHifXyq+ZzR9NPEf3jn7Gsqw8PfyKdOf3j35M5ReUpAABvPjZ0c+ZWw8VB1ITAtjU4Mv9KByMhuIMfC/qwzyW0jzeDEGkst3nbw7Zd8ljs9ftEycw424Lh2ajD0xFljlbqkvmrFPIWl3nW0pb62pE5xT3nU+h4WrIkzVj08N/Jr95FrL6Di3u4e+ZMQLtC53g8FdUVuUzNcmCutTCCcTu6gF//Ui6eqCfxtfv/HvDvWgrOjVQiYO706pyoOTh8m5MrrNxOp1rMjrnQYNXNLJXYgh1quiBs6bSSVSlqr9rXHaNrz/6fWDbQDSQkjsNRUU8wW3UToy6f5SMyLF3uK1i7x7in1/S0bx39CEczIeYwZnijHB42FeGnAtIaww09dRz5zdQtKqfsOYY14af1tsqvdvuNWtS92vRsB92IxypuCrZMUuLV9aurlvSrmNw77xK0w37xCR0+rROddAsbx6MwldTvLmmfis3w3rjLajmG0ar8cTgKsYd/ZwlEAfCoNP1wy9ULO00LNkxDG7BRjbKx029cEs0w24lNZZEmJ4dElIFPdGBWUN4VFSyLLqFT/aTIAelAqbBkF1tlTANqmSlVpYIM35DKfeVZQPVxdUv4NU0QfASv8Yoeq+un3ereBKDNBf+uRd5SdxXSbGV5SBB+UMMVARsF5jVVvewo0Jts4UZN1KgpMhwfoJYRTF95wwF+07zaTlSzxiMhMjK/WZK0O08hZ2v+H/rXCnorQ0sBcvW9IRoxJeshhtcMSKjk5Iw43GwfPUyrxYJJANdvN/lt0/Dq95v0NcvlL9n3ry1MNBwXhRJpMfat9kkXweh9aF5BwXG3RiQpC6i/2VnTmJnjFUE4Sve3KvLKisFSI8+UpdBXamntFIPeJGMB/V4q/IqHVjrYRDZt36v2oA+b37c0DMqLR8Dn9NTr1Y79l7kDZ11lLep+TXhO/lK3I86XK1hQmaNVsN82060X2a90V611O9TKKQbBCpwugm+69y4/sp37RDnrGpMPLRyAU6LjHbqh3SI8Gavx/l2s7G6tLbWcKvjjlGuy0n3G4cfa8mDhHjPV9vg6w+/JPQ8ehdjt/D3J+Q6/8UcbfMCK2PMP9ddSB5OHHM1pQ7qapyqeZ2RZTnCGspR7wLHI0AJsgLo2HWNWrEyf+pItssKodLpjdk9y0TsUxOzB3aiOz0dXN+OiuIUfKGTu4OMbKddLr0EwyTLp7rCais2xgWTfIhYXYw8w4t5I+7HP2RWXO6ZFaxuh1kUzAZhPwXM35Mf64KpfuVWlOxEqNE6U+Sx2ojQFyzImAYQD0iwknCPoFF32wWW+TmFOUbYcQsyXwQ8APNBdCdCZ+SwN5UM+nt4CQQh8YlomHAB3UKnKfSPCge8todYuWQ4TNJ8hKmv+Wi0zKixEStjBWqggosb47YWd4I4saE9puJx+0pkinrH3sovnVX7/9iVTmfO+J1lyyfNWu67SmPlG8bLm46nApO6UX3ZLfePbz+4FKaOZZuCY9ulhVOFcD446160fe/Xs5Kj+vcsLgQv+Tfh2JeDRrTFqmlUgXkVMz7lE5Y2A3kPztSQbz3zNIZrJHhJY+9QiYcS+iN0Rz78tFE5i5ZnsSfTwXq4OEFA3Uywi6erUe7eFQvOYyq8CRP0y1utX8+yDBpbwbQgD5EyznGatz9zMH22LRc/2J89mH5pnsW1cXUcZwbYwZ8L9s8edBrV01Gxvbq1gc/VHUwydKoCWfywVEFB2ezjSwh+X0FHItGCxybkY2oRB+KpDLup4fVzXZK585xYyjf5OU90ZNIcD3Tf2Z7nJa9Rxjn8jKEhl+s47j49fMTSUmoU0/sxWn+WtwevYwZGu7thBzuNOuZl6y3kd5Xocy8PcpHJkv6d6DX+xKU18UTRiVlfEgpt5wUnffA1vSDTx1CZUKYXHJM9+D6JrmJ0CjQX38d1PR31peeMieWROUMFHFtGOwK8rBWHna+YI82NARczIwAyBSN/yOzy15UUD0pjLfOjZ8jStpxZsKyG4APr0wL2Kbh7rMSwsFuYi5455lZEhxQdKg1Fz4/a1NLl2I4xJf64R8oN0nkQPZFne4xtqnPubQZ1pfytIJkX0zRJK93TtHXdDON+1HtzEEW97M0wz1FoSgYNh+JdLrE9IfDXv/hNYE3VZ9jdMFHfP9VUxlXvTse54I3DfwUwVHm1iNmXOfK5tuophpF9ifosTFSMVr0nvA1eDQ8BRR5SRCXLsXafNAs066L6CQu5/5yi0hBPCDHIhlyuyWvXjqgbaC8pfHA8E5hpc2dJzSrUhC6lmo2jdGvoPHbuRqOeddvXbs1txVSbXaswW/rt3N7mpjnbN9uT9aQYT5o4OGVR8aAGQmh2kJCPMuA7B72I5AOQx3hhzlE/hEtsEAH9CsgDCyQ14DxNiDcuBXeT9C1FhUHVtRlPLzm77nbUfWuOFCGYj2zILWBUh/QHo2hkKHsYXKkqEbDjDDjefDvpcUaZFVxNo7tpDNgbBr0I1xH3mxisqLcVWR36OX+NHJlCG88wXrSCzbZjvTNS0me/qrL2t73Wfv2tGnppd2Zzmtq94am4kBdhHVEQXMQSz2p+nnILZ1DmGAxhmZSJYcmZU/g9ijEdjOMaxQ6QN6SFk7OLdYpHpI15s/ZRvC4dvJ21G/PHdHF9ZebAl0JIWw1EermyOl9sN7+qa4udvSSk0qTstMmKcQqr7Fhnp9J8fYLnx47z+GSCU8TbIEnf2ejvrcTMIpBvd16N8hUKO0rSPZxRc4m3wTcXd6PuKIee4mGz1Xkt6ZKKzOf4yTTWCF8MA+z7RjwAsaSYQTtQaw11DLrE7pROtFuKrCdjr2rgKkbz1jzCLleS/BXMV2jmeFZz3JolIwyrT6OtfJ6pdpPuRZvsSqZN6XAeoNmYw2RaUw1H3Eq0M9Q35jo8wb9NemZe6qv9cGBbbA6REnjhQlNJ6ynSJLAJohAAUxs0KgYo7H0TDcEMWuYgzAOYNnIlItHOY6nUIwXKNwRbw0UQpQe6bxB/YS4htSNq01i5uvxGjjMunIMvhFn00jnur6sZOHFbLuzBbaHRmFbLDX516dWLk8AvdCItd8Y59nXtQCcWo0H8g5FNWjJyXFl7N1ULK5zAcriDgfP+G0AjXDVLvL0VYXlLceNh3jZiosRl2mY81cVytKP4R58JUgnUXlqNlWyttBpDMDyrLCR6tsZxjhKdOmphIJqwfPD22xI0FtGQDVDTcqxkcafqGSnwyItcVphDYbDZR6SQsXMZBVQhysJSjOtJ5Q57Lit62OLfglEw1xWuQblXcZRqGA/Gz7HcuLiC53N/5gD+M4v/OYv/eeHAodPXMdHdxM+vafjgaWLjwlr+sjZEUF9HWWSp338NF6/pui/afHGvJ0tpGsLlbnpzGCede6MQS0RHK8b/MGJrvisHV8KW0BXMRPDiDrW0W0q3Riz8eiH4b6Mkjzh08dz5RS1KW+9ThNE/tWCqt095ijcyDN7G2CFkkSK7aoNaspprV5LXRY6ZctxBhYemWFzmD9NEqBaeaEI3z8kLYaB27auje0xnxRIj+TknP7uNIk+Fk4rF2WnyLIIM2K3bpGnAVdZ8YBh3K3K/d9aG/Thvfvv/+LYjzRPB6LwWDbaAR1pcCM6iO7ceWkhNbs3cxnInY/sy7Xs8KJyadUvKezaJWZiENXG9n4DSpUjjeUIeuXaDcoNfDnebM23e5bhZB8dCVkrw9Q4pyR9RKlNM80U/Md3pl0cfoKL06D0TRZmBzPCFqg7zs9IT/u5OqEm91iDExhsNHLdJbQXmSakBXgLOvPEG/J/o2xuq1OWSW6tUdO5jw+uW+MmJTA7n91tcibNhAmjXckf6VtG+sg60mKNIGINlvPr9q+nr23DtrQ1x1Zw3RMsrcshm7glPNLxymbQmk3lqCoCmRO4V5SoQSRgqTeOtTctR0mxUpVwLh0OWDsBeK4gKxgi1vRUNZNC/mMelIvhffySSAMCQMrRVpgHQmo5RDEhJA6DDpUQAGtTWfGUxa49hguGb2fLZx/x7qmOzEfT9nyhOft9hwNf3Xo5rv+Y2gMF6a7zbRRZNKkY5Hn/0L+ilATcLGf0wCEuPtHoYHH7C0m1jBCc33GHQ5yPMQHn0Hrt3NJXC/ClnLXgki9rsO3gsM8fxwB7K0Sh+qrkx5HGQryc4CtzXg8GjYyCh1TwCLqPb8Y6LP1/F6thh5p5DM+5hXR03/nzyA3tD04QfI2uGlyiMN4Q3qFFbJJ89oGZSY9N6XuOIqqXPmB3d6qvkYsKcTizujKVWs5nrLj0Zw5asV5tGvTjrApiUjGsr/Ae+5xXJ67kjMb/oAlZHVmotEpMokIy3zySQ49fCfzPgm06Jqo9+xvwzyLmi8NDQihwIzzvzu/3+fg+lAwiPC5kLsEoCCs8mQHNxPHDbwjlRgPGtcp14kcrictwagxMVHOQS2sER2QwstuCgM0schagQ5B5zDsQ/Nd+6YT2/upIv3XBSPzpZh0GULPFCMu2rBjBSQHMNIIYvXcPoEL9PHhu3tg+exR2x5pIVCe1p/evIt0i3okEGT8Qml5IuuwP9vZZ9YbdBfzC45+qYbkrJvtgw/PRMFbm/sOQX/3tqqg4RNCmoAH2LYNy28hpjusQeH091TmMlyuECkKmQPBjWqk62VfhMlqi9pC2O2bjLFHSIVEwxWCu77UD8udcOGjs7Daf/Zp73I4qGIoLzKg+xWt4OB1uRK2DhGJTE3KkkjbfwbF+vLA+vLJNWkN0xwAS0wZzL2J66k1MLu+Gm5Aoa7dYW7vhJZ9ZR5aa9775pgwbjvTDLInN6ak0g74mB1TLQQgGHFZE0Z8vD35fTvDxkHl2uAOSj902PWgn948NfHv7r4b8d/g/6//85h3X8PqWcP49RDal4olIxNVeEMyv+pMz0KWo1ed0NXoNJJqIBSGzVOL/+t4BLzUbwNrIRci2k6adlegS70+77D6aD2rPSo9MsvBG970ZD0p7IbGs8t2kWkIMncHuDZJT1RVSiTk46pbTxo50huf3duMQ8+YKNNI42+zIMM42mwuGwv8dyK1ISefJLd1c3mKHqBsG5WqVD1vYyoAcdRvsyMlECgsOAMXOW6awkF++gdshGuHjn69sY1kmWY/qrs9aPomHz7Ivj8GwWd7nlcMjkSmeJvHEqJmi1XHboVsied6E8y0dqVYPG8Aik0FLhpAcSE/+i2qViWC5n99XAQdepvScOwnOrwEdzs2aNNknnn1YhPr6HpTp8FdNWqkPV9O40PTy9XgGGa2fk9Q8wfDqNb3f3YQ6dvLnNecDlxnlQnf2sRgUsRWKsSW4ML0fdScgrNM7Mj+OFVMf7qO6h1lxAHN5H/PR1WdCq9/hV+DJReDMHo5R15Y+04q66l5HSiNCiysmoukpulWisje9yyypxvtaFKORhOWlbHi+GDWbw/MHE8q6itTt5BP4GoagSKOhYft1DybUL1RV6DQF1sly9vNnuCRQE2KsBY13AWDdgsCLnASod4DBf3hEpg3ct5UF42z2z7Z6l7VoJGPzP12aPtdmroYNWD13F8reNk94WVUoq9oWh0AlsDhtWGHcKwTbr3CRtZ3K3MKGMkbOeuAIl0bP4umK42jXmfieIoKM+O8XsFGCNryyXlWAlJViNEMEU8Qbq7Kq3+Qp6RWKRK7HXq2Gcghyika+/nDqLTErSaD8K72Dw1g7aaoLZqZViqtthf3MKK3H05oKbIE92Qd4FKTXox3BBhH0T4l1gY6NgHb48hptaetmuLl1rrl653ux0Oq1Wh1eFoZpTcMiyuBeR+Br2elNYMi4zoWLeoDTqx3jnsF4UtQay8g5K37i3pDhBvytR7izYSPJtmEFCZrc8KgFVatcIORkD7fbE7DAud2eIAhJNTq5IRmm52DSSQSkYr5tgzRx0zCDaD+vJ1Kl34conDzLUFCBWYDKmO3EW4zcNkywmSfmPQhgLbuSEKaRaqMxSeouf+DErbhVqN4xypOBdq4cMWf/T6E6cjDKmfrg4QATqkSeA1pSS6kfUZm00hE5ZFvXsTq3VnpX8XCG3AzucM+zJkAJgKalgZ5QTXeWRlxzZhmnSG3WBjcHgT+hggxoPpkTQJiW+YqdliM5MBIpGxHXBI62rkWR8pg3uJnzvNjSiU45SGpxzllesOOf8YCN9AmA7dKhl6cBex7oIpOwSXh1ZoO9ByFKahYWWaOou0oEMzkmXfZANaCa2J2P7FWzGiKLTuBikiKWQLSyI+HdRxJRiXfhyGKLPl9oKlcccb6BbCU6OQlqJY2ZnfxdWViITc2pErpUCUc2KVeyo2fHOPAFoONDajF1UrATBHrNsQW7miO2uJiPoH/nNiB/nF4KX5K/65WPGr0fovdHdFb98QpfZrZCyUmLt3cEn6d6E2blUScM+OIoXqTfHSCHFjZtRyGqrkNeeJW9F/Q9TSa8O0TdJd/VJ6a6FqmxSP9Nf54Oz7C8bqtWb6bGU08dQVI+DRNVfcZLIVAeh/EhlRayMTCMVWFXvS1XsUsBOOt2DsSt2Vtj2/F+hzj7arZv2x6eD5PdMjYT7Jp0fg0AH+9bLxHqV+a3pB74IrYlcmRrM9FiVUpBlSJbZ6oKX2L03FWdJP8ScCWQe/Ap9TmVesdJYTWX/uMYRhDQyLuJwn1IOnPeEofQrNdcMynCytzTWlhXWss0ph3eSXzlXQ6pta7x3JaOuKG2ZffC623DivXsRBzUIitJWfa5pbnNFaas14ppbnLikWKa8dUkR49Sao0FhbI12MQwDmFmQxPrW+tmMvTVBI+tnKVQaZzJNbjgCoQ74S5p0J1jqIgYHlJuWxkW2UXSjymId17LzVs51r1fwtPDuVqEpe6C9cG6C3qpyFzQzYon9ZKRFeW8ywUwxVC0FOmlOqXTqyZRNddbtGr926vh1U/2fyk9JtEtGX+3EFiRrkAwi/FL7uTsTNKZRX2ceON+K8AENXC2P6MAyMWQJvebHviH0aOjxAp/LuVGL24UnOvsppqedE4aG/ZkDTIU6X+Te2T97ML3/Ajzh3hT75+BvfVn2X4RHYtcX9l+yhVRnRUy/nZNrKzvdVndB/mjVCtFTswnQaUU0ZTkPxykXyLvVVEOT5xI5LnHo0O+15G6UypZN/+SFS4Vwk2QOEox6Rz3xTRRhodmoqrw3BLyuAGW4cAjXyxq5IJ6Ni8cSATrPv2kRdaSIeA41l3gnzGKLNWovCMxzRZD4yDW9qkWvHZ5zogD0vE0kND1D2HAXn41/yBZL4G7PNFesBm/mtGLrc7R+ufr16qieyq+sWdnrxGW/HhRJpNTzXhAZY5pu19oxBZ66FvItqj3ttpAbZgyEchP5CRZXs+5P6k5mLrZDhelslWmOtqLlwg5QnXibq4Uq29H3YB3Xypao+KfPqd90veWXov3uPOoy4hrc5LtyM/hOcPbFzrl6vdZ5r/XKXlTPhSPW1f+/vWPbcdu4vvsrWPUhVEIr2psvVVXAG9uIgbpZ7G4SL4rAoCR6rVoSFZKyV3UMJA3gFk2aixOgRdA2eQr61qaJG8CJnT8o7F/wl/RcZsjhcIakpA3Sh/jBK4mcc87MmTlz5sy5oMMRiY4cw8sbh9yonL+qP5WasyaHhwP1BbyKQSySXEmHnOy5piW+CHkMJbNeF3w8C5cTfPVMLbRk1FrCOWI9jYJKFzJtBklgV9LbyMq5n8dfc51eqKfpr5ITXuvRwQ/YI+We+Bh6NMBrZcGlkxnH6rWdy7YHStuDTuWUo+QYe69HiQvon0UankNg8GnexAuGdqu93qxRJMC24WlLrjiPO8doKTTbv1aIlUlN4STs+PaFP8qIZaGACVkjIpfplTIrudAT3XxrilOmts0FQh/0Tt8pJkXLBymlUUlq1LXWg6Ep7lqlXJewLrVomgO80ulR6bJZVBhgS+eMOzkbm+1UAZhiPFGFUYL3+XsMSAFJ6XVOL3qNHPZ+g2o9pUpDAGxZENCFK48Fnee0La6Uui7P0KtsEvaiPmKw2ybvxHwiHGPztlki6lTay/DQmKTssgxH0y53y/ptjiA9USFozXl80nEq9xkkP4TFddi8KbjoNqxrqKgfqTp26dMD27xP1fOWxv5UWdcfCMUG6BGGpGVd2mTyKtCG/NHQj2XkJGpHprSPrDWZPOrYlpJ7dKA8cu549eCpbTCU6ErDK38BsBRkaIk2CBiBx9BPUANFl6u8ZetvObqHoLAvE8Jft19rUmlC2/O110p07HKFUcyyUdj3RziTXP6hmTOiplS0OHnPpZergR2UA1urBMaNrhzsh5Tyhyn0BHBPOc4px7XSuqPFrHcL7a+mHU5zTrKFQ2mChD21QcCcG420R3EtI5odaDEKyfSaW2Hr8gcD2uONZhnlYcx/axm7hqhHse4k7hqKvNCNg9Pr85jchhaxDVoKUvYL+kXMRwib4sEKR8funBNRqAuoVfgBlCoDBnpW30VHivwjltyeM52bZPji5hYhLciaTavlSPydLy041Ey5VhCkeuyiR5c7PRIGDM/ZbGY7TgN6B/8aVfoPyOs3yrJqqpjmq2AqGWo5Hem0Ax1fNKDLsBTL4rrY0I/LbFgZcBWVWcCujMd4TEwZYH3xgF+U47dk7NaSZ62hOKNkZyzWtvMHlLLjlZRMbq4lH1NWPFrVo9h0ojIRnBJaPE41rbkyqkLfhPBgo4jZMwGdX5uZKmzcnumddGuWRkdlRPRY7FJsniSLk1DirUYRmbyhg+Gk13Jr9qfKvzpSwhmPGyZyBVF7/jW6ydPOlUAYXzPIoeHXxdCQxli4FZax9fSjFeFlP06CiAobWFDKn8fpCZPbdCSGsXq/i7YnSd2Ys4aVEGU+3sBGSimXRKXgemdsAbkk5STuQypYBlfrclRtR5sXfKcxU25Kq1KYvhyDEqAUdEAYVymjw0JXpnXIFTOWwbH9O81FF6g5/JZLCVzm3YDwF/RkMKkwArz4JJIMmw0W8h0tt7D4GY4FOD2faTyj/qi1OemsybdKjRiy2d6sxyPhrqW37Bms9VxqWpGcttGoZQUwqvEVWUgFU/TpXWvVYGoIiitgx19ZmxtLAsYO/IKTnVybPIqwQWdH9IeKSO3FGIaYdwcdKOZXR6Jo0j+L9aD8gZ/4qOqGXGh7CloxVbVC9ysAeHgYRBTw4s+ScEy+HDpQ9Lnvh1E0QwcqLNN9axgHzmwSBey6RwkrMpJB+QumsRMHY5hzw36MKiUGEpl8uJReDSL/FpLO1rVYhDVwRAMlcA2iGE4uAaVDIA+y1oKrSD1DpUJVBOOLAmu2JNrQYMGK8SoyHhZxEZWOU6kC3ReSDte6TQjabWfLuXHVScyWM1lmdodpNl8l5c1FnXPVvNTQbYMwTbGoioIeiGjU0e27E2sgacId+nocjsGWojAw73cDHyNiRnOq1AsrDssYw+LHMDTn5kZr7exJ+H/9rDOgJNW+NPdpq13jgFCyjNvdpUGjWbPEySg49Ptz8/DndDQ7IvMaKmEB48x4wN9rhM436qUFsovnnFJqVyXM9wg4ADBQ65vrnRMriZlUxKyW65fNL5mvHPk9Yy3Px/cf/wcLIeiFOu+zGG007fTXkVziOiRW7z92/VuiFa9X2+UIjmHxTsR0H6KDX+5mJKMITt+CBo2cpsmFNj10L+sha7G2y5Dy49RPzbsIr1dh68bfykPR6wn03HDiO4Pd8FaBvQJhkc92ea4e/mQRAl6jtioEDUsVAkU2DGWN4TjwMYKiP/Lj2LkwGCYhxq+N4QiFf07kBYCUJuhWTlJb2Gucq3BeHyqBOoUX8Xy4HR45V7mOaMmbv8K0HcP+y9Pz4a2Jc3VwtMC78/rv9haA21sAbrIA3GQBuFMMOK0zwFEwoaohxXf3hwARsIocsfRVWeDTWW8Eoi6bA67kLjHXtiEw6zHDfn4K4D9xgaYuaefpmx9j6t2HLICzdOxP3hEiOA/i1eGAyiBsrmsm3heD4eF1hH7qrPbkMuwt49l4D8Pr2SyOH92NM23POdXWFx7V69kRke1is8/9BgsSF8tePwoCrX/47nYYDUSNFtFa+aUFmFFp2Q/DEcf2acivh7cuTfb9+EbPj8yh3BfDibytwI+wtwWHISbRg6V+9qLWmf1wejmMkwxS/qnfw703CkdO4vdkSjjl19vOeawd3aU/3AGA6GVjvXm2rdv6oDnllEeRBJ8zoHQn1Xj8zyxNs767yqaHQWhq+ZGe3dHWnmoGmyBoHvSF6oYwCC3xNue6FJ1odgzPmErjI0lAszjgo+CX/hxOfTv+JBjRIFGxKPy2rpsT6GlLMIMhb8+ShJKafEKp0NMoMirl9PTuBzAJ3NgLmt1f7M4mrgt/eT22zs84dpSOSO7JtWaz6bW99soY79XESAjXFkL4qZL0O6tXVdZJzDOZ69/aMaC7V41OdG4RbPeevEM56r9Jy3AB0veULOZP3rbi5cSahJm7uW5EjOp9OJqNJ3CUmLj8G198IT3o6SlFmosgClCYVqcHckoeESgYAH8FMYwL6s+gMD+gUftO9MOakz3Xm22AmTt6NKuHTqUD+rxRo8+5JusLcAf79R0Jm4eSP48ef0Hng69hety1skYk7lQqyO/5WD9AMGpzQRpEOnqmAAhSyHhyV5shAueF12fDKRWzojm5aWbqcALqZ5K+q/P1nmShsfcOsvYtmLHvAxnv5oi4lIdbh68aKTBKWzVYq7fSuZvqPXITEPoQb2ndbEO7OMQ7l8t+dDicdKkqInHy0N1qehQaGVOyG1S9u1imDIUfJfx9RLUnvqaQ2t+nqX5zU17fGw29T+mEfp9aQlo9ZI1JlcrWybkrUJHkSBHTXQ0LMBMBsGflSSCq9J3t4ii8pW5s6NvOn4Sqoj03aBbbIXRtrCgXa+ugoGFDLnYt1DH1O2ojqA57kmmysKVg4Vq7qbMgJcw0rmL2/w0riOAOIALrgNHfULbmt8meWzK+WPaQ4pzRc8ZjpatZKAZcgwYGReievvl5HYyEyyOXnSJGIyNTMirVFFB1Ml0q/8jASF5RvFZF3m5n03Okmwh8O7sAw66FEV8dd9ud4c83O3g9jAS1hDDgYoiZw0D6o4ta/v58GrR2gqhPMmJLH5er5EoORyv35FYbBE+bVCI8ORp+zvOQKFBGk9yH/F4wuo3rqdv478dXPAeW5rcN79wsCZGYLjLnDqtdRQBAi0FBqoHnwIJn3YZn7m0U8Ih9Ibx2LQ4K28GnZDJTNyNMRQCCTtRofAtUGdgqHn9pnagXMKj8JQLuykt06HCLrKde9sucfykuGb0XTCirePQ0vz2Ix5bdzz/qqoqYEJ4PQXZj3640PHMnzo2Gh9DkqIHkpbDmZbAOKmDNG9Vd9Y9YxTN0Ex6tm3jsg7pja8KaUH4Z9I66NNvX2zDV6T9aBr258efE/HZienuxyfz4Q9Ix/oU8KKyaDeNs7uGqMT6yAj8wLBULcFwqGwv34nNU7HkmFXqxaUSUHLGutgBwUy8swLEXlqXQ63dLT3isdX7Bqp9tMm/7cUAOWvuRP4nx9pk3wHRd9worvTfXf0kK7yQ2aSBpH3crTm/LUs+b6fdFfoFDvT5rvYblCo+MK7w3BnZbmowNK5zshbQ+12g/22zXmmz/gKH7Uiq19x8/sG5pp4wzj7AaFEvBwHHgx3Bayrj4Fy7BReYd2mb+gPhVxu0gxMvczlXE8GAYJxmcz2D2vkXK2331lK0COj/Ei4DeLAkIpFvJJEEsDLuxr0gALDNLTyfZjvP07gfOmhjG6s3yJKoElvk/zYAyQLZWVAMtgTmZK4R+tAChbY+MLmZCVaAfLgR0rXr1THB/PG3iyRSlqvHJBDdIcxsUlqfN/aC8rHE3rxthTibeWFjkYD2YRzDzvuJbRrJkw1lZmntE8Tpb71Uf5OquM0HQ/TNGSSAebxbBFA8DQVh1piOrZlz/QMfngNUOcJtwCH818qdIK2by6pJkLpyribKSE909TIIFJ2XMtvWuTIKFDALpgmV3eMsgm7BNg31lGM/80fmhfzgJY/TdcQ3HrCo6VAO0tJeJSkB2cx+MaAKHoCXQfWzqIQpVvG95x4pwexav2E+Sv4hHleSI9O1Sg+qFI2DyANDvoglgGcR/JzvV/XQ1pmjFdoAmLTuP0advBey7gQhocLZFqLvt1C7eS0PYRbz0KigB1iIIMQa/HrpUJ8BUe+q2j1azI3mz1s3u1bZQ8fccoUGY56BwxRBK2wOq6IqswoR499kdQyyLn2lGGDpz3neScHpyFNwEqp78STyQ14aUJg/X+QNU/lLJC0rMe5T5/f2WwxPteeQ3FefiAlzQBIQEvgXzBu2fmDCPsKF7IPuQnEeXwZ0onLaS6fP0N0pajYKPv7wB0sQ1DW9BN+M78JqGytkoGY6GE8kC9Jh6aTKai697fUA22vajuJt9bL0SRJRM2HO2/f4N2CDCqMuJQelzLPKMSp6p17PAuUc0oP9uOXRp8YUUXsIG+uSPxMDfUeHdlG9U9KwwtGRVu89b5Lfka/MVLE1kEdbvbRXspWJkWgZXkD160jC/nzfb6jfOsakp72L8SDVcqrtbgRlim8qZjc8ULFgKUE095if6fMi9ozTWpljuNbyDtPlhhwmni8KSsxFmq+YiH+RBF7jk3s7udOggb8uJfs1x05fQbTnvNmD2AC160uVbtfbgq8mHWntNklr5pjH6Lu8e14PDXgow6/ZCQ/fSBK/1XxhRU1f5TNlGz0WHsROUDWTQwvcDWLoxqkRdR/naQr8gAQ4DHuBdf9IPRrS+O86LKPWbHSUVVaFzeeps3vns3CHdAHk1uaqbaVkHLk1uhjeA4NdnoMgNqphOmyE3cd3LQXI9HPC3qDkI0KExCaCjGRWMvmOMmzJlAL5jlAHC14RdZjWvfmUgUscnGgpOhYm7A/7GIT1yVDigyOr2kkcrokoN0QQmh88L42kydwUCWF0nLGFx5IcSY+EDOEi9j9ZWW712g0MaNZYFoUVVc1DBaeG4NbK4ok5xcTbpp7GmnLe/JHIDuKoNCzdxC7nGyCM4n7642Ljx9JPPqFjLxWgIu/do7sJrnRr1jIwXzqsGnKRxw1JpLmAwSCvTJLHVYl+d44tw3eKl/X3ypHBXfNws0RBcmiRhFlCK/g/ybv5HTpVzquhacNys0jH8yJ363ClYMo+bOTqC1MJN5l1h5P6RS2WRFqV0lWha/wdqtqZeFRRuPLPS59sO1V+8SdknNrYKnqEauv1h/4bzXNeROmBFnxhHIrDqXstLnAvkECe5kcUYY3XQxLdsbFYK3bcsMDEjgh2YVPBcThRbbY+aC6tkcVFxr24g9NyrXDUIMJetOOeNN6yBZFYU8D+GcP22ArY9Q8EiK7okQ8HKK9uQ1aCwyoDSmop0/hZrVXktwwKlWyrDFZuBoTRs0B+OYZECE+JgYF4U5/kdzFe6g6/xocxDn5ie8GWPWxdHoZ+UR/fIVEOIqdl01B0DCOY8a8OJuChsCXuilyVgkw/Yhd9LIVXuNo2nf/3IUe4T8dpFeKvQnSJV0RAjhzkQ8Eaq1fhBdggZIS9bmKu43LaUk+vPIljIHY4JxqrDwINJEKUv/KQrMjHDe8Wn5iyEs7QMSOlsLjiDSTd2C9GF96ddk0/Zbc3WhiEH7BTY3Ti15SmOZd11T3qVdU97JmvcWruprdrpEo5jW228aV66pWmMp3ogljqw4rpR3JnKzLqU9I1MTC/6MFFg07qOM1A6Q1C/+Qvf3lMDk91SDuYZz+z2qnm9Ipw7HafXemEEW/Zz3etpmo1ep4p4uqVYqQMU8NPd2GiXk725Ktn5+Cp0lJBycjyceKnQHPtH2Zc0RYsAjATl4NwWgquLMIR06yIIkoBdFqpC1u7gASiGKX1p0o/Idbzbbm1dNnHwTieN3rtz4n9HLmQqruYCAA==")))

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

            clsid = "{1B72DC21-5C05-4531-897A-A53353BDF338}"
            progid = "EnergoLogic.VisioEditorAddinV338"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV338, Version=0.3.38.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.37 -> v3.38",
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
            progid = "EnergoLogic.VisioEditorAddinV338"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV338")
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
                "progid": "EnergoLogic.VisioEditorAddinV338",
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
            progid = "EnergoLogic.VisioEditorAddinV338"
            clsid = "{1B72DC21-5C05-4531-897A-A53353BDF338}"
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

