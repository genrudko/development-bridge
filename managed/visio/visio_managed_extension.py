from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.124"
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

            build_dir = workspace / "energologic_visio_editor_addin_v326"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV326.dll"
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

            clsid = "{B0DB7395-E237-4F35-BED6-AE59C2C5F326}"
            progid = "EnergoLogic.VisioEditorAddinV326"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV326, Version=0.3.26.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.25 -> v3.26",
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
            progid = "EnergoLogic.VisioEditorAddinV326"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV326")
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
                "progid": "EnergoLogic.VisioEditorAddinV326",
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
            progid = "EnergoLogic.VisioEditorAddinV326"
            clsid = "{B0DB7395-E237-4F35-BED6-AE59C2C5F326}"
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

