from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.133"
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

            build_dir = workspace / "energologic_visio_editor_addin_v334"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV334.dll"
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

            clsid = "{F7028167-E35C-4AD5-AD2A-4AA1D248F334}"
            progid = "EnergoLogic.VisioEditorAddinV334"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV334, Version=0.3.34.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.33 -> v3.34",
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
            progid = "EnergoLogic.VisioEditorAddinV334"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV334")
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
                "progid": "EnergoLogic.VisioEditorAddinV334",
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
            progid = "EnergoLogic.VisioEditorAddinV334"
            clsid = "{F7028167-E35C-4AD5-AD2A-4AA1D248F334}"
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

