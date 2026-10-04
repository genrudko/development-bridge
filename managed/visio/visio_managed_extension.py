from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.126"
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

            build_dir = workspace / "energologic_visio_editor_addin_v328"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV328.dll"
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

            clsid = "{8E75F86D-AF28-455B-B20C-62492D9BF328}"
            progid = "EnergoLogic.VisioEditorAddinV328"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV328, Version=0.3.28.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.27 -> v3.28",
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
            progid = "EnergoLogic.VisioEditorAddinV328"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV328")
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
                "progid": "EnergoLogic.VisioEditorAddinV328",
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
            progid = "EnergoLogic.VisioEditorAddinV328"
            clsid = "{8E75F86D-AF28-455B-B20C-62492D9BF328}"
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

