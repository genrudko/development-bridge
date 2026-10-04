from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.146"
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

            current_progid = "EnergoLogic.VisioEditorAddinV346"
            editor_progid_prefix = "EnergoLogic.VisioEditorAddinV"

            # Keep early known CLSIDs so partially-unregistered historical builds
            # can still be cleaned. Later builds are discovered dynamically.
            known_legacy_clsids = {
                "EnergoLogic.VisioEditorAddinV31": "{F2236480-88B8-42B3-AEC4-0707D59A14FC}",
                "EnergoLogic.VisioEditorAddinV32": "{9B2D0D65-A68C-44D0-A523-612148808DBD}",
                "EnergoLogic.VisioEditorAddinV33": "{54D4E77E-73B0-4D45-94E2-B138DF35D1A3}",
                "EnergoLogic.VisioEditorAddinV34": "{A6E63A2D-0DA5-4E84-9B2B-5B3E6944B5F4}",
                "EnergoLogic.VisioEditorAddinV35": "{D93F00C2-1C95-4D0A-A0A9-609E25B9794C}",
                "EnergoLogic.VisioEditorAddinV36": "{81705A73-9C25-4E72-84A8-F58E4C818AAF}",
                "EnergoLogic.VisioEditorAddinV37": "{3D58EA6C-A51F-41B9-A46D-BF0FB3BA7C5A}",
                "EnergoLogic.VisioEditorAddinV38": "{9974BD0D-D56E-45F5-BB8C-7A21485C6730}",
                "EnergoLogic.VisioEditorAddinV39": "{B42A3C6E-8C1F-44AB-A486-93C6AB3D8F39}",
                "EnergoLogic.VisioEditorAddinV310": "{D1C940D2-5A7E-4B4B-A92A-2D443A0DBA85}",
                "EnergoLogic.VisioEditorAddinV311": "{6D8D560D-1F9F-4CB8-BED7-5FCBB70B1F2C}",
                "EnergoLogic.VisioEditorAddinV312": "{2F8B22F0-0A1B-4E30-B850-09B1F7197D3D}",
                "EnergoLogic.VisioEditorAddinV313": "{1A6AF8E1-2576-4EF3-96EC-676904B6DA57}",
                "EnergoLogic.VisioEditorAddinV314": "{6989E63C-E667-4B14-B85B-210710468940}",
                "EnergoLogic.VisioEditorAddinV315": "{E82068B0-D05D-4646-82B0-0CA923733CAF}",
                "EnergoLogic.VisioEditorAddinV316": "{89DDBB87-8513-5078-9BF3-1DA6D75B2454}",
                "EnergoLogic.VisioEditorAddinV317": "{D0F27C51-9E15-4C2D-A584-170EA8B7F317}",
                "EnergoLogic.VisioEditorAddinV318": "{6BC8DE0D-79B4-4E0D-9E0A-C6E6A7E0F318}",
                "EnergoLogic.VisioEditorAddinV319": "{A2ECDF6D-77BB-4B3A-8B29-3B736850F319}",
                "EnergoLogic.VisioEditorAddinV320": "{08DA44F1-A58D-4E53-8F2F-A1107D57F320}",
                "EnergoLogic.VisioEditorAddinV321": "{9D1B5AC1-0C47-4C18-BB03-7ED263E8F321}",
                "EnergoLogic.VisioEditorAddinV322": "{D65447E9-8176-4EBB-8CC4-4DAA1C3AF322}",
                "EnergoLogic.VisioEditorAddinV323": "{3C74BB1A-284A-414B-BAE0-5D413682F323}",
                "EnergoLogic.VisioEditorAddinV324": "{7F0BF42E-719C-4A53-9926-DFE2B0EEF324}",
                "EnergoLogic.VisioEditorAddinV325": "{8E9D3160-A441-4944-9471-728178F5F325}",
                "EnergoLogic.VisioEditorAddinV326": "{B0DB7395-E237-4F35-BED6-AE59C2C5F326}",
                "EnergoLogic.VisioEditorAddinV327": "{9A7903D3-1371-4AF6-B80A-01F6C039F327}",
                "EnergoLogic.VisioEditorAddinV328": "{8E75F86D-AF28-455B-B20C-62492D9BF328}",
            }

            legacy_progids = set(known_legacy_clsids)

            # Live COMAddIns discovery removes loaded stale Ribbon providers from
            # the current Visio process, not only their registry entries.
            try:
                for index in range(1, int(addins.Count) + 1):
                    item = addins.Item(index)
                    candidate = str(item.ProgId)
                    if (
                        candidate.startswith(editor_progid_prefix)
                        and candidate != current_progid
                    ):
                        legacy_progids.add(candidate)
            except Exception:
                pass

            # Registry discovery makes this future-proof for disconnected builds.
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Visio\Addins",
                    0,
                    winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                ) as key:
                    index = 0
                    while True:
                        try:
                            candidate = winreg.EnumKey(key, index)
                            index += 1
                        except OSError:
                            break
                        if (
                            candidate.startswith(editor_progid_prefix)
                            and candidate != current_progid
                        ):
                            legacy_progids.add(candidate)
            except FileNotFoundError:
                pass

            # Also include orphaned ProgID class registrations left by interrupted
            # historical installs. They do not create a Ribbon by themselves but
            # should not accumulate forever.
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Classes",
                    0,
                    winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                ) as key:
                    index = 0
                    while True:
                        try:
                            candidate = winreg.EnumKey(key, index)
                            index += 1
                        except OSError:
                            break
                        if (
                            candidate.startswith(editor_progid_prefix)
                            and candidate != current_progid
                        ):
                            legacy_progids.add(candidate)
            except FileNotFoundError:
                pass

            def read_progid_clsid(progid):
                if progid in known_legacy_clsids:
                    return known_legacy_clsids[progid]
                try:
                    with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER,
                        "Software\\Classes\\" + progid + "\\CLSID",
                        0,
                        winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                    ) as key:
                        value, _ = winreg.QueryValueEx(key, "")
                        return str(value).strip()
                except (FileNotFoundError, OSError):
                    return ""


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
            for legacy_progid in sorted(legacy_progids):
                legacy_clsid = read_progid_clsid(legacy_progid)
                try:
                    legacy_item = addins.Item(legacy_progid)
                    if bool(legacy_item.Connect):
                        legacy_item.Connect = False
                except Exception:
                    pass

                legacy_keys = [
                    "Software\\Microsoft\\Visio\\Addins\\" + legacy_progid,
                    "Software\\Classes\\" + legacy_progid,
                ]
                if legacy_clsid:
                    legacy_keys.append(
                        "Software\\Classes\\CLSID\\" + legacy_clsid
                    )
                for legacy_key in legacy_keys:
                    delete_tree(winreg.HKEY_CURRENT_USER, legacy_key)
                removed_legacy.append(legacy_progid)

            removed_build_dirs = []
            current_build_dir_name = "energologic_visio_editor_addin_v346"
            for candidate_dir in workspace.glob("energologic_visio_editor_addin_v*"):
                if (
                    not candidate_dir.is_dir()
                    or candidate_dir.name == current_build_dir_name
                ):
                    continue
                try:
                    shutil.rmtree(candidate_dir)
                    removed_build_dirs.append(candidate_dir.name)
                except Exception:
                    # A DLL can remain locked until Visio finishes unloading an old
                    # COM add-in. Registry/Ribbon cleanup is authoritative; the next
                    # install can retry filesystem cleanup.
                    pass

            try:
                stale_bar = app.CommandBars.Item("EnergoLogic")
                stale_bar.Delete()
            except Exception:
                pass
            addins.Update()

            build_dir = workspace / "energologic_visio_editor_addin_v346"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV346.dll"
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

            clsid = "{A91D7D4D-2466-4B49-889D-674E914DF346}"
            progid = current_progid
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV346, Version=0.3.46.0, Culture=neutral, PublicKeyToken=null"
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

            addins.Update()
            editor_addins_after = []
            try:
                for index in range(1, int(addins.Count) + 1):
                    item = addins.Item(index)
                    candidate = str(item.ProgId)
                    if candidate.startswith(editor_progid_prefix):
                        editor_addins_after.append({
                            "progid": candidate,
                            "connected": bool(item.Connect),
                        })
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
                "removed_build_dirs": removed_build_dirs,
                "editor_addins_after": editor_addins_after,
                "single_editor_addin": (
                    len(editor_addins_after) == 1
                    and editor_addins_after[0]["progid"] == progid
                    and editor_addins_after[0]["connected"]
                ),
                "migration": "all legacy editor registrations -> v3.46",
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
            progid = "EnergoLogic.VisioEditorAddinV346"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV346")
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
                "progid": "EnergoLogic.VisioEditorAddinV346",
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
        # Disconnect and remove every EnergoLogic editor UI registration.
        try:
            import winreg
            prefix = "EnergoLogic.VisioEditorAddinV"
            discovered = set()
            addins = None
            try:
                page_obj = visio._resolve_page(
                    "KRU-35_normal_scheme_v2_energologic_qol_host_v1.vsdm",
                    "MCP-v2",
                )
                addins = page_obj.Application.COMAddIns
                addins.Update()
                for index in range(1, int(addins.Count) + 1):
                    item = addins.Item(index)
                    candidate = str(item.ProgId)
                    if candidate.startswith(prefix):
                        discovered.add(candidate)
            except Exception:
                pass

            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Visio\Addins",
                    0,
                    winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                ) as key:
                    index = 0
                    while True:
                        try:
                            candidate = winreg.EnumKey(key, index)
                            index += 1
                        except OSError:
                            break
                        if candidate.startswith(prefix):
                            discovered.add(candidate)
            except FileNotFoundError:
                pass

            def read_clsid(progid):
                try:
                    with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER,
                        "Software\\Classes\\" + progid + "\\CLSID",
                        0,
                        winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                    ) as key:
                        value, _ = winreg.QueryValueEx(key, "")
                        return str(value).strip()
                except (FileNotFoundError, OSError):
                    return ""

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

            removed = []
            for progid in sorted(discovered):
                try:
                    if addins is not None:
                        item = addins.Item(progid)
                        if bool(item.Connect):
                            item.Connect = False
                except Exception:
                    pass
                clsid = read_clsid(progid)
                targets = [
                    "Software\\Microsoft\\Visio\\Addins\\" + progid,
                    "Software\\Classes\\" + progid,
                ]
                if clsid:
                    targets.append("Software\\Classes\\CLSID\\" + clsid)
                for target in targets:
                    delete_tree(winreg.HKEY_CURRENT_USER, target)
                removed.append(progid)

            return ok({
                "removed": True,
                "hkcu_only": True,
                "removed_progids": removed,
            })
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

