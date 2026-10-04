from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.141"
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

            build_dir = workspace / "energologic_visio_editor_addin_v341"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV341.dll"
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

            clsid = "{E7766CFD-D7C3-4127-BE64-E7F041D4F341}"
            progid = "EnergoLogic.VisioEditorAddinV341"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV341, Version=0.3.41.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.40 -> v3.41",
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
            progid = "EnergoLogic.VisioEditorAddinV341"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV341")
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
                "progid": "EnergoLogic.VisioEditorAddinV341",
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
            progid = "EnergoLogic.VisioEditorAddinV341"
            clsid = "{E7766CFD-D7C3-4127-BE64-E7F041D4F341}"
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

