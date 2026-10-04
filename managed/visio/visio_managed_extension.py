from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.127"
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

            build_dir = workspace / "energologic_visio_editor_addin_v329"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV329.dll"
            helper_source_path = build_dir / "EnergoLogicTopologyRestoreHelper.cs"
            helper_exe_path = build_dir / "EnergoLogic.TopologyRestoreHelper.exe"
            helper_source_path.write_bytes(gzip.decompress(base64.b64decode(TOPOLOGY_HELPER_SOURCE_B64)))
            source_path.write_bytes(gzip.decompress(base64.b64decode("H4sIAAAAAAAC/+29/W8cR3Yo+vPTX9GaBLsz0bBFUrLjJU05FCl5dWNJvCK1FiErQnOmSXY8Mz3b3SNxliZgW8l+XG/sG2cfbhBks8nLQ3CBh4fIH9qVZUkG7h9wQf4L/kveOaeququqq6p7hpTWeVkDFqe767tOnTrfZ5RGgx1vfZxmYX/x1Eh68lfiXi/sZFE8SP03w0GYRB2txGoS3IdH/W0U7AziNIs6qfblynXtxZu9eCvoRT8JsBft21vR4MfaqxvhNh+R/mE0yKJ+6F8ZZGESD9fD5F7UCfXuN8K9zPAKmt0Z9YLk0t4wCdMU56uVejsadOP7qX85Tvr5t0t7WThIo62oF2Vj8fJq1EniNN7O/Ovb2zAEWMQkXDx16naQpmF/qzde8Fbi/o8iqNcLm1kyClt35I/L/NdGlMH3xiVY9Z34rXgn6nhYKfYudaMsThrmWj8KExx+szHrn/Pnf+DPYrlTg6AfpsOgE3pSc9Qaa+zU/ikP/otw7QZBz0vDoBd2vU4POvDe7I3CjSDZCTMqxIrif8PRVg9GBbU89v1Kd9H08UZ8v/Q+zRJawUF3GEMZ9v3gVMUwLnV3wiuD7dg+kPV4lHRCw0CMHU41C+coV8Je72p8L1zPgiw0DxOL4CToh2McG2HSj6ADw3i6MfwNvdU965dx6ctbUZq9Li/iBe8KnwK+9Za8QXjfUKrZqjHtG+GwB+DVDwcZAPewF+IJdawBLWhRx75ftFhdGFyjYZvrrX7f9mnT8Am7hnMOSCTsXoUzEyYr8cgAELQSUPiCVvpKN5XXCkuIJXKvtmim1mqXV2J91AF8lq4l4Xa0Jy1IJTi6D8zyoLMbJxaYvzhK7V8c8EknsRebT9lKPBgwFF4bMRi3BfHqBJtBdSq30L2a+cjXcGwVmGg3GIYTYMTpoFmcd5hHMOiEV/v5NOjv7fJVQ6/fHEXdZmPl/PLK3Kur52dWL56/PHN+7tWLMxcvzp2bmVt97fyl+fmLf/ra3EpDVCFksQ0HdmM8DJvQrvLCz5+upKujoMdrFXNmH70r0gXE7p7lYaQtIgcB+LA6GkJ1wCJvhduZvLGGIjeinV1LGUTI9hbwq6PyeogEBx4k83dAY0GU4CGGo3kvCu9XFVseDntjy2TiDqyIZRy78f21YBBahnFpL+hkQHGkYdbkQNHdu9pvCwjpjq/2jRWXe9HO4FbT/m3T/O1ikIYr8XAsetvay/vaGuc/s+JtNra2g1tw3HauhkE6SsK1KOvsWlY3wt9bo4wX4u0N8cGyOCtxnHQByWVham7z2ggwtx226LMDuOj7zaHj42p8f2CDqMGIri8ETf4acNpqmMKmETltXm+gZNmtChcv0K3mxleCYQarKd3R6wHe61bgxmKXfjyKhlj2chL3XeWvD8MkECTCyLK0nJAI18IBbMHORjyMe/GOZbyC7lXRuBv9Lc/+6cUfzK5enLn82p+emzn/yvJrM6/NL78yM//aq5deO7cye/nc/A9y9LeWxDtXugo97ksU9HIXxvgjucIKXhk5Vmyqj4Qyl0dZXMaVphvHW/CurG4o7MZ8uxYuHSbRPYBeL976S2znbjBk6JIYKGuhbvfK4MqAXSnlYqwv5IS8u9vwb7kELHs/GHQvBol3dytIXAUujrIsHnh3s3hnpxeyp3L5u3qFS/cAzNK7KzCZd+n3D+FrL0xEQ/yx3FISBt140BsXk03Hg846/M9JAvZeoSJ41a047vHyHCahynbQSw1rxCGTld6I3w0HOg1rKkgUMxaMYPBVha8CNRjsUHGZSTz84vD50YeHzw8/9x0tDNkE4MIZ4YG9BgxixQB5jTXoEkvftBQnikrhgi7kdemRSK+RwvnIVYlMExUuI33JLmAAWGtFbYg2SlmuYmdY8makItaeBRAlRdmrQQqHvHKspRqOLQDcgxPKRyZQ4Q/DHiBS8bXm6ojKa71gsBZku/W2XdS6EaajXuaoh+StXmll3OnRvs+6y8P6A6ZeQ6mGpXR+em+EO+Ged3cH6Cn2kx1e+t3Mq+F/f9ZovvF6Rhz1hdt/cbrZat850zpdkPJp842Fd/xbUCiJ7+9deKd7pvXeOz57pCf42Gq0lTapm+tDJhi7sjMATmQFyBjvPfULQlYEyLxVPZFOPh48O5VT+ovy+MXAxZD/+Nhj1nmNe3HU9a4Piq6bHPyXi0ul7YV72V1e5GrcDT3pd1ucl2VxwbRhIba95SQJxl5nlGZxv5X3uq8MX765YGWWTfcYKydfXlhSPKvlsmTs7QNVPAj6MLXdOM2UsvTGv86Gu+Rlu1G66B140GNnF+odKG1Rb73ehnSFyfcH/mek3g9sSwyUagEQTVzR4g0t6o2wD+iVrWndFYQZK8/qV+J6t72mchF7pxlS8b73Pe1iFV9apUZoE+RGfLqkvZkl693M1kJ+Mq8z2zMaJdId8uhO0xsfmM8oHcYpwC+jTXz+DMtu3T6pWSBW8pkR6eKvhkiDuqqzsejYV1oGsWSOIny5jSVwTKYP0rBVmM8nUIJvjbLTgJy6gGlaJ6ofLcNg1VOqFrCCOx279OawC5ixWQJnZRxqRbgwkmw0FJzCRHUvhjvRYH13lHWRwzLXLKFtsZ6AfiynTIjJK06Zsk5iv7JduHMI6V8Z3At6UTfnky7tdUJC0M0GUwIcPjt85B1+A2Tel4dPDr8++vjoZ0d/e/isoaEd/C8JgZMbWEh/9egZZkyrZURwlgUQSwTdMTytdlYQ8qm3hf8seU3pXQuq+dKzWhlQIMAxJ02gtqCZJPq3YTok/Axhf7d5tTuLFpQjlfUBMJu8fNu7msYworU4jXAJ/T49AokDX6IUVT/+jwIgR9oecZqL8mLWO+mAR7wm0kMRfJ5bhD+vLzEkBHdolsQ9vJ1RVO1FZ860KqCsWENe2UMGR2ntdnRn0Qid67TAPrDzwNw0O/5GsNNWFtlnLKDPAKLR9lgNPIdBEqWwOtdJbNJrle+H/eobAwYK8JOWuMRFY9UtoKXeLX86cFwv5YtuyXad6QNr6oNqqTuEIAOQwp+Jz+/nj6xGCWDcjwycHMDko7CGIVzHSVCrwJZqxbU9dVVez8Y9PHd4IugNvaATQY98PM7+gZfOoiEqX3Ech78BTPbk8OHh7w4fHn149EtEbQ8RxwFq+6VXd1Jc1IP0GqxZ1V0MaLa2WKF5fcDWhb60XINg1M4ZN7VDMGMbrg0LK2MowaG3kiU9Rg2SoGIFL+neargdAMNmQ9ZKobI0Y1LKVSpr6bAg3viJ8957zyvRbuVTKGgs2LRC/NREslzbDOyAE4N8fQUliIPTyXL25WJCzOrlBE6pucQyUOK4Ee41sCou4Frht3D+gaS2M3OtxTKBYldu2NqpaKbQfxQN4LtaY5DUI4baFZVl5UlRW1GpuKobdCtFK8VHku22GfDWbZBrYYzNUUO12hMKG2ljhArHuSzFOYGa8gkTzTS+/ce/8wArGpEgI/w4uoQCD/2Gs7tauqFiCkpxVo6UR64uhBapaIXeNBt7jRoVNw0VxxUVp9E/FZ1gbVLibiTBIN0mZEJAhM1gfayImqaqIUyqunIOgQPeJGNQ1V7SCVXVYU4gduvFJNjWCuaaM1frigqtaEvVrLkakFRsZhidmfNn296sP1ujnRImkxuaoB3U2ZkbmcVG5mo1wnR7jmZmKtupoQSUUZxUWFcVOgG9pDOUwLisT3SCg1WxKMGGXflYgdytWkgFz9t1la7mS0pLC4nTi4H+axZ6pZaNI2+kqG9YanhnFPXPGQ+weYYqI+kTUyHRpz7T+0gfuSZIJk0cx9GiVZWPpk3x6mo418AWDXEjxIbCCxemNayqSskg+9uNEib5nFLEID4PmXYMJQpEv4VryiIR/Sts8YAK7kFZErPeYyeEAEPonprYWMvcT0o2h8IcClrBsj7Z/6T+lSzsY0tXVpvYh68YTlkazBT7P2jwzTCT6l0co20VjajtiUavdPlv/AaQUSyiRh/DArP2qSC1Tc2pnWq1Lg3wMhEfLydhyLvHDWupVf0rq20i1H8YpLvrobCv0ucq6BA2hKt9bQBtr7EWDW41Wt4M/64uc/7d3OzY2exmRbObDZ3hLnSTKbcwRckVLXhuU4ZCjzC5OG7CnC54ey1gcrGazlEYTAN5m6o5JseC8lu+6PkQdCUDQSu8ryhHI2ArdfuO6J1IEcUuLi9hnAE7vqI202Eq1XmBGpVRClCnKtBIYdDZ5UKyLsCyNMUKeZh6WOlw2k9q1DXIUeVlIjEPDlesESA9GZyoyRxE27ZvCIcH1q74mjKRUq4jlltpWevSklLN9WCbnlz1NFElLi/gQVohOuCIQklefnPQjdfxSzPHL94Fb9Z7QxElLXiH/wAMyjeHj4/eR0MELtM5+uToZ8DMfHX45OiBB2+/ga8P4e/zhrcwTf2v4QFra5Mh6Ucn7vcji0SjWhGG812NV/rd5tzs/HnDIgto6orLq6tcNMxbwM9vD7OYlZa2aIEJd1F7kwM1ezWZYuDzw0ewas+OHhx+TVoC4hW/xhdHH3vANLJ1hZ+fH310+CUyl/D/M3j1iUl5UOA96J0hvXxWiGiK4dsqF3gGWpgAyVgOPBtGXbGy2CeoNc2Rx//yUdvPvGi9dODVD7bTfmCad6EJmCVNgA4UBiWAfRkQ2iQMYlkCtrS3ozutVgGFHAnBW5TU5chkkiYIF+E749joRE4A348Pf3f4lIEsQjhA99H7R58AJD8/fOId/Q2BM31nRlAeoZnHBeRzjEL1Hy969BZPzMOjn+Ih8Mh6inWA/z9s1NoxTncgM3UvXOW2GwJugKCE5WoOkSwY3p69g8SHepuUSixW9DB29TBX2cOcsYcCFTGpxh60ImaEQqDicQwQ3e+blgYIvqwX0l4tbwPkvBnG/RAw7spuMNgh+WkZFwKgB8wNYdAlu5cC1unN9W1GOwtfhZYZn8ptvO7N1kSbh79GTSpsNFwsiA6f8bFI1w2Cz+c5BB0+bjhuBOiNDdOOavghkYZr2o2CmS98YHAVFpDvQwNW/1p4nwxZkdBkCrhm41pjIjSK26Uw73bs2C6GYuiC6Fnus9HM14CzJOJD29OJcfqsOIQY2gbOMtoeE/1rb9nGiNTqwUCS54ehNlXOl9QMm8bmSjd+6ZsZZdaBayuuFXj0G0J0jwh5fo1kA1IIHwIiRKyHyPERbaobfyqHpA4yNQ7LsGY5/VbW5EkSFK6oRl1QkDVXRj22NduxvzJKErTtZK/axm6ZjP3f8wk89I4+MEzzobc/e+B7h/8IM/sALxVvf+7A+/ann3r78weLWOdLKPn48Atv/9zCrD87e+DBlJ8u8uUDChWqYUVs7DmnW5/B/c3PHLbwHC61L4Us3zzaEsFdoqAlkliSBbQldh+Q+F7LZXe1jeemV4c8hpNXMAPELLT5prVqWJfoQqBcn/QH+c8Llv/IQhkvvj/gtLgiq1HFGscVBUEn/+FkPzqM5MbsXspN9HHR1C8GGxwGVLic5TOtO/kKXru8gqWqRF929wwfcOrdcflD7UtM23r1JC+euJjgN3RbEMFOKPLxxIKCei24RAU7gkI9lsggx0kVxF8VIbsaZkCq5aRUYKJ2jGS3KvpzHmGBw83CCkH8I8VvJfNLi1a+p0/yZlG7q5BeoQWIVuHUVBynAly/4DznI40xIEPMz44+Ahh77pFCniQwRz+n8s9LkuRqBmlCo204hUmYZkDjd8WBhv24wV4hChIKHOqONpeLhxFtnQQsvSBqjNOS8vJPTYtV0LfPudgMxQYfta1E2+HzBW///MHJk2gWJQzSa+3S7raqLeebORR7Gd/9S0kSJ1VSck6OASE3DAepMONeEY+huPHSgucxenzt83vSJO6amnuxnUeNyYA9okN59IBI6q9pK39p2lN+VzCZ0RMCjscIf8QG0En/4PBzYI9+h+cc+aUPsCR62D2C+jgItcpz9L2TgBCIeQ+4deNklCU+A8UOf8PbeoxwvoAV1b3zuZrXDHtK0VMVHFYtmly20qogxDmlvfyiKO2JMJJiQfWpIuR+iFLvD4AvlVA4X2pNlcc4c9yXskix7eXUBuz2z3HDjj4qGuEEeEN2v3Qsc9l+4rvN9QhOQajwwj04/8wXVmYkhApPtgwPE2EXXvifVav4XCSpFYPlzDWxAjVFXBbZzWl+sV1Jr416vevJ27tRFq5jOKWm6KbVyteB1AT5+8UKK/S8FgO4C95c6yQR5qckXOBI73MD7ZJLPQGCCYM9O/orgPfHhA4fHH0MaBYRoURzs7VcsCI2vlj/BQjVJlxyjXaxMmX9OLncNA1eAjrVJC4mIQrV1m1pyZsrtfFGUepylKAivlRkobZMtcw3BD104hwLaxkjDXxscJbhj/tjWCV7EwB629oIW2H7d5unh3Si62qlygto4Lwm9PIoHTCtk6r1Phna1ziD6QjifymOr3p4gbz5LRIjyHE8Iarom8Ov0QdsAWlkw7UlSRyBaLbRsKZ70F7ySrea1FAez54VwgePVjqJOnAVwsHJdr2Lly5fv3HJu59EdJ8Eg7F3M4U740+oq9T3frSxio7TnSzV2wzvhUjpFjMEliroBllArYUpNNYF0njgkb0c4NNBPEp7Y4/2bv78eWQ69TbhyMbebtDbniE+oQlFbnk9aC2BEZ/FCFWb6G0RwkZ2wm7L5xOjoSOndT9IuqWB9mL0bc92g8wLu3BRb8OZhEdYDR4dLCfkvGEvGPhVlkPRlIKdSpOkUI1WdnEU9bqSQaYczKwM7maJlzzW8teZOdO7U65LoY4AShMX/Q/ptHDy/wPLCXsBdiUTXgeSyKC2kq4jNHQn0bkZb/O7GM7hSEinpyewLJcca1xMpz3dtXMi+jJGSP3awFCS9y0ADhMdfMnhqUQqQT0vJeMTpDKirrUno6HB8W8oTZVW+u4IhTLMw9ywSBTWgmZAUSI8CnNJIfs0Xyq5rttFh9zq93MRfy0xa2GYY2xvc7r2Nm3tGcJLlo1FHTerKeCkxdQUzjHQ0nC0cmNTd5McncvY3VxBD6JTg8CZhsipQehMS+E03ERuva1wEDp0ZMsn1k4idnbD7qgXsig3eWyc/CTx88zPXB01rbdfqYqtJ+qxO1wcX/BTWBBGBMgcKmD+bwHV1nPKGvBiiHJpzOmlabnjxuGvAHLQHOHwM5LH/u7opygMQsh6KrhftIf8jFD5YzSM8LhY+BmK9THMwuPDZxrMlfjCXCNcZWuYlm28RN2+OX5UEcwgL0C9+MxAzx6eBNdQVLE5uddbw3/la0Qr+IxkqCTvVM/hQ5K+Hn0oxvnt+7/yYEU/YHaoR7+ERS9MeqEONkG+jE+k7YEGfuoJ10fYrU8aFoHAgEWAkM2jycC5DEd2IQ620apiDNna8+5W4sG9MMkKGQGbq88CRdhxYMt74w2MmmXdrIPjDbv+XpromeekrHjE5aWMmgGofwoHh+8lKlOVI1TaFmMkNFZ7saIgD+aB03IIdP9JBRHlBOPDNySZJ00AE+zSltUXx7rcw1w+7YZ5H++0/QtK5+AaxA16aMBOyqmb0Y8OF+79Fgqw8v/r/yHeRywP312l1v/62orQji9z/k5dAyeN95GjintdIlwZcncZ9tgvBmpDm7wu+dS5LdbmRAiP84itF6Ga+1JaXVi+r1Tyja+wjeVue0c/I1LuM9gYxeH9KV42qq6WgXAuLpEVdIoZInDyleJll0aE02WmvWG2UBxlMIMetJCXOLOinmlT4ZuC+6RrzLitRTUeOCW3xzcW5wZRUPyWZhLltqCCCpvGCptGmchukArLFGHM4C2VlvyHRamizS0U1jRa3ve+V6880Mb2MZPkB2c66886y2y6y5Cgr6qEsQ08dobVqKIt5LFri87emyxw5MmYKm1aKvHZaVXwrb3CprFCqQdNWlGs1/Jgh+LclBZMwI8ogOftEipt0qIn+tZoGVeavtUj3aRhFOTbKg2R9+Vj7+nNpujRZ8FOr9xUSTpEjUkUFETdosEfRJB30tyYxNBJ8BUr9nbUpRCr1hUTBUwrRt8sK0bfaq+Y6EXbfNGBe+KismXiL0e0TevFBv427gW3zuO3tSaTOhn5MvdOyiks8lB6QB5KwnCexe5TiOmjBy9A4CwID4k6tXqabAWddwG/lr+fPetdI7cfltPC5/cdc6iLUq8b9qItpBPC3ti7dn2D9BldHlOKNDPxwNQoc0SYn507d8b3rg8oyCrqeGb6wQA2titriLosz5QX4Y4wOUrqBaZWYTTBGCp3Q5SkhIPOGGZPWiCmdunESTIaZqgS8kaDBEqj1kUAm6nFkKNzr8k1RS2m4MG5wUEBoAiQlIXJd3phUFhceTDQzru+qckNXKEkHp6FoUUJjAxDwATMdgwWAbY6plVMQuBDEhhfvlazQDtmu21To1AnHuDKZ2Q/hqrvjthVbHVI2ioUPnkB5qjCfoDvGQ2HcQJrYN+ieyy0Q+p7fx6GQxoY8wODxeyG3la4G0EPMPNwD71cYI+2R6Ti24G1Lc+f4HqUhgyoFGiyqoARe5mrfO973jqbQlr+2qytjE6UaN/8QlCaKrN4bWBELNpqvupLXoOvlNxUo45HYQjrMIF7p4bi7MoQzcBY4PQqA+PyGhEPswpAbFwZIjrPevOv+OfbjKBkD9ULJp8LtJKD9WMpD2otG66FMk5XnOKJA67KztVyLyR0aticG8kzTKE74BY7Ny+Pkzwl3FSG5ZaWG+FcAecP7GImk1JRaselRQSkcBlu0LmZVRk9Ew7EqDhMlz2AKzIM6VYRhtiIgOCbE79iALa2N4gzrx8meJkgj3IW+Q7fWyZ8OQRUyGVRfYzVGySIgI3XQLRNqvksv4l6MCygR+hCur8L/0RwCaQk2oFd4kGNYZRMhwCzMmLuq4DSYF960U9Cmis7P99PAfcB/i7m0iniWwGCRN1rfi+YmmU2vswaFPA4ERln4Ti2+bDbgF6RjCQ7BhgfNAeXDqL0NEzuhV3feBBMnJmB1dLZLQUUXDyauyIxa3Xx7zpRmGoDnPlpFwySBXtYK29KlTcnqEzsUFuwS5NV3MwrbrbqInqFn8ErTSLr1Q44bzLFtVZib1CXN+oFNw3MusT+UWnJGm7W/yPpv0YF1iIT2iToNmrptskQwHjN150vw4n8+pZit5stmHRb+XDPfE/sHy9ygUnanj8KOTu8/WuSNz47+ujwK65CkoRa8rUo7SrZV1oA9KDumgNS2/WXt9LmmwaQzl3x8EpvoWuDP+e9956xx6qGNkVDm7yhY9zLGDNYCPwUga4SIYLMveULiTtomRkzcxAUmXV2Hk7OF9tQpXN1RN2ZnO9+WUt0+JAgUl4kfldOukiaEc+bdhKjdQKmPcdbAtn/HT0DCndszQasTrSA3HpvUku53FpOtY5j8gkeU6DKxFJVr4SK8UjZdMQ4BO79l5uTINnMRCRvcOp1AY1MzHVXyci6Y7Kvpu8lWxVzsSJa2u/RRIkme2zTJMSULlMjRIAvz3RIg4iJDIS+I8ZB/2STohW6JuGeN8v9AecOfO8i4yoX0DuwUWXTbtKUKQqaFhyGZqMw5WOaHTgZSil7N2aVt70854nrGx5V2goCdFPYKnakD6aPu/HdMWVSksepSLk+JlbUf+qGXLk0GPWZ1Mwhn26b1cHl17TyNkMC98ViTxitG5lfHKWCzNlGxxdmOY8Ms5CECuFoVtg/bDNuIOWyzShTWUoxkDwKmjwKkyMFD+Gkm32abpYKu1DBXoqm8qA/lpgKRadKsI1y8RtAPiwZIgSp4KovcG5HrawAWfNHAwUqqtQsk66ptq7YpV88l9dVKWBB+8XaUmn72mrrS6WLZ0vnooC5Obb+VFBfdbHydsTBUZFYQ2f6DOHRWoW2rMYteiq9KnLEdsL5QLpq2s2SORkTrfJCBquyMpvN7MpMfQ0tCTsLblkuYR4Kfa03BEtWpXp9TNUFn2cmkqwKMdukTn3uuN22PF5SNthjcSnMeAa9lY8eHP0CWLJPytG0FIuYR0e/OPpbNeDEQ/JI/8DMn62gbmo0VHOHLidZtI0OVabom3XSeOpl7Sk885JaAl0zoaEmzqW9tRXKk+byITRsBaWEuYd/nzPAeRQBtAPjsVIZMekj3flb+PhlsbLe0V8xB30yTH3G9km2SqIwYpaIAkd/XUQUAAbz2/f/rWFfSS01r4wy7JXk7Lz5kXPulikhr15MzYTLX9qLl7P2CsqFGNR90YKvMl8HjnFq/IZoQHlf47JofPvJF17NvVcOm3zKHh99WDNmBJM70IlmjtRPPTqlX6ARJuy+FOVfg3DDHUZaU5emc+q0nxyBci2vCUGjfT+P7z/FRST10Q/+Mk64lor3568Pe1HW/L7//dbt2TviqU1Pi0Z1GjViFkCRXs3fSMZrQZKGzby7tneNMl9QojKMKpqFO6ildM2l7cUj3plFAMWhiop4F5a8uVcmz2nK29DU3rYUYDaDQ4VW0dgZKeS/nfVQwsL1c9HRZKHhViM68UEyfp1iclJjnV3gwtbIQkJIx1aKV1eDocniV/FVFNFgkbwW9sKCp21NFvfdbnorOnGFT+VAnOv4WBxV4qi5loxrvYB0ramvQIqf7aO3wyQvALxvhlnxno+snXfrcKJkTYh0op14kEWDkcWhnpjU+wMy0Jf2iDIZBtEg/fNwTO3lNLzdpOANuYHbSqU71koLnlLQIL0Qs0olFidzDsaupyEvGAbW+QybNP1W1UKpFhYGqzGbuF/8p8wzr63wprWaIHbJxK+2nHWrZ3cC/rGfao5BjxyWb4/p9kUXITKzfwR34jO4ID/Or04WremZFq5k0UMzfXIf+gZVFoL6KkSA3KOLvFhEwLDGJO62FhVZrt4oQVCONVAtxE9TFZCe0Ir/Q9kb6yn3zzGobD42JAuWlh/25CvNyeElbcGp2qfVvdb4Uj1op1/SRlhl04rTG3zmEP81vPoti0JHORmKTO8e4XdY5C/JTYUcJJ4UThS56uoZi/2BO4g6rC+5mxxTHPeD4ZD4/iTejnphYzJ3c/OTgRzB64PHGJTI+DxXVE1JyksWvLZPVRjHWl28pCCLjK09ZbDo3Crkrv1RmnlboReMMniMMmYESNLYRbs01hCCRBPOkuES2h3xfjoUNTL1S6beZgPnKmpJIkdYB29aiJKStZjLdrAIzv+mRKDYbAiKkspZNlya1Q3glXm63pVpp8/EzN6Ost0baENlxwjysri9z92CVjpptaNIV3Rll21XXIUC4s+cmSy9dsl09cWFy5VyAwTmxAAGRUB1UoCDFyXyp5hvitz+tBCdwwWmCtXFFxeBqvBHk6oEzM1l0wr5F6uZL5mUZ228odjRLkzBnpWcK2VCfaJOcnJh0YUYO0xz7WTVZFWKBSGKZk5zbAjbz18pKy7TN+I7ZwSE4qR1ajKy34zTjGMXyQPaRWcmpbAZTRgFHaJwtayDHe3/DMRFzetaw3f2K3hKpGf0OJA6rBkaZ9qhvCiM+wcMKe2h85Tj1ljOea0wMsY841KWcdcByG0ju3st73VvLpz5AaK84vVYvG7VDqCghYkmD46njPtCVuyzo4+Y7S35c2BYbmCgnjYscVl+vyEQmOD3Wnxpr+T+GNUJ51fbmbLc2hRekP8X8KU/4/xoEQ77Bfg36gZO0YvIdTBZxH6dXSzH5DetuozQbAd48nonnEWJG+OZd3fBu+Xtzy6QewCLut/2Nr39OfmN7x1+emJx+Ocxhqkn9m6iIPknHT/rYpCyRHsb6MeJzHqTA/dwnOO/rQIVbhVvs+JtZkWQcsKcDLPybe3ZU99kmKdva7z4ElDs31LoGBbO6RMMOnP0Ux5rnb3BWB4AKk+YLhTLfQM1voRvH7MoKn9AtBMiWoSomtl2P0BhrdgfFCLmuwEP9TPpuJv5faF04qBgLerKcfSU10mndhLakj6SxU6NbNFa7Uqo4+egztXpSecFp6A2+w8ZZiHZeUySAFluqTsa5pRvcTWvipSJTYfGk6oKhSdrZ9JRyKmYixBT0YTZl9HHKzchIWwoMgl+UjPVsoq5rOmWXTWlXMtkWnksALdlWq4H43nCy+OAOczCDuZqDyVIN32eAth51l26emk4xmS+eBxr5PBVWhybW5yztThnbRHgVkrY281z9Tpo2unoWsmSp3PcpLRuqKNT+cMgrRtYujVdkGzrSbIkg50+CayEsIqmJHRTM/VrbYvSE83yyoLVWMiARyeWRHuCkBfHZOmmB/+pebjj8HEHL4ezQ98p91YveP/7V7c0pq4N74DRm1cYPUxvxklVnTplYMfSoRkTeuVc3cuNgVwEbPh9hz2muiK/Epz1VL7KRWKl6sRJUXV6mdoBi+0JynvBVtiTQxGyALz+RhL1mxbK3e5wR60BNhetlkxRWdDjykC7hiMB60jExDHTFP4RnpL9uQOSdyhAv4jyjnPyG4vPYYRhPXCCOVVuptUVwqVVxxuGHbbnLB0BEaIfihCnCv258E7yzgDvbCVbE71ss5UqcjPVDJs7IANbCphZpK5fDdNoZxC4kjkL6+OAXa1NtRazJzZDE0ISVfPfYu7qwAjM1iXXP0VJE0vawGTDDNkJuzXAfiz8rinpZ6NqIBe8V8/XHcg/VXbHJddfEnPxWxaYNpddf0nZup7RRfsIukVBCxrYfU6lYVKmwZ6+Ee6Ee3D+rqJNMht72/uzxl/cfme4/9YB/HPt4I70+53Uv3u22Trzzsyd/dn2q+cO/rgxdeTpT80r/JhN8BsgT0j4cPgUAfezowewAp+jLJAoi78CQgblgkxWiLZoX7eL6+lhGxt5hC4aRx+0vbNtAHAmenpCpU0O/d+xXOLHsYcoosPKB0jCzKxx+2Fy+kHLR3n6CPIi+oZuuviVBvHPyd3mAf37IZRm1nN4Vg+fsMyLzuPasM+Ox6ZQZ9T2+BkoBaPQ7pXp461X4RdFPspm+4GY8APmPVICXoPVPhMaTGa3D7QDpxsG3RAZ3blF/vN1LomUoZG4E17gzJm6FEYnGHSjLvPU0mG7SW1Z9Ch5xSJFev7Kv7JqJjD6UqwEbj4qteM0+RbuhFqA5bx6LcqGA1lGrif1QOuEwp2Yr5N3GnjZszv2jNd4p5GnjzMYqZKfWxHmQF44p5VUgX/W4YzT6uFf6ZjpeMSIv2CG1vo0g+PrJ3+TK5keEOuhyM2l1PETi7cJYIl/7Ja9H19IfrB9t4x2SuGb5RCYcms4LpBL/SEGqIealU4WvMPRsBuwaAdYy94RL+dfQcRxfbuEzavQOHprzdolLMUwREfcDMl8bVhWJA/sdtp5sRKQt6o8QDwVs4hxMVzUzg/dNDdYedZrPKzg9RFQ+TTalEbLS7TzM1o/oVteleFEW9Cn1qTyZsYPcpdC3oldoMzPpsmg1SxnMQcYzY+4FYrq0sIV6XkfKTl6MdmOQgEJTwEufZMRmkh9UC9Sl4VEPAZZNIHrexGgyzqNnG58xkNnw7QfUK70r6t5N7NNx/Gy6B1X4ObI+PrvRWpy04oIGdpDLdYR3fyKjYRw+fmGLnlokhlNeFfySGcIfH/NqXCS09qywlqoZX4OXkqAHxHDQycJREiNakkDMbten/5FYxxkgRkD3NUFDsQMN994fQvIsQv+mdYM/L4X9zKAlQvvdM8031i47bfvwK/WG60/bpgT0FNHwkXde4M/v5nEo2F6u4EtN+74PyKSbEEefp1IJjYELUiwJNrBZW+L8jVdXNIsILpLI1zu70a9EN1f8evreetC2oEREXeDBK43+WLjhW5TrTtAANAPHfNiryzus97qDHAhplFgabi92WDcXUNR7Bj+zMyYY6OIgAJ55+ujLfatOdtmfZiJ1HS0zWricM54c4ZlecPUKi+OUcN0N3kONnxMZxSrzzO8w1qyuOUegJIAhWAvSqvE2d+l7E6ve/OtyZI5fX70EaGwzwnb5zEqy4mdMBcWlXmKyNQjw7WHpfR1je+OQZDYAHIbmzSdILcpE04RTKRMLbUJKJB4aew1UENDYmeESFOKnzrsldaeymx9SvtDKbWAvPmQZ871bhlMkCxFN19OKubo5fFX67KA37kbwja7llZwcpXmSzdJrWfe9WIMVyXw4hSSOY8sgzqgqmAAZb1mjqvYzvkb8c0hoKc8fAiSzcY9e7H6y6thgIhqLUKC5qQUmEKmfYEI5MIcKexSMHEbOqfChXHDpBidRyfmVgqIy3nYnMo8iEcfKen7vkTJMUZdYmwVcE42o9Nszi1zRwyreV1aGpqvamjO3VC+frzHwvtVVEWPwHrr+e8yN6n4/wtX8icez/+I5twUnohFt3pqSbM2jBj1rIWyzublQOH83Vz+zkwgU1t6ZPlG7TQYjrOAEYmTaAuIY3Yc5MG7nFDY7F6fQI34PxEuC90c+eTnurnPmFwVFvURdzIpW/6dMA02xYFlh3Ud2Crgg3oh5uxp5rqsXridSQGFgKDdzeqK/LGuAHP7ocBSzgOheNNh/9VtUrHKRjkYMmiVB5vDrc8kHuFGLEK2y/3bwPugAiNOTOKSHOQDJTvvo0mI3ArtNQxpi/CMQDMC8dimsTwYNztolNgpEBS10KqtfUeBhKYFhN+6ACxXeTNdsHDXwnuAMiUwxSHDWY+MhCtycOu9WMSOTf2r0UCMHd+3LGcIjcgoOt4FD7gwJYid+lknqhSVXMrP3lV3QK2UW69dDYqFLWRRVmUdMerw53VPgi54Ua2U01XVbNujOzWcq+EcSOfq4hgXkZNyBAJtac3PeJFF/BhhaoNJiW3gjO9NPgIUJLhNcYNONiJsol9qaqrU/GLDcdjOvtHfhncwwy8gSusw/8rxDDwnoH3hknrMDk0ReYkRVCWHLRG/B1XQzzQ7P7iZ2UTafB61WBLGPovdupyEgk8gXpInasHkV9pZsQCOWsscTMula1KdF6pvEkPr5UYRQ+R26gp6sED0SnHsXIGWpVAnS/p6Gaut7tny/ObAq068sDkztze2pQF2trdpa+/KlCk9a4SGLtNyuCk8gUJJTbNfSyHgxstS3os8d4WdytBl+4+FBt58ufMMJR69fZiHd3oqGTvl5PrRR77HCFGW8b4OXa3rQzFNE2Nw3Qs7ua7972ACz4mdY7FSneSMnVEjkY9IJrdyMqIf9aimGYtrRcd50rupym6LGqcMXK5oNnTm1PyMIqqN1EBFlkYdkqWaLgVXHat61tTqnmh01W5hX74JSptXlu0YJSQVu2mTnqjdVeOL01qFKQ29pgR3rtkEGhfzMakBh3MPCovIfVuPtzwd7rLoOVyZXiZRcBoQ4IliPpWU8T2DbwF6jc+ZEsEQxmx7xZVhFliI/AH2hCfQQFvbj7a6hnXNqTEXJl2IhPiQ5IzC+9cHPThx9IZnBl6JB9sR7oVD7/ldVPMAxzg3GRPMloR7K5W43ufM4F0TB9qELZVie4NChfF+ecwacvdnkhZCximjlJZ7Pa2MUeYiWEDh5MFjQIZdgdvTPFay/oVMnqxeIxsjgEjerAgsIP5euJDHEFY8Stx1rI4mU0dDNkdFOy0nEuWakTzksTMEGrmC6+tXGH6KVxjQmGgWZjKEPEfRvquDfNGIxqfV8ldgEbKwGeYRdBSXjXxNUKvD1gI1OzyfKdN7dcueHq5qm6JapSsIhZiTliGngGsbaZess79AfKzpSenGIitlMr75LJfIYOF8JiKUKUPEzwsVaxXomk7ahcIW1QHAxppWKL4XJF44RODN16xVm34s9+RRU6Z27DQkcSsMDbG4Txz/VJhMipgfQnCx/uMkYzKHtfg+NIip6GZgboTZ5tsodDzjSd835e/n8LvLbRWl4nP+7KTmeaYlIsdAtn2mz/tevhRevixtnixoiLGp2jzNHs2xzXPq0YTaJPrHTM5X8Z0xqUQu985hyXCu2arMMS/GVms6c0E9/r8Eu1LnIj0iJ9Jot/xiGjYCjdBe0crk5/yfjz4hAetTo6EhUqiKlFUix+iFHrbYa377i//bmyPqq9WoM9gLUFqOP1MUQAm0vg4Aq1KBuXIBDF4z68++0qqX7iLob0U7IzSDW1K94BY9dF4tBrsRvBs2X22JFJm0TTUSHjpTS5jN//ZnD2YuMNoE6NSzxeFI/f35gz/LfQuB4zK30Mmhlq9OfnrECzo9BiBrGR3+JvVx0QDoEfe8QqB5gq+eC7dEev058zT+mvS9LD1OCai+ff9XHrJCpJh/iib6SrqVr5SbRYk9jhHOmTwk32nntYkXwVZIdjYKIBrZom6YdpJoKBys6stiYYsXvHyL5cuK9rjNmSJm4EuZadF9Q/cqpYGKvc5/S9stvaMdl56lTS+fUYnPaMk+pUgIfMkyIcEyS6Q4W2FpOcptOjkV8xFdjQLgr26EKaybFwzS+5SlgudvuhjvwUThClMgziPGUBrlwjsD5uIq7xX6vsDrw7/nfCcy2SzOEU7mjUZbsUgi6JMmC5+LMVwcZRnu2maYXovlD1cAiP3/OoIVL7u4iDXhczq9pEwV2yqWXWF48ngKLHB/7rEjHFc492yQ3x1PfCfP/uSNsCyRaBk1LMO4hVErg35Lh/2pjYtIXsG5TXMUOt8N+y/W3Gc17mRxcnKGPt91xpakDltBV08n1nTFTuizQ1kzfkKhVp0jtarD97G+36NN1NCMLP6OUa7sEXxqjYxEw5PIRWTlwoct7733vLo8NkY3gCqtmvxLobLKu6tim53tjeu1J/PT5vaQIBiEAQn12XTf3g0TEY4p59coVlhOx5qZsD0b9zUmtossjvzXbJS+vD84oJx8npgbg/NDvI4z6JY4NFSysZ77gUZd0hLhT1hS+LngUeRP9BrNGQO6huFyLRIm6iRdmxx2imut7ObdOBF2C1cL51ssVkkzgp+rlXjMn5ivicxmyRcFiob7IcfKCx5QbmjD/BGQtHBERx0oGPRm8rAFdFXzJSjzXr7ZMaDx7T/8s96PzrQpHTDaTBs67BvKxuVywvRGt6RUw4YcfeS7gobk3RC79FqrKoCIkre7sFpTrdXkW8yZNFuytuEpDCeQTOtp64rRjAbRj0lTjbeHtViNUDz50Ca1zJGDSOQW0zafPjZcJYObGi+ixWdER1vNuk0d1gkxw1sgx6XUgLEMe5xPyh4S4+XsdM6ter2AOL1y3tPjbB5Lp8zXybJzplhe5JHWLAYX7rWgHT7EcG/RiedyD68gpfVg1XhSCQy/hbbuyGF/zuO6SklrH5MLJWoX4TLEij5nYzRCvm4ATI+SYD3EwDPQ1S8pLpyk3XtccrDn4cb0+EQfcxSVj4+hMjbHNo10CojTsmQSM8TRjT0x5snltFQsA7MYdXGlbJaGUD1QUsqBVox36vg7ms3lV+Q1e/TfWDpbj+d8Qx4H/hWXOAxipocjLXtLPPWgxF/jq6OPSoJ9QZ/uYdDDiAdoZARanWCN8nQNS2N3q1c7NKyV4ZBeHCvDaUvA0dZm0JYhoI2ro09cBxt58y94O0kw3LVcK0rJGlcLds4avB1175hMTOu18QIjxb0YdkVKyZNbp5Yz8uQsjJ2mFrXr502l5S6yfvD+HWk+RMUhQYy1BIUWKFKxstnQTdtUumSpiUVjE8dMOHvWW/ZYvLawy0C5LHndCnvxYCcF2PACntkOYCV1NRrg1cXFFES/bAHJ2QXI9r3lwdiLM+CfLN25mpVHAj38eBQNySl2B12pF70Bil170U9CL8qwTLYbZAXCcjXMkkimMWxNJ+4jZBJJ3kRZQLgXoHGHd+Omt37NmwGMLUL7izm0XE3D3mSAL4ak7olYyr4UM7n3UK7G18d35ptFtMa2SLI/5ahJgYbWcfO/6uDshtID+0GSryp1iJSeU+mG+OZJITfHc0TBql1UzO+2UvqOmw+ejNVUbvYOILsaWHg9CzrvcmoWf/IqxeuyQRZ88ddG6a58Ldoc9aGoRUpgzpDUGaGcg/cRD23hrU7j7Bj3MHJnTlZuGczYxHcB6t1pSW3l8DJgIQLEHAduiz1J78/ML3KUz0i0C9wi02AnYC5f45bE8f5nvSalu6scH8JwmcpZ7Sw3mnZpaneaKx6SCzNqrTpwIweQsvIfBZjC3L24Yxcnlj6JDia3ePtXix+U4l4oO7oK8zctozOTMD3JXaQWNYER14/K49TmiULQ3LaZFywpRXMnoUp3CtYC185YMDfxZcxlC2CFvHtEw2afVNborVzuW933XCt3fDC2CJ1tovCFngAfphGqToChjAbAHpirBHtSlWvoRmmtMi1u0QXcrhD3xlgOAjLH3us0x5aY6dhW7gJNrCWmN3YJiKitGQDzWV9DEFT7jOmL5lZ8LQwwkRMca+a4y860tHPnlCcrDPFmd4PeNgIjtX7Wm9d7LyRKfcVDr9Au0b6cBP/EzF+RyZBnU8tVaYqrxKZbMQK9S3liBSNhfcatCWTvOcxCwc+kBf6KlFOi+gztFdeEzJJd0BjD/BBM0QN8IVA8RqSxX5NtPrNoEjHCuDTsCy4ReXz0U4wJI2HfBSkUJleBkATktyjOUpDwU3r75dEDHtWN5F7kiovG7kWTmMndGpgtX5HXGfTOVKwHPpzm0FsQU5gSQ8C0mdLVji4vSl7gZuN34dvGbPRKYxeCZE8B8LmyndJF7mqsHGpTKcX7zXjoy9W4qy9eH+WPSsJRvU00kzE4LwqDXLWwPXn3CgZTIdt4om6Fbd8e6gz3ChVTueJVKXov3w11vyaXd0oCrZoZc1WRaNskymOpU9oTyUjbTjlotbjfhpxPBDGLeSlhht+snUymVhxgqXGRfMYeArMyEPAJnesiTrKs1kRNfxmfHF/uLFkVcSkwkzRT9BGy2Pu5pDQ+/FyJjFkVL7xOYOx14nxKbHnf6G788sS3ov9KEe7vnf0VI/2DoLgsKD4m0/xdZJH3XxzjXE8yeXDqhOXvJypdn1xuWuBbONb/aeSkdaQiU90oZhN6JXru0QewdDzWLUWyZxfPGXNVOcOKiJXxAgUtpUHoOL6W6OVli54VIcp/EOEzxgZX5c9280dNJs1C18tiaXzjlEyfrDDsPyDzVRLa/afixMgq3nz7GsxPuNG6hQOqNqCvSWyJflwx0GjPWIIHPLeLTk82lKfllk7M9N8dvZuLi3T5XnlJeAgnWh0ltIx9mUQjqKS2LgGLT2ZxB6eOHMunD8QobEwlaRtVsIjbpIS8F3L5WVrO1juBiTpMbnoLdaaQpwhu1QbqIgQTVeIRmErL48DMzEROgBvTo9tt4vaLlgxldAfYInIXtSvHPkr3bOI2CsY1O9cqdoJumG6li3VRfnLXy9qmcixKF4988SgnMJilleEcF4PCOHduGzmx/8Z4au6DiYHzHGE0SXvz+kTr8TAnnYRfeZ6H/iHRTmk5WN/U554dMlb7Ahyr0UBxKxFfvoPnjx0fXGP1CNExxBVis2FEUuXhqlJgsrYmV1/+I9+55zm45lvI5Ocmf+PHCPX0ySCjf26BdxqhQhTbrmSkni7twfYWVuWc5ZcEm5hWdPrLON76SyBqvCRAkoY57xS93myKDtpwLqwXcZHv9MogOzffhMYqAuLizpz0bY1ALgBMp2enXx8EKWkbsiJm3M00THwEj4aF27asDqH9GwgDTR7jtyVapaWHVZfb9pmb5ZWb7gAa5uMhEF9ZiEpjQXHCWpCkYZFLJ1+xPJsOowrXs3EPD/kgC3fCxL29TBbBjvb3vseO0AXJ+aQ8oroWBiWDv/ysWpIv0pGksNwSbm6475h7cdQ1hYAsXy9ZTj6oMlQv6PXi+2H3OtrqWTNZTG5bPb0WVxmQpnJ7MdrcFy8WnVoiKhv6FAI4vI4yA90+ndr237hnAM/x9LR8u4hkhuj+T5kj4KOstZ3AeMcNxFoaEBWMlehYtSBVqFVMQptyYoSTc0V4+cnC/39nAs5sh5cU6zbZ8UoXsntvyEVva5/veAv1hdinBdgUyIdG0zruQftUdcOh9KB5xOBC4nn08dHHwg/kCQ9zyENywKXxMUWEOvrk8HdHv/Q9FmlByi/6FYvXJngdkrFibHyoR0FBnrIoDmhEISn42t7Rz8jb5DO8n0QSOGhDZO3E/fYbxzvnxvNlOlF1nNWMjfWDoUVtaNFnvxCXdHY/1nJIBz5iNUw7cCqBJGE3Hlp5i+jN8ZDCqMG06ngOQrFqYsHUY84pMXBHmolIBn7DUymkG2xrPj3JWp0ZOR9TnfTIdkymM4OlZp15knNBOtaW8iRzIY25AizMbV4Bdc7aaprrmHaHC1tKu1GGiiqj2TLhbYAS5QKVibw6p1KpnLD4MrU8piY7iLxpYsNL5fhhg30x87SsbrXTNM3B6v1aZzXyCz3sKTFC9OC/ZZaHanDK7733eLiKsJcnuKgtKvgXzuI/ZGFvC0fQPK5n7prYPPqoxZI/CIfDcs6HyfkAPaRplYWRBRDyyU8VHARrHzsoSNlbNDIpr834R0eF1SrmAsA47cklHqxzoPEI3BedLk687mlBdhXTZF+suMvsg2Rm3M3lzas1uQ8taY2J/Hmf64JlmG0TUUPy2/eZr+0zg+j3GZEyT+nV4yKmE36CxiXnW1pia0rfqKuzo/imhpUYRzxQuibWyTGDjHcNbvL7L+io8ZjkMsYVU9WKVCHbqjkTTVLEDVEZviuXBqM+gMcWM6ty8n2i5n3CrQZ0qynTGQqGy5b6Xu71mvV4OFGTRyt0uQjMu2U3EnNV4qnMItQ8nK5DN1AR5lfou0txGUQ8ctI1rXBRKsu/WifUrmZbcfast5ZEfaAUhfIv3sZwYNnugkfpE70B+W8ITXUKBFlPwJT3o41VKJ+FA73NNEwickVNi3hdtPjruyEsYxJuh4DWUNu3NebIn6YBGAZdY7PdoNQk1WQJUmLEtSmuAkYaHPWCm17QiwehF6XeICZ6mMKSz6TBduhPqUnuiAlLCJ1eLE5HHFPd4xLFrBlGFrMGK8lhDi/bAO+4xM5CWWwvQoyGkyWf/OoUg8LoJblEm2fr4DP08aBSzgYseLNKB0BJq+13LZugq7uN+OQ6KwzidHl90VsB1jWz/dW//V0q4xwLqfbZYkPaGn6pZ6RdIS1iacdR+3OVpx6/W8jesSc5EznbKYek6nTekEgtXkdaldCVU1TlWcjn7ohGrLv5hsfUG0y3YWrhRywXvHMfrc0vuJufr9f8oktphGSGdJfteyXD0SK8dILBUiVbo/x2OZiWk9Xx+eWg19tCozsKMjC4FyXxAKMZpN59jC5XXDjxFmZ4D3i0oh24Ufr9sBvBzaylRMHAC5jsl00y9r0bYdBlAQfY1SbdQNvs4vC6UQKd9Ma+iSbSb3tERfzGKd3Y01IQcpv/AYkJ003DZlMKgQpQIFbdgH8LNXF6s6mOp+WLa74eQnarfWkRtCIMH2Gg9Ls7sDMyHuJDNkXd6ReIx7rAuIbbHNLZyeqLI92AM7bXsCMeFeGUqk2FbRbsbTamwTCCbiBQvhFuK/Njb0W7XPdrXx4JG2lqfLY9KR5ccXMoV4Xove39WeMv6Hy/4zff6Z5p/XGjzUpeH7LI0tJtZZDl5B3kG1slFS0PXV5fqcHJbgkXjxr20rAmCVsj5q3mX4ZjDStZ0no0r0kkOCXZK7zGjNL6atp3wJCajVaTSt10FGMobGCjH8UYfUYv1UNUDkmN2uXN6j5vnlCnZa+9Ac1IOmY1iEHvvfestE659ZuTNm8npDgMkwykRHbnC1ZJcNfK5EaeLLw/2TrMeh1YkAZvo+TUcHBqQjJOb1uQc9IVVEnW2QzHZBJjOkpFGC8Vpk8TpglyDpIPwpGbzGCloKU4pmx+aduaU65tTAdnm6/IkRB3RkjZ2lhPQmmrvNAE6MPUF7Z1zYLIGDaRS5iHMhEyMZJa9fqYqotcUvFuiEE+G0LWs4AGLm+Ooq5/LbyPfymOscj8eU2XFfdi4Dyad4N0POisw/917J1Y6TUAVmjzOOEXfsN0/qjiOXpw9AsWeOH54TckO3949FNKiSinX2BpPNRkiLmPsEkMvtILg8FoKM7AD8MejGM5yaLtAFgq031+d8jmlR+bcadHlMCsvSwcmq0eEBVpai0pL5k10QArtcG3lLbWVohlKIV950No2Ary+K1Y1JCKEnNzkRnF54cPfe/wnzCIBakicr9rPe/k4yIwtGbqQflahKkH2ml8+/6/NeyLtqpiAxk52CutSQcqP1zOjdEyg2m52hmec4DBZT2VpkoQqljR0c66ljZTwZs1LrvGt598YUqdSwpSMqchQ+lnuI3KiZH3j+KTWPYOt1Xs3WP8+TUdzQdHH8PBfMwSbD5EcDl8CvvKgHMJcY0Gpo4MFfwGCtfUE9ac4Npw43pTGgvTvWaM83wjHPaCTog9FVclO2ZJ8clY1XZLVidQXbTidE0/MQ2ePq1iHVTL6wejsNUUX27Ic+VqWKcJNkvj+mthEfxIhjjMTcOj3qt4/fArGUr9hsFhXqMWTGjDkHhdwg8lnGHWkmpLIlTPFg6pAp+ojRmt+mVQMiy6gU52oyALpgKiQeNdDaPRk/kasZXB6YTfUNJ9ZdhAeXHVC3gtibH5HL4mSEcir59zq7hfc5IJ+9xLe0OykXyTBFtpBhxU0xkmVQbAdgFZbXkPfbnVNlsYa6MW5rwkyLBOQayiGL51hIJ8p/G0LNEoNEJCBOq9m1DrZprCTFf8v3WuFC1p0kNKmvSYDBs+zoO8SD70T72V61d5hgxAGWji/QG/fRpO8X6DZr9Uns+ifmuh79GiSFRBr5W5mThfC6J1gbmPDONeBEBSF9D/sDMnsTPaKgLzFW2P65LKv+ExHvAa+0ReBmPiLzVhinu5y6t0YAyRT2jfOF+5AE1v0ixrKGEIASJX4q58tZqh9xIvuGgLlLVLxW8I28nLUS/0uVhDb5kVWguyXTPSfoPVRn3Vcq9HPlP2JlCA04nxm39z4/Jr5hYXjGJMyogsFuC0CHIlT8QnxJtiDrpmY215fb1hF8e1pueBrXi/cfipEk9EsPd8tTW6/vBrAs+jD9BVC58/I9P5rxZom+n85NM9Y+9zkZuaUgV5NU7VvM5Is0wJAsPuRQ5HABKkBVChi6URJFlhU+7JdFlhq3R6I3bPMhb71NTkgRnpnj3rbeyGRbx6vtDx/UFKutMO5168YZxmMx2htRUbY2uTbIhYqPwsxYt5K+pFP2FaXG6Z5a3tBmnozXlBLwHIH+eTtbUpz3InjPuYJJHcmnhom60QbcG8lEkA8YB4qzG3CBp1dm3NMjunIEMPO65B5ouAB2DRC++FaIwcdGfiQW+Ml4AXEJ2IiglboztoNIX2UcGAh/sXKxcPh3GSjTAaLu+NlhklNmJlzGnYVFCwUWNc12KPGSU2tMtEPHZbiVQS75hLubmzavsfs9DpzBm3sWz5pC3ZMsC5JFaubpy06WQisFw2qi674f5x7QfnwuS+TEOwbHuu4ZRbeN2bty/avnP2FEFMm8+FJe9V9yYc+3JQkLZYNQUrMKtiRqd8xjzpkfbgRA3Z1jNLY7hGvFcV8g6FeMihP0Fz5MPPG5WjaDkWezoZrIOKEwjUTgTbaLoaGbqVUduTNlfWVchHHnhM2womBXmMmHGB47z92YOz8+188Snj96uLzK+Ni+M4McAO/oK3P3/gN6qHI0N7dWkNnqsr6GjoVAWwuNuSGQVps4/PIbhtBS2xBQsam4CPiUUsgCcT7LqE10115cSd48RSCLrf8dgnOs5xtO462wy4Dr9EHufwSwaGIiclg93nh09YpDoFYzono9R/lKf2ZM0odzdmnmzUUS8bbyG3qUSPW3mQiUwa9+6Fb/E3NqmJw4tOjPqKEGhbL7jcBl+RCzJ5DGUOZHLBCcmDHxHrKnonR3MxPy7r8eWPjjMmlicPIyjaMQW5ooZXlHyRixVjpLGxxsXIqIE8Kht/yfTyG1KIB6mwEgzO0WVpW84sGVZD0IH1cQGbCu4eyzoq9Bb6oqeWsRXeIUWFSkXRy8M2tWQ5pmNMGWwfkHCDZB6ET/KzPcE21Tn3JoW6lBFToMxLSRInleZpyrpuB1Ev7N4dhGE3vRtkGTJN8aBhEbznS2yOEYopeI3RuzS9G8bu+puawrjq3fGtC944/HtohpIxFj77edhsLq16jm5kX6M8C2OXolbvGS+DV8NjAJHH5FHJwi49JMkCjbpIiMBc7n9HXmkIJwQYpEMup+k0S0fkDTRnGT04ngpM17mzOEcVYkKbUM1EUdoldA49d6NRT7vtKrdu12LKxW5UqC3dem5ncV2d7RrtyVpSTMZNHJwyiHhQAiEkO4jIRynQnYNuSPwB8GM8V9+oF8AlNggBf3lkgQWcGlCeeos3r3j34+RdSYRBCXcZTZ9Tdp3dsPPuAglCOvB+yDVglJrwx6NwpAl7WLu5qES0HaVA8Wa7cZcTyiwHYxLeTyKA3sDrhriOuN9EYIXdndBo0M/pa6TIJNx4htGiFWS2GeqtnpIu/VWVtr/t1ParX2XXS7Mxm1XV7nRPxYW8BOvI8n+HXMAka2GVElanzAkIwjIqE92SMaewexR9WgjHdfIdIGtIAyVnZuski0gT8WasI1ldWmg7YzVmj2mj+srEgSuEkLIaCPT5yqp0sVn9Kq8tVnaikEqVslUnK/optLITnZ1K9fUJnh8zzOObKU4RL4Movb/VG69GTCOQ7fpvhtkquR3FyRhH1FzmZfDLpb2wM8qgpnjZbPlvxR0SkbkMP5nEGtsX3QD5vhUNgC0pRtD25PQjvoaX2J3ih3slz3pS9soKrqI3ZxoUrHItzi5jYEI97Ksc9lKPIq9pfRptaXqWzNrpaJtdybQpPqcBmo0FDKY107D4rYT9oboxG/AGf+v4TL/U13rBwLTYvEUK4IULTVluZ0iSwAaITAAMbdCo6KDQ903VBVNo6Z0wC2DayNWQWDuHplL1FCjfEGwNLwArPVBtg/gHfQmpHGGbxur1lXcyHHFhHHwxSMNXz3N7XUXBidtycQy3hYJjWi1782vLb16apv1CJtKyR5xjs2t7KrIYDaIfj0zckhbjyli7KWtY4QSW3R00mHffAAriqpn16d0QM96JGw/jthERJS7TNqOpLpW9HcV/6kgQS6D00qisZGulpB2B7lmAT1GzNYlxlKjky7lCaMD5i/fey5vGuPp5AZS0HCtY3Kl6Sgo88iKWFcZQGGz3EChy37mUHKoQZGEpJrWksrs9lwU9bPFvQy8Y6wrXoFyrOEo1lAfOoK1mXv3SKp7P/dkD+GcO/5nHf84dWGT6KiTai7jpNQUeHEVMVFjLnemCEOrbyIss93pv4eI1bfdFmy/uRrycJMEYY+Gq1hzaSefWKEQS0dGK8B+GbPVvZedK2BK6ghkLXtyhhnLLyc6IuV8vef91FGchb128t86oRZGsXYIw+q9Wm/LtUx7izRSdt9F3CEmk0CzaoJIsDdO1+G0RY6bsd1BhoSkWl9nDNLFVA000pZnn9LHxUbr2zdEDJrNigZHclJOb3EaWp8JIxWDsNH0UQdbY7TskacBVVmxgGHUrgkT768NelDW//3983xLmidrw3woHO0AjXVjy5tGcW3UtpCK3Z+9gBoSJbZn2HRYUVsm6IQw2G8TcnemjXlN/DpdHLt2gIOBXg73mbJtXOW7UwYmAlQJ8vU9C8icUyhTDfNEjhjv9+uiXKCg9+lAHUaYg02yhqt38jPiEf7sXKFyv0Qmx8U4D+21SWQF5OdcAHwFm3nkH/hJ+e0fmumx8a5WIzn5seCoDNzrJg8O57RZXo3QYA9i17J6+VbivLAMtxigCxmBmn17vevL2Llx760NcNesN0XKyHHkx+4Cn6l66TFrT8Tw1GUCdI3eychWAJBSVuvLWJOUoSTaqQq4FwyELB2BOH0I5JITY3ggGudO/GMeVwvlffSWCAECXuWtrHgZAKTpBfhApDIDaLgUCUFptLVbmt3UoJhi86SVfvM+/I2Eu60Hd/6n85PctCnx17/N+zdfcFhBY7052u+R5VIpejkcf/QqtNOBmIaUfOmGpnlaPvcPPWLht9ODkijt0+nyCESiPPmT3jiJSWDxlTQ+NaFEZvY/HMrUcD6whHY3iUY6NkR+H/PMUR4HberD26BjkrdU8Ajal2/GOiztexdrEbuaOQzPpYV2b1P98+gN7U5GEHyNqhhMpTNaF06lRWSSXPqBmUGNde17jiMrZkJge3WirZCPCrEYs9oilRrWZ7S49GcVWnsIyCbs8UT0p1+Ss9TxJcT1zJGYXXbTl58kbi8AkUkva1xfiyPEbYb/p8U2nQNVHv2D2GWRcISU2l5McCMs7fd5ue7/HuQEI9wtZ8DBLAjLPeoP64jjabQvjRNGMa5Xr+ItU5pvi2hgcqKAgl1EPjsCmQbEBBq1R4shFhVruMuNA/KnY1g3r2dWVbOmG09rR5XkYRMoSZ0u6flVrjATQXAKI7ks30DvEbZMnUnTXtMEzmCPWXLIioD2tfx3+FvFWOEjhjdjkUtBlu6O/U7Mv9DZoDwb3XB3VTSnYF+uGn56ZIvbXBbRdYb9nZuogQR2DiqZvUxt3jLTGhCaxx4dTldJYDTO4APJQSA4Ia1UH2ypsJkvYPsctltHY0xT4hCpmWFure21P/By3vUa/37Dab2ZZLyRvKEI4b3IXq5XdYLAT2hwWjoFJ9J2Kk2gHz/ZGZcZoaZmUHM2WDqbADfpYJrbUnR5bmBU3JVPQcK82c8dPOtOOSjftQ/tN6zUY7YVRFpnRU2sKfk90LGeGFQI4zIikGFseflEO8/KYZ5S3OCAffaRb1Oatf3r468O/P/zHw/9Of/9PIAaAzKCYP09RDClZolIyNZuHM0v+JI30OUo1ed4NnoMpD0QDLbFV4/T6fwFYaja895CMyNciV/20dItge9h998G0YHt0bdxYPcvcG9H6bjQk6UkebY3HNk09MvAEam8Qj9Ke8EpU0YlfChs/6g/J7O/mFWbJ520lUbjdy90wk3AmGA57YxZbkYLIk126PbvBLGU38M7XSh2yPk4BH/gM96WkogQAhw4jZizjr8aX7qF0yIS4eOWNXXTrJM0x/fLXe2E4bM6/MgnNZjCXWwmGjK+0psibJGOCksuFJ2J/2YnyDJNUsgZNYBFYZDS/Qska+Ixqp4qplaP8Sq3ce+IgvLQMfDwdemi3oxCo8z9WIj6+h6U8fBXDlrJD1bTu1C08nVYBmmln6LQP0Gw6tbnb6zCDTl7cZDxgM+M8qI5+ViMDlsQx1kQ3mpWjaiTkZBpnFyexQqpjfVT3UCsmIBbrI376Osxp1Xn8KmyZyL2ZNyOldeWvlOSuqpWRVIjAosrIqDpLbhVrrPRvM8sqUb7GhSj44XzQpjheDBp05/mDqfldSWp38gD8HQJRyVHQsvyqhZJtF6oz9GoM6nSxenmxvRNICDCu0camaGNTa4NlM/dQ6ACH+WpfhAzeM6QH4WXHetmxoex6qTH44yozZmXGNWTQ8qGrWP62dtLbIktJxb4wEDqBzWHdCuVOwdim/i2Sdsb3CxXKBDHriSqQc9zz2RXd1c4x968CCVrSsZPPTtGsNstyWgmWUoLlCBFEES8gj656m6+hVSQmuRJ7vRZECfAhCvr6w6kz8KTEjfbC4B46b/VRV+PNzawWQ90NetszmImju+DdAn6yA/wucKleL4ILIujpLd4HMjb0NmHmEdzUuZXt2vKN5tq1jabv+62Wz7PCUM4pOGRp1A2JfQ263RlMGZfqrWLcoCTsRXjnsFrktQa8ch+5b9xbEpyg3ZVId+ZtxdkujCAmtVsWlhqVctcIPhkd7cZidOiX2x8ig0SDy1ckpbBcbBjxoOSM14kxZw4aZhDuh/Vk4tT7cOWTBRlKChAqMBjTvSiNcE7DOI2IU/69IMaCGjlhDCknKjOk3uInfsKMW4XYDb0cyXnXaCFD2v8kvBfFo5SJHy4NEIC6ZAmgFKWg+iGVWR8NoVKahl2zUWu1ZSU/V0jtwA5nDHpSxACYSsrrjzLCq9zzkgPbMIm7ow6QMej8CRVMrUaDGeG0SYGv2GkZojETNUU94rrgkVbFSLl/pqndbZjvLhSiU45cGpxzFlesOOf8YCN+gsb6dKjz1IFd37gIJOwSVh2pp+5BwEKaBYWUaOY+4oEUzkmHTcjUaCq2J2X75W1HCKJncTFIEEsuW5gQ8c/DkAnFOjBz6KLHl9rYKvc53kKzEhwcubQSxczO/h6sbA5MzKgRqVZyRNUzVrGjZoY7/QSg4kApM3FSsVILZp9lA3AzQ2x7NhmB/8huRjy8vuS9mj/VTx8zeT5C541uz/jlYrr0agWXlRBpb3c+ScZTRueSOQ1z58heJM4YIwUXN2lEIaOuIr/2DHEr6k9MRr1qi65B2rNP5uZaKMom8TP9et2bZ79MoFZvpMcSTh9DUD0JEFXP4iSBqQ5AuYHKCFgpqUYqoKreTGXokpqddrgHE2fsrNDtuWchjz7cqxv2xyWD5PdMjYD7Op6fAEF7+8bLxHiVubXpBy4PralMmRpM9VgVUpBFSM6j1XmvsntvJkrjXoAxE0g9+A3anOZxxUp9NaX94xJHYNJIuYjdfU4xcD4UitJv5FgzyMPltXNlbVlgnZc5ZbFOcgvnanC1bYX2riTUJaEt0w9u2BUnzrsXYVBpQRLayu8VyW0mCW2VQlxyiwPPMZbOb12R2Dg556hXKFvDPXTDAGIWOLGeMX82I2/1ppH0MyQqjdI8TG4wAqYO6EsatO8tdxCCPYpNS/0i2SiqUWYx37bsvJR13eslPC2su+XWpD1QPlg3QS1VuQuKGrFEfjLUIn3XiWAmGKrmAq04p5Q69WTSplrzdk2eO3XyvKnuqfJTEu6R0lc5sQXKGsSDEGdqPndnvMZZlNfpB861IrxDDVbLPVqgTHRZAq/FiW8I1Rt6MsfncmzU4nbhgc5+juFpF4SiYX/2AEOhLhaxd/bnD87un4M33Jpi/zz8Vpdl/xV4JXZ9af9Vk0t1Wvj0mym5trTTbXkX8odWLRc9OZoAnVYEUxbzcJJ0gbxaTTE0WS6R4RJvHeq9Fd8Pk7xk0z14YVIhzCSZgQTD3mFXzIk8LBQdVZX1hmivI5rSTDiE6WWNWBAKK05Xyet8JBdQsongYhFOiW9CmXWhRsYEAS82vw8XkqVPtbCsxd5NpG1eNDFyuj0H6+7Si7Hq2GFh183x4YrV4MWsumd1jMaZy7OXe3Xka2XFyrYiNq3zoAj9JJ/SAjVow7QbxE7IptTVa+9Qxmi7XtuiMCkrsKihG1NqsRxqFaWnzRPtyaY7Y8oXStlh+DrmSrWKzZc0Nr24E/RuoRc+e9FSlWGsO595r165uViruU1rc+MJm0PAwMHNMgenTXd0fd7Xrc2NmPxl2dzafFDMjZ5aLH5utqrHgMB/i0PpLe9PvPlX/PP1am3yWpuVtXQsxqYyHRarJ+0gAJPT+ara2eLUV5hvafMWN+6tXBNobrd+lt8anW1O0Zmk9qzXWRcVoXxuM8U869Udi7qbUt3NxcodonAO6z9OsiZ0/yc4hjPYGPwat1AkPuvPzrdqhLW3IXsFxZb3fvEEJVtmec0xfDty0S1ZMDJtAfspPGw56aHmn6ciLqkup5Caam3yq6W6rQlM9fVJH5SDeKlONbkXjewlrM0gMvkJyyPX79Mm1WiZHZJy4FisNHAurrs1Rv+i7RUcvOVeT/uU1iKL7Y2W7YpNxZoVdHDQ7dIqGEk26WPK/tYihCOENAZdXHqwaNdkJWQXCnuKP2BHz83Tz/rqq0rSJjkmrVFJ0Ry3g8nJQ530UcxO6lxHkuGKIEMU6cikRM3Y1tDE5Mwep2XGbkKGdZLTMXtA2HGSZY//HTtQs2ZQbTg4gJbWGUONwB8B4mcGzMT33+r38bLa4zRL29tkL8b8hdGOeTrkb+aeFHeQOXIHUU6chgzhMOVnuamUYKiv5eQsS+jZ6piijMSElZWBlFFwy+oPWmXezaGHUThm6TsaeLRyRtkMrVQmB1ZBkkoroPsbOXtri2GxQEsoAyh3JqRQsHxUrMAkjVn/j6T/GlXSSYwv1+83TMPlg1oPtklapY4ZB8bASiwNK86XhuSKJcmn8B+jl9YOrwZpFiYUvNfSpXjdF3eMz+osih76sgwTCVIxuj6LjOEYVGlUZEoEBD2FFeDZ8LSBuWVsjrBKAHpKs6y5WgJAvWqtEVmugMbNNEx8KXoxa7nRakmrM1U4Opdk/ZQdRXNgt46rEL5PHDazHH/SFPiZYyk+dP6LB88z+zSIMlrMPP769uwdBMnvN74vv9TqzHhzopQzkIiotj7aYqvcnMulx0Vb886Y42Y8bdhth9+kHf4UjHalawNHIDlSFF3HSYaGk+vsOsVNh0WfPz+vTiDe+ksUsHLTLgbBN4L7OQ5Ylz801fba3qxBqVYSqWpNVyFP5nPLegeygPendV1hvF19BPP2EXV1gaIoza1Rrlee8IQnC4lWFsaP7aEhUp8EHpHIw5OGAVoZdHpBmnqXulEWo41XH1Aw/jmlwoAAKFS9svSfjKby7sJ9H0nGLKWCeL9cjPe8uyzXhqPkNXRtiTo3h6vx/YF3t7s3Qdlx/bJbE7S7NUG72QTtZhO0O0SjzDoLnIQDiqxZLrsRQYvQK4+jQo8SGz4EKgbwQQEDTbG7tLk2nMC2HqPQqSBALoRMWymDu/ft+7/C8DTPWDahImTZ0UfMXkBD7G9HXQoVeH5e4xN+GEY7u9j6qz/QvlyNBlF/1F9HE3TGOOPP5rnXgON4dVY/ZhTTdo1bf2Pqapi58g6OIB6W9U4Shtr8sOzFOOnyOKa8tvTGh57RXGcDaBJm/6Z1vhvfvzLYCNJ3t4LEbO58OR4I/h9/Nhvr4U6MjuaAMn5wWZvMRjy8GqdZ0ZL6NdhCn9QE6KMs2BJu09LbfW8V8yst0R82AWixXaz1+R/M6rwBVKe4a4h14HfRKLFsjcN/L0IZ6QJGUXUnjE01/06PgGCrT3l1TC1oWuZSBgBYBJ+XZvEg+CSAUyp/Y6M0fhIDaJUXvBe+FYyBVV0LBmGPFokCKuPTvE6a0FefbwZr+eIoy8jx5x8oXFhuaUXhjr/96X8HIGim7bC1dOHGaNBswl92Hv3VEbOvJOOH5sxcq9Vqz7Znj93jpzV7pA7nJurwN1JgrCKms2uSGItBmd/cCXT3aXV3fHKT9Pbp0UcUx+3rPFQ1dPqxFOnr6IG1XxZ8gnpm05w3dowUXtwb9QfAqwya7B1yHWw8qEsUKK2JTZRaYWP1tgBPCSqRYiLgW0DDeKD+x+FDDBlJUT54Qjtb3DJlNhehTYX6bFUvnTwOmPO5GnNWqsxPsDs4r28I2TwT+/P88DMK1/c7AI+fWreGB7eQsqytBxhjj2/U+QnHwEO2sRF8gzn68mEc/VSDEN7npR+PoiEFfCaY1HvM6QGBHDmdwFD9UoHoL0coy7gaJDvRYIki6tMMd5qvtNpkVpeSoxTStEsY4hqRAgWLeU5xC39H5pg/y8PEKKCg3xmGZcjHCav2yhSn+BmjJGRsZd20G7wrOlF5xyQDYQfbNADA5eoQaFQ6xr/ci+/LCB/1SuwXv8K174Yb92IMU+tLl+7cPBAuWJElSuJkivyMtzSSiW2xaSIpAt/COeB6tC3IB2ZaV37af43RJxEzikSgn1EcoKdHD8gWxLG+GDKfbGTRxaXNiJFWKZFMjTGwpqi7b9//tzo9Ul9t8q0p92jcyHwYldc3kAAFjaF+MmwkO1EMPfGYT955EjGLpx9MsGHbccJEsEuzi9Hr5xdJzAoD8jn+Y4H0C2F3/rKJ1O/GGHjJtTDpAKJoz7+ir8tdUuoCy9GceWUWDuAskQrIURleq3tII5BWkxRVwVbY28fztNT437+61fbgaD5ttJdHWYyDWcLNOWDkSLkBGIuBcKjRz6aln3lbP+P2uVI//BKMt7fTMNOvP0prqiBpNGMHRMfj+38AV/znUOILK6BeQoPk69R4UwinYcI+Zf5pF2/G7E35yOizYANlpA99VW9E/vm8eZbB3pJMoHDk+QxwN87tVqNtnsRyL9qBKnsNHF7e1tjV1mZFW+NG9VSDPUb6GKYJn+ZNexwAGWCrwigE9Rhs7S0RtM/PAqjTP3QMtsbG15m5dGYqPRkwH/4tUR4PcQ9Kp+acEZq38NQYP1kb3zQcFUvjeFTOTTyLf0OCl0FSaRbnjR1le4yGmaBx0ywsjeMsLEdhq7Pk5HwYNfYZIwhtwIx51Ui5uJEEgxQlvOwCzM/1Vumkb431N1mpTGbDBmLs/aUKrmba0bPL9EUNv7RDWx1G/RmOK3wynvCtPmy3pUrfcMJJjkbnc47us/OztYDtf2KGbEHUPjp8Yr3SXjVCHvUKkP2qeQP7YZACF1HsIs/fTWIPumZ+jv3LG7eGLV5l9ZoSGu5GaVa0888AvR8Q8fZI5j7lhlYjFP1vjbKQmmxWbhIfLCy7ca44ADhmlpkOihsHGHtvji9j9WU5gySBBf6HRaOsQcbFVzfqaHMwlgb6dxMMdLZNwgjzQOVG/3aiRueqT88A78c/Ne3JELGq8csAL0hzHUSWf2qeB8X0SJdU2gj9+djFwlAOxhJ9DpD3JfPMIwnv4ee5GIQHPrfNfqUIG9KsnjobEEz/NSMm4J/Pl5spMwNhXMXTkbQvrc/QMT7geAzceWDC306CIY4VvUCXCDOX+GoamYOjkwWiQn7Do7faxU8wkwyYDwM3Zegux5zozCojR5Qt7Am5/FIhlX8FyaO2x/DsOjTZDz3WI4aa/QVFNaL7GDEZ0tnogAoX/wNAxQ8PHy94RHFjVi10P/0lCzyL0IflH4qgtZ9h5i2WgKso9gVciszx6LEEmUefsD4Vllf0/Df8kass/EbJCkjIgjUApaUq3UY883w90cyol0WYMJEv540w6F4f9Mb8cb0DnfUuBkm6VPz0fxQmFHqj7V0MOu/CkYiTJeZGT79T7pUv1l9W1ODykJfu575H4svPBNhwqc/Rf2PZzShNRQ5IFCKYogSzSMCw1rg5X7FqT1jIYajx5dEDWnTMduGXJER8ZXxhjicNbJ2+NMzlVUGVrntKTVXZuWWfZFGNfJ5Lm8EPpiIoe63Es0uNagQB+6LDg1JGqqyBmFIMtRE2A5Q4Y85VmKAhwdguLCQeT4pGhjJdekBTG4cJSl4IjSFUBWKeia3CvESt5a/Do8kyQytW5G+rKGm0bFVtJbaAvM0bLKY90dJdH6CCb6VHVZvSb/LNX052Us9pyxP6WD6Eo5viJbDkSY+Y0jPhzaHpFJQNBp2wR+d70fshYvDWouQCVpqcOrrQMjWm5hU2Iew01UoWyNI53ovfhQH/eARXV7dq08nBgFVpNq+G2W7cZU9Jqxv2wh3USu9Lo2DdLxotK03xMg6MOIBrnaVkhtXWMXjlXR4NOrlnIgvk5E5TqHXIqjRLZpZkuqPGsyhXbnz7D/9M0fsuJ1E46PbGTUxaVSPApVG7csykpIXZuWANSz0YDqQ6Id2eU4YibplLavYUY58BPfzJF5NlJM119yIvDE9uBCtMGKFZbU71IvekrJ056T3Re0AFn1A+/WF33LtTYnpPenP0DnJhCEkCuDzkD7vksld0jstxRX0H6BPtXipRKkjs0+99j8I836P0LsAKlchgtbuNCFjLM0ueuDwr5sT6yHivuuHXFASVWOJMWVk085YXjT/JuXeP4d1mOWAild2aml7WFkKs5sFyHC6KIboE1clu8i4LTgg9u06cLYOh5J1S7gL+3QI+7ycVbdv99iY50Q6fvWOfbIMjSemUYT75Vi3yTBV4HhdfM+IwhybeLr8MDBHow07Uh0M6xCTmXfOhWGVlilzn1IeW6PxyLw6yOmnOWU+tliffGDBgltc8GnCZss+FKu0i4bn4wKwg23lLlbdN49t//DtPEj2jhI4rNkn8zLL5sJVDNxQUXuoZh17SDcF3Ma9hDha3b4la2xklcJAXWcgpTG4AezAIk7zA6SUeOgLKlb+anUdHebQxJzSX7AaEJaBl0KXywyWT+cG+JqRAq01mP7J0bn62LdkgLM23hQHC0qttkxhjbralndrhFDYGr8yiUmLqmqY1Huq27PLCcsk0F6+L6AEUp4d48x8GAChwae0iBAq9Gc2bPTBFD1UwCXzEYr7WNltIaQZS2M7BorcF7D5c2WeWdnNPp63FqsGTqPZYEyCb6aVz52bdwz5/3GGrJuqoUxN4sh8N2jnS7Ad7xUPuJccbxgEp7exzxLWEbXDstoRNEAZcYkiV49o1ZIBSAOkrg05C1ndLs/4rV007eLCYO0AcnPr/AF2x4e/dCAIA")))

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

            clsid = "{A07B90DB-F873-45A8-82A5-286E83C0F329}"
            progid = "EnergoLogic.VisioEditorAddinV329"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV329, Version=0.3.29.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.28 -> v3.29",
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
            progid = "EnergoLogic.VisioEditorAddinV329"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV329")
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
                "progid": "EnergoLogic.VisioEditorAddinV329",
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
            progid = "EnergoLogic.VisioEditorAddinV329"
            clsid = "{A07B90DB-F873-45A8-82A5-286E83C0F329}"
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

