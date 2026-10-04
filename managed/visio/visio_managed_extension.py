from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.117"
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

            build_dir = workspace / "energologic_visio_editor_addin_v319"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV319.dll"
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

            clsid = "{A2ECDF6D-77BB-4B3A-8B29-3B736850F319}"
            progid = "EnergoLogic.VisioEditorAddinV319"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV319, Version=0.3.19.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.18 -> v3.19",
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
            progid = "EnergoLogic.VisioEditorAddinV319"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV319")
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
                "progid": "EnergoLogic.VisioEditorAddinV319",
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
            progid = "EnergoLogic.VisioEditorAddinV319"
            clsid = "{A2ECDF6D-77BB-4B3A-8B29-3B736850F319}"
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

