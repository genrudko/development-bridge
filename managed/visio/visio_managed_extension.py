from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.130"
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

            build_dir = workspace / "energologic_visio_editor_addin_v331"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV331.dll"
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

            clsid = "{C75AF3B8-3C1A-4F39-9D26-B76A21F4F331}"
            progid = "EnergoLogic.VisioEditorAddinV331"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV331, Version=0.3.31.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.30 -> v3.31",
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
            progid = "EnergoLogic.VisioEditorAddinV331"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV331")
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
                "progid": "EnergoLogic.VisioEditorAddinV331",
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
            progid = "EnergoLogic.VisioEditorAddinV331"
            clsid = "{C75AF3B8-3C1A-4F39-9D26-B76A21F4F331}"
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

