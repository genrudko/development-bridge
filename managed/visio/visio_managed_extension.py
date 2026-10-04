from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.144"
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

            build_dir = workspace / "energologic_visio_editor_addin_v344"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV344.dll"
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

            clsid = "{42C03C70-F217-4EFF-8F44-D51063BEF344}"
            progid = "EnergoLogic.VisioEditorAddinV344"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV344, Version=0.3.44.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.43 -> v3.44",
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
            progid = "EnergoLogic.VisioEditorAddinV344"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV344")
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
                "progid": "EnergoLogic.VisioEditorAddinV344",
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
            progid = "EnergoLogic.VisioEditorAddinV344"
            clsid = "{42C03C70-F217-4EFF-8F44-D51063BEF344}"
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

