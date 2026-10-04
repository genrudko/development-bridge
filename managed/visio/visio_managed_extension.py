from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.140"
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

            build_dir = workspace / "energologic_visio_editor_addin_v340"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV340.dll"
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

            clsid = "{B1EC0497-C3A5-4300-893C-29AC99BDF340}"
            progid = "EnergoLogic.VisioEditorAddinV340"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV340, Version=0.3.40.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.39 -> v3.40",
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
            progid = "EnergoLogic.VisioEditorAddinV340"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV340")
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
                "progid": "EnergoLogic.VisioEditorAddinV340",
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
            progid = "EnergoLogic.VisioEditorAddinV340"
            clsid = "{B1EC0497-C3A5-4300-893C-29AC99BDF340}"
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

