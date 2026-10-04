from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.142"
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

            build_dir = workspace / "energologic_visio_editor_addin_v342"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV342.dll"
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

            clsid = "{9B58B36A-B7CF-4A30-825B-0D71D24AF342}"
            progid = "EnergoLogic.VisioEditorAddinV342"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV342, Version=0.3.42.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.41 -> v3.42",
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
            progid = "EnergoLogic.VisioEditorAddinV342"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV342")
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
                "progid": "EnergoLogic.VisioEditorAddinV342",
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
            progid = "EnergoLogic.VisioEditorAddinV342"
            clsid = "{9B58B36A-B7CF-4A30-825B-0D71D24AF342}"
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

