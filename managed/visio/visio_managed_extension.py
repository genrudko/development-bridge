from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.148"
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

            current_progid = "EnergoLogic.VisioEditorAddinV348"
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
            current_build_dir_name = "energologic_visio_editor_addin_v348"
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

            build_dir = workspace / "energologic_visio_editor_addin_v348"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV348.dll"
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

            clsid = "{64C8B1A5-7993-4CB0-A5FC-95E6D3F5F348}"
            progid = current_progid
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV348, Version=0.3.48.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "all legacy editor registrations -> v3.48",
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
            progid = "EnergoLogic.VisioEditorAddinV348"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV348")
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
                "start_base_copy_interactive": "ApiStartBaseCopyInteractive",
                "start_base_move_interactive": "ApiStartBaseMoveInteractive",
                "start_base_copy_capture": "ApiStartBaseCopyCapture",
                "start_base_paste_interactive": "ApiStartBasePasteInteractive",
                "clear_base_clipboard": "ApiClearBaseClipboard",
                "base_clipboard_status": "ApiBaseClipboardStatus",
                "cancel_interactive_mode": "ApiCancelInteractiveMode",
                "interaction_status": "ApiInteractionStatus",
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
                "progid": "EnergoLogic.VisioEditorAddinV348",
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

