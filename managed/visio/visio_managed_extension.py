from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.135"
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

            build_dir = workspace / "energologic_visio_editor_addin_v335"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV335.dll"
            helper_source_path = build_dir / "EnergoLogicTopologyRestoreHelper.cs"
            helper_exe_path = build_dir / "EnergoLogic.TopologyRestoreHelper.exe"
            helper_source_path.write_bytes(gzip.decompress(base64.b64decode(TOPOLOGY_HELPER_SOURCE_B64)))
            source_path.write_bytes(gzip.decompress(base64.b64decode("H4sIAAAAAAAC/+y9f3Mcx3Uo+vfjpxhuUvauuVgCFKXYgEiFJEiZiUjiEqRFFMWwBrsDYKLdndXMLoENhSpJjGX7SrFuFL+6KVccJ8+vUrfq1atQsmhR/KWq+wFeAV9Bn+Sdc/rHdPd098wsQFqOrSpJ2Jnu0z3dp0+f32eSxcPNYHWajaPB0pGJ8qtzLun3o+44ToZZ5/VoGKVx12ixnIbb8NN8GoebwyQbx93MeHPxivHg9X6yHvbjvwtxFOPdG/HwHePR1WiDz8h8MRmO40HUuTgcR2kyWo3SO3E3Moe/Fu2MLY8A7OakH6bnd0ZplGX4vUarN+NhL9nOOheSdCDfnd8ZR8MsXo/78XgqHl6Ku2mSJRvjzpWNDZgCLGIaLR05cjPMsmiw3p8uBueSwY9i6NePmuN0ErVuqS/P8L+uxWN43zgPq76ZvJFsxt0AOyXB+V48TtKGvdePohSn32zMd17qvPRyZx7bHRmGgygbhd0oUMARNAbsyN0jAfwT49oNw36QRWE/6gXdPgwQvN6fRNfCdDMaUyPWFP8ZTdb7MCvoFbD3F3tLtpdXk+3C82yc0goOe6ME2rD3u0dKpnG+txldHG4k7omsJpO0G1kmYh1wpq/wzvJc1O9fSu5Eq+NwHNmniU3wI+gPzzyuRekghgEs8+kl8P8oWN5xvpkW3rwRZ+NX1UU8HVzkn4BPg1PBMNq2tGq2Knz21WjUB/QaRMMxIPeoH+EJ9awBLWjex71ftFg9mFyj4frWG4OB69Wa5RUODecciEjUuwRnJkrPJRMLQtBKQOPTRuuLvUxdK2whlsi/2gJMpdUursTqpAv0LFtJo414R1mQUnT0H5gzw+5Wkjpw/uwkc7/x4CedxH5iP2XnkuGQkfDKhMG6LUhXa2wG9SndQv9qypmv4NxKKNFWOIpqUMTZsFmcd/iOcNiNLg3kZ9D/bxavGnr8+iTuNRvnTp45t/DK8sm55bMnL8ydXHjl7NzZswsvzS0sf//k+RMnzv7F9xfONUQXIhYbcGCvTUdRE+BqDzry18VseRL2ea/8m9nL4KJyAbG758woNhaRowC8WJ6MoDtQkTeijbG6sZYmV+PNLUcbJMhuCPjW03k1QoYDD5L9PZCxME7xEMPRvBNH22XNzoxG/anjY5IurIj9HWwjrKvCWdmbwcEsbUN8Sw9aej77WhoP/C2uRl12Hs5Gm/GwpA2cZ8fybiXbK+Ew6rumGnbHwEhl0bjJcb23c2nQFojfm14aWDue6cebwxtN97s1x/qFWXQuGU3FaOs7cqz1qfxznD8dT51wELMOCudSFGaTNFqJx90tB9LE+Pf6ZMwbcXgj/OFYnHNJkvaAdo8jB4ZcnsCF5D4y9NqDGvT++sjzcjnZdqLMcEK3Mp44/hhI9XKUwaaRlGBfb2DQGbMA/ASw43bg58LRGFZTYT1WQ2RXnGcWm51/ZxKPsO2FNBn42l8cZlE6ls2BJCb5lVHW+cooSkPBNk0c+8KZq2gFzi88upaMkn6y6fhYIQvoV5v/SnjlwiuvLFz4i1fmTp5cfmnu5Llz35/7/tkTZ+fOv3Ly/PcvfP/shZdeelleCStpsnmxp8koHUWqONODOf5I7XAOr1F5UzT1n3SNnJmMk+L9YbuFg8Xg4vI1TQQ70a50v4zS+A6gfpCs/y3CuR2O2BVCQqWzUa93cQgbTNdssRkbC6XD4PYG/LfYApZ9EALVDdPg9nqY+hqcnYzHyTC4PU42N/sR+1Vsf9vscP4OIF12+xx8zNv09w/hbT9KBSD+swgpjcJeMuxP84/NpsPuKvzL2ST2XOOseNf1JOnz9hwnoctG2M8sa8Qxk7W+lrwdDU2+3taQpAhsGMPkyxpfAg453KTmquC899u9Z/sf7D3b+7zjgTBiHwCX8ASP72UQmksmyHuswJDY+rqjOXGZmmR4Wvaln8SOTjRpUO1KrKvocAF5bsaUAMI6OxpTdEkPahe3ECfBKE2cIwskSvO2l8IMDnnpXAs9KmyB0oeRX6YBEPKDoze+KXYFbiWKgRlMtqHbfLEX0DtcRLkagvz+MOoD8RZvK+6I6LzSD4cr4XirGqqJXlejbNIfe/rRFxqdzk27fcK1eX972HO4HVZQu+RoLSnG1Wgz2glubwJfy/5kBIP+bspu+M9fNpqvvTomzcbpm39ztNlq3zrWOprfj1nztcW3OjegUZps75x+q3es9e5bHfaTfsHLVqOtwaRhroyYgvIiML1pdA74ruBd/Q1icwwXSKv8Q7pyPnheSz/pb4rzFxMXU/7zA8/ZlPnuJHEvuDLMh27yI3cmv8jaQbQzvs2bXEp6UaD83RZn9Iy41NqwEBvBmTQNp0F3ko2TQUuOelebvnpbwsqcsd2drJ16YWJL8VtvN06nwV1g44fhAD5tC8QWrS096Vxh0z0VjLfibCnYDWDE7hb029Vg0Wj9/jXl2lTvLPzHKm7supYYWOscIZq4ovkTWtSr0QBIOlvTqisIX6z91t+S9mEjaGqXf3CUEZXgO98xLnPxplUAQpugAukQYxDMnXLyA2wt1F/2dWZ7RrNEXked3VF60rkIQmg2SjLAX8YPdfhvWHbn9ilggUGSX0bsUmc5Qr7X153NxaS+yjKIJfM04cttbYFzsr1Qpq3jvPyAAn4b3KSB5DQEfKbzQ82jZZmsfkr1Bk50p2OXXR/1gDI2C+iszUPvCBdGOp6MhHRSqy9pD1a3JuMeioT2ngWyLdYTyI/jlAlzRckp09ZJ7Nd4C+4cIvoXh3fCftyTstn5nW5EBLrZYMaYvad7D4K9r4G1/GLv0d7j/Z/v/2T/H/eeNgyyg/+kEYieQ4e4oR89yxfTalkJnGMBxBLBcIxO64PlwkMWrON/TgVN5VkLunWU33pnIIGAx5w1gd6CT1N47obtkPAzhOPd5N1uLTlIjtK2A4jZ5O3bwaUsgRmtJFmMS9gZ0E9gceBNnKEJrvOjENiRdkDS7ZK6mNVOOtCRoIn8UAyvF5bgf6+eYkQI7tBxmvTxdkaTQRAfO9YqwbJ8DXnnAIUqDdrN+NaSFTtXaYE7598BgThrdjvXws22tsgdJnZ2GEI02gHrgecwTOMMVucK6Xn6reL9cLf8xoCJAv5kBcl0ydp1HXipt4uvdj3XS/GiO+W6zsyJNc1JtfQdQpQBTOG/SbcwkD9ZjwLC+H8ydPIgUwe1S4zgek6C3gW21Ghu7Kmv8+p42sdzhyeCntADOhH0k8/HOz7I7+N4hEZwnMfer4GSPdq7v/fl3v39D/Y/RtJ2H2kckLaPg6ofxdVLyK/BmpXdxUBmK6symleGbF3oTcs3CcbtHPNzO4Qzrum6qLA2hwIeBufGaZ9xg6QcOYeXdH852ghBYHMRa61RUYNSl3NV2joGzJk3fuKCd98NCrxb8RQKHgs2LVd5NZEtNzYDB+DMIF9fwQni5Ey2nL05m5KweiGFU2pvcQY4cdwI/xo4DUhwrfBbWL4gNfPcQmupyKC4jUwuOCVgcjtUDgCfVZqDYqay9C7prBqx8t6aacvX3WLjyqHkL0mf3GbIWxUgt4ZZwRGgSvCE4UzZGGFK83Wz2NRyCDaDmw+YaXnLIRVscj4wpnEuB1Mw2/nA6Pa7HIhh1/Nvkm7gU/coN+uRmq3ZWMc2jYoAyRroBQcfWgJMoXEASaWOAmzjm3/5pwBuNOsFxph2ftVBg/udRsm2VDBEqnulNGftyFLpG0KYLHMo9KTZ2GlU6Lhm6Tgt6TiLsVNBa+hNjhDX0nCYbdBFQAQAwWB/7IhmzbIp1LWTeqfAiUadOeg2VoW66rZXLwHyG2EVumQ0lGZaH3TNXpvD0s24PgCKPdeOo3MLnfl2MN+ZrwDHQphyQDXgoIHYDmQegSxUAsIMyR4wc6VwKlicVVqlNDbt0l5ELxioFTQuGq+96OC0Yiu44bZ0l1zMTpO3dke7DeM+8JUt5PlY1Y3qvoEL1nUHX9xPQGho5gbQlkuN08jQMHaqERzT7JTHArhGxmjbVF4xWye9GjADpfKSmyxVftZDBxzmf5UmuDwEvIyQcBXIAXEP4oamQMn94lhXnf1FnUkvTtnWzKiXEq9HzIyLaihi+qMVbZFIaBKOtCA69aEt6ebvsKNJiCGMpE0E1rKPk5G5UPgyAhRs2yHnvaxzcRwNENLF5SaO0dG8Hh0Ax5rzLgB8PRor/c5O0TGSZtQOBNCLPf43vgPMyBfREKpggRl8akiwCZw+qNHr/BBvMfHyQhpFfHjcsJbetXNxuU3S3Q/DbGs1Es6R5rcKBohN4dLAmEA7aKzEwxuNVjDH3+vLLN/bwU69YNdKwK41TC1NbkTPuHs4qjtpwaVDKGrKovTstAnfdDrYaXWuJdjNFEMtfr0cpu5Lzcmv+pQvupyCaZkibIXnJe1oBmylbt4SoxMPpDm1yhbWL2DHV/RmxnatO29QoTOqjqp0BeYsCrtbXLPaA1xWPrFEiaofVjqc7pMa9yzKd3WZSDeI0xVrBERPRScCKVG07XqHeLjrHIqvKdNDSmcGFUrL2ZeWlHquhhv0y9fP0G/j8gIdpBWiA44klCS468NesopvmpK+BKeD+eA1Tf+4GOz9EiSjr/ce7r+HHjNcEbj/yf5PQIr6au/R/r0Ann4Nb+/D/581gsVZ+j+GH9jb+BhSmXWTwSB2qMHKraf4vcvJuUGvuTB/4qRlkQU29cTl1dMuGhbq05G3h103T0ubQ2AWATT5SaRmj+pZkz7fewCr9nT/3t5jMi2RkPoYH+z/PABpla0r/Pn5/kd7X6BUC/8+hUef2CxOOd2D0RnRk1+FhCafvqtzTmcAQg0i4zjwbBpVbRFin6DXLEce/5Gzdp95Ab1w4PUXrtO+a/vu3Hw0T+YjEyksliP3MiC2KRTEsQRsaW/Gt1qtHAs5EYKnqN6VxKQOCKJF+Mw6NzqRNfD74d6Xe08YyiKGA3bvv7f/CWDys71Hwf4/EDrTe+atFxCZeZhjPqco1P/hUkBP8cTc3/8QD0FAbn5sAPz3fqPSjnG+A6W4O9Eyd/gReAMMJSxXc4Rswejm/C1kPvTbpNBiqWSEqW+EhdIRFqwj5KSIqVN2AIr4ItQ+5T+ngNGDgW1pgOEb9yPaqzMbgDmvR8kgAop7biscbpLSvUgLAdFDFkM07JGzVI7r9OTKBuOdRaBRy05PVRivBvMVyeber9D8DhsNFwuSw6d8Lsp1g+jzucSgvYcNz40Ao7FpukkNPyTKdG27kWsR8gA2XIVFlPvQ07pzOdomj2tkNJnVttm43KhFRnG7NK2Bmzq286lYhiB+Vqhe5RpwkUS8aAcmM06vtWguC2yQLOONKfG/bsguQaTSCBaWXB6Gylw5X1I7blrBFW78wjs7yayC105aK+jo10ToHhDxfIxsA3IIHwAhRKqHxPEBbaqffmqHpAoxtU7LsmaSfyuafxUNCvduQANiOG6em/TZ1mwknXOTNEUnZPaobR2WKff/U37A/WD/fctn3g/uzu92gr1/gS97Hy+V4O7CbvDNh58Gd0/sLmGfL6Dlw73fBndfWpzvzM/vBvDJT5b48gGHCt2wIwJ7xvnWp3B/8zOHEJ7BpfaFMCLYZ1tguAsctMISK7qAtiLuAxHfafmc9Tbw3PSrsMdw8nJhgISFNt+0VgWXJFMJJI2Qf9L/PGf9j6qUCZLtIefFNV2NrtY4qCoIBvmD0/2YOCKjLoKMx5LgoulvLI5bDKlwOYtn2ozQF7J2cQULXYm/7O1YXuCn96bFF5UvMWPr9ZO8dOhqgl/TbUEMO5HIh7UVBdUg+FQFm4JDPZDKQNKkEuavjJFdjsbAqklWKrRxO1a2W1f9eY+woOF2ZYVg/pHjd7L5hUUr3tOHebPow5Vor9BtyOhwZCaJU0Oun3GZ84EhGJD37mf7HwGOPQvIE4A0MPs/pfbPCprkcgGppqc/nMI0ysbA4/fEgYb9uMoeIQkSBhwajjaXq4eRbB0GLj0nbozzkuryz8yLlfC3z7jaDNUGH7WdTNves8Xg7sndw2fRHEYY5Nfahd1tlYdbNCUWB2O+++fTNEnLtOScHQNGbhQNM+H7f078jMSNl+UyjzU08S6/J23qrpmlF9d5NIQM2CM6lPv3iKV+TFv5sW1P+V3BdEaPCDkeIv6RGEAn/f29z0E8+hLPOcpL72NLDAV9AP1xEnqXZxgkqiAhMPMBSOvWj9GW+Bg02/s1h/UQ8XwRO+p71+FmXjvuaU2PlEhYlXhy1bWvhBHnnPaZ58Vp16JImuvWp5qS+z5qvd8HuVQh4XypDVMek8xxX4oqxXYguQ3Y7Z/ihu1/lAPhDHhDjRP2LHPRcePbLfUISUGY8KIdOP8saFsVJIQJTw0niFIRTJAHLZab+HwsqZOCSeGaRIGKKi6H7uYov9guZpcn/f6V9M2teBytYi60phim1ZLrQGYC+XypJHRB9mIIdzpYaB0mwfyUlAuc6H1u4V2k1hMwmCjY0/2/B3x/SOTw3v7PgcwiIVR4braWi07Cxhfrr4BRbcIl12jnK1O0j1OcVtMSWmJyTeJiEqpQY91OnQoWCjBey1tdiFM0xBeaLFbWqRblhrCPkb9T4S1j5YEPjM4q/vEgHqdmrwait51A2Aq737vCg5QTXdUqVVxAi+RVMzSotoBqiJP/E07EI+IxvhbsgXKAtOPzHOzONdFFESkqK/G7QoN/GIPb95Wf1bA7ngjt1ewE2HEIGHDxOe3Z0PJQ9OmM0P7KwnBSSCcgDhMtvuD4VCCl0C/IyDiNVCjuOUeyGiIPLr3Nomq3zrGuxGecf+d3v8Z5uX93HERc+N8hX/6lcngfYwztIoqLFg5OUb6D/NhpOIdeLBt69jHta2JjQ90tL/aqc/qKEgbEszIVfjURwe0hfHCBIfc8icnthGPUtWT0RnQn6nt5VCQYseTij56alatq7P0CNhXNWHufkRz/5f6HKETgpj8RXBP60XxGR/whGtQCrk54iuogjOkG8cBAhwI/IS0JZT4qWdE3QPQd2BPk5JHTsgGN0mGOHe5cCLiGoosrorbaGv6GrxGt4FOSvUlO1o/IfZLa9z8Q8/zmvV8EsKLvM/+l/Y9h0XNXMOiDICj45pGyPQDgw0DE6sBufdJwMJJDFm6uutWRY1wRj9zMP8JolTFwbO35cOeSIYhZ45y3ZN/aYVHpbvrZCl57DVP0ODdr92DTrr6XtnvuGSm5HnA5m91ygPVP4ODwvUQlvHaECttiTfXEei+VNOSZA/Cz3E0rJHaydzETOtXk6PLM1wGFtwGQa+kUOKL8BcM8kJRE/JsPSDTs+UCwmDe7tyEfX2SoAKrYJGj8QeXw/vJVZSOJlC6viS/D2xQnuOTjGlO23gq08gFPyRFeYyPgSOzJUsVv0Lb5Aqpk9ES98OJMHlvo5BfYPjhfGx/nbjjfWZg/UpkHLNEGl6DoDMek2lHxMKpCS0P9VtJkI8bg+cIYHs1L2axbwXe+U2/Op4N5iwrhOfC9XNf7bP/v0YWRVNNSQwM8JWMg0aahZAbreHjGsqVo1z4DRa7Spjnxfwa3jGmXA/LHS4Xr+gvGXMO18jX53xG/jPf3I7ziv2AcmMJydRoehe+/6rA1Tg1/fE2ae7IUMMUvXc2krkXpS0XISupbXxybL3GC5b47GJf176jNA8kEL+b7Fq5U47bmzD3gysDfQQPW/n//P6QLEcvFb3Wt1/9+7GRkD66j/lax/4fN7yNVTfo90mQypt7nCOQWCAiG8fGmptTUvjCYtRhdrjNqPQ9T3hfK6sLyfaVL1HyFXSq4drD/E6IWn8HGaJH5T1DI0G27DIWFnUwz6Glui3sPG6XqaJ8FhetdbHvDfKc4yWCsG3rUK5qavJ9tU+GdxvMq4ot1W/NuPDuP9N+3NucOVND8huFC5fe4gg5r1g5rVh3pVpiJq0k4P1ju/h/mrXKYnEW23e3W9hZ+OJ8zaYLxS+c78942a/42MOyN0hZWGHjsLKtRJlOqczcWnT23yQDqx9g6rTk68a8zuuBTd4c1a4fCCAZTmK/XmeEmJVMqLJjAH9EAz9t5NPJk+Uj0rtGyrjS9qyayK9PIxfZlmiIfq4OjZ9ebYsQOy6h78bouyiNpTOMwF+aXLPEjQqxXvo1ZELzsfb5ib8Y9yuPrXDHRwLZi9M6xYvSu8oqJUYzNFwP4P1x0dnx4WRBtPKOPo2W92MTfxL3g3nz8tuYhv3nFm8OwN/FoJslhUUTTPYpoEo72LEGkpkTZv/ccDFCC8VC4U2dkynrYfRvoa/H98ePBZQoTYgVsOvy+YwF4cRb0on68jnxC1J8Gl69cAzYigocscRkwd8MgGdqAssCFE/MLLx3rBFeGlMk3+NG15blBOISN7QXEE6ZxF7jzHisqF8S4I1tRb4JZq0MbVJhNOIXOvQhTV0fD7hS+fjsF5gcGCMewoGk6GY2h9zCYDFNojdGeAtlsECMhODdPnDyJWvZWEKLrHX4bHBRAihBZWfj4bj8Kcw+tACbafbtjA3kNVyhNRsdhanEKM8NcNSHzNYNFgK1OaBXTCOSQFOYn12oeeMfxVtsGFPokQ1z5Mfmboam8K3YVoY7SaAO2CSlMiAXpcByQeyajUZLCGri36A5LBZF1gr+OohFNjMWNwWL2omA92ophBPjyaAejYmCPNiZ4VoNNWNvi9xNeT7KIIZWGTU6TMVIve5fvfCdYZZ+QFd82K6vBUi2NPb8QNFBFEa8NgojDus1X/VTQ4CulgmpUiUCMYB1qhIMaJM5tHDUckgVNL3NILq4RyTDLgMTWlSGm83hw4uXOyTZjKNmP8gVTzwV61cH6sVoelZYN10Kbpy8Zdu2svmowtjoK6QkbrmBIiiTT+A64xV46oc6TIiv8XIbjllaBcKmAywdu84LNyUCB4/MqAKJwAW7QhblllTwTDcQsOkQcoiFckVFEt4pw3EYCBO+89BWz/LWDYTIOBlGKlwnKKMdR7ugEZ4hejoAUchvEABNChykSYOs1EG8AscO9ETdRH6YF/AhdSNtb8J8YLoGMVDuoJ2KZs2GWzKwLX2Wl3JeApMG+9OO/i+hb2fn5bga0D+h3/i3dPBEXEEj0xZD3gg0s8wlm3qNAx4nJOA7Hsc2n3QbyimxkCGekC/MDcHDpIEnPovRO1OtYD4JNMrOIWqa4paGCT0bzdyRhrSr9XSUOUwfAhZ92LiA5qIez85rSea1GZxKH2kJcqtdxTXZca1Ul9Jo8g1eawtbrA3DZZIZrrSDeoA580g+vW4R1Rfyj1or33Hznz5R/GiVUi1xu07DXqOTrwjkj4AGD9Uk2NxYRc8yO3sQ0CnDM6MSubkVwQS/Mv9ICKjBEmrFuJS7sfALZAIISA+8zDdanzACXBBtpMkC2JZmM55KNuRGv1nLuyiXg5GJYskU3T8SU1BlzFSLe/uv9eyxiae/J/keo+EL3yy8CMqGSsqvRIedgztjJfbGNwaOOtrfQjgJ8HPBpQKKAMlHnsNebQ28uYN/w3mwjOUvZK6Bn1mUgIQo5R8YIJkgEYSFksi5CuA6tPtwcTCO+RTVsEKyVfb+DYdxxlB0H0okX9N9FjPp3hf+f5IPXJ0DRJ9mYSDtcDLAEiQ1iN41CYtNhjrD/bNK0SVk3xYvMTuVKWR9/LpH1PBLzALGe1sB5j+EwP9Ne181OuW1RmX8JLC1svqo50ojYfyGfVFzt5/FlFgJEnolWOaMqVjGmjMsPSoUSu8+XGdwT7dgZ1bsHS7Vic/OQP4WDBzz9MRk8nhL5YjRX0aqrfLmy2eQQ7sCb3aprDlzVVufMetZ83XKnythhlClaaNftLATvvmsdsQzQmgC0xgEdQDDAzPjC4qBZlLSUNhSfonLEnLbbNUP2rE2q7s7LHXDFnItX866O6DsnFX8vaon27hNGqovEmfW6i2R4Fb/ulnFah+BrfLAlUBN2YChTnj/CcEqvkt4k4pXE4QY7O4n7PcWFUy0y3nS6nrY1fSs3W/EkKEcqENPcvhtptdGLaRWtU+Dhys24h7EkMalmmY72NS4+L8JT+zZgIalxPOzaAkLovYhTEcAdzfL0joX3njqII1njkpWEcza003Ct5D0D4rrtZN4gX0zHjcGAaQBu2N+vifdr9vd6ZXsejVPDjVnvzzLMGRjh78jV/aKPvbFZu7KCV88snj15HPO/utT4ubFbxBNzZx908AnOMrXWIoYzN8qCcGymes1C3ILD0GzksQXMtAwnQ2vlHsbua+nhLNns7fxU8WpfKg9eAOymPHvsSO/OHr3AbQCsLKUsZilPHB+On80X6kNfOTn1H4U3UXWnlHIHQAvL53UAfPVUMH+oPi6/KQQOPK3qPg2LTQ7vXyOvwzlsVHOg3QLlcXKYFL5xmt+dO+RcuDPt/wP5zKADPdeNai54yFvoLng5zbrv5LA65U4z/0WdwwyvxzL3sKf790gbLnIL7H9sdQ/Li4aWeonlTT36CAWcrcySqpXN2yra3HffDdyNHJrbasv4qRobwjRheGr+O8vJwM/MJ5g5A/6LKRdQQNJXcP/n8CNXgjfKoodNPj//mBfnF6e5wKk4VNcJrjGDc1oJOujIZzg9HCqJ/FUeqhNwQvkekT4W54NaXUs6zqXiMTMTvOz/HJDCOGelFMqM1rgm/C8LARe2M7J0xB20URGSxV8N90ObTF5sTYF7kNvee1lYyZuM5LqP2yYXmO4RuMN+x26KhzxFysc80U5+fcCe/VikG4B7cf/H5Vvz3Bx+6D5QE2+eGU6bUQ/vIJBN4f8dtsb8JKgH51CX+5fFKLmvzAQ0eYVYoRT4gm7i37JsNRpTtv8RnBLYNrrKn+B50pLbfKUdNxYzR9cT5aJkzB/AqXCr80pLukOihtV2p0S145qn45qjY6Q6JmrdbM6Jeac1ZyfXSJSokIab49/pTjxIA/Bma9Zm+ahvMKXVKaZnW30nxUJfwfdwvGMIDf6aeqkzB/BqcKIzfyjXr3mgSRH1cP+ndFaf0JGlkI8PMPISqYONA204UGTC0hYGxwtLYF2nCUtmWLU5WrmjFDGiyXHxGO1ZCx1JHK65rM+a7LPG+qzJPgd17/tUrkuZe9/nBkP4nBz7WIAL6f38/jhiOYVLjlgqp1cOo6MC+nPzolFQ7TG/6aX1warlxWQWfFpWpxrxsopHjV2HrLLFApqHc1aaOPjmA90kdJuwXZyzBEYXWWlKP/x5nkCTzNFPiHdyoevek8qJnF1hnTPGltYK9cQefbLL1QnuzPfHDNeksEwH6hvjHD3l1TU8jz1fUVUDQrAvmpYUCx0efg+TcN+k7Mi+WZIiurN6+4sYGDEMyrlwRzEUAaw5AayVAtBiG5TurugGs/Oao3P5yJar322BW0m2m8qE57T1awcnWg6FT7Hzmt55DTtXsdbADZyNxRcMYriHw94lNAwsmDerOA/aZ74KJ+flg9jEfiMRGvlU4kKIcX0EyMiYFkqb+DumWMfLQrInLJ+iywCoTfMYXvrAdeUfeLrAezyHk1vRGDGrQYKJF06DxFMeXMCTat6X9wKWvNAkEqoglHMpi8ryiu25O79I/l4s7WrbqYrM56VrHjGfqwqhE+z9irL7kOz4GUmXD3DCYuSiCIr24Ye5YETaFNQ8oyYVI/w+6DT8a6WihL+liRvuzE2VCeTx47nPPF/TcEyepzCtSRr2haUbHTtDLNGLIQ7bMTwhdy7SfNp98/PZdpiqLJg7HQBNCDaSfj/ZZs5YSRpvkmeTolSUaW07Lpq2FfY3KAWHcpgsXLfSg9FLeQMIbnMOhYTvEbwqXddkVyRsk2m1rpzqizGPVR6TU3wx4jHfiKuOO62tfXqrasc1veNalY7cKTX/6Iqd1tROjpE09Wne3esHvjrqA66Sw7fIGcqxLEnJoxpobpBsYERONGbBOxjnA1iNjoxvw7HIbGDxcEi0ZY5USwyX4T8p68w9Q9G5OmRTkB7o37W7VxOnRuYW5uWYt+f1HnLX7XH4NndlTEajJIvHVo9KY4qdsszv5RrGsk6OZDB5jBd9owikEZvokHJqsOZVXd+quT5K5HJzvmxYdwOHTUTRqkodnyczptq8pj9ktS9VNm/2b1V3tZplvzT5x4v5MMTW2lsoNeBVNjBvXMvp8wCBVoeG4d/SxXnBuP1f6Rz7d/TFnWJ7VAVz4OYBqyDW9Kdz4WS8hVUIyCYiQpT6UXgHb2q8/K5flBEGHV8KM4Hu7P6wmcSO1D8lZddTFSFX1WCKyR1Yj1kjMyzjK+bIxaOo5uQeG7osYxdslcXOkOc668o8V43HMMGdt+egq8J74BKrU8ptmTnkF7nkpOCkum+YUDJPRamboi3muBn8bGWtDK2Freyt6CQrzqo9XPFwvGRmYFjrHc6TeW63CiEWuQG0cqQF07VWiLXY9dWr1L6b6A4gjWqsrVMAl2y5+TIZtlz8BULHxJF+XNsShFSNVTjYRuZ2i9JdnC0HnLKxOuGT96hvd40uVXf3oNit7FrpsnhZCuXrc5pU6cuV5t/Kr3YzF+Y3Q6/qX4yNXd976A7+QDa6IdWSJQ9gxYa3+0fg1l929Gv49nM9l8+9n2u0DurhHxwLFv7k5U8Wa4N7e6Yb+Mnrf0mLoSt4XpgcyP22qm832UBDb944PKd+Van7HDz7tXP9X8C9f5TGd/CYIyWul0dYSwLftvmvRtbLnKuox0kfWOFhN7o0cIUKcDA7vC5pZLeqc0U1K7XZu9GwphScVoCxJmCsNVy+WNQ3N8HyNNY0wZa3z5rZZ2rpQ1fQtQkgwatkvmcwTp/GDAC9uEfqYIUvt7RsFstTsfooKd2KC0v0x6ungpdO0J/HjlWsT7XDMzg21By/NzBIB6Dk2RNqZngRm2MDvnZQ4OTrokSSis1ikUbo5VJ8STNp+Zhr03XJzcNzDOgn3bBPbl7sQYuVM+DJKthsZCa+pVJIay5I0xqQkLzwFJBt+mHN9ih3iYa5sXYtwciGJvugNp9OG7NLMID5n65UJKp/IpvD98g9K5jLD5e/55T3XCv2XPP3jHkGnDreiyoqSQBweqy0q3AVyENLPDSd1s45SgHRBLxuyym1KslmVQspKMPKWmPzLXHzGFusERalp2Q9x9GAmE/4P6kwT7QUfrN06NPBgi1UW4Zp5x1uzt9i8GFDlacL/GmLXDLmLaEv9u/iT4vwF5Z8l6BFIVI92lgLY9CvvIvnh5MBS03n8Qlv23MuFx9TdKHr0pxVqXPEUKmenWQilH8Dq9F1KJ4Ls1KJdIMiA+E4jxHcYCl3Mp5AMDbMhnWFSpeSyBY9XaJFqq5Bqqk9qqQ5Kkics6qM7h62oF7QMpnrqjUoFeWpdWUlTiFcwTp4FXmfGlbRbeza6IRYQy9xEGVmy3h3Z5CgPv9y2byELe4l3Qn2vuyo1cP8pXkjS8meYi4rVrTHNhbCQgjXLcU1WEYYtYV9KvS22hSsNaKrjjHTEPw7x8nbEVoeGiK3U91Km8AUvR00b4fZdNhdhX+r1MtkrVfMTa9vR/g1C8/DEsL799A3jpUCU3LFwwMt7fyD/Z/t/6NeBV461NnsIecwAexkJLD+h5RB60w6jjfCLnDRlh63OTLLgzLt9onbmHe3ZUdrJcwyZ0t1yZzSNmt1je8p7a2rETt4sPF8Cg1XQ17UGpvu/bN0Vn6QK1I+YgXARMKEDmpdfgcvv1BcFakECUacYyghd/1UU/+j67KrzPf+j3OzzoO9r7557z8a7pVc1mmESjLcnVaUYyaPnHe3uGBaKOSmNruqJ1dlD93NL+B9KwOjVc6FdLR3BYSOronc9czT0LYJANrzCpdF45tPfhtU3HvtsKmn7OH+BxULuTPfdzrRrLrxk4BOKbqKPoHdZ3h9ipVf1zDccodRZI4vnbDjyikP2OEElKdSthFoLJ74I/Z6hotIGWMQ/m2S8lSwfLwO+eo1v9v5bgs5ff6rTb/scRYExK40oDibzrV0uhKmWdSUw7WDyxNU/a6Op3306AAmbRNDj3zfwmRiAuEInOFYRU2C06eChZeXygpkFaRADsOItLLs/50k7jmremi8iiHOBMxxkDurOLBE1FKnEzqQ1hO1zDq+anrjW5djOvFhOmWqLQLW3QIpbIXSkIsMUOfyR5fCkS1zglYgOBMsLrDXIu+C0O6WFkWUqk7hAuLw7BGD+GzEhm4U5yN0y8L6xyOFdus4JnKHh01mdygW3KOZteWwHkUHAyHK7vnNzCSkbg+p+qGyRygJjcN4mP11NCV4uZ+Tp2quAuCm1umWp96t1tCix5deHIqIM/ZOxp2LkEqMMrSWX9ikz2+VLZToPlZjszWR1pHSTvyjfafsrcmmlUCQuGSTV1tloQMlX3cIRak/NeLJH3jiTylYn+qvUrKSB3AnshwKamzF5zyCUMvEYKSqYdyXljKG6q4hLw33rSdgzON4t+tGxKMFDJJUA1Mf8tNUhqSHtOKWIP4nvPipJWnOz42gfiyPpyw/i9LXgvpf0BYcqXxa/WuND/WDdvQFbYTTMqtVFIbXHOMfw6Pf8XhiDHNSwl+Ivi+JUHcy6ypJWmR6xqesCjnuIMbHf8ETm7Dw5EE4GpHcz8IzG/VqvNt/OYyOVykzvFqTW4iKVTUpL1jx2j5ij07IU2+6Mp+hHY59bc9SnJcnB1/P9a6UU3o9CpgrazxmlTZIG7vk1saaQIvKWaoOQEElbJzuVjjcBE6moNC3VxFqVa8hzAZ43cGUFEoy+Ap04HxUcNIV04qbeUvtLFsuzXIAPD66ypVZ7lb/ZjzeuoqFCl5Mpunq6b6fV25tgfHHjtUrBVwIW3Cz5aGoeuX7Wom9xWko6b8ZKAMb2zZDgA0fvOXiDk/lX/QOPSpU53CB6Up18cbHoGryUV2TgB3ceFYl/1K58KWy8gzGa1qxmsUZxLNCBVOVUa81iGQXvI7pXea35RXVVFOKgyAKMKJ2OWw/f6StuMrfiPdcEBCGEzt348YZO02zzr0diCJMcjCbZ5SdTFgVHaJxua6DHe0/Buai4nVt0Dv3FTwj0bNGmykDViLRs0/leVHcP1FIZQ+9pxy3xnHOK+UXPo91pq5sbGRACqW/UDt3APIdAOlY0ttBj5GFaO4HSPLyx1PxuFU5r/ATKYPm6SeeMOkLRbHP9j9ikTmU7gnaoTz9pJCY7VuRSpYpfi8n53cKKQfjgh72IAkMi9BmyEX2f4Fc+hMuj4IQ/AUmJdv77XPINWa6+hZnTwKB3JQ3Y5jydkcudedScidqEpJO20FjMGjYcxCM+xFlCTuDvjGiXtk5kr2ajkxg4qITawyfyOVl26qrBM11gOv3q+jSrPmue1zUuSu6fXcXgxuFnCxrxRwrn+q5U+lkspydqhWVFB1t1JZgTF0xD9QzSlvfabQDsXfmcr/QxOpnwywin+trWCwVhfUmR+7RVNK/9ZwUrudPx/nTsZNAqs6X4x3M+bjjTgs5nmKD6dILILH/SPneSOlFeZGC/Q8ps/gD/gRzfQGqPGK2UGz3NfT4At79fP+DPxHaGQgtYhR6vev09pekkH3IDxDLZ7z/Piprxf5QSKnYDfjB/eVVICJHtMzOVwXM74uks+Sko2lVPQ7tFDslN2+dDrK0q/olyBdNhyZEs0fGZInEedU0QunMnsiG4uDnYlcZNzKnp13pNCgmD9SMhynk4GWJqrbrHVad2q1cI8vyFYqfh/ueXfJC6k1GkvPNr2ZZALDpc+3GrsLgyeDUnQWCoeMG3fNU/TJvf6t6JLh0ISFq+Igfyk+YoeYLThmdRaJ0ykW8PxIvOXs8EjBFX88cwYfkWnkgBGczmBXHe2L3DoLm8BVuNNdHKGC67fUMyM4zKdLVS9O5A3sPXN8IfetHN+dvYVUyOo6FF0t+iFM7xAUXxAUnRMBbzsdizkXGEdFfbp52Nr5W8eSRBQ4a+FcFX8t6WEen8odhpiX/cqNQq1XIFOZurOQOc54k/VKXuFR6q/PpewlWDkohN2paeEZ3DlZXkSc1Viu5PS5ULjC474c50XpPMWWyhPBONuDBUtFTlUbNfeysqUMOlO7ogCLd7Og/swx3EDlu98VIdlgfzL/Vi8H/94sbhlDXhmcg6J3QBL1GOxCsqsmdMrQjBlTjOaWmRkp1L1SGO5dXRXf6UhoyyJnnJINQXzat0xhHqYWO8udNn8ecg0P1eMfNcEnzdeuH6xEqN9APEV0tWTwmkP80HjQdnLu7zg1BA2ouoBZcUVlEYzFYQEdom5UC1pGYicqHwl4948/wlNxd2CV9h4b0S6jveKlCbHzca7MPbOuBxSavrjEurSrRMOywPWNph4gR/QAdRgr85+Jb6VtDvLP5YvxVEsOdQQ/bbKWuJWfSNJw21WE9p+dqNCQHWyr8w58Byi5HWbw5pLupJCQGLjK6Wpt6L+ZPbMcmxCTq1hEprilcsmItCtQ0seRMTDfMiJ3wW1MLkzC3bqMMkncip4NXTladyL+WDsc113nBm2eK7jrPTozJil85iYoWdLD7nFrDR9kme/RqtBntwPm7hD7JbO7t4C8bf3PzrdHdN3bhP5d3byl/v5V1bh9vto69NXfr7nz7lZd2//wANbjsK/wwKFaqx8+8ByvwOeoCibP4e2BkUC/IdIXoi/a4nV9PLG/FAwzR2H+/HRxvA4Iz1dMjam0tGHJoWidfLSwqrugj+YfhD8FPUtLvqQdIocwMuPsweWt9qkd51r3/jawwbak/pGH8Mwq3uUf//QBaM+85PKt7j+iR/7h66jvy+sv6F7UDfgYKBZeNe2XWL/9VKX3R9KPsa98XH3yPRY8UkNfitc+UBvX89mWqCWClox2WbIL9+SrXRKrYSNIJb1CehEJWDhTx3BbcbhIshx1FdiRpk2YjH3UuLtsZjIGSLYi7jypwvC7fIpyQBanIsyO7V+JsOJKNKfSkGmodUklv+3XyVgMve3bHHgsabzUC5kJqdVKlOLe8lK+6cF4vqZz+rG5hYklYPfy/csxMOmKlX/CFzv70BQe3T/5aGpnukeih6c0lHdq/V1u9TQhL8mOvGP1Yrvu2MPHGwa2awOQAfL3nEDDW3q3cMC6Q84PReEqHoDTIgg84GSGi4dphL/dAvF3nIhKOKxsFal5GxjFaa96tYcmnIQbibkj2a8OxIqjOYOyW92IlJG+VRYAEOmUR82K0qC0P3Sw3WPGrV9Ioi9I70ZUJcPk024xmy1u05Rn14MJR64TbAaOJhVleIeG736qrb2byIA8p5IO4Fcr8bNocWu16ll275UkccScWVeWF1VKrdrYfY42/IukNGX+dA5JF8b4uEDTSxBVFFcfuOFjEA7BFNULfZZEo92dIvlGWkHkMTNFPsAJLuexm9+nQrYxe/ug5KNzsugVyr/hPiQL3bSsidGj3KbNf8M2Hn6I2osMyBGo+EiLk52u65AEkc5oIhIqcId+PORdOelpXwRoHt8zPwQvJcidyeJgsgUipUa5pIGE3GNB/0RkHRWAmAPdMhQMJw83XXl0Hdux051hrDv6+k/THgCun3+oda762eLPTvgV/tV5r/bmJXzIsGECLEPXgNf779TSZjLKbDYTcuNX5EbFki+r0q2QycRFowYLxAiDtvCZepRCXbBwS32UwLttbWOetyd6+KqELbcd3vhOc2wpTuN7Ui403ukm9bgEDQH+YlBdHjSjJtwl1LliwzgJbw+3NJuMfGpriwPC/uTl7bhSRUEAOvjpZZ++a8202hp1JzSYbrCdO51iwYFmW12xQefMWar8bVrThczqmeX0e4wNW0sWdwVpNAhXCnTgrU2f/fj1uKBe+zOv6KtaYq3ZxyKrRHxEJ+5yovQh4/MRSt/sJacpQtXQPK8yi49p9I+qxaKr6PToEiQ2gsDEfF58Vzc3Cp0wERTCVMkFqE1JQGs0dSqG5IpJwrlgqGVYRrwx4ZmHaj/i19RTYmw94hvzghsUFydF07Tm4GVX16Hk+8tWqquD37obwza5kFaxv0nzhLqnV3Luej+Oqgl6cQ0IOyiAAxFZ/TeUBd2ECRbumpFVs5zrXkusjIE8yfQiyzdY9e772y0tRiIRqJUaG5rAMmEKnfZoY5NwdKepR6lIXOafGuXNDXYrOK8lyLwWk5Txtzv0iUTcr0Qdyh58RhQcx4cdCrALJyeV0Ol7w69wpC6UedekAdKIM0IIfkFw/PmIe/Sq6YkRgtfX8T1Wa1OL/RSj5I579m9y5KT0Ry271xFGffhQz7lk6DbN7ZXxCWi+BcePPFuQzO4NMsBQ3ITpnjdLK2BXOAqbnT+N1YI7ZcVAn7wtCYV/3ag0z4v9CvMxtcxSTL21znzG9KizqAx5kUvT8O2QebIYDyw7raoJJdaHtJnpcSltWP9oYKwmFgKHdGldV+WNfgebuQ4GtvAdCi6bD8cthUrNSoBwNGbaqk5V422Eaj+hawvFcG9+F3rslFLE2i0t6kPdZUg3djl+NyS2xXsOU1onOCDIjCI/rM84Mp80uOiV2cwJFEFqVre+okDBr/n5UUIBJkzezBYtwLaoOTpUMyHDIaNYDK+OKEtxqPxG5Y7POpXgo5o7PW44zhE5klB3vdABSmJbETn9tMlWaSU7UyL3kT6iVce+1S2G+sLkuymmsI0Ed/vdqoGAXPCg3ypmmarbt8a0KwdVwDpRzdXaKi8hZOUKBtrLmx4LYVfssOG3TnPqZbZCM79SfASoS/K64YXc8IWpiXmo89Nm82HAerrNvjbfhA8zxCwi/vXPi5YM5eNbgfeGS4pU88sxLjKEqBGyJ/D1ogn5aKPTBV6rNv6OSSMLEZ7FbF9JIyAkkS/ICtReX2+ZZcSCO3sueTMtna9KDF8pvEgv0IlCkENJPXSMPDow+lx87X6JlJdXJKXO9rN2Wd6Sk70Je/cNznzM7vKkV3loJvDUXvItVdSFlVs9dvyWaeDncFCWNfs2wo3K6rBSBkon13VyGqdt/KCzw9ssdLzwUQunpfZne6Yni7CTZ9f2POgFjRBfJYF+FrzbtocegJxNw/Qtb39b+T/ABz0icY7lSveyMW1Ajlc+m0GccjupHP6rZmOW1ouNc924q89si4FTvw5fNhs6cXmZbZLVRAJz3J4I0MVnp6TNwVfGqZ6CWdwTQZbeHffEmKGxeUbdj1ZCU7KZLe6IPV04vjhodZnT0mhHduWUTeFx4fV9POCwjKBwq9w0z3/JstMth5/DVOatj4LQQwEOlfDor0wkssQUYNb6wazFxEsVsB/mVYVdYiPoB7qpfAKBt7EdbX8Oq7tSjMKYUZiyQHFnOONq+MuzDiaMnafTOJE6jc8lwI8a98Ng9v41mHpAYF+oJwWxJeLRSQep9xhzeDXWgS9lSqra3GFSY7KeXWGOaFiLGGeOUzvT7RhurzkWIgCLIg+eAjHqCtmcyV7L5hlyenFEjrLAYAysSCyjVyCIFvFGMzNXHGWgyczZke1a0o7Am8tbjlhGZ8tibAo1Cwc31yx0/xSNMaEw8C3MZQpkjh+8bQC5asRiULJOnh2xULHfXqtFNqXBXEgpCKeaUZcgLSVV10i54Z2M1cNNOSjcWeSmT881nUiODjeWXiFSmjBA/y02sZahrO2n+anrenk4svhOmQTRC5JVr1qrMPxZHCgiUDY6bhyRphZEhlveJ058Sl0mR80Mri0Z/rSTbABBLss7Bt7EyXG1UOh4LlPdr6vuX8L0vbBW14gud+bruebYlosBAtn2213cDuRSBXJY2LxY0wtxUbV5ulr6xzQvL0ge1SfXPyrth0QxbUQmp9/YUeeOrssCiGFut2dwFd2sVbONMGu1WJ/+MWlXb6pzzf9v/hBSsT6yOhsihalpWhR2jB2ba4qD5zc/+72CBuK9Wo3qJOW9JOWUd7NXl1IViheZerlgWMxysx5sTdIM7pUfBLQUYvJpP9lr4dtR8pcX5abZNFcr9ektL2N3/7s7vzp1mvAnwqcfVkpp3T+z+pYwtBInLDqErsZavjjw94gGdHguStawBf3VjXAwEesAjrxBpHuGjZyIskR5/ziKNH5O9l5XHKSDVN+/9AgsQf06G+SdUgFgtt/KVdrNouccxwznTh8id9l6beBGsR+RnoyGiVSzqRVk3jUciwKq6Lha2eDGQW6xeVrTHbS4UMQdfOKAsfMOMKqWJir2WfyvbrTyjHVd+K5tePKOKnNFSY0qREfiCVUKCZVZYcbbCynIUYXolFfsRXY5DkK9YPdQgHGbbVKWC1286m+zAh8IVpmFcQIKhMsvFt4YsxFXdK4x9gcd7/8zlThSyWZ4j/JjXkGNV6/4g9ikfC6/zOZydjMdU7DbKLifqi4uAxJ3/NoEVL4a4iDXh33T0lPapCCtfdk3gkfkUWOJ+GbEjAle49GzR3x1Mfad+/eE7YTky0TJuWMVxh6BWRP2WifszOxeRvoJLm/YsdB0/7j9fd5/lpDtO0sNz9Pm2C7akdVgPe2Y5saYvd8KAHcqK+RNys+oCmVU9sY/V4x5dqoZm7Ih3jKWxR8ipFSoSjQ6jFpFTCh9Rze2qMjZmN4AurYryy45ZXj0alYnNXnjTavBUedoODxmCYRSSUp997ptbUSrSMUl5jXKFST7WLoTtuKSvKYld5HHU+b6L01f3Byck2efa0hicH5J1vEm3xKGhlo1VGQca98hKhH/CksKfiwFl/sSoUSkY0DUMl2teMNFk6doUsJNfa8Uw78ahiFu4Wvi9+WIVLCP4utyIx+KJ+ZpY6nLTRYGq4UHEqfJiAJwb+jB/BCwtHNFJFxqG/TmZtoCuar4ERdmrYw8MaHzzy38zxzGFNm0AxpsZU4d9Q9242k643pielHrakP2POr6kIXIYEpe+36qbQOTsJANWaHOYwHZ0DyUDj2iKVVko927SvxMJbzgYzqqkVnyh8tQzVFWwCc9JaVjRPVGAI6TnaMN9V1bkIwTqd7TkPfAXkDRn8+24N96SlA+aAfV/E58VdG3o6Bf1rKX6xtyKL658WljF+SGzjK/dtzmuV7hxqaaagJybBfL1atlEdw6fiJNdikbpkjKIiBMoBqHjYI54zA6kzZRQwXI4DgNKGS7LwDIbu5xlob+LsciYGxrwFvTXq+qnsmcmVyEvZXXSeXU+7OKIvDQWqlGgMmwO+CUZ84LzFnKU3NbpIOl2JyOQH4UGz93Um6GKhgeeJf8y+CKLxlQOdxN73LJxf99ONk4pOWASktz+UIOUCFxQ6wMwn0sPm/WCKldK58BiQRTDjuNmbASMasUr5YcB1lAI5QpIqQolI6FVRa9Z6kUiEB6gKQuxVKiGqaMtAYFZ3qKD6CnSUI3DcdPejTRCBJUjF0AJ9hWX5hRbIvZ1Ti8p6sXVnlo3+J7cv8iLxBaAdiZX+xb6iJhSEcz+PacrfI51F2p+ousK+ebDTwvMUrvRVieqMJ/CCrCD37JjWTfvSnqDW5XLIN9pFISAcSUpCBjLhlXNmTIN3KkyfXctPxDKMilcUjHIqsn1oSd2W4vCywNdYu6+tLskHVVP6pn2qA73ewLIy7rrR8OyJY29/4naGwwrRD+Qm3df2b0FjPC/68ZLfPEX8MLmI0LLWXwuUycgbyTzhABbjCQ1aKiPhuIRz65QgMX8l4tDSz7B5bpSeEz8oGWyBUOHOGoKv17SrY3dkNooXY54GCC6tUwUtB5Ojm7HQFpHqWJVdmKSTHHyCliX+SIvOwWgl6pVsRnDfQVs71UM9mg+f6+ab4mgktc1qyClqBXMsPL5/Iz+cqwUZgY7IALUviC3nt/xUG4q1POEWPr3ZVDLwrxKJoqBbSLDuk1QSvq9lYqilUdSWo+QAykRkw7qOftvZAnihI7lpmJeb/dQ8SLMF8+eSw2GIgK0JYIcswZUlMceW/lZK65RxKMy2uzZZRQpTrgMiiQy7PrAvNjMmUUmkSGTpTAzolqK5d3h+ObKqKMGjxhoFcxJtGPBH/MLB0qYQ6m6uaGQoYfMofmU3E+FtPqUaYV4PC21eUxKOX6riiVp2HZHkCWYjhInUR5940cTXi6Px2QBNAKgjOFYXtHn0DCDpWSkIkZSQVDMLPSAFyRi1Y5YlW18EMgyKdbc5s6oF5NWKx9eTrPbxfCxlm3nPIQrxKNZQ71TR9hiRLHlti3Q4JoKQ7DaZGCg17nARMogySsfMB2+99Bo54MafBzEeZIkSr/5QGio4ZJBb2L0csMLW+CO9QjNksag1JmkeiYpwWQXvvq+doFoiaQUSpcz30aaa0Ys6USQHgcYdVfiKH5WvS/xIDvTTq3Y+Vv8h5OEMgXc87XDIiv/J16xMq+IXoSz59B9wNOUfhKwdGhAlj8mtNaZo/zNA82FLa9GVpVnFJHswKHOcgdaVk4FZd0RtUHdrXFeO/qoVe6RPzx2+V/JZfkB+oDp+KD4+tx/4czy3AtlludeCLOsHT5ZXrXINt//FrLNqO3haPKIF4U9LIb5kNku8hMrcEyCshxKxk0ijQ81DlhkI2WfrdvS0FX46zxbp7qS1kSjTtOXwFe32cvDM5LBCvnFo4ys2F8yZpIZjTA9BTVlvw+HlTQR6b86E6l8733GVSpk1cNC3qOD9Zj8FvVYEYWBPHEwBnLOxUDyBr9fFvFqxH1gcscq3RznYhvzeKA8okcviIImgGRbSz625AwGwnMg3KC+851Ae4y2Px9fdibdnGAmSuUcqDE+luxHNFBAh+FhQOCfW+WNQw5LnJE9FWGKfLM9QYoLc8slgYqGBZkFBDliGUXl+Hp14YvOfqIyvIyJm7nIR634MYlG5FiWG4qP+H0FjdnWcxksugpWAOf2GFRM4blgVLSFmwu85PW5IHzubsXAAYUcJPObzR9dCkcCpSt69Nrj52xNnd4bzqA3n5NwlQBQLQROYq3iCGDVJSbbIAQ4gkLzleqw3SBNUlMJKksmHEKrqtuDKQ+UuxLkhIxvo+OgsnkseV0SMIvD+R3YM1xXuheDxkqajDrjUaNF2ZBdDdJxw5P6/67XmwG+mVVdlYKuZfpyVVvavWiPvEOJ8m6+tcFucPx4sBX3gF86Drcv0fkAbUMqd+SEuVujoKsY2+ZqccQVYrkjgg3Rl3fJ2WwqwhDRs9fdjAfgaHGbMMT3cJxjCOV7xdqHMg5TdPaFYxqRjc5AS+eC2gIwnY3VwExnIzVg09lIDeR0NtIDPPkPOwL4k36UxWPGgNvojIH/P1A85kz3qMO3MQ/a3H9fibK2BXAqoluFgM0yFtkTwVno6ojo9MRylkVxHmzVFJ6MiftMI6iUiVi0hL8ePHrRuqhHysKjy4MQVYXqUeYwZ9sG3kS6rJHLIAZHiePt6UOHmjfHKKoXLXZSYmZeokrT1bL4t0eBM0zWJUjKVA3Wt+q6eFrAUpTu6SxBdgI/DR74kDWVFrxpmfmmSrhUlaGRbp++6DzBFCxVDf4zxhe5tNs5LrqSkVO6nGJ/bWt9UEoULblb3Z04IfOLZPbZWlrRBqSHYTKMGtaXi8UzeixoaBhNFdjyQ/nC9T85blLoMqp3SM1zwjh45KtnjV0+aSRQn+F0ijU/6Nn1vM1voN+vsuhHcTYJ+4ccCvOtD/HUsuaO0gT45IGjkuUB4j21jiBwsLUOxskERIJtIEEoDoKY2yfa1PkWx4ceWkjB84wQKM3qFLz7rjs7S51o0zyNkw/eLLGoM6mXSiNSZ9IyaYyAHpiKCblHLnd2IqCFcFVn0wOHsVohl4S01g3PyElE3XjWzBrPKjaERbWKEFZu2MQy019aUyDMGLcBpOcsMBDCezkKgNUPuNJDWuI4wsbj6beREOHRVnRNslS91EWhfc7VgHRRvoxuh07mbFo7B9HCgmQ7IyI9NvcWXwlUnwGY7a7LAuyDSuedZT5gUHJbhZioM0jKFXkoO3oNsLkRVoxrBh/yedkZZiUK+4Wdb6/esYHaxPzoL5pnjr3UFvmYH2A7xxWiI/yHs1Nr9rqjTHHZlLoOGKzqRVx1NXVKaS4W+8AOT3RTmvK3SPNWojQDYgBrhQlqbwPcwSRDhouc2IANA/Cw+MBMg8BEml+eVZnIY84RmHBZse9gMw1HW53gR6gawkzOCCSNRlgpEdCWNnoEzYRNvuOyvog8gtygyFpf1QGdOmJxRnQBaarVU6NUlLpVCn4v/TGwmpzDlD4RRAupEgV/4qSCJTWUBURnDeWj9l3U6JkE4vBFsUNgx4m9wspgflHR6ketoZtwpbYPV7bRzE4Dkmw3gS3DpRV5iXM36qXnSlrUgSqQGCo/QuH03On7MCgNy2Mmp+WJNzPzgSi9pBGgRyaAnpYdpFJ6kBetqOHCrKI5WPTkHrGlHRFpQT6XpdeeCUpN/j0u3Y3zdDmyIziTm9g+YYYMJ8XYT0fGk3Eymuujh0j13Cf+0EhrLpSFE6XJUER1X0GpLX7dqrbHpRHK/WAyJRt8XW8Y2TfH5oXKVwyfsccdRUAvZti2GLkFPI+Z22ziNnRzVBMdvMZBs0KSSlTxS7yrqDvpl1SWsXvmKB/Ikrk4JSvltf3Tqxay47EixQr0rrhMtM8rLsPj0XGcgDX8FibpRXzkNgqilrKMvqJ9nrWa3YUp93+2pqgK5BCW2Aie68dknOxm0qvQutfkFQpbGI5BhfquN/Ov6LDskBevWyKzfTxYWVB2l1ejW2DZ3bhBd/4g4RmPYLneo8sDbc9Pq8RTOmIx5A4wGt91V2WgV36yyvRwuof5wbDrIEetInY5D5MTWbCHRJbge8GJlzsnvQtzJwH+ZtVz7to5RvsWaQZMEg6lVybjKxtXMepBWSICUQjVsJ4N5KMm/fC6RSRrXLy8fP5GE9GHzxDDI2bP6tFo82E589ZqeBfXow2yK4EqYKQHpszVgavrblc97yWu98yyJvneBZSiqFq6pH4yXnIINJkeK0ygPXKM5ldmZTDYUlXNpVU5+bWsRBnsfQEHmXxDgBrek6kQzZxbRQaF5kWJgqBFMVqYPr1c9vZKoeUJMQQCGwVl9UKyL4YfNTE4n81kGL9DReRsSchkM28OMlb1XU6tbtFMi5xt1azRLcKmq0fyaMXAWvyLaPe1V6wWXZU95RBI/s4sbmqWPZYf5WZwX8xO58oHjFUMmEfF4W0eoyR8nRw7V1EzAnD4FKOdJW8KUplFKcxoPVg37rD1WkBZ+ch97HPOGaE/2ic82o5yEGDhr2CROgp1iOH0U5U1k4E4FOH1MXqzqYW3eAitZP4xjBarcOlyMDT7OZel5fwYf8a+kQWazoBxGpIxpkOIaWqqtbuH6DHvdD8YJxiPIpBWaIdsQhq0zI3SynxnZQw/Ncohf8WCrv47Y6eZNEaZZR/Df8Wl4lJicCfR/R/jI0vEojD474z6cTfmiliLUtYrx7PPtSyNW1urD9hy6slU9Dg71abTVpCjbXxBW8WANq5OWXJLdfNPMyuC41rRWla4WnBwBvBm3LtVwZnFAeOA+n1Z1az1ojKJ18oNOTq0rJC4arTcucermbbR3ZGFSzhbeOJJtCFZTIkA1qpr+Dx+PDgD34oGLbSTERddcNxej/rJcDNDi1nI7WSAK5kPaIhXF/c0I/5lHfUOgNmd4MxwGiTjrSh1DOcDq84ERnhnEo9QqINdSCajpWCIclI//rsoiMfYZrwVjnOC5QNMwTBBlsDWdJMBYiZly26iuBLthFh3Mbh6PVi9HMwBxU7DYQZvBuIbWj7QsDdjoBcj8vzHE7YVBVk4iII+euPy9el4DeJI1tgWKQIcJ00aNrT8aUL96Iz/mOjsx9Jd90FSryp9iqhP1YchH6G6mCvpHHGw+hAl33dTa33Lb6SulwVeu9m7LAlFGRVeHYfdtzk3i38KmVo+LtZKhTedlUm2pV6LepttwMsIySw2ddik7lpF4+4kpSSeNEYyarpEDPw6Jj1M0lalrMCUiwuPANsF6HerpcCS+DIEcMo3Dv1xNUpJPlYZUZJ8xqKd5mZ9Swk/e/sKt2S3kHjqj+eaVO4u6D9fepnmESOB60YzLk3jTvN5D/ooo5lB2U0bOYIU6/Kht6eIB8jv2KXahSHEAPWL0f7GsJBYY9+5GfWpEjUU0O8H+z/lGTdY8YdHUme0ZFg6eekydZ7Gd2J9Ell2nDd0RomP8+xFDrxnEHjhJAflVpzJhDZubE/bx1XuDOgN6QBbPvZCC1Xs6F1rhwiDraHyhX4BPcxi1KOCQBkPQTywdwl3lC6Xo83Q3WVW2mJ6+rqJC/u8NVc+nGnwKn1jS3zp1NXuNH1YS3ze1KcgIlhzmKe1YxAI6n3M9sYoRHE5gvOWSQsKP9PKzr2k/XLiEAe7FfY3EBkJ+vHghDl6rlFi7l1ZIfU/7cthyE8sBQQKGerX+G7Qg1wlLldzK9L7vMidaOSIM8aAzJ1gTpzJsnxMsvsc7RX37p6nkp1TzPlLOEU/4A2h4oHU58W4TK4N+y3XiDzc/9CwT4tKioo3N2lAfofqLI0IP6GnX7BkYJjASKQ+eoJJIXOQ9/FBozT2mmHvXMl64I+jHHtzZipGXa94auV0jaPLm6JJp2k3CFKAt1CrFfFbKJIDDcEtGXPO8iSB2qG2tdIS2FkPvSWHOLs3yLBR1K1LmZNFk2swrYFb5/PcOFrj885AsnNAHFhMEXG3RsJ9qS4vdrxEO8C68t3Q96u+vlNRaDljutrFqzfXetlUeV2mAKulI2179aDl6n4XcT4Uwiy+S0RC19FPxla+EI8xV02ef2eCRlcFeFusYKA67MZZMrS47LYc7o2Hcq6ZT6EgHLJkA3r+FOjJwfXOSiwy1wIzTTOS3S+pmO5PlXpue59zGkpp4j4vJvv5SqPRBb2zhmPsa1ajsU0s559aYhJ8fupbMX6pCvf3Lv6Kmf5JUVxUFB9QaP42ish3n5/gXE0zuXvkkPXvh6pdr683zektHOs/Gj1pFa3IYeau+c+czcbsNTIQhPz72MXjKKWUq1koE+VDSr7//BQtpU7rlVQvL1r1rClR/kCUz9HO2NA/uyPJDZ00dDXU0vjEq5k+XGXYH6DwVVDa/VFJYhRIa799Le4nPG+NQwIqT7ZTkdnKnPlxOH6JPWPBcXhufVKFcIHknVmaIHvmEcM72tTvFZeE57bPc5PmmFiWo8QbCbFuCYKol91UmYhV2ZgVE4da1W3Ei7M+p6X+TGPU+ctvoxct0EgaUTiJ5mk0leXxUGY9y+PBvGyFClLVPbL1J7hy+YM52BuXuk3kfM93gm4Yv1itKur0ct2H7CrHE8LncQxqbnjLOc4ndSkeNqvFgVkLTfgPJnoWezz1RQKAGuuh+jU/FQXZeO0jlzfzzOeeHTLW+zQcq8mwpx0//uZbeP7Y8eFVGpQjRMeQstLT1zAmqfRwlRkwGaz65st/4Tv3LI9BEVvI9Oe2TJIsh7c1d+LTYv05cfXgDDWm2HUlKxE22qXZVhWbl8NBNPtlnKz/LaYwS0NkaVgEez7q9aYYoA3nwnkRm874AKzEDx935rBvax4pp1ECyc7NvD5G2KUACHT6ehalHUSPkqhKc3UswW0CqoziUWDnMW6tKgu2e+RIeQQJeWrhZFCfsBKmWWSXTGUFV7mOzgKt+A/jH1fH0z6Sg+E42ozSdmkct4kcjoJXE07CbQokOqSnPaHlbAkKWc54GmVeZnOURnNdUgplPOOy4vE3xzh5ok9pNOwEb25Fw0IeDxYFxRKlEJyQ6E4yxPtonAW4mKi1D/rhZpsLn7TXw/Fx+MDQCE1E98TJGASHmGfXiAeDqBcD5P5U5mjZhokEk/GpC2feWD3fpk89NRwfW+gcLqZj2JkRYGw2mViPwl137h6+ygor5D8RE+08EBf0sltvdZSBr13gHMXvSmGqJSGr9m8Yjv1xqzPFsHriWc1VYWVpgcsRUjpVmTsMj0IHCarqPVRw5i2LBTVK8FQoQukK9LRUByvykmOlSpimwQr7/WQ76l1Bx1xnfGL9QIrZXTa0CRn29efjuvH8bSAzmz9Urz494/PYIqTP5qPxHzwMiJfJfVJkJUXG5i/zUuuai0YNTz0/El9OznNvdkr6q6OxVg6mEqYqaSsKGlqEsfSc4o4syK9N+U9mvNJ4DxYocEpzZVWjLE2LWvCa2vSm8fpWsFjdYnVUoE1OfFy1ROrHgSkxd6y6GLow0X0gzRv7P9//uQj6giuCB+VR2nqsMEbVtvY/2fty/+NOsPfPWK6LZ7P/Es7pV6wkkVBskEEFqyVCP0rY8ITs+eQxpVjz28H+Tyi07LO8NCCmfMCcIKQWocS5jYOdc+v5sp2oKpGpVmCDcOTwEagXIn+wfGzsfqyUje1Mr7ccZV04lcAasRsPQzrabBoY3IFB4fBZVcKEoVk5s2AbUapFGLqD2MNYBn7DUyvkG1xrPrt8mm8BZpDm20B/iq2QczL3A1vZElzaKZmp+SmAZVuEQD3++NSb7DOaRtaREi0c3eQd0MHEWE17H9vucM1qYTeKWFGdxfVgiXaBqkxelVOpddYyV5SER9Y7iGpGhUI7fthgX+wKrKoZEugbnKHuVVZDyZ6lJXJ/E/As2e5IYNZcXTKg/N132VrAM64YfLW6XvDfuT7vPhV4VaK+Zek6GYfc3P+oFfAKkCy6eO9B48AB1WYNvzJ3QgciyI+fKTMm9i7PiMkG4mkwHfZwLd4u7r3I8mJcvckGBx6P0N0vLfO+siZI/pnsjZN21a+xVW216gfMk4sIsT/vcccPFWfbxNSQseY9IUQX7TxPiZV5Qo8wLcMzydYgcCXSnpbY5SZ+lJWTVL8m7lVyCeWEB1pXpDqSMqh015IT4+5zOmpqnkBOccWnGk3KiG3ZN/NMVSJfpy7wXTw/nAwAPdaZD6VX7hM9t4m2Wsit4TnDSDBctjT2mX6/WU2GEz3ZnL3xQCf8uhtFuCrIVHZ7SVld2dLCDLnarJCEhQ/BDMvnuN0Ec6FUq5RQVE+vpPEAOEVh6U82MJv4eGsxoOrowZCphLlbSgYMWV/gFGm2k41xUUOdRWlMcedZXl+FFn91K4ow4/RGBGQNTfvrU0786TOAwmAc/HgrLICknsRlZwnS2gxXQSYfC/uYbTrOgmFC/HDSTzanc1m4EXVmdBvpig9WCDo9WJqNOaa+B2WKeSWgU3J25ewwx5cNwHdcYm+jceJuQoKGVySvf3WKSWlacJ4cjn9hBw8qonkHG14vM/hRcWb3Xcs+0DfcteTwBsu9Xwt5xORoOVrXzOZdfvv7/EMkFdKDMcSGtA36Ui0io0RbdInmhaZe9tep4HaujMeRrkabmHUaXzbZTnk0VUcloM7qpAukJKuirUrpysm7vo55MqgCIgfi3M3XAmbKZHZMGwRyly7ZRyf4RT/4E9XAL/ksxMhmKHfZ3aDgJY7SKvM6hHVqq46F8nbZXToMYw3Q8wthv7+OHraUUWR4J06TIaYuydDSmCoXTrIOt8mdkKcm28xU62TBjLmBFlb6yKQTXI3CHssuwq425QbaYBdH0IvTCCsedGw8kXnbIyniN07hxp6Vg1Bh/gEyE7abhn1NoTYiYIFYdQv9zX1CsutNfT55jtFqBNnv40GLYDRh9Ajr2d7ehJ1R6RCfsi3F1iAnPM4FxjXc4JjOTtZAHOkGnLGdhpvw6ASn0G0marPohtmYhcIIvoFQ+Wq0oX0feyrgcpcO9/Io1Mjw2WHbk+HBFTeHdlWI0dvBXzb+hs73W53mW71jrT9vtFnLKyNWJdFZ8oN0OXIAubFlWtHi1NX1VQDWuyV8MmrUz6KKLGyFwoRGMCnONSoVSavxvDaV4IxsrwgRtWrry3nfISNqLl5NaXXd04yRsKGLfxRz7DB+qRqh8mhq9CGvl495/ZAGLYboDumLlGNWgRn0lRYsQr9eF7ybkeI4TDqQAtstF6xuCl+37kyMp7qCOq8DB9HgMAoRTLtHarJxJmzBzilXUClb5/ISVVmM2TgV4alYqEpXv8qjZZJ8Equwkr1JHxhApgRANOpHBVNAO8+ufCm5E62OAQTFfI2jTPVgoPKyUs0nPzVjF8RKGm3EO67v5W17SZcyrbtETyJpy7xRDfJhGwthXXYQMkZN1Bb2qdQiJlZWq9oYMw0hNRVvk0dfQ+h6FtHB5fVJ3Otcjrbx/00l0Xzjsqkr7icgeTRvh9l02F2Ff6v4O7HWK4CsAPMguVZ+zWz+aOLZv7f/M5Zl5dne16Q7v7//IZVfUJICBPDiZ/v/yNx6qDiQmhDApgY/14/C4WQkzsAPoz7M40w6jjdCEKls9/ntEfsueWym3T5xAvPutnBo1vvAVGSZs6W6ZM46hazVNb6ltLWuRnROcd/5FBquhjxZMzbd+yfym2chq+/R4u79lhkj0L7QCfb+lcqqfKEmWVCXWjiB2F094K8fS1cP9NP45r3/aLgXbVmnBipxcHdaUQ6UPFzejRnrbJxO55qMznnQ4IJG9goMoU4VPXBWVTqJqlT1d4XLrvHNJ78NbBuIBlJyp6GoiKe4jdqJUfePkhE59g63VezdQ/zzMR3Ne/s/h4P5EDM4U5wRDg/7ypDzFNIaA009FcX5DRSt6CesWePa8NN6W61x271mTep+NRr1w26EI+VXJTtmaf7K2tV1S9p1DO6dV2m6YZ+YhU4f1akOmuXNg5H7aoo3V9Vv5WZYb7wF1XzDaDWeGFzFuP1/ZAnEgTDodH3vKxVLOw1LdgyDW7CRjeJxUy/cAs2wW0mNJRGmZ4eEVEJPdGDWEB4VlSyLbuGT/STIQamAaTBkV1slTIMqWamVJcKM31DKfWXZQHVx9Qt4JU0QvMSvGmXc1fXzbhVPYpCOhX/ueV4S93VSbGVjkKD8IQYqArZzzGqre9hRobbZwtSNFCgoMpyfIFZRTN85Q8G+03xajtQzBiMhsnLfTgm6naew8xX/b5UrBb21gaVg2ZqeEo14zGq4wRUjMjopCTOeBOeuXOLVIoFkoIv3+/z2aXjV+w36+lPF71kyby0MNFwSRRLpsfZtNsnXQWh9aN5BgXEnBiSpiuh/2pnD2BljFUH4ijemVVllpQDp/ifqMqgr9YxW6gEvkvGgGm9VXKVdaz0MIvvW71Ub0Oct1Q09o9LyMfA5PfVqtWPved7QWUd5i5pfFb6TF+J+1OFqDRMya7QSjrfsRPs11hvtVWf6fQqFdINABU43wXed69cufN8OcdGqxsRDKxfgqMhop35Ihwhv9mY83mo2Vs6srjbc6rgDlOty0v3G3qda8iAh3vPVNvj6vceEnvvvY+wW/v6MXOe/WqRtPsXKGPPPdReShxPHXE2pg7oaRypeZ2RZjrCGctQ7y/EIUIKsADp2XaVWrMyfOpLtskKodHpjds8yEfvIzOyBnegePx5c24ry4hR8oZPtYUa20y6XXoJRko3nusJqKzbGBZN8iFhdjHGGF/N63I//jllxuWdWsLIVZlGwEIT9FDB/Kj/WBVP9ys0oGUSo0TqW57Faj9AXLMiYBhAPSLCccI+gSXfLBZb5OYVjjLDjFmS+CHgAloLoToTOyGFvLhn2p3gJBCHxiWiYcAHdRKcp9I8Kh7y2h1i5ZDRK0vEEU1/z0WiZUWMjVsYK1EAFFzfGbS3uBHFiQ3tMxeP2lcgU9Y69lV86K/f/sSudjh3zO8sWT5q13HeZxso3jJc3racCk7pRfdkt949vP7gUpo5lm4Jj26WFU4XwanDCvWh3vV/PSo7q33P6VPCKfxMOfDloRFusmkYVmFcx41M+Y2kzkPfgTA351jNPY7hGglc09g6VeCihP0J35L3PG6WzaHkWezYdrIeLEwTUzQS7eLoK5e5dseA8psKbMEG/vNX69SzLoLEVTAvyECnjIqd5d+d3j59oy8UP7i7sHn9licW1cXUcZwbYwV8M7p7Y7TTKp6Nie3lrA5/LO5hk6EgJsvhhqYKCstkHlxD8voKORKI5j03Ix9QiDsRTGXZTw+vnuiRz5zmxlG/yS57oyKQ5Hui+s73ES16jjLP3BUNDLtdx3H2294ilpdQopvdjtP4sbw9exwyMdnfDDnYaVczL1lvI7yrR514e5CKTJf070Rv8iUtr4omiE7O+KBTazgtO+uBrekGmj6EyoUwvWJM9+BGJrmJ0CjQX38d1PR31peeMieWROUMFHFtGOwJ8TisOu1QyR5obAy5mRgBkCkb+kNnlrykpHpTGWuZHz5CFbTl2yrIagg+sTgvYp+DusRLDwm5hLnrmmFseHZJ3KDUUvThqU0mXYzvGlPjjHik3SOdB9ESe7RrbVOXc2wzqSvlbQTLPp2mSlrqnaeu6Ecb9qHd7GEW97HY4HqPQlAwbDsW7XGJ7QuBvfvlvgTVVn2F3w0R9/1BRGVe+Ox3ngjf2/hnAUOXVPGZf5sjn2qpnGEb2GPVZmKgYrXpPeRu8Gh4CijykiEqWY+0+aRZo1nn1ExZy/yVFpSGeEGKQDblYk9euHVE30F5SePdgJjDT5s6SmpWoCV1KNRtH6dbQeezcjUY167av3arbiqk2u1pitvTbub3NTXO2b7aH60lRT5rYPWJR8aAGQmh2kJBPMuA7h72I5AOQx3hhzkk/hEtsGAH9CsgDCyQ14DxNiNcvBttJ+raiwqDq2oynl5xddyvqvr1IihDMRzbiFjCqQ/rOJJoYyh4GV6pKBOw4A453vJX0OKPMCq6m0XYaA/aGQS/CdcT9JgYr6m1GVod+zl8jR6bQxmOMFy1hs+1Y74yU9Nmvyqz9ba+1X3+rhl7andmcpnZveCou5HlYRxQET2OJZzU/T7GFMyizBkNYJGViWHLmFH6PYkwH47hKsQPkDWnh5OxineIRaWPerH0Ur0sHb2ftxvwxXVxfkTnwpRDSVgORXq6szhfbza/q2mJnLwkpNSk7bbJinNwqW+vslJqvD/H82HEen8xwingbJOmD9f50OWYWgfFW5/VovExhR0k6xRk1z/A2+Ob8TtSdjKGneNhsdd5IuqQi8zl+Mo01whfDAPu+Hg9BLMln0A7UWkMdgy6xO6UT7RQi68nYqxq48tG8NY+wy+VkfAHzFZo5ntUct2bJCMPq02grn2eq3aR70Qa7kmlTOpwHaDYWMZnWXMMRtxINRvrGXIMn+LdJz8xLfaUfDm2LzSFSAi9caCppPUeaBDZBFAJgasNGyQC5vW+mIZhByxyEeQDTRi5HJNp5LJV6pEDxhmBreBpE6aHuG8RfmEtI7YjaNJavnHtrjDPOnYPPhln0yknur6sZOHFbzk7httBoTKvlBr9y5vXzs8DPdSItd8Y59nXtQCcWk2H8zsQmLRk5rqy9m6qFFU5gMdzBwHn/DaARrool3t6OsLyluPEwbxsxUeIybTOe6nwx2lH8o88EqQRqL63GSrZWWo0hGJ5VFhI9W3Wco0SnjloYiCYsH7z7rgSNRTRkA9S0HChZ3JFqRgo88iKXFeZQGG70ESlk7FxGAVWIsrAUdT2p3GHPRUUPW/ybMArmusI1KPbKj1IF40H9HMuN88t4Pu/O78J/FvA/J/A/L+06dPo6Jrqb+Pk1DR88TWxcWMtf1oYI6psoi5zp99/AxWu67os2X9xryZk0DeFyN705jJPOvVGIJaKjFeN/GLE13xWDK2FL6ApmInh+h1ranUk3Jyz8+lTw3ybJOOLQxXPnF7Uobb1PEUb/VIKp3j7FKV7PMHgbY4eQRYrsqg1qyWquXU7eFDlminEHJR6aYnGZP0wToVp4ohndPGcvhIHata/37zGdFUuM5Oec/Ow2ijwlTioWZ6fZswgyYDdvkaYBV1nzgWHcrcj93lkd9eNx87v/x3cdaZ4IRueNaLgJPNLpU8EJdOfWQwupyc35W1jupLYv012PB4VTs25Jec8msQCTsCau9xNQuhRpPE/II9duUG7wS+FOc77Nuxw062AtZKUEX++RkvwRpTLFNF/0E9OdPt7/GBWl+x+YKMoMZIYvVHmYn5We8Hd3Qk3qtQYhNt5q4LhNaiswT0oN8BJw5q234P9E395SpS6X3FqmonMfG163xE9OZHI4v9/icpyNEkC7ljvSt4z2FXWg+RxFwhgs49XvX0nf3IJrb3WEq+a8IVpekUM2c094puGVy6Q1m8xTUQA0JXKvKFeCSMJQaRpvbVqOgmajLOVaOBqxdAD2WkFUMEao7a1oIIP+xTwu5sH/+iORBACGlKGtMg2A1rRGMSAlDYAOlxIBaFBbS6XFrD2GCYZvZsvnH/PvqY7NRtD3f6Y4+bsOA76+93Jc+zW3DgzW2/VuF1k0KR/lYPzRL9BLA24WMvphEJYeafUw2PuMpdvGCE5uuMOgz0eYgXL/A3bvaCqFpSPOWvBIFrXZd/BYZo7jgT2Uo5H/VHNjyOMgX89wFLivB4NHx0BCq3gEXEa3gx0Xf76Kldph5p5DU/ewrtSNP5/9wF7XNOEHyJrhJQr1hvAGNWqL5LMHVExqbFrPKxxRtfQZs6NbfZVcTJjTicWdsdRqNnPdpYdj2JL1atOoF2ddAJOScW2Z/8D3vCJ5NXck5hedw+rISq15YhIFkvH2uQRy/Fr4bwZ80ylR9f7PmH8GOVfkHhpakQPheWd+t9/f76F0AOFxIYsBVklA4dkEaC6OB25bOCcKML5VrhIvUlpcjltjcKKCgzyDdnBENgOLLTjozBJHISoEucecA/FPzbduVM2vruBLN5rVj07WYRAlS7yQTPuqAYwU0FwDiOFLVzE6xO+Tx8at7INncUesuGR5Qnta/yryLdKtaJjBE7HJhaTL7kB/r2Vf2G3QHwzuuSqmm0KyLzYMPz1zee4vLPnF/56bq0IETQoqQN8kGLesvEZNl9iD46nOaSxHY7gAZCokD4a1ypNt5T6TBWovaYtjNu4yBR0iFXMM1vJOOxB/TttBYzBoOP03x+N+RNFQRHBe5yFW57bC4WbkClg4ACUxdypJ400829dKy8Mry6QVZHcMMANtMOdS21N3dmphN9wUXEGjncrCHT/pzDqq3LT33Tdt0GC8F2ZZZE5PrRnkPTGwWgZaKOCwIpLmbLn322Kal4fMo8sVgLz/kelRK6F/uvervX/e+5e9/0H//z8XsY7f55Tz5wmqIRVPVCqm5opwZsWflJk+Q60mr7vBazDJRDQAia0a59f/CnCp2QjeRTZCroU0/bRMj2B32n3/wXRQe1Z69DgLb0Tvu8mItCcy2xrPbZoF5OAJ3N4wmWR9EZWok5NOIW38ZDAit7/rF5knX7CextFGX4ZhptFcOBr1pyy3IiWRJ790d3WDeapuEJysVDpkdZoBPegw2peRiRIQHAaMmbNMZzk5fwe1QzbCxTtf28KwTrIc01+d1X4UjZonXq7Ds1nc5c6FIyZXOkvk1amYoNVyGdCtkL3oQnmWj9SqBtXwCKTQUuGkBxIT/6LKpWJYLmf31cBBV6m9Jw7CC6vAR3OzZo02SecfViE+voeFOnwl01aqQ1X07jQ9PL1eAYZrZ+T1DzB8Oo1vd/dhDp28uc15wOXGuVue/axCBSxFYqxIbgwvR91JyCs0zi/V8UKq4n1U9VBrLiAO7yN++rosaNV7/Ep8mSi8mYNRyrryR1pxV93LSGlEaFHmZFReJbdMNNbGd7llFThf60Lk8rCctC2PF8MGM3h+d2Z5V9HaHT4Cf4tQVAkUdCy/7qHk2oXyCr2GgDpbrl7ebOcQCgJMK8BYEzDWDBisyHmASgc4zJcGImXwjqU8CG87NdtOLW1XC8Dgf742U9ZmWkEHrR66kuVvGye9LaqUlOwLQ6FD2Bw2rDDu5IJt1rlB2s5kOzeh1MhZT1yBkuhZfF0+XOUac78RRNBRn51idnKwxlcWy0qwkhKsRohgingDdXbl23wZvSKxyJXY65UwTkEO0cjXn06dRSYlabQfhXcweGuAtppgYW45n+pW2N+Yw0ocvcXgBsiTXZB3QUoN+jFcEGHfhLgNbGwUrMGXx3BTSy/blTNXmyuXrzU7nU6r1eFVYajmFByyLO5FJL6Gvd4clozLTKiYNyiN+jHeOawXRa2BrDxA6Rv3lhQn6Hclyp0F68l4C2aQkNltHBWAKrVrhJyMgXZTMTuMyx2MUECiyckVySgtF5tGMiwE43UTrJmDjhlE+2E9mTp1G6588iBDTQFiBSZjuhNnMX7TKMlikpR/L4Qx50YOmUKqhcospbf4ia9ZcStXu2GUIwXvWj1kyPqfRnfiZJIx9cP5ISJQjzwBtKaUVD+iNquTEXTKsqhnd2ot96zk5wq5HdjhMcOeDCkAlpIKBpMx0VUeecmRbZQmvUkX2BgM/oQONqjxcE4EbVLiK3ZaRujMRKBoRFwXPNK6GknGZ9rgbsD3bkEjOuUopcE5Z3nF8nPODzbSJwA2oEMtSwf2OtZFIGWX8OrIAn0PQpbSLMy1RHPbSAcyOCdd9kE2oJnYnoztV7ARI4oex8UgRSyFbGFBxL+OIqYU68KXwxB9vtRWqDzmeB3dSnByFNJKHDM7+zuwshKZmFMjcq0UiGpWrGJHzY535glAw4HWpnZRsQIEe8yyBbmZI7a7moygf+Q3I368eip4Rf6qXj6mfj1C743urvjlE7rMbrmUlRJr7w4+SaczZudSJQ374ChepN4cI7kUVzejkNVWIa89S96K6h+mkl4dom+S7uqT0l0LVdmkfqa/Xg1OsL9sqFZtpgdSTh9AUV0Hicq/4jCRqQpC+ZHKilgZmUZKsKral6rYpYCddbq7tSt2ltj2/F+hzj7aqZr2x6eD5PdMhYT7Jp2vQaCDu9bLxHqV+a3pu74IrZlcmRrM9FiWUpBlSJbZ6oJX2L03F2dJP8ScCWQe/Bp9TmVescJYTWX/uMYRhDQyLuJwn1MOnA+EofRrNdcMynCytzTWFhXWss0Rh3eSXzlXQapta7x3KaOuKG2ZffCa23DivXsRBzUIitJWfa5pbseK0lZrxDW3OHFJsUx566Iixqk1R4Pc2BrtYBgGMLMgifWt9bMZe2uCRtbPUqg0zmSa3HACQh3wlzTpTnCmixgcUG5aGhfZRtGNKot1XMvOWznXvVrB09y7W4Wm7IH2wrkJeqvSXdDMiAX2k5EW5b3JBDPFULkU6KQ5hdKph1M21Vm3q37t1Pp1U/2fyk9JtENGX+3E5iRrmAwj/FL7uTsWNI6jvs48cL4V4QMauFoc0YFlYsgCei3VviH0aOh6gc/F3Kj57cITnf0U09MuCkPD3fldTIW6lOfeuXti9/jdl+AJ96a4exL+1pfl7svwSOz6qbuv2EKqszym387JtZWdbqu7IH+0KoXoqdkE6LQimrKch3XKBfJuFdXQ5LlEjkscOvR7I9mOUtmy6Z+8cKkQbpLMQYJR76gnvokiLDQbVZn3hoDXFaAMFw7helkhF4QmitNV8iqfyWnUbCK6OJRT4p0wZp2uUDFB4Isr7sNHZOlVJSrr8HcTZZuXbIKc6c/Bhjv/fLw6NlnadXt+uHw1eDOn7Vmfo/XL1a9XR/XUa2XNir4iLqvzME/9pJ7SnDQY03Q7xNYUU6ratTepYrTbru0wmBQNWATo6oxWLI9ZRRtp7VBHctnOmPGFSnZY3k65Ua1k8xWLTT/phv0bGIXPHrR0YxgbrsOiVy9eX6oEbs0JbloTHCIGTm6eBTit+bPr87FurF1LKF6WfVubT4qF0RPE/M+1VvkcEPlvcCy9EXwvOPFy52S1Xmu811ppL5OKsU+ZjYpV03YQgqnlfHXrbH7qS9y3jO8WN+4NaQm0w61e5bfCYGszDKaYPasN1kNDKP+2ufw7q/Wdir5rSt+1pdIdonQOq++k4yYM/z2cwzEEBn9NW6gSn+/Mn2hVSGvvIvYaiS3u/dIharbs+poDxHZI1S15MDJrAftTRNhy1kOvP09NfFpdziE19d4UV0t9WzVc9c2P3i0m8dKDamQUjRolbHxBbIsTVmdu3qdN6tGyByRJ5FgqdXDOr7sVxv+i7xUcvDP9vvEqq8QWu4EW/YptzZolfHDY69EqWFk25WXG/l+JEY4R0xh2ce3BktuSlZJfKOwp/gE7+tIJ+rO6+aqUtUkPyGuUcjQHHaA+e2iyPprbSZXrSHFcEWyIph2py9RMXYBqszM7nJeZ+hkZNojkY3aAseMsyw7//9RDmg2HasvBAbK0ygRqRP4YCD9zYCa5/8ZggJfVDudZ2sEaezDlD6x+zLMRf7v0pIWDLFA4iHbiDGIIh0me5abWgpG+lleyLJBnZ2CKNhMbVdYmUiTBLWc8aJl7N8cexuHYte/o4NGSgrIdW6mNRFbBkiorYMYbeUdri2mxREuoAygOJrRQsHzULKckjfnOnyn/NMq0k5hfbjBo2KbLJ7UabpC2Sp8zToyhlVga1pwvDekVC5pPET9GD50DXgqzcZRS8l7HkOLxQNwxHdZnSYwwUHWYyJCK2Q1YZgzPpAqzIlciYOgprQCvhmdMzK9j86RVAtTTwDJwlRSAaj+kZvib1kzRBpal6bqeRWlHSVqMMG5T1GIttWCV6XKMZeBYXlKZbyVS89TMlvbOp8FH+DW19TbOg4Pnf/FEevb4BtHGyJ/HH9+cv4Xo+d3Gd9WHRp+5YEG08iYVEd1WJ+tsJZoLUpOcwzqhpV/jCdgaDW9Wcjslz09LhU030bvSqcHwR/KdY84tov4klr3JAniCyE7muzZ5kaJBH21+KXmEoZ9exm4HEyjmEMVJEdJ/D2sehL1wHCL3mbBikqNRmFLlBjQxAsDNzSglp85wMk4GZK8wgaJfWTdJ0wkaCbEU5XacRcFkmEbMPE1BmfmUg7ejaJQFWTQAnIu7GTId6Cxrs1MqX9VLw22cerL+t2TmZK57zGuPkpRFaQYsXUQhf2Ql7dQ8RapUIYkqDzjjRURciSI3o7pVUdXB2LJwVaVcJy9P3eWUDs+6iwg6mbgZTZVVi9WKZVHY7FGOr2LmrboOKGruRSyHXCSmchSVUTCd7a0Sgft2YhyIDCqnn4fh/OJIfA54f1UWgsVqdHDisFQfHH50tQ7uvNRZ+MEc/PfED4IeJWIMhS7TOO3GDnAmy3rdXew1WhXTePejzbA7tS+/xqO5B7KfIc8WsDHzPWC/K4SHNaqFvrvJs8aUulkJkBoz5DeSdIy+76tMIsIFgIU6cfLE0pEDkRlJYg6Wz44pJHJ7MPn2YL2qvQd7v8Nkv2YxqgeMjDZa7vlXoVyMYAtvZIaOV8Nt3oud11X1ZVNfw3Ywb/EFKdAwA3wZj2Mv6ZvPCCRcPgdjOi2bm4gUeGf1ArG5J8CeCs3JYfKn9luEnVeulMFn/nCragRdW05s07uabBe2lw9Y3Gc3PVeFP5Fol51RV6bdhiPTrkIbYlFHL4tC9BLs9sMsC8734nGCPtoDEKHwf0d0AiCoCbpOsfLdTCcS3AZ5PVacUQsNUT48m+wEt1mtLE/LyxiaGnevj5aT7WFwu7dTo+20etv1GnDXa8Ad14A7rgF3hEEVVRY4jYaUGbvY9loMEGFUngeNfioHfDRZ7wOpy3GgKXaXNtd1IbCtxyyyOgrgP9zbSD3SwTfv/QLTyz1lBDhPObr/ESfBOog34x6l+j15wtDz/TCKN7cQ+is/MN5cgrtlMBmsYggZU3zjn82Xvj/fDl6ZNw8e5aRf4dFb/LLXnsGBxMOy2k2jyPg+bHs2SXs8DznvrTzpwMjItFxLkj7zXzcG30q2Lw6vhdnb62FqD1e6kAyF/h7/hLst2kwwUQwc9R9cMD7mWjK6lGTjHJL+NlzHuzdN+sE4XBdpT5Snd4NlrI94iv7HPgAgtvO1PvmDeVO3B90pbyqSJPg7B0oq18bef+apCM3bVXTdjBJbz38yMxi5+lNdPBsEw0usUMEHFqHDW7N8TvwjWkuWd2yW1ldiAq3igvejN8IpSH0r4TDq0yJRQQT8dcJUJ9DbDt8MBvnsZDymwN1fUrpP6SlN5Qq++fB/ABI0s3bUOnX66mTYbML/2XnsLE9YfASJSM25hVar1Z5vzx94xE8rjkgDLtQa8NdKYsu8JoPvIzGXkvZ9C4cw3Kflw/GPqzPap/sfUR7Wx7LUBAz6cyVT5/4957gseRSNzD7zhHVgZO+T/mQwBFFi2GTPUCPD5oO+QIKkNRFEAQqba7AOdEqICJTTCJ8CGcYD9T+BYX5Eq/a1KEjryjuqfc1ZgKmJHq3ypVPnAd/8UoVv1rqcqLE7+F1fE7F5Kvbn2d5nJB98CejxoXNreHIqpUrqaog5cvlGnaw5B55ylc3ga6yxK6ex/6GBIXzM8+9M4hEVbCCcPGnf1HgI7OdYtjX39VNZ3Nf29QFuLa8uvP+xNomLOtwq+2pMBVbp5Qpba/Yyd1fyPeIS4PwQu9JO5RfahRhtLpfCdDMenqLKP/9/e0fT47QRvfdXuDk5qjHZL6BNfWBZEBxWrGBF4YScrHeJyCap7dCkq5WKkNqqX5TCoaraihPqsRRWlRDwEyr4C/tL+j5mnLFnxk42UPXABdaxZ97MvHkf8+Z9ECZ33JW6R+7/CQV0o+odYCkOZH6U1O4l5Vf+m8JGvsrS2eW2fFE2GmafjRPmfeII3OoFa0wqV7ZuzksCFHGODDDd1TADMw0AZFZ+CDSqomQ71+1/pgo29H/hv4SqUnhv0CxW+zC1XUW5WFgEBQ0bckFHoY6pz6iNoDrsSaTJ4k0ChQuNehEF2cBM6yp2/2+YJRslgCxY/pgMBc9f3yF7bsn6YmkfiuXBUFyPla66VvBuijFwVwTu8ItH00AkWB7FAOsQjYjMhlGppoCqM9Gl8q8MiGSKYloVuSmdZboKl08fzoCw7X7MV8VBo9n5eLlJ18EwIF8wAy74M7mUz350UcvfHA8ifyOK28QjVorrcp2cz+Bo5R5baQDjaZBKhCdHw895HNIIlNUkh5qwFXX3kJ6C2j8PrnoOkObzmnd6mPZxMAEiZ5/VLr0DGItBQZoCzjULnEUbnLG3pMERcqG/vZ1Emjig8us5YYThdsDoRB2i26DKgKh49cS6Uc9i4NRF6tyVl+gwYZ+sp97klzH/opNMcRY8UFbx6G1ePIjXFukXjgJVERPM8wXwbpzb1ZpnnsTpbmcHmoxqOLysr3FZX9cq+hrXqqcajljFM0wTXi2acByCumNrwppQngxao4B2+2IDtjr9Q2TQGht/Ts1fp6avZ9vMr+6RjvEn4kCjmiXjbm4h1RhfWTu/ZiAVS+dIKkszz+IRKva8k7RZLBsBpSPW1Wbo3DQLS+c4CwsptNpB6QmPtc7HrPrZNjPWfyUnqM047CV4+8wCMKPrlkbprXHxl1T7JrVxAzn23aDi9HbU0bMwfVvD1zDUarPWayBXeGWk8NYuoNvSZNdA4WQvJPpcIHm23Jhqs/0BS/dEKrUHr55ZRdoJ484jqAbFUiBwNwoTOC1NsPgzl5kg8w6Jma8Rvoq4Dexxndu5Chve6iTppJ+HsHtvk/J2oJ6y1Y7WOngR0BqmEXXpViJJDBaW3ThXHACQmWWmvYnEOfzyR2dBLGO1sDyGKoFl/w8mnXKHbK2o7rSkz95YGej9GQba8MjoYh6o2um9mTpdqKaeHsrHkyacDJCrGt/0UECa2yCzPGmeB+UeS4K8boR5B1iwMMvBnOcvYec95VtGsmTDWVmae0SBFtvsz0zSm7nVU+cBwfRPGTmBeL2sd6MfBqJ+1ZmOrJrJ9Ac6PgfMd4BbhkP4J3E4wLFitoqAOLN2rqaRlZzofsJED3BSxowS38lED4gg4C6YWp5FBtmEbRrslU4yDLtrnXCn10/Qd8c1HLOqxqEaoKW9TGS7t5v7YEVTOAQdAdwD0wyRqeJ9y7dWgKvDZM55Ev9FOConR6B3Sg2qZ0eA5C0AfwlNAEcB/DvZqQ4yaszACnGAJi07jtGnbw7olyIR8+Gsilgy26ldfJfFiIkgqnlAQl+zAMQgt+nAZToBppNRxT5azUbyZi2Y3KutoOLvOUKDMO9B4YohlLZnVLUMUYVJXw7YHUOQxUcFIwydOQ+w0O2xbnQLRvX6e/FCXhtSKhik82eo/GWcF5SYHyi76V3f4Y12HPFNBSi4yAQ0ASaBX8G+4YK6Ahq6B7IPyRq6DG7E/YGfDo7T/3Hq1zTffXkDVGDXtLyabsZ34FMaKofdtINlzgUK0GPqYq87Fo+X2wCsuxrGSTD5078SxZQwz3NWw/ZNEBD9OODkV/R3InJpSZyp17OAuZe0oH/5Dl1aPJbMS9hAX3/DNYmpuFyGNyrsoS0tWdUOWEQ+J1+bp0CaiCKsUedr9lKxMr7BFeQyvamZv8+bbYs3zompKUsxfqUaLlXppiFDiKmc2fiUZsFSOi2ox/ymuB9y3yiNC1ss9xneQdr8sPspp0TAsmoxZmTkRNailDG5t7M7HTrI2/J+bjtu9hG6LefdBsweoLonXb6VfxkeTT7Uhc8mVZcrvjTGo+Xd41pw2Ms6nEx7pqW72MNr/TNdauoqf1NGrdPxTuJEZQsZ+fh9BKSboEoUOMqjj35BojsMeIBvw1476hJ9N53zyPXrTSVxgza5/Ohs3vns3CHdAJmapirxzUXYb/VvwoA/HYIit1WFdBKG3MR116P0Rn+Ln+L6VoQOjWmEgVPZKBh80xgPZcpyt2/kAcLXRClBXu0QiWLz3LDXzvKJcPrV8uLiBYDcxNWCo8jpNZ+FTm9cO/zlIeXcPhd3QEB1xy6Wmp0iLb3xTnXemIosWFTqhRoEA0HmJ1SMwlJ3kYinI+eaBDMWw+nwLpqQbYVWLW7T1IGs5ihKksIKE0dwq0Mc3iZOtOvQN42SAoALvbQ/iUvEK355/fwOU+WY0m/P3zSqihDeYWd67GjGujeNnCKAzIhLFkxhx32HpbJggtJxlSgT/wNNsqBBaDolHsvo7z2HyujcovKZcNDVDix5cJud9k3ng8CRak7FnBhGKqAWHXOPoPrKJU5zK4thtOqiiafJ2pgjyGfLrFAkMFkqfAM2FbyXG8WWonlKwiohLqrREEBz8mu/zsnfAXIZxdkqxCvR/zoI+BejlD6v6NueF2UWii7JiTI3ZRsC9TUqg5G69akU6fxFzbz8Wka+Sc9L7lcIA0OFr6jd2QUiBSQk0ZaZKNb4G38zHm/gZ3zu8NDtoyXctRP/XLcfpuUBLDLpFUKq1x1VYsCAKdHQeqcn7sJ8YTLzxItwlL1gL3Uv66lS2tQOf73vKFdmeLMgHDLo2oyrpfLKYZg/XroUK7r+RxJCBoHLFuZk3HuWqiDtYQyE3OSwVyweBzjoRXH2wfuBSM0H3+lvzcl5hlk259LdrPk7SU9ty6C17weByW1qr2BOQq969nsLlk6seIrvVLDoScep4KRnMjgtNOoFqh0cwTdqpYGXqUduaVrjQTHWSF1YcaMmrgVldjbKg0pWlPMhbBQQWjdwB8r7fpo3P/AFNTUwmebkYp7yzJ6dBcdO7Ge/6bT8M10Q2R8EN7JMEq1m1eDJED/XBCimJVhaapQPe3neYedDiNAXQPLJ3U7Py5jmbjiaPGRZSETHOKBcP3uCcQXYh+BuAXZBHDBgpip47QYegBLY0hd67Zi8o4OGv7JuwuB+MwtQ23/vX9o8LtAXqQIA")))

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

            clsid = "{6F661F76-44D3-4CC8-8B2B-E64E8F8BF335}"
            progid = "EnergoLogic.VisioEditorAddinV335"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV335, Version=0.3.35.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.34 -> v3.35",
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
            progid = "EnergoLogic.VisioEditorAddinV335"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV335")
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
                "progid": "EnergoLogic.VisioEditorAddinV335",
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
            progid = "EnergoLogic.VisioEditorAddinV335"
            clsid = "{6F661F76-44D3-4CC8-8B2B-E64E8F8BF335}"
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

