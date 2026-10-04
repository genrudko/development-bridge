from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.132"
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

            build_dir = workspace / "energologic_visio_editor_addin_v333"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV333.dll"
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

            clsid = "{92191C8E-1C12-4F3E-A012-95A3E431F333}"
            progid = "EnergoLogic.VisioEditorAddinV333"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV333, Version=0.3.33.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.32 -> v3.33",
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
            progid = "EnergoLogic.VisioEditorAddinV333"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV333")
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
                "progid": "EnergoLogic.VisioEditorAddinV333",
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
            progid = "EnergoLogic.VisioEditorAddinV333"
            clsid = "{92191C8E-1C12-4F3E-A012-95A3E431F333}"
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

