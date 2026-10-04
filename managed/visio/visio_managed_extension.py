from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.129"
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

            build_dir = workspace / "energologic_visio_editor_addin_v330"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV330.dll"
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

            clsid = "{A07B90DB-F873-45A8-82A5-286E83C0F329}"
            progid = "EnergoLogic.VisioEditorAddinV330"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV330, Version=0.3.30.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.29 -> v3.30",
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
            progid = "EnergoLogic.VisioEditorAddinV330"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV330")
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
                "progid": "EnergoLogic.VisioEditorAddinV330",
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
            progid = "EnergoLogic.VisioEditorAddinV330"
            clsid = "{A07B90DB-F873-45A8-82A5-286E83C0F329}"
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

