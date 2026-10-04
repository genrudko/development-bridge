from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.115"
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

            build_dir = workspace / "energologic_visio_editor_addin_v317"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV317.dll"
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

            clsid = "{D0F27C51-9E15-4C2D-A584-170EA8B7F317}"
            progid = "EnergoLogic.VisioEditorAddinV317"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV317, Version=0.3.17.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.16 -> v3.17",
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
            progid = "EnergoLogic.VisioEditorAddinV317"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV317")
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
                "progid": "EnergoLogic.VisioEditorAddinV317",
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
            progid = "EnergoLogic.VisioEditorAddinV317"
            clsid = "{D0F27C51-9E15-4C2D-A584-170EA8B7F317}"
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

