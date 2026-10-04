from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.118"
CONSOLE_SOURCE_B64 = "__CONSOLE_SOURCE_B64__"
TOPOLOGY_HELPER_SOURCE_B64 = "H4sIAAAAAAAC/71YXW/bNhR9969g9dBKqKEmaTcMVZIidZzMQFoHdrIGSPPASIzNTSY1kkqcuf7vu6Qo25Il2ZmL6cGwqMv7xXMvD5lKykZo+CwVmQStdOXN7/A4JqGinEn/nDAiaFiSOI/5PY7pP1gLlb71+qWBQcoUnRC/xxQRPBkS8UhDIktSV2SqglaL4QmRCQ4J6oLhEb/gIxpe8YTHfPQ8IFJxQVqzFoKHan0Mx0gSHJMIhTGWEnWjETGfMyH9JOl9TEMtj4Y8FSHpRUH5o1RCO9NlUcJBMKiafIXFiKiKyfrjgD9l4/NWyTsFWQqtd5eCjwSelB0U9BErkotaX05JyCPi2rdHHKfEW0xZTtaPICoVDLyHGSDsX1+d/QZLp4Zmrtvh7JEI5Z8JPvmMJfn1g/2QKfWWAVnnK5zSMX7BlFl/bu8QZEPWOWSdFkSmsbrEaoyOjLx/QdgI3o7RPvpkRm7379BH5DhBYb4Sz4X3onaT3wfkrmp8dYQOvDUpo2ss+BNi5An1GARMo35ChEFudxqSRP9xnWuJR+TjKuj8Eup+JzHM88mUoMMkxuwYHWbhHTuQwDXLNgNaciX+2727oE404mE6IUx9hRIA8XJKVpWCrw1SF1SqQ10Hx4jArwQxHf1y2K1y+AFixOEY5YAT+AkWHZ3RmPgDgqOTOL6gjEg3D6ldxJu3nv1Z5Xrolcvw5/fk1zSO++LbmCoy1GXvglnPQyGHnsFSElRqWEAwwULp8GCSP0xiqtw339UbL6i1aybkkDkCyKDXrzMtsDJ6wDntd5xqHOmntEa2RDMF+3c1hkksyZbWL0/Ouw3mVxZ+R9O/rJnuntaantU6ZPDln0SRqxGmwdUgrJ+8AUMEsB+8P/AvsZDLMNqoAxWVCtJjD9zX9SooZsoOeu1G3XnzBt2ZvoO75gl5Q6905v1uzsB+UKn2wya1tVrnNWs8b62PtF5WdKuw9tCPH6heNIegt0OzzTur6Y6ISjShUq62wHfaCqIR/KXq2akIXMeTga/DU73kR2jvp3k0xhIxnoG7srlHz8BTYFPESQKL/AWWd4xjveGeAG16JP37P4E/uc4fVFLunyTQmUJjsSqSXFceu+7WkPSgqkEjV8ObsohMQWw/sH8Pj8wHD9zxT60amxgr8vbttt05dyfELKKRJgBHqKi3B3TNNVobGq0FUPfvFMdyQUCuuCUeC+2+xtKmQiu03bYFZ4dPoKKo5MzvC9iFcNwbMdjDOkBwvJf2sZXkL1wLaqXvYaf8a/tirMrP0mC23DtgF8YYMlBbhsG4ArykLAJqhd4W8teEZ1N2/x1/uRloeIvK/CkALCneiEBLYVi2Ve6GPvTpUyXLKtm53mzoegdL6zXFjOt5O96qKqCz12J6Xfn1C7W/tOYs2P6fesuM7VxrWZkZZaUSW+yLTdTaECS9rWhmbbaXbauifCDaoqXZOpKGcRlONCL+cIwTW0H6NNg7Nbuon9MyL9ioTxnStEFfzqwa9NnaydzrkDi2xNbMX1I5YKb3ZESZA+dF57P+d+PoAyNI3DgbtWfOrmh3oEZZfrlxoxfO2AO2tqzaxiJtMGki8bUxee0W4/L8czhpX3E3cygXKrrnbU3w9AOMwkAqB6cJpCsEFy8txG2Q30zqs95xxsUEq8b0NXNm/Tjdqb04yTKGHjCcQKHILI5ne3M0258HOQ5nB/N3s/dzZ7PmAtDbRZzZ1xy27QUqNrD8Zc534ObmiP1NAMWGM7a+B3OX9yZtfSYcDr+rHKp2W90SreUz+rqX9upor/il6Pc61KbehuuZqn5Vfx3wquE+YJEKr/5otCGD3cGgP7ApnC4zt0V21tcvy8Ws4ovN5H5dJuf2enDe+hcfH4MNfBUAAA=="


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

            build_dir = workspace / "energologic_visio_editor_addin_v320"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV320.dll"
            helper_source_path = build_dir / "EnergoLogicTopologyRestoreHelper.cs"
            helper_exe_path = build_dir / "EnergoLogic.TopologyRestoreHelper.exe"
            helper_source_path.write_bytes(gzip.decompress(base64.b64decode(TOPOLOGY_HELPER_SOURCE_B64)))
            source_path.write_bytes(gzip.decompress(base64.b64decode("H4sIAAAAAAAC/+29f3Mcx3Uo+j8/xXCTcnYvFyMApGQZIMiAACnjRiRxCVAmi2RYg90BMNHuzmpmlsReCFWWmMj2lSPdKH51U644Tl5epW7Vq1ehZNGiJZKquh/gFvAV9EneOad/THdP98zsApTlG7vKInam+3RP9+nT5/cZpdFgx9sYp1nYXzw1Un75K3GvF3ayKB6k/hvhIEyijtFiNQkewk/zaRTsDOI0izqp8WbtuvHgjV68FfSi/xrgKMa7N6PBO8ajG+E2n5H5YjTIon7orw2yMImHG2HyIOqE5vCb4V5meQRgd0a9ILm8N0zCNMXvNVr9KBp044epfyVO+vLd5b0sHKTRVtSLsrF4eDXqJHEab2f+9e1tmAIsYhIunjp1J0jTsL/VGy94K3H/rQj69cJmlozC1j315TL/azPK4H3jMqz6TvxmvBN1POwUe5e7URYnDXuvt8IEp99szPpn/flZfxbbnRoE/TAdBp3QU8ARNAbs1P4pD/4X4doNgp6XhkEv7HqdHgzgvdEbhZtBshNm1Ig1xf8NR1s9mBX08tj7te6i7eWN+GHheZoltIKD7jCGNuz9wamKaVzu7oRrg+3YPZGNeJR0QstErANO9RWls1wJe72r8YNwIwuy0D5NbIIfQX+UzGMzTPoRDGCZTzeGf0Nvdc/5Zlx482aUZufVRbzgrfFPwKfekjcIH1paNVs1P7t8Y5YHnd04caztpVHqflOyDrTjvdi+myvxYMBIRW0ENJcLXlzw8PyudVN1gfC5WBdrn6twGMOkpFf5asqZr+PcKjB+NxiGE5w8jiG3+n3Xq9vuV6vwHcGgE17ty8+gf+8USRo9fmMUdZuNlXPLK3OvrZ6bWb107srMubnXLs1cujR3dmZu9fVzl+fnL33/9bmVhuhCSLkNtGpzPAybAFd74Mtfa+nqKOjxXvk3s5femkLoGI1bHkbGInIUgBeroyF0hxP7ZridqRtraXIj2tl1tMGD74aAb0s6b4R4seFBsr+/EQ6DKMGjuZ6ED6LwYVWz5eGwN3Z8TNyBFXHMYzd+uB4MQsc0Lu8FnQxutjTMmhwpuntX+22BId3x1b6143Iv2hncarrf3ba/uxSk4Uo8HIvRtvbkWFtj+WeWP83GTji4BceFczUM0lESrkdZZ9exuhH+vTXKeCMOb4g/HIuzEsdJF4hcFqZ2mNdGQI/duEWvS5CL3t8clrxcjR8OXBg1GCE1I9Tkj4GmrYYpbBqxbfb1Bo6JroVuCJxZ5sDElWCYwWoC1vbg2Pah6UbQHwIVcSE3Nrv8zigaYtsrSdwva399GCY0Q7yOR46lBRIDAGCzwgFswc5mPIx78Y5jvoK/0sl4OfmbfX11+dy5K3Mzy6++vjpz7vKrZ2devzJ/ZWZ5bm72+6uvfv/K2flZSf7Wk3hnravxfb7CqS13YY5vqR1W8MqQVLGp/ySSuTzK4iKttN043oK3trqpsbXz7Vq0dJhEDwB7vXjrrxDO/WDIyCUx6s5G3e7aYG3ArpRiMzYWctze/W34b7EFLHs/GHQvBYl3fytIyhpcGmVZPPDuZ/HOTi9kv4rt75sdLj8ANEvvr8DHvE1//xDe9sJEAOI/i5CSMOjGg944/9h0POhswP85S8Cea1wE77oVxz3enuMkdNkOeqlljThmstab8dvhANo2GhUNiTvFhhFMvqrxVZCIgh1qrgojh785fHH0/uGLw8/8EghD9gFw4YzwwF4DQaRigrzHOgyJrW86mhNHpXHbF2Rf+kms10jjsNWuxKaJDleQv2QXMCCss6MxxY1RByTMFK7j7WjPMU2x+0lO4K4GIFEmlYMUepSsHRANnImcmaBhPwx7QAHF25qfJTqv94LBepDt1tsv0etGmI56WUk/eTBA5g73vPs7wKqwP9m5oL+bshv+788bzYvnMxKKLtz5y9PNVvvemdbpnEtOmxcX7vq3oFESP9y7cLd7pvXuXZ/9pF/wstVoazBpmOtDpttY2xkAk78CHIL3rv4GL4cI6GSr+kM6cj6IlpWf9JfF+YuJiyn/6bHnbLLxD+Ko610f5EM3OYIu5/S67YV72X3e5GrcDT3l77bA6GVBu9uwENvecpIEY68zSrO435Kj7mvTVy8FWJll2xXB2qn3ArYUv/V2WTL29oHhHAR9+LTdOM20tvTEv86mu+Rlu1G66B14MGJnF/odaLBotF5vU7kdVNKM/7MyxgeuJQYmMEeIJq5o/oQW9UbYB8rF1rTuCsIXa7/1tyRQbntN7Y7zTrNj733ve8adJd60CkBoE1QgPt1/3syS89pja6H+sq8z2zOaJV7p6uxO0xMf5LooHcYp4C+79n3+G5bduX0KWOAD5JcRV+CvhsjelXVnczHpo7IMYslKmvDltrbAOdleKNPWcV5+QAG/DabJQHIaAj7T+aHm0bJMVj+legMnutOxS28Ou0AZmwV01uahd4S7OslGQ8GET9T3UrgTDTZ2R1kXhRd7zwLZFusJ5MdxyoSms+KUaesk9ivbhTuHiP7a4EHQi7pSBLm81wmJQDcbTI97+PzwiXf4NXBQnx9+efjV0UdHPzn6u8PnDYPs4P+SEISkgYOr1o+e5YtptawEzrEAYolgOEan9cFyHjn1tvA/S15TedaCbr7yW+8MJBDwmDMP0FtwNQpr2bAdEn6GcLw7vNu9RQfJUdr6gJhN3r7tXU1jmNF6nEa4hH6ffgLnAm+iFLX3/lsBsCNtj4S4RXUx6510oCNeEzVvEbyeW4R/zi8xIgR3aJbEPbydRwO4nKIzZ1oVWJavIe/soeygQbsT3Vu0YucGLbAPkjLIDc2OvxnstLVF9pl05TOEaLQ91gPPYZBEKazOddJI9FrF+2G/+saAiQL+pAUBbNHadQt4qbeLrw5KrpfiRbfkus7MiTXNSbX0HUKUAUzhv0mE7sufrEcBYcp/MnQqQSYf9SCM4JacBL0LbKnR3NjTss4b2biH5w5PBD2hB3Qi6CefT+n4IKZm0RDtZziPw18DJfvy8PHhF4ePj94/+jmStsdI44C0/dyr+1Fci4L8GqxZ1V0MZLa2xN68PmDrQm9aZZNg3M6Zcm6HcMY1XRcV1uZQwENvJUt6jBskHcAKXtK91XA7AJHKRay1RkVFwaScq9LWMWDOvPET5737rlfg3YqnUPBYsGm5ZqeJbLmxGTgAZwb5+gpOECdnsuXszaWEZNArCZxSe4tl4MRxI8rXwGkTgGuF38LyBSlEZ+Zai0UGxW03cMGpAJObFnIA+KzWHBTLg6V3RWfVLpH31qwVZd0tZoscSv6S1KZthrx1AXIDhxUcAaoFT9hClI0R1pHSZcnPCfRUT5gA0/jmH//eA6poJYKM8ePkEho89hulw9Uyu+SfoDVn7cguUzaEMNDkUOhJs7HXqNHxtqXjuKLjNKadfBDsTfbRzSQYpNtETAiJEAz2x45oxKmawqRWodIpcMSbZA66RUk5obqlqRSJy01OCm4bDaVRqgy6Zp3KYelGqzIAivXKjqMzc/5s25v1Z2vAKVAyFdAEcNAcZgcyi0DmagFhZrMSMDOVcGrY11QSpzQ2rXCliF4wxyloXDTVlaKD02an4IbbrldB3J0GPo3Ou82AZeAL9kAHi9OLgf9r5iablksib6RoalhqeGc0y8oZD6h5htYY5RWzztCrPjOpKC+5kUVlTUqOo8NgqR5Nl02zDLA0buaAuB9ZQ5OFc68V1lXnZFD87UYJ03xOqWIQr4fM8IQaBeLfwnVtkYj/Fe5UwAX3oC2pWR+wE0KIIcw6TQTWso+TktuY8DQCKNjWJ9ea1F/Lwj5CWltt4hi+5pPkAJhpLlwA8I0wU/pdGqPbEs2o7Qmga13+N74DzMgX0eCPYYEZfGpIsAmcPqjR6/IALxPx8koShnx43LCW3tVfW20To/7DIN3dCIXrkvmtgg9hU7jaNybQ9hrr0eBWo+XN8Pf6Msv3drDjUrC3K8DebpgCd272S7mTIGquaMGluxYqPcLk0rgJ33TB22uBkIvdTInC4kvHYeoedZwKqk/5osspmEYGwlZ4XtGOZsBW6s49MTqxIprLmWxh/QJ2fEVvZmXUuvMGNTqjFqBOV+CRwqCzy5VkXcBl5RMr9GH6YaXD6T6pUdeiR1WXidQ8OF2xRkD0VHQikBJF2653iIcHzqH4mjKVkrTiqlBazr60pNRzI9imX2X9DFUlLi/QQVohOuBIQklffnPQjTfwTVPSF++CN+td1FRJC97hL0FA+frw6dGP0cbPdTpHHx/9BISZ3x1+efTIg6dfw9vH8O+LhrcwTf+v4Af2Nj6GtB+duN+PHBqNakMYfu9qvNLvNudm589ZFllgU1dcXl3tomEO3768PexqVlraHAJT7qL1RiI1ezSZYeCzwyewas+PHh1+RVYCkhW/wgdHH3kgNLJ1hT8/O/rw8HMULuH/z+HRxzbjQU73YHRG9ORXIaHJp+/qnNMZgDABkXEceDaNumplsU/Qa5ojj/+Ts3afeQG9cOD1F67TfmD77twSMEuWABMpLEYA9zIgtikUxLEEbGnvRPdarRwLORGCp6ipk8RkEhBEi/CZdW50IifA76eHXxw+YyiLGA7YffTjo48Bk18cfukd/S2hM71n/kUekZmnOeZzikL9ny569BRPzOOjD/AQeOSYxAbA/z9u1NoxznegMPUgXOW+GwJvgKGE5WoOkS0Y3pm9h8yHfpsUWixWjDAuG2GucoQ56wg5KWJajT2AIr4IlUD5zzFgdL9vWxpg+LJeSHu1vA2Y80YY90OguCu7wWCH9KdFWgiIHjAP/0GX/F5yXKcn17cZ7yzCAFp2eqrCOO/N1iSbh79CSypsNFwsSA6f87ko1w2iz2cSgw6fNkpuBBiNTdNNavghUaZr241cmGfSNZpJcBUWUO5D31D/WviQfESR0WQGuGbjWmMiMorbpQnvburYzqdiGYL4WR4O0ZRrwEUS8aLtmcw4vdZiLSywQbKMtsfE/7ohuwSRWiNYWHJ5GGpz5XxJ7bhpBVe48Qvv7CSzDl47aa2go18ToXtCxPMrZBuQQ3gfCCFSPSSOT2hTy+mndkjqEFPrtCxrJvm3oiVP0aBwQzXagoKsuTLqsa3Zjv2VUZIASvNHbeuwTMf+7/IDHntH71k+87G3P3vge4f/CF/2Hl4q3v7cgffNB594+/MHi9jnc2j59PA33v7ZhVl/dvbAg09+tsiXDzhU6IYdEdgLzrc+h/ubnzmE8AIutc+FLt8+2wLDXeCgFZZY0QW0FXEfiPheq8zvahvPTa8OewwnLxcGSFho801r1fAuMZVA0p70R/3PS9b/qEoZL3444Ly4pqvR1RrHVQXBIH9wuh8TR6SfuJdy73dcNP2NxQeHIRUuZ/FMm3GaQtYurmChK/GX3T3LC/z07rj4ovYlZmy9fpIXT1xN8Gu6LYhhJxL5dGJFQT0IZaqCHcGhHktlIGlSBfNXxciuhhmwapKVCmzcjpXt1lV/pUdY0HC7skIw/8jxO9n8wqIV7+mTvFn04Sq0V+gBYnQ4NZXEqSHXz7jM+cQQDMgR89OjDwHHXnhkkCcNzNFPqf2Lgia5WkCa0GkbTmESphnw+F1xoGE/brBHSIKEAYeGo83l6mEkWyeBSy+JG+O8pLr8U/NiFfztC642Q7XBh20n03b4YsHbP3dw8iyawwiD/Fq7sLutas/5psRiL+O7fzlJ4qRKS87ZMWDkhuEgFW7cK+JnKG68NJd5rMFU+/yetKm7ppZeXOfREDJgj+hQHj0ilvor2sqf2/aU3xVMZ/QlIcdTxD8SA+ikv3f4GYhHX+A5R3npPWyJwWtPoD9OQu/yAsPaFCQEZt4Dad36MdoSn4Fmh7/msJ4ini9gR33vfG7mteOe1vRUhYRViydXvbQqGHHOaS+/LE57IoqkeVB9oim5H6PW+z2QSxUSzpfaMOUxyRz3pahSbHuS24Dd/ilu2NGHORDOgDfUyMaSZS76T3y3pR4hKQgTXrgH55+FmaqChDDhqZ7hYSL8wvP4s2oTXxlL6qRgUrgmUaCmisuhuznNL7a19Nqo17ue/Gg3ysINzIjTFMO0WnIdyEwgny9WeKHLXgzhLnhzrZMkmJ+QcoETvc8svIvUegIGEwV7fvTXgO9PiRw+OvoIyCwSQoXnZmu54CRsfLH+MzCqTbjkGu18ZYr2cQq5aVqiBEyuSVxMQhVqrNvSkjdXgHExb3UlStAQX2iyUFunWpQbgh4GcY6Ft4yVBz42Oqv4x+MxnJq9CRC97QTCVtj93hXpoZzoulap4gJaJK8JozwmFlANcfJ/wIn4kniMrwV7oBwg7fi8BLvzhOiiiBS1lfgdocE/icHt+8rPatDJRkJ7NT0BdhwCBlx8Tns6tDwRfTojtL+yMJwUnQeIw0SLzzk+FUgp9PNSMk4jFYq6zpFqGSInFt6m0bRbpzipwGccf+dnX+Ss3L84ziGu+2+RLf9CObtfYTTkAkqLFgZO0b2D+Og3nEMvVA09/Zj2NbFxoe6Wa936jL6igwHprEqDX09CcPvpHl9eyB1PIvI64Ri1GQ/fDB+EvVIWFelFJJn400vTMlWNw1/ApqIV6/BTEuO/OPoAZQjc9GeCaUI3mk/phD9Fe5rHtQnPURuE0bkgHRjoUGAnpCGhykUlLboGiL59e2KQPAZWNqBRfObX4Y5qxzUUXVyxkfXW8F/5GtEKPifRm8Rk/Yg8JqH96H0xz29+/AsPVvQ95r509HNY9NwTDPogCAqB+VLZHgDwgSciZmC3Pm44+MgBCxxWverIL66IR27eH2G0qvg3tvZ8uJV4AFJWlrOW7Ft9Fl/spp8t7+JFTIfi3KyD4027/l7arrkXpON6wsVsdskB1j+Dg8P3EnXw2hEqbIs1xQ3rvVjRkMeA42eV6AH+SUcR7QTjj69JoUMKJKYPoC2rL8WXRRWUhUJavvt4p+1fUKiDGwo36LGFOmmnbsY8Olwm/C00YO3/1/9LLLFYHr67Wq//9ZWToB1fVfGdugZOmu4jox33uiTQMuJeZg92XwwEw/h4U2A2mXAGcyKCx0WH1svQ6H6urC4s3+90zoqvsEsSa3tHPyEu61PYGC1O8hleNrqKn6GwUJdqel3NewUEvEqtRJkijfPftr1hJnROMpgdGB0rFY4972fbVHin0T7lGrNua96Nx9tLN05rc25Hh+a3DEt6ueEdOty2drjt7rA82KEI+Fl/1iJN7wapaIBLehnVOWkOmt41LDgs+tW7nZVp5Df0Kk2Rj+Xj6OnNphjRZ4nK1m7qtzZifxIF+b29aBHQxA2ufBvTFZTe6RYPtWhKm75lndlX/ghnxK3XnCzxEJc8//JJ6Fe49668SsiD9xF58ArHMpbbRuMajh69BIWLoLDKNez0xNwKOm+Hg64jZcpoOIyTLL1G/rH8aBOlbtbWhymTQHGcYZ4GqsgutOFScyjM2HTRbZQ57XoqqEYdXUIIKzrV3OmeWk3ioXXGRFhe8eZf9c+1GdFgP6o/hLkuzs/OzZL9DD6L5RltuPVGBmq7lUCG44UgMlWOFwdWdNCWoyxT2sQpn9TwDnUUkl8aLvdq8k3V6BvQibPz6jzJV6ucmjnopwqEXzD8qnFLLDa1pQJH0VPallfSzu99T70YNACCVreq8LVA3FHJNeoFN70lJ7KIK0OxEsz6f6L8r1GxlmRaTIJuw7Fhwuafe3IoWhYZkWudn8pFqHcE5ym4o3JbXYJKRifXwp4AnWNYw+mbkl/Prucy/RnCPfuO7h8vusQm2sqfQqiFp39DzD1IAMCjMn2NwkFqREldYLKCOejbgYWmOHzgbTgwxXa7dvdqkO36y1tpk7Fw+nGSHplIvlvo4eLPee++a/2kKkC3BaDbHNAxiCOmjhIMvCagaYFCZPUPB8CahCGzTjBOx85/WBRHDjvEG24a1joB68TxVkB18Ufnh9zj3DBjWT1XSbABEsRlGqJFFgGH0MtBp9XeBeeK00tWdffLCHmYAEfw8B/+RvMD+p1b8lzIXf9c9nCXWh9vABBcGVQOwCtbMFfoRKUJCFaNghUZE3DwXbIBSeWcXQbIVQLC+W6We/vNHfjeJcYYLjDfP0Wi1x36Dh+XOfSREyCAOOu0ybgVIpoc3vIues1GbshjAry3oEvr9iHsWs12GTvcdrA1jG34du1CWu75Mg5h6szEXAR7wHKM2FTpaEviKUiqWC+mTHeN0Q/+Kk44G8vH8zeGcKE3/8z/s9ad2XviV5t+LVrZNwJip4nEePubyXg9SNKwKYdre9coOQ/lUkypVM0OSktl3wJ3/IgP5uRz6ehSE+/Ckjf36uRplzkMQ8B2ZSl0KbdUpW9b15y1lawka10XlmiRK32ijenE0SurEamLg2R8nsIGCVhnN+p1YTuY8HppBL9W8kdXg6FNu6y5S4iAVXSaELppQYBbk6WmcKt5xSBlEZ4ciUMusPJQTyL/jS3UzKBLFrxtwD1Qk13PS7h5O0zVBMgLfE/+nM+sLYct8eNgIETG404MDMlg5PD5If34wwEZg5Q9omSrQTRI/yIcEzx/s4A6RScCBcAdrdO9EvO/1tBy1Yqvkvu/tGTB43piCllcGVrLL2zS57eqFkpXdlgUdyAolzqwaN8pe2uxarVA3AAmTfTWg25L+1Z/3Qm46HxiGKGflCgfnxLbgeZoMuk8Ofop8IsfHX0kPcKZQ/lzw6Ny0UOTEJmqvz58DG3RFqcajoT3AFlMRUxDYxKPH4d8KMWTAgZJqoHKEn6aqpD0hFb8l0XL/zNuC7bIXB9Z8pkry88Ycc2g9i1twanap7V8rfGhftBOf0sb4WSwNQcLeM0xHmWg37JAGUobkxej8FjBQw8AoUmU+Okvc4OdFKyeM6cs3EGUQT/nLhlMb9IHNhNvqWESb0e9sDG9x1spO0pFDGsqzzTuxG3j01+tXR6M+rAXW72wxDbTttt8i4+ZouZUhX3C6U6gaw1nDbx95RVvcxdY9FEqVB/9UZp5W6EXjDL4GWXMSLCNntKL3lubq7BNqMN6CK9CrxtiqR5TVQhApSPENtOapt7D3XAASBuKcToU2Jb6BSud3cZUxS0p7Agb4A0HU1JQJ5ep8fP8IW8oDIpLv5W31M6y5dKsBoBX5ul6V6abPxNf9qMo272B0YRuiqAuS7nCQibXcDarH+heMZT24acmuAoFxp85M1kFgIJp6+VF9CrpSwJ77pLietXIW2IwAVICUAmRF8IfKAOo9KhOyAH280U5ZERPdlbhAqM3KtJzPYebhdPkoyVPB70kQF/k6qkFvYEdXM7nGvNxgSsWZ3YKXyorz2Bc1AxtC1OIZwVHHpVRn2gQyS4slhHGDlO9lYpquCwVBFGAUeos8Ufaiqv8jXjPBQEaxcn+u3HGTtOscxf5Tdr5YDYNpp1MWBUdonG1rsNtlfk/jbmoeV0b9M59BU9J9KweCcqAtUj09FN5WRT3jxRS2cPSU45b4zjntUIWrKUQlEIIZQdAWjW7ey3vvDcXzvwASV7+eCwet2o76xqR7OTi8YxJXyiKfXr0ITM9k8MHZg4AAepZwxED8Pt1t2WK32sxVgA2PNAiewriKf3ZitCmcET7v0Eu/QmXR/OI/ZfgYmZa46KXkY5lsqQiprhYTBtiW3WVoLkO8OT9TjjRG7co2nd3wbvl7c8ukKcOSwzS9m57+3PqE987/OTEUoXMo1HRE3s3UR6Pk47VslQb4cg9zEuV1Clg4grtUnJ6ZZg4dGvPnZ0rw1SiW+PFb4HE/h2FKbDQoY8xwOHoA54Ogj1Bv3FAFYojfI/aYeWxz+HdR8xj/4+EdkJCixhVMyH4e6isFfuDSkS5G/CjfrKvcjC/L5JOEhSsRV09jpmVP+nUzpPtCN+OXAHjbiPU8dPkS3N60nnJWfLtznOWr1Bqs0+So12F1B0NJeebX82ydkmzxOJJXYXBk8GZdBZqtvjceyqaMEE8ujiKbPCMGopkpx/XzAavUy5nRviynko6eFQRHA/BXcng6+G4zMl7HDSHr3CjuT5CAdNtr6dAdp4YnK5emo413zgexxppxjWIYzvEORfEOSdEwFslp3hXphMv4Wmn42ttsW/T5s0uxzo6lT8M0rq5LVrT5elwniRHvurp81QrBCsHpZCbmtmpJw1rOJlE1CxeyMEGPDmxPP8ThMQcU6SbHv2nluGOI8cdfDuSHTqAlm/1gve/f3HLEOra8AwEvXlN0MMMjJxVNblThnYsY6M156CU6r7dfBtqzcTfb4oNrYoTnPUpyzdFExRumqZkE1u3XrAV9tSwV5bswd9Mon6zVVoD3eL1S9CAmguoBVdUlmCjMqmD5UjAOrKaTcfLpPoneEr25w5I36Eh/SLqO86qTxxOz1G3zT5QcuV2Xl1jXFqtGtYVdthesIxIxIi+L8LpNf5z4W5yd4B3tpZQjh622Url6eNqpmioLJXpOFPC+zhgV6tROpP5E9uxCTGJuvlvhoOdbBcFgdqFST5BTRPLG8V0w4zYCb81oH4s1YMtL3GjaiIXvNfO1Z3IP1UOxzXXn5Nw8VuWBEHqrj+nhILP6aJ9AsOiogUd7D6j1vBRtsmevhHuhHtw/q6iTzKbe9v788Zf3rk73H/zAP5z7eCe8vfd1L//SrN15u7Mvf3Z9mtnD/60MXWWk0/sK/yUfeDXwJ6Q8uHwGSLup0ePYAU+Q10gcRZ/DYwM6gWZrhB90b5q59cTxiIAmh/9Nbpetb1X2oDgTPX0JbW2BeR8x8odHMcfIs9EoB4ghTIz4O7DVBqMoR7l6bMVicgw03XxdwbGA/8IePCI/vs+tGbec3hWD79kyWFLj2vD/XU8tkz/orbHz0AhmMy4V6bP7VNFXzT9KPva98QHP6JMoc8KyGvx2mdKg8n89vOKaLxE1Nwi//M810Sq2CgqpGEDs0qam8PoBINu1GXlHUzcbhIshx1FdsyrOMhH/tqqncHoK9Fd3H1UgVPq8s1PUWYk85Dda3E2HMkyCj2ph1onFK5ov07uNvCyZ3fsGa9xtyHz+lmcVClUL4+1Uheu1Esqpz8bcMZp9fBf5ZiZdMRKv6iun6M/fcHx7ZO/lkamRyR6uAphTqzeJoQl+ZG7iU6m+z6xLKHH4etLDoEtj1vJBXK5P8RkSNCzMsiCDzgadnm9T+zlHoi3kxXsTGpeRcYxWmvWrWHJpyEG4m5I9mvDsSKozqjKcS0OS6sqAsTTKYuYF6NFbXnoprnBil+9noRpmDwIr4+Ay6fZpjRb3qItz2j9nLKyK6OJrqDt1qT6ZiYP8pBCPohboczPps2h1ZUtwGp5EkfciUV1eeGKDOJ68URM7KhxQCJSQBbzyAmaSLNVkXad746DRTwGWzRVgL3zMyTf+JxnL4LPfkTlHL6qlt0aJ1GG5fdTM8+yIrJynhGwTTe/Hn3NQ36+pkseQDKnCW9NrY139DecC39SVh/PwS3zc/CtxD+LwhkmS8Cfd6s1DSTsen36LzrjoAjMBOCuqXAgYbh58fwWsGMX/DOtGfj7QdzLAFcu3O2eaV5cuOO378FfrYutP23Ya2TQQP7GqNMJ09S7yH+/kcSjYXqngZAb9/y3iCVbUKe/WGMVXARasGBJtMOKrvEHNUNc0iwgvstgXB7uRr0Qw1/x7XkJXWg7ME/QbpDA9aZebLzRHeqFJYvpD5Py4qgs/5QJdQakENsssDXc3mwy5UNDUxwY/pmZsbKawyTcjvbUwTdGW+xdc7bNxrAzqelom/XE6Zzx5izLctEGlTfH1AVmmDxHGz6nM5rX5xk+YC1d3HIPUEmgQrAXpS+/6MnJZRI97823Jksc+tnRh7wMFFJ7mWSmmEQU865Sm2dITD1yXHtcSJXc+O44BIkNoLCxSVNXc58yERTBVMoEqU1IgcxLY6+BFhpSOyNG2tJJ1hGvDHi6sPUJ7Q+lbwX25n2evN+7ZXFBcjS9/e1Ug4i+PflqQ1Xwl+6G8M2uWZ9gUpPmt+6SWs+96+U4riroxTkkezkBhnVY/G7JYteUtIrtnL8Z3xwCeZLpQ5Bttu7Zy7VfXg0DJFTrETI0J2XAFDrtC8Qg5+5IIVXVSl3knBrnzg2TUnSeOIp7KSAtP/opkPXfVOfcPvpQSxX9OWqOj/5GiFUgObmcTrO5cp07Uth65YXnqwDNlQOS68dHzKNfRVeMCKy3nv+uSpNa/L+sSuXxXOPozv2MF1zDWHNHVuFhxLhnIwldNl8sK5zNyWd2BplgmUkeG7XzZJachdUI/9gC5pgdB3XyZUEo7OvOT2BG/J+Il7ltjmLypW3uU6ZXxWqlPMik6Pl3wjzYFAeWHdYNEKtADuqFO+hxKW1ZvXA7UxIKAUO7m9VV+WPf6sLd2Kr0QGjRdDh+NUxqVgmUoyHDVnWyEm99XlpvMxbJFtXxXeh9UEERJ2ZxSQ/ynlYJ4skkTG6F9RqmtEV0RpAZQXhcn7E8GDc76JTYyQkUQWjVtr6jQsKwAsLfpgJMmryZLViEa+E9QIlCmeGQ0awnVsYVJTiqGcm/zb8aDcTc8XnLcYaUcqsghQ1UBxz9dbOsBHzKz97V8oRaKfdeuxrkC5vropzGOhLU4Z/znoJd8KDaKGeaqtm2R/dqBFfDOVDO1aUxVdZlrByhQFtZ8zNe5FA/RpiZdFJmGyTjB5PPABUJ5a64spaaeanpafnlxYbzcJ19a7wNH2CGX0CUlXX+1eM5eE7A+8Il9ZQdmjzzEmOoCgFbIn8PmqCfG35+cDOLwnDsO2qJJEx8Frt1JQmFnECyJM9TjNmxjbPiQBy9lz2ZVpmtSQ9eqL5JLNCLQJFCSD91jTw4MHolP3Z2feumVqo6t3zn62XttrrnqikhkVf/8NznzA5v7Co5UQrvtgve2pRVFYp4Vl2lnjZFFjCdbU0YdlRNl/1Vqn/aycjXHa+GZsvNZZi6fVlZz3658wzDHj19LNM7PVOcnSS7fvSh7zFGlFVXqsNXm/ZQKpJNAu7iCRf9/HujnncpO+MW1EjlsyP0GSej+tGPKiuqHg3oOE96N1X5bRFwSoZfls2GzpxeKkFktVEAXC5PBGlistKzzMBVx6uegVrdE0BX3R72xZugsHlF3Y5VQ1Kxmy7tiT5cNb04bXSY0tFrSnTnlk2W75pfwhQKjcKjiKBwqNxpndQ4vOlol8POQeardWEomd7AaSGAJ0r5dFbG9yyxBRg1PndgMXESxWx7+ZVhV1hsdHbD7qgXikQ0vLqqsGswAG1jP9r6GtZ1px4GEaUwY4HkyHJG4cPrgx6cOHqShO+MoiRciQfbEe5Fid3zO1swbiIhmC0Jj1YqSL3uonBTqe0tBhUm+8mcNRTuzzQtRIxTxikt93pGG6vORYiAIsiD54AMu4K2pzJXsvmGXJ6cUSObI8BIDlYkFhD/XrggcwhrESXlfZyBJlNnQ3YUYoc1kbcet4zIlMelKdAoFNxcv9zxUzzChMbEszCXIZQ5cvhlA8hFIx6fVstfgUXIwmYoM+hoIRtyTdCqw9YCLTvEKAm7V7cY6VHW7bboVhkKQinmlGWQHPDLKSmLSXu5383nsrH8EpHKlBHiF7mJtQp1bSftQu6LWoLA1p5OLH4QJF44ROSVa9aqzT8WR/IIlA2Om4ckaYWRIZb3idOfCpdJkfNDKC423kkypnNYjx8CwFv9Pkhp4ZAo23wblY5nPOX9bfX9WXxfFraKWvE5f3ZS9zzbElFgINs+2+t9Ty6FJ5el7VHSO3gA/7Y9/Db8Af+2vdv8x238gYwN8MzhVXzW9Q5KfAElLlnONVuVORbF2GpN5y5o5v9XcFcZ/HrSDZNLkkmj3fLzz3AxaET2ciiTn/N/PvqYFKzPrI6GyKFqWlaFHaMHZtpir/nNz/4fb464r1ajzmQvQGs1/0zeADXQ5joArioN5ooNMHnNrD/7aqteuYugvxXtjNANbkmPglvE0jHKZDeDt8Pmay3OT7NtmrBaS6G0hN39b3/2YOYC402AT30lPxypvz9/8OcythAkLkfdeom1fHXk6REP6PRYkKxlDfibNMbFQKAnPPIKkeZLpXQvT2v9GYs0/orsvSAQHP1NEamoUjmIQmSYf4Yu+mb1IOVm0XKPY4Zzpg+RO116beJFsBWSn42GiFaxqBumnSQaigCr+rpY2OIFT26xelnRHre5UMQcfKmyFIZvmFGlNFGx1/JvZbuVZ7Tjym9l04tnVJEzWmpMKTICuHWYuul9lRVnK6wsRxFmqaRiP6KrUQDyFasD6wWD9CFVqbgKQhSwvZfiPfhQuMI0jGP16pVZLtwdsBBXda8w9gUeH/4DlztRyGZ5jvBjLiLHqpY4RuxTPhZe53O4NMoy3LXbYXotVl+sARL7/2UEK14McRFrwr/p9JL2qQgrX3ZN4JH5FFjifhmxIwJXuPRs0d8dT32nfv3JO2E5MtEybljFcYegVkT9lon7UzsXkb6CS5v2LHR+Oe6/XHef1biTxcnJOfp81wVb0jpsBV2V7ycDalnuhD47lDXzJ+Rm1Tkyq5bEPtaPe3SpGpqRI94xksYeIafWqEg0PIlaRE4pfNjy3n3XqytjY3YD6NKqKb/kJis5XJXYXApvXA+eKk/b4SFDMAgDUuqzz/3RbpiIdExSXqNcYZKPtQthey7pa0xiF3kc+a+7OH11f3BCkn2eWBqD80OyTmnSLXFoqGVjQ8aBRl2yEuGfsKTw54JHmT8xalQKBnQNw+X6WAaSmixd25OVAR1h3o0TEbdwtfB788UqWEbwdbURj8UT8zVRxSz1okDVcD/kVHnBA84NfZg/BJYWjuioAw2D3oxMW0BXNV+Couzl2wMDGt/88p/NcUyhTRuA8WbG1GHfUDeuthOuN6YnpZ425OhDvyxpiByGxKXXW1UJRERAi+G1pnurqbeY66bLb4dUMYFMopk2y9blsxkNonfIUo23h7NZjVQ8cmqTeuZYasJGroKwp9l0tQpuer6IFv8iOtraK2bwrpNihkOgwKXUQrEseyw/yp0S49vZ6bzQdS8gSQ/zRp7c5omK7bROjp2z5fKyVOEGOHyK4d5iKZ2TEV5BSuvBuvGiEph+C33dUcL+jOd15ekpKeEbhVCidREuQ+zoczHGYOSnrfFNCV1y697TQoA9Tzdm5if6iJMoOb8FXsAXv7FNM50C44wqmSQMcXLjLox5cjUtNc/ALEZbXKGapSVVD7RUaqDl8506/47hc/k7ipo9+m8UV/y+x2u+oYwD/xWXOExipoczLUZLPPOocPsTTNhTUOwL/nQPkx5GPEEjY9DqJGtUP9eyNO6wen1Ay1pZDumlsTadtoIcbeML2ioGtHF1zA830Ubd/AveThIMdx3XitayxtWCgzOAd6LuPZuLaT0YLzFT3MsRV5SSPNI7tViRR4owbp5a9K5fN5WWO6/6wccvKfMhOg4JY5wtKLVAXoqVfQ3dtE1tSFaaWACbOGfCK694yx7L1xZ2GSoXNa9bYS8e7KSAG17AK9sBrqRlQAO8uriagviXLWA5u4DZvrc8GHtxBvKTY7gysOpMYIR3RtGQgmJ3MJR60Rug2rUX/dfQizJsk+0GWU6wygCzIpJpDFvTifuImcSSN1EXEO4F6Nzh3bjpbVzzZoBii9T+4htaZaBhbzKgF0My90SsZF8aAOfeQ70aXx+/tN4skjW2RYr/KSdNGja0jlv/1UTnciw9cB8k9arSp0jlObVhSG6eFHMlnSMOVh+i4vvuaK3vlcvBk4ma2s3eAWJXgwpvZEHnbc7N4p+8S/646JAFb/z1UbqrXouuQH1o6tAS2CskdUao5+BjxENXeqvT+HVMehiVV07Wbhms2MR3AfrdaymwJL4MWIoA8Y2Dco89xe7P3C8kyWcs2gXukWnxE7C3r3FL4nz/o16Tyt1VzA9huUzVqnaOG824NI07rSwfUhllNKCW0EaOIEXjPyowhbt7fscuTqx9EgNM7vH2r444KC28UA10Fe5vRkVnpmH6UoZILRoKI24fVedpfCcqQaVvM29YMIrKIKHKcAoGgVtnHJSb5DIWsgW4QtE9ArA9JpUBvSX1vtVjz7Vk4IMVIgx2G5Uv9AvoYRqh6QQEymgA4oG9S7CndLmGYZTOLtPSFlPBXZbi3prLQWDm2DtP39gSXzp2tbtAH9YSnzcuUxARrBlA81nfIBDU+4ztjRFWfC0MsJATHGsWuMvOtLJzZ7VfThziYHeD3jYiI0F/xZs3R881Sn0tQi+3LtG+nIT8xNxfUchQv6ZWqNIUV4nLtmJF+jLjiRONhPcZ9yZQo+ewCgU/kw78y0tOie4ztFfcEjJLfkFjTPNDOEU/4A2h4jEyjf2KfPOZR5PIEca1Yb/hGpGnRx9gThiF+i4oqTC5CYQ0IL9FdZZGhJ/R08+PHvGsbqT3olBcdHbPQWIld2diNrki5xn2zlSsB/44zbE3Z6awJIbAaTunaxxd3pSiwO3O7yK2jfnoFeYuFMmehuBzRT+lSzzUWDvUtlZa9Jv10Be78VBfvD6KL7WCoyZMdJOxBC8Kh1y9sbt49womUyHfeOJuhW/fHtoM93ITU7HjVSV7L98Nfb8m13cqCq2aFXN1lWjbpspjpVPaE+lI26V60Gp1v4s4nwhhFt+lpRl+o3YxmVp5gBXgoviMOwVmZSLgEzrXeZ5k1ayJlv4iPTm+3lnxKuJaYKZppuwj5LH3U8VofPiZlhmzKl94ncTYGyT5FMTyvjXc+NtT34rxK1W4v3fxV8z0j4rioqL4mELzd1FE3n95gnM9zeTBqRPWv5+odn1yvWlOb+FY/4fRk9bRikx1o9hd6LXsuUfvwdLxXLeUyZ5dPGfsXdUKKyJXxktUtBQmYdL4WqqXb1v1rClR/kCUz5gbXNc/u90fDZ00S12vqqXxSalm+mSVYX+AwldBafcfShIjr3j77WtxP+FO6w4JqNqBviazJcYpy4FGe8YKPOC5XSyNZEN9mvR0Yq7/5dm7ubrI1O8Vl4SncKLV0VLLuJdJAEEjtXMJWH4yRzg4DVSyfOZErMrGVNG2UQeHuk0pyHtB6s/SYrXeCVzU4eOm91BnBnnK4FbtoC5SMFEnnoGpsDwllJm5yAl0Y3Z0t0/cfg7J0sYMgM0zdxFcNfdRuudSt1Eyrtm5Vr4TdMN0K0Os8/aTh17WdpVjWbp45osnksFgnlaWc5xPCvPclfvIif235lMrP5iYOK8kjSZZb85PtB6PJesk4splHfrHxDulxWR9U597dshY7wtwrEYDLaxEvPkOnj92fHCN9SNExxBXiH0NY5IqD1eVAZPBmtx8+Y98515IdJVbyPTntnjjp4j19Mqio3/hwHeaocYUu65k5J4u78H25l7lXORXFJtYVnT6yzje+itgarwkQJaGBe/ko95sigHacC6cF3Fe73RtkJ2dbwKwioS4uDMnfVsjkgsEM/nZ6dcHUUrZhizPGXczDRMf0aPhkLYdq0Nk/wbiQJPn+G0JqLT0sOoqbJ+FWa7dLE+gYT8egvAVlag0F1QnrAdJGua1dOSKyWo6jCvcyMY9POSDLNwJk/LtZboIdrS/9z12hC4owSfFGdX1MCg4/Mmz6ii+SEeS0nIrtLlRfsc8iKOuLQVk8XrJJPug61C9oNeLH4bd6+ir56xkMblv9fRWXG1Chsnt5VhzX75adGqNqOrokyvg8DrKLHz7dGbbf+ORAbzG07Pi7SKKGWL4P1WOgJeq1XYC551yJDbKgOhorGXHqoWpwqxiU9oUCyOcXCjCt18s/P84F3DmO7ykebepgVemkt27qDa9Y7y+5y3UV2KfFmiTEx+aTeu4B+0TPQyHyoPKjMG5xvPoo6OPRBzIlzzNIU/JAZfGR5QR6ujjwy+Ofu57LNOCUl/0dyxfm5B1SMeKufGhHyUFecayOKAThWLga3tHP6Fok0/xfhJF4ACGqNqJ++03jnfOrefLdqLqBKtZgfWDocNs6LBnv5SQdHY/1gpIBzliNUw7cCqBJWE3Hnp5i+zN8ZDSqMFn1YkchGbVzIJtRCkpMXRHnolYBn7DUyvkG1xrPj3LWl0ZWc6pTnlkNyUzhcEC2NI6yVKRjr2VOslcSWPvAAtzh3dAm7OxmvY+tt3hypbCbhSxospptsh4W7BEu0BVJq/OqdQ6Jyy/TK2IqckOIgdNYnihHT9ssC92mZb1rQ6apm9wRr/WWQ15oYc9LUeImfy3KPJQD875vfsuT1cR9mSBi9qqgn/hIv5jlvY2DwSVeT1laGLz6MMWK/4gAg6LNR8mlwPMlKZVHkYORJAfP1VyEOx97KQgxWjRyGa8ttMfkxRWm5hzBOO8J9d4sMGBxyN0XywNceJ9Twu2K/9M9sZJu+wxSHbB3d7evlqTx9CS1ZjYnx9zW7CKs21iakh/+2MWa/vcovp9TqzMM3r0NM/phK8AuBJ8S0vsLOkbdU1xFJ/U8BLjhAda16Q6kjKodNcSJr//ko4az0muUlzxqUaTKmJb9c3Ek+R5Q3SBb+3yYNQH9NhiblWlcp/o+ZBoq4XcGsZ0RoLhsqWxl3u9Zj0ZTvTk2QrLQgTmy3U3inBVkKnsKlSZTrfENlCR5lfYuwt5GUQ+crI1rXBVKqu/WifVruFb8cor3noS9YFTFMa/eBvTgWW7Cx6VT/QGFL8hLNUpMGQ9gVPeW5ur0D4LBybMNEwiCkVN83xdtPgbuyEsYxJuh0DW0Nq3NebEnz4DKAyGxma7QQEk9WQFUmKktSmuAmYaHPWCm17QiwehF6XeICZ+mNKSz6TBduhPaUnuiA9WCDo9WJyOOaa+x2WKGRjGFjOAlewwx5dtwHdc4tJGWexuQoJGqUg++dUpJoXZS6RGm1fr4F/o40Glmg3Y8GaVDYCKVrvvWvaBZcNtxic3WO4QZ+rr89FytK5Z7a/+7V9mMpZUSPfPFhvSNuhLPSftCm0RKzuO1p+rvPT4/Vz3jiOplcjZTpVoqk5LQKK0eB1tVUJXTt6VVyGfuyeAOHfzosfMG8y2YYPwFqsFX7qPTvAL5eDn64FfLDMaIZuh3GX7XsFxNE8vnWCyVMXXSN4uB9NKsiY9vxL0elvodEdJBgYPoiQeYDaD1HuI2eXyCyfewgrvAc9WtAM3Sr8fdiO4mY2SKJh4AYv9so+Mfe9GGHRZwgF2tSk30Da7OLxulMAgvbFv44nM2x5JEb9xCjf2tByECvMPkJmw3TTsawopUAELxKpb6G9uJk5vNvX5tHxxzdcjyOVmX1oEowmjR5go/f4O7IxKh/iUbVl3+jnhcS4wruE2x3R2svriSDfgjO013IRHJziFblNRmwU3zMY0FEbwDYTKN8Jt7fvYUwGX237dy6NQI8OMz7YnxYMrbg7tqhCjt70/b/wlne+7fvNu90zrTxtt1vL6kGWWVm4riy5HDiA3tkorWpy6ur4KwMluiTIZNeylYU0WtkbOWyO+DOcaVoqk9Xhem0pwSrZXRI1ZtfXVvO+AETUXr6a0ulnSjJGwgYt/FHP0Gb9Uj1CVaGr0IW9Wj3nzhAYtRu0N6IuUY1aDGfTefdfJ6xSh35wUvJuR4jhMOpAC2y0XrJLhrlXJjSJZ+Hiqd5jzOnAQDQ6jENRwcGpCNs6ELdg55QqqZOtcjmMqizEdpyKcl3LXpwnLBJVOkk+ipDaZxUvBKHFM1fzStrOmXNtaDs71vaJGQtwZIWfrEj2JpK3yRhOQD9tYCOuag5AxaqK2sE9lImJiZbXqjTHVEFJT8XaIST4bQtezgA4ub4yirn8tfIj/Uh5jUfnzmqkr7sUgeTTvB+l40NmA/9fxd2Kt1wFZAeZx0i/8mtn80cRz9OjoZyzxwovDr0l3/vjoAyqJqJZfYGU89GKIMkbYpgZf6YXBYDQUZ+CHYQ/msZxk0XYAIpXtPtc+zlkSgLXa5ItPm+BqxGqJwg4NGcyGqyHPtIpNLUUjsYoWOTx8dvjY9w7/CdNNkNFARkibFSKf5imcDacMqqwinDLQo+KbH/+bbVp8xqv6uVWPsbvTuoL68hi4m9MqpSVV1RlFarkhXDGLXuqsm06/SuBsGAUuNQpX41pqfPPxb2xFbsmUSY4v5NL8HLdRw211/yiTiGPvcFvF3j3FP7+iQ/To6CM4Qk9ZKczHiC6Hz2BfGXIuIVUw0LSklgS/K0J+DMTxaU5A4Mupsq3ghO0GWqxV4bS6UOmik3Yenxye1knGu+8WkJpbM8t0UqwY6q+EX+0TFRuwwgvPHa9Tx8PfqRjkN2xJebSjazvRlurlytEtHOdFS76MiqOrL4dNhio/uo4TDteiIZ1ZQJvlaq2n3BJWwSm7QuctMf10GQ71M8KumPUkRvDurbcLerBCSSYcSgXEG2GaAbvfVPeynW9SWzJrNGmHBGjcRSIr6/2EgNuvJfvV9P/VoUpGhZzHVCHnKVmxP5IZPZSA6WfeyvWrvBwCYDb6877HCVijVJfboI9fKn7Pokn4MNBkUVQloMfat9nEHMdxL9txH6WDvSgLu3X3/I87cxI7Y6wicNrR9rgut/VrHtCP1PZjdRmsVZ706hjly11cpQNrPnSigNbvVRvQ501aUgvFyRAwciXuqleAHXsv84aLrqxIu9T8hnCUuxL1Qp/LsCZk1mg9yHbtN99F1huNE8u9HgXIuEGgtN6J8Z1/c/PK63aIC1adFZW/FQtwWmQ0Uj/EJ7qbYsGxZmN9eWOj4da9tKYXeJyqmsbhJ1ryCCHL8dU2WMPDrwg9j97DuBz8/Sn5Sf9ugbaZzo/83DPuMRe5XyF1UFfD2qVluf6EGqHHNaqkjk7j3oPwTf7EdWc5nNro1EZhd02wo9YcOXm1XZXNYLcgVedgbEZN8vsWUQoxIgVxiO/hN6uvvnSVmhIV1UV6DgHDFjxOQFe0OiyLJXOjOTHAYkbUWWY64A+ZrmtTCZtSGmsJFlz1rczlP7NkWQGuw66hFWTTxx1i1XuEVGEusI0lzD2s8saVIlxOJJGsc9av4WiXXwA6j0iXUa0rUFRXopMpolY/o9iF9/mD5yRq53Uxi0vsNcorNBZqwQjicDlJ4qTSMKOtyHYABLd7fxCG3fR+kGWYCSceVC6QPTsOFp+yxq0bcixGrf9tTc6kes2pxKIj049F5pYJ4/jV/VjUH6esPSglP+dtnuKEYOOfki8xCzh+TGSWoOWpQFmwyRfkj/ljKjP7CIewFqixXxXqBtrr6xhMwqRSqanDspTiLPJMLg7DxjK52ZUSvVGjUU9bVNYuVxNZTQpuXVBpc1PlY5vBZJrEg1P2IP37aEZXQyRP0xN/LV2N0mGcgtjgsScbYYYfO0qb6mK33GYrne1GYqMcfiJqlWy3fVudTrBlwmqVeqhdqh7S36petXY7hVO7U6GwCtI07G/1xqsR3tnIZ/pvhNkq+cLEyRjn0lzmbfDN5b2wM8qgp3jYbPlvxh1WwrjEGsHYK4QvhoG7cCsawL2ez0AvNewbK8oQzg/3Qlsp9dMqI56PVpqbE7tci7MrGC1v5iJRczGYqc0M7hR4ZWVAe7mndLTNThZtCrD8wx4WZWosYITnTMPhTBH2h/rGbMIT/Ns8babYsN4LBrbF5hApqhQXmkqvzFAmCjZBvI1haoNGxQC5XDLVEIzxNgdhVII2cjUkPqlEotLpgLvgbQ8mVafaLbVjBT5Xr6/czXDGucXqUpCGr53jRiRNEMNtuTSGM6ix+q2WG/z68huXp4GfCw+tihLDWpFG42VTlevgPBUt6vaUMseWcaaRWoo3+yuvkK85gspSVtsoxDwxM1zwoLSDWJepE2Dc2MMkwrw+IeJRSD4qjFrb4ErbM/f0StFvkEgPDSLrOLHKTzTadpSkWO1sN8RYzrdDG1hpWgi7WHe5OYgzIORjb/7cOZRgsJDS5sa1+RYNQheQF4wygB5lzOGeZI5TL1/gUlwJOiyGblnALkQ7lEhjjlgcA6SMlLM7LquNfTXxp13SqwcHPSAkCItQWFNgFlcnAf2LEAsEqMWeLYtdd53EWiklSeUoJY4uOW3h/jToJRlkzdIsKqUFshqXV5FG7c8ewH/m8D/z+J+zB43yfnW/fQqJvVVLCyqJDOLqZThwlB4ST54kMbo2Y0IHNJkXr+S04Wj+BjV0KjaKZ82ap4EnzSOINfBGgFJLDbFHWh4SAicfKI3IRYi/tx4Iea5K3ev5AXm7cDS0lan/WcpxePsP5CCUfWlb34B2vt4TBocTp/QjvOGWe7038dubLkawzddGlqA21ckG28rV4STh0BGK8D+MoTDfFV15YZmJt2Zib84cW9otJzsj5uy/5P2XUZyFHLp47vyilii9XroP9WCqbGVxijdTDBVATzWUfUK7OoFasqTf1+IfiYjGou9MhbVULC5TyDcRqkXYmdLkOn0mRtRofX30iOmJWBhuuUhUy0HPujf83YNAo85W98HG3QZy0U1qy4TPVi5awUsQQu7ehX8JV+6qoqlLpK9ScrjTZgj9RunWyLDuciMUV4U0S5QdVXhU1PfkcyypEuw8ba1SuUw2c094quGVg9maTjCsKSWbaotSebcCkQSvYIpJNiVQQfFTFSwdDIfMkd8upVH2R6F2dFVzZ+76Yh5rudu+/ki478OQ0ilVOvBrTSfI7Kk48OtwyYVfg9parKxMU6JYZfhmtnz53volpW7YCPr+T+XhbudRzb2X49o5qy24rN6evISjMcrx7ppfHL7ADFmidrrp3fXUO/yUJcpCj05ueEAn0C8xd8TR+8ykpOldFk85CzshWdRm7+OxTB3HA3soRyP/qUa1yOMgX09xFLhWhcGjYyCh1TwCLqPB8Y5LeaTJ+sQO4iWHZtLDuj6p5/j0B/am5ml2jHiXUqIw2RCljpTaIpUaZeqlIzKtfzWOqJrHmNkBrVpBFxPmNJu7c41YrSKuu/RkNJGy+EQSdnmJOUpbqdab4+WF6unfEBFVWL4su5CHFCmQjLcvxSvn11S08SuWXJDZ+NG6/DPmXk/GYaUkmVahlzT+xe8uc8jxKNXPM+67T04+C1TcFwURE6C5OCVw2x6fogBTtsou5x/7OXJkiuZ6Y5yo4CCXMSAdkc3AYgsOOuO7MW0Bg9xlanj8U/PcGdbz2ikoj4fTKo5lBkWRbLQUkqnvM4CR0o5rSdAX7UYIF0O5548orlXT08fi7FRzyfJUdLT+deRbpFvhIIUnYpML6ZLcjv+lKaOEoQf9WeCeq2PfKoTpsmH46ZnJo3YvoM8Z+3tmpg4RNCmoAH2HYNyz8hoTql2Pj6c6p7EaZnAByCDGUmtGZZhs7qlVoPaStjhm404w6BOpmGGwVvfanvhz3PYa/X7DAXAjzLJeSPmaiOC8EcZ9PEQru8FgJ2w6eh2Dkpg7FSfRDp7tzcpaT8oyadWVSjTmE9IGcy4T+wNOTy3s/oAFV7Zwr7Zwx086MyGrpZPdN63XYLwX5kcQ3jOTy3tiYLWmi1DAYS5jzVns8DdFF7SnvBacw5v86EPT/09C/+TwV4f/cPiPh/+d/v2/gBkANoNiAJ+h95niSUdp0F3u6ixtszJTKpbKM2by7MkyMA0gsVXj/Pp/BlxqNrx3kY2QayHV6C3Tf9GdMK/8YDqoPTN3v8ISsKFJezQk7UnBVu2Rgxpwe4N4lPbGPP+NTk78QsK3UX9IZueba947oxA2aSuJwm3ovhUikww7MRMMh70xy4rgsEZreQlnKS+hd65W0s+NcQr0wGe0LyVrDSA4DBgxjyJ/Nb78ALVDNsLFO2/uAjNPdgz2l7/RC8Nhc/7VSXg2ujhVk+EFbyUYMrnSmdx+klyHluq76bed4t7ykVq+3+L70gSLKbduTVMIt1Z1sbVaWfPFQfjWcucLm2y13fIPK4V+ocI1z6BfMW0lr7PIRyHt7u58f8I06i1JPHIbVC1pKtyN3TVw3X1YagzeHH7YU+xNeHnWz12tSIw1yY1+ismxqKbQOOs40VZ/CQPw8Q51lVvEybpEfGvuENX1bapEY218x8IUOV/rQuTysJy0ra4Ww4YzZxZroW+1vKto7U4egb9DKKqEIzmW3+XZsThhbR1DQJ0uyw5vtncCqfzGNWDcFjBuN6zVQJVioOwz9iyJPXnbsdl2bGm7UQAG/5S1GbM24xo6aPXQVSx/2zjpbZFftGJfGAqdwOawYYVxJxdsU/8WaTvjh7kJZYJsc8QVqNXp+Nflw9XODv+vggg6CqlRSEYO1vjKYkJIlgySZfcUTBFvoM6uepuvoYMYpqcWe70eRAnIIRr5+uOps8ikJI32wgBEwsDro63Gm5tZzae6G/S2ZzCHZnfBuwXyZAfkXZBSvV4EF4ThgA0QWan02/DlEdzUvNZL6q0v32iuX9ts+r7favk8nytli4ZDlkZd5poddLszmOw9NaFiDvAk7EV457Be2W6QoazcR+kb95YUJ5hYUiQq97bibBdmEJPZLQsLQJWss0JODh+EyVjMDuMK+0MUkJjfuFiRlGKs2TTiQWiC7cSY7RYdM4j2w3oydepDuPKx4mEHNQWIFREAeRClEX7TME4jkpR/L4Qx50ZOmEKqKcYtSbP5iZ8wV3audusFaUbBh1YPGbL+J+GDKB6lTP1weYAI1CVPAK0ppcMLqc3GaAid0jTs2h0Eq/MUWEMbUqQAmATa648yoqspw2GObMMk7o6wujHQX+xgj0CYGXLHsJXrV8VpGaIzE4GiEXFd8EjraiQRQRHY4G7D9+5CIzrlKKXBOcc8zjB1ec75wUb6BMD6dKhl0v+ub10EUnYJr47U0/cgSNmRz7VEMw+RDqQPsXw6fZANaCq2J2X7haEbgKKv4GKQIpbi2rCUwV+EIVOKdeDLYYgeX2orVB5fuYVuJTi5QVdwzDxmBFZWIhNzakSulcI8zFzT7KjZ8c48AWg40NpMnA68AMGea8CC3Myp1Z0HVtA/8psRP84vea/JX/UTv05eSaD0Rnfn6i4TusxuuZSVEGvvzvvvmH35F5iShn1wFC8Sp+VCl+LcbQ7cLv6mrUJee5a4+/ofppJeHWLZJN11I6S7FqqySf1Mf5335tlfNlSrN9NjKaePoaieBImqv+IkkakOQpUjlRWxUjKNVGBVvS9VsUsBO+10DyautVFh2yv/CnX24V7dQh9lOkh+z9TI4WfS+QkItLdvvUysV1m5Nf2gLAfEVK5MDWZ6pBJjzDD4KboWkaPRU5675DHPJ0T1U5m302vs3puJ0rgXYDViMg9+jT6n6LFqT23RVPaPaxxBSCPjIg73GS/SzA2lX6u5MlCGk72lsbaosJZtTjm8k8qVczWk2rbGe1cy6orSltkHNyuLDtvvXsRBDYKitFWf6wW1FaWt1ohrbnHikmKZ8taaIsap1UK83Nga7mEYBjCzIIn1rJWvGHtrgkbWz1JiJAL5t4ekf6xH+PrecgcxGKRCnMuAs42iG+UE913Lzls5171eqZLcu1uFpuyB9sK5CXqryl3QzIgF9pORFuW9yQSLwo9VvK+T5hSKnpxMwRNnxu3Jq55MXvGk/FP5KQn3yOirndicZA3iQYhfaj93Z7zGK6ivMw9c2YrwAQ1cLY7owDIxZAG9Fie+IY4TGKrlSSTXm/x24YmafopFWxeEoWF/9sDbnztYRELCqtrvzx+8sn8WnnBviv1z8Le+LPuvwiOx60v7r9lCTdM8stTOybWVnW6ruyB/tGqF6KnRu3RaEU1ZnPYkif55t5pqaPJcIsclDh36vRk/DBPZslk+eTMfBnOQYNQ77IpvogiLiWokC3gdAepkUmws01Vyns/kAmo2h6y4n005Jd4JY9aFGukvBb644j7KiCy9qkVlHf5uouDSYmnAvkaLL78crw5UVDlzYeWrwZs5bc/6HFuLFdX31FFLKq2wZkVfEZfVmWEgOV5o6SckaTCm2Vo84TLHVXbtHar15LZrOwwmRQMWAboxpRWrxKyijXT7REdy2c6Y8YXyr1rejrlRrWLzFYtNL+4EvVtYIpo9aOnGMDacz6JX124u1gJ32wluPCE4RAyc3CwLcLptVzFKTGRj3bq9GVO8LPu2Np9U20MjCEHM/7zdqp4DIv8tjqW3vP/kzb/qn6vX6zbvdbuyl0nF2KdMR8XqaTsKtf5062x+6ivct4zvFjfuLWkJtMOtX5+nxmC3pxhMMXvWG6yLhlD+bTP5d9brOxZ9byt9by9W7tBVzIy28U6SNWH4/4RzOIPA4K9xC1Xis/7sfKtSq+Um9hqJLe794glqtuz6mmPEdkjVLXkwMmsB+1OWNWesh145jpqUaXU5h9TUe1NcLfVtTeCqb370gUGRT7b2nZi5o7KdPSBJIkd1ofr8ultn/C/6XsHBW+71jFdpLbbYDbToV2xr1qzgg4Nul1bByrIpL1nZ8HqMcISYxrCLaw9KKhqyGsGwp/gH7OjZefqzvvmqkrVJjslrVHI0xx1gcvbQZH00t5M615HiuCLYEE07MilTM3YBmpid2eO8zLickWGDSD5mDxg7zrLs8X/HJaTZcKi2HBwgSxtMoEbkj/RSzbf6WL12uMd5lrZ3mz0Y8wdWP+bpiL9detLCQeYoHEQ7cQYxhMMkz3JTa8FIX6tUsiyQZ2dgijYTG1XWJlIkwS1nPGiVezfHHsbh2LXv6ODRyisTW7GV2khkFSypsgJmvFHpaG0xLZZoCXUAxcGEFgqW7wGr3Cvr6M36f6L8r1GlncRcXf1+wzZdUa0x2CZtlT5nnBhDK7E0rDlfGtIrFjSfIn6MHjoHvBqkWZhQhmPHkOJxX9wxPuuzKEboqzpMZEjF7PosM0bJpJyVNSmtAOYqjTLDrapCx1aSVglQTwPLwNVSAJpda83IcQU0bqZh4ispnhnkRl6X3KI2r7jUC5r3gmb9lJtEc2R3zitXvluBlKF8oYM1OzanUnzq/C9rfWzDQOO/GQ52sl0M1p5XDC93Zu8hSv5Z48/Uh0afGW9OtCpNJCK6bYy22Co356T2OIc136ou3uDK1F4vbtKNfxpFW+u60BFYjhRV13GSoePkBrtOcdNh0efPzesfEG/9FSpYuWsXw+AbwUNJAzbUF00dXtubtRjVCipVA3QV8WQxt2x0YAv4eMbQFc7b1UdQwkfS1QWOovBtjWK/4gdPeLKQaWVp/NgeWjL1KeiRl2kMA/Qy6PSCNPUud6MsRh+vPpBg/OeUjgMCodD0SiZWzlN59+G+jxRnlkJDvF8uxXve/ZQqEZS0vIahLVHn5nA1fjjw7nf3Jmg7rt92awK4WxPAzSaAm00Ad4hOmXUWOAkHI4w/LLbdjAAijMrzqNBPRQwfAhcD9CDHgabYXdpcF01gW49Z6HQUoBBCZq1U0d375se/wPQ0z1k1lDxl2dGHzF/AIOw/irqUKvDcvCEn/DCMdnYR+ms/MN5cjQZRf9TfQBd0Jjjjn82zr4PE8dqsecwoP+g69/7GOmTw5dozOIJ4WDY6SWjW+MS2l+KkC2+zcS/kvZUnPoyM7jqbwJMw/zdj8N344dpgM0jf3goSu7vzlXgg5H/8s9nYCHdiDDQHkvGDK8bHbMbDq3Ga5ZD0t8EWxqQmwB9lwZYIm1ae7nurWB9mif5hHwAQ2/lan/vBrCkbQHfKu4ZUB/7OgZLI1jj89zyVkalgFF13wtjWs1CEx9W/sxtiffYiBMPKXCiTAIvg89YsHwT/CJCUiu/YLK2vxARaxQXvhW8GYxBV14NB2KNFouS0+GveZE3orc83g0G+NMoyCvz5JaULk55WlDr2mw/+OyBBM22HraULN0aDZhP+ZefRXx0x/0pyfmjOzLVarfZse/bYI35Sc0QacG6iAX+tJMbK8+OWfSTmYtC+b+4Ehvukejj+cZOM9gmWJofRvpJpf2HQj5RMX0ePnOOy5BM0MvvMeevAyOHFvVF/ALLKoMmeodTB5oO2REHSmgiiAIXN1dsCOiW4RMqJgE+BDOOB+h+HjzFlJGX54AW5XHnLnF9zCeBrnGihCodlHdVJwQKcrbEAWpf5CbYKP/JrojzPxWa9OPyUcvd9AbjygfPLeKYLnjgZYy42Aky4x3ft3IRz4Pnb2Ay+xopwchpHH5SgCx//8jujaIiTwJ1XJjJXmIjkGQQB5bwEuw6W8svgSoT6jqtBshMNliiDOY2403y11SbXu5SCqZDvXcL810g4KKHMC8pt+AW5bP4kLymvoot5r1hWR84TFvPVKU76c8ZtqBStZBHZUHTq5MCkJ2GLaJsA0Ht9CjQr81a40osfqpcC2p7YX/yaN95bbuVLMXxaX7mY5+aBucGOrOIUZ2XU33iTIyvZFpsmktDzLZwDycjYAjkx27pyivArzFCJ1FOUMPyUcgU9O3pE/iJlSBpELJYEw2DajGFpFWhBjTkwUDQcFsmtMSKN1ab4m5aV+hQ2Uk6j8ooHNiHnQ/RXlo1kJ4pRLZ4XyjtHamjx6wcTbNh2nDA17dLsYnT+3CKpYmFCPieLOGSqKMTlwyZyyJtjkDfXw6QDNKM9/6q5LvfJ8AtiSXPm1Vk4gLPETqDUZXms7yHNQFlNMmYFW2FvH8/TUuN//+JW24Oj+azRXh5lMU5mCTfngLEsRQAwFwtzUWOc245x5l3jjNtnC+PwizLe3k7DzLwiqXSjRrvR1R0IHdZ6xmxZwAZ8Bi1+40TUy+i0fJ2AN4UCGz7Yfws1x+38yZg9KR4Z8yvYRBl7RG/1i5K/Pmf/ymBvSWViOPF8DrQbv+1Wo23/iOVetANd9ho4PQlrXAbrdgWscaP6U4M9xh5ZPhNezdv2OADuwNWFMQ76MdjaWyJsn58FVKf/0DHYGlsfZ/bWma31ZMh8+HfEkDzGPSicmrNWbN7CU2N95QR+23JUHMDxqJyd+Cv+DZlihkmFrzhnHSjbYzzMBMBtX+EAjl/hOApbnaVS6YgxaZ8yPtGFzFigjgyQm0kwSFELzC5Aea63Cid9a2w+yQptMhc1EHPvL1VIPtPOnl2mL2v6hR3a6jDuz3Jc4ZX1hG/1YbsdXfqWE066Njqfc3SfnZuthWz/E6sAC6b2yeGXzivtNSvm0aiA2a/ZN7AfBikIF/ku/gNL8UyqEbpmforjqxu3jhCvsn5NhQx3ozTL4fwzYO97xLw9USVUFdBqhOaBrVEWEshm5SbxycKyW78VJwDHzPGlg/zGAeHfm+PLWH1ZziBL4MD/YQ6UAWSSfjXQEpiDsTLRv59gorNtUljYJ6oC/buJgM5Vn54B3o/ft+3JEKmq9c0AL0h7HySW37d/B+X9SJd03ghj/tjFwkgO5ht9AZj3OYveIy3w4WdSVcKTo7u+fiVPLdKs/nQ2Ifj8162UgL8+VwRTFAbCuEqmI41gWl+gY3LA8QS4cyCE/ygJhjhXjBRdIspckKtpZiUSnao0FToenuHVrXOAL8lA+LBIU5bhJOXEgFeVOKJuYU/o7pdyzf2ryB61PUZnNwBkP/TYiJiO9meU+YjuY6RkyGdTNfivjh4BKX58+HTBI477CxD/MUT15yw5LWIftn8sEtt+Ct/4hUd0MG/2G7gUWXDSUwUzjz5mY2oirxj5b/lPbtbwGwVPIaEvNhCUlqpwGzGLWU3VzKiXRVigji/njTDoXh/0xvznRgcG610KknQp/9N/K0woPUfbuxR03oYjESdLLNSe/k555L5Yf9WYg8tDkbyf+R6pOD8VaMO1Pkf/DW9CXCo43hKRKI0wZRJm2YJhrXFzfse6fcnSEkOPz48e0aJjRQy/oCHiK+MLlz1lYqzeecPeXldUmfap1NaVnVv2SlXVqOe5sBn8YGqKstcLMrsC1GAI2BsTH7Q2SmcDxbRmaLFwOanEGQvAwiIOCeZ/YWnzeOE0cqbp0g90xylxU5GN0GFCNzLKam0VLih6L38Dftq8N4xmeY23ipZW71fdn2IL2FsJMP/siZbu+gCNgCs96tpU/qb4/eVkJ/VK/X1CH9uHcHRTvASWPOUnllBMODh0r4K2waAT9uh8L3o/RAreWlTCxAofp88udHwaMwULvxF2mmoVFMQPWBs8iN+GCb8zgqurW7XpFITAujSbV8NsN+6yX0mrG/bCHbRc7yuzYMMvWr0vbTk1Dqw0gFumlYKH1R40eOVdGQ06MnqRJXsqL2VoDMi6NAuumOTeo+e8KHZufPPLf6YMf1eSKBx0e+MmFraqkQTTxsK7Z13PUUx6pgsOwBhAinYk13DpznJE9U80vUBVvOL+vGScTzFjGnDIH6MazVXoyVHeiQCIajK8JBKsOdGIZrUT1kvbpfJ5lRy47wC1NU5Zge4i60J/73uU2PYBFbQAxq5wqevDbUbAKJ9Z8gQpqPgmNkbGRzVdXaa4HsQSZ9rKomOrumj8l1pt9BjxPI4DJop3resFNV1Jk2oerJLDRVkTl6A7eYrdZ+nYYOTJT9ykp64kkujYp8/i3l44CVgxuFXrQtBVLMelqew6kjvO4XKCbcmLHXaiPhwk2IQ07NoRd5W18TeT8To2Y/dnGw02W9xJKfVBzgyycudJESqKI7VankrVYcIUnnc1GnAtls/FuDZ/EezJF8w3qy0hVd4IjW/+8e89RdmFOgFuSiGFF6sxwlYOneNRXWLWQfmWqDjfRdnDnsJq35FLszNK4LAtskQ4mHId9gDkEtng9BIPaId2xbf2kLaRzIFUis0FS6XwT3JMutB+uGQzeO4bYhH6kjGL9dLZ+dm2YvVcmm8Lk+fSa22b4DQ32zJO7XAKq+ars6gGnbqnbY2HpoeturBcF8YVeiKmmbKHkDTwwwAQBS6WXcRAoamn72Y/mGqZOthETLGYr7ftPhmGSwbCOVj0tkDAgGv1zNKujL/YWqyaPCmHjvUB5Mm5dPbsbPm0zx132rrjLGrxBZ3sR4O2JJr9YC//IWN3OGCckAZnnxOuJYTBqdsSgiAKuMSIKqe16+h9kwJKrw06CbkBLc36r1617eDBonTLPjj1/wOZNwTkk9cBAA==")))

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

            clsid = "{08DA44F1-A58D-4E53-8F2F-A1107D57F320}"
            progid = "EnergoLogic.VisioEditorAddinV320"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV320, Version=0.3.20.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.19 -> v3.20",
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
            progid = "EnergoLogic.VisioEditorAddinV320"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV320")
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
                "progid": "EnergoLogic.VisioEditorAddinV320",
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
            progid = "EnergoLogic.VisioEditorAddinV320"
            clsid = "{08DA44F1-A58D-4E53-8F2F-A1107D57F320}"
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

