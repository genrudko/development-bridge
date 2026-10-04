from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.137"
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

            build_dir = workspace / "energologic_visio_editor_addin_v337"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV337.dll"
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

            clsid = "{A5BFEB63-9E60-4A1A-A2B3-DBA0EE92F337}"
            progid = "EnergoLogic.VisioEditorAddinV337"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV337, Version=0.3.37.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.36 -> v3.37",
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
            progid = "EnergoLogic.VisioEditorAddinV337"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV337")
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
                "progid": "EnergoLogic.VisioEditorAddinV337",
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
            progid = "EnergoLogic.VisioEditorAddinV337"
            clsid = "{A5BFEB63-9E60-4A1A-A2B3-DBA0EE92F337}"
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

