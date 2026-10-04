from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.114"
CONSOLE_SOURCE_B64 = "__CONSOLE_SOURCE_B64__"
TOPOLOGY_HELPER_SOURCE_B64 = "H4sIAAAAAAAC/71YW2/bNhR+969g/dBKSKA1bTcMdZIidZzMQFoHdrIGSPPASKc2N5pUSSqXpfnvO6QoX2RJTuZiejAs8vDc+H2Hh8o0E2MyutcGpp1WtvAWdSXnEBsmhY6OQYBicUnimMtrytk/1AqV5vqD0sAwE4ZNIeoLA0qmI1A3LAZdkjqDO9NptQSdgk5pDKSHhsfyRI5ZfCZTyeX4fgjaSAWthxbBh1l9gnKigXJISMyp1qSXjMFN50L2SbNrzmIrT0YyUzH0k055UhtlnemJJJUo2KlafEbVGEzFYjs5lLf5+GOr5J3BLMXeu1Mlx4pOyw4qdkMNFKLel0OIZQKBf7uhPINwtmS+2D4KTKYEeo8rUDg6Pzv6HbfOjNzaoCvFDSgTHSk5/Ug1/PbOT+RKw3lA3vkKp2yMnygT3p/LK4LZ0HUOeacV6IybU2omZM/JRycgxvi2T3bIBzdyuXNF3pN2u7O03qj7pfdl7S6/30iwqPHFHnkTrkg5XRMlb4mAW9IXGDBLBikoh9zeXQyp/RO0zzUdw/tF0EUl1P0BHNdFcAdkN+VU7JPdPLz9NiZwxbLPgJVciP/y9VWnTjSRcTYFYT4jBVC8nJJFpehrg9QJ02bX8mCfAP5qFLPRz4eDKoe/YYw0npACcIre4qaTI8YhGgJNDjg/YQJ0UIS0vYy3cDX7D5X7YXcux1/U158zzgfqy4QZGFnaB2g2DEkssWaIDDqVGmYQTKkyNjxcFI1Szkzw6qt5FXZq7boFBWT2EDLk5ctcC+6MHWgfDrrtahzZp7RHnqK5gp2rGsPANTzR+unBca/B/MLGb2j61xXTvcNa0w+1Djl8RQdJEliEWXA1CNunKMAYAZ4Hb99Ep1TpeRjbpIuMyhT0xTcZWb4qRoXxg+F2o+6ieKPuXN+bq+YFRUGvdObtZs7geVCp9t06tbVaH2v2+LG1OtJ6HukWYR2SHz9IvWgBwXCDYltUVlcdCdNkyrReLIG/WCuEJfiXmft2ReA2nhx8XZnZLd8jr3+aRxOqiZA5uCuLe3KPfQoeijRNcZM/4fZOKLcH7gG2TTcwuP4L+6eg/SfTTEYHKVam2FmsiqTQVcRuqzUmvVNVoElg4c1EAncottPxf3f33ESI7kSHXo1PjBfZ2npqdS7cialIWGIbgD2yrLeP7VrgtDYUWg+g3veMcj1rQM6kbzxm2iOLpXVEWyq72x6cXTlFRjEtRTRQeApR3h8LPMO62OCEz61jC8mfudaplb7Gk/Lvp5OxKj9zg/l2b4BdHBPEQW0ehpAG8ZKJBFsrsrWUvyY8O9r9d/wVZrDgzZj5UwBYUrwWgb6FEflRuRn6yIcPlV1Wyc75ekPnG1ha5ZRwrhfl+EmswMpei+lV5efP1P5cznmw/T98y41tzLWcZk5ZiWKzc7GptXYNkj1WbGftjpfnskK7/sl1OGOIRhOaej7Yu13/0J2JUdFk1bCj0GVc+7NGV9EjNTMtd6sLnPv21K2dN2TYX17DmIk23vraH+2/i7a99qHERTO3cicXNLeRZaL4PHFhU+9sYb81510jzWrMuQgia0ifB8vxhNEx3pPPZJA7UwgtuxZWKK5oxNx96ovCfgovVPajRzC/JG/bC8Bo9NUUUfka+sTAyheyVX/8d4LXyzPLjMFOxUG1AD3BKrvmLl6+rTff/V40XP5mqQjr++A1GewNh4OhT+HdPHNPyM5q5chz8VAx4zO5U5fJR/8t6LH1LxBBs+tpEwAA"


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

            build_dir = workspace / "energologic_visio_editor_addin_v316"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV316.dll"
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

            clsid = "{89DDBB87-8513-5078-9BF3-1DA6D75B2454}"
            progid = "EnergoLogic.VisioEditorAddinV316"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV316, Version=0.3.16.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.15 -> v3.16",
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
            progid = "EnergoLogic.VisioEditorAddinV316"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV316")
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
                "progid": "EnergoLogic.VisioEditorAddinV316",
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
            progid = "EnergoLogic.VisioEditorAddinV316"
            clsid = "{89DDBB87-8513-5078-9BF3-1DA6D75B2454}"
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

