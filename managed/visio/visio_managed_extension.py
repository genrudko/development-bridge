from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.122"
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

            build_dir = workspace / "energologic_visio_editor_addin_v324"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV324.dll"
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

            clsid = "{7F0BF42E-719C-4A53-9926-DFE2B0EEF324}"
            progid = "EnergoLogic.VisioEditorAddinV324"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV324, Version=0.3.24.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.23 -> v3.24",
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
            progid = "EnergoLogic.VisioEditorAddinV324"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV324")
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
                "progid": "EnergoLogic.VisioEditorAddinV324",
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
            progid = "EnergoLogic.VisioEditorAddinV324"
            clsid = "{7F0BF42E-719C-4A53-9926-DFE2B0EEF324}"
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

