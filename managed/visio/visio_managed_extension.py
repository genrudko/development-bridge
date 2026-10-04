from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.139"
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

            build_dir = workspace / "energologic_visio_editor_addin_v339"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV339.dll"
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

            clsid = "{55AD5A2C-A8C0-4CF5-A7FC-A3CC4FC6F339}"
            progid = "EnergoLogic.VisioEditorAddinV339"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV339, Version=0.3.39.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.38 -> v3.39",
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
            progid = "EnergoLogic.VisioEditorAddinV339"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV339")
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
                "progid": "EnergoLogic.VisioEditorAddinV339",
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
            progid = "EnergoLogic.VisioEditorAddinV339"
            clsid = "{55AD5A2C-A8C0-4CF5-A7FC-A3CC4FC6F339}"
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

