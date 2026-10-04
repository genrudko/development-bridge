from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.116"
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

            build_dir = workspace / "energologic_visio_editor_addin_v318"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV318.dll"
            helper_source_path = build_dir / "EnergoLogicTopologyRestoreHelper.cs"
            helper_exe_path = build_dir / "EnergoLogic.TopologyRestoreHelper.exe"
            helper_source_path.write_bytes(gzip.decompress(base64.b64decode(TOPOLOGY_HELPER_SOURCE_B64)))
            source_path.write_bytes(gzip.decompress(base64.b64decode("H4sIAAAAAAAC/+19f3Mcx3Ho//wUy7PLdRceVgBI0TJAUAEBUkIikggBSmSRDGtxtwA2uts97e6RuECoksTYsiNHimW/qpTLjpyXV6n88yoUJVqURELfIAV8BX2S190zszszO7O7dwBl+8WqEnG7O9Pzq6enf033MAnCLWdtlKR+f/7EUHpyl6Jez++kQRQm7it+6MdBRyuxHHv34VF/G3hbYZSkQSfRvqxc1V680os2vF7w9x62on17LQjf0l5d8zd5j/QPwzAN+r67EqZ+HA3W/Phe0PH15tf9ndTwCsBuDXtefHFnEPtJguPVSr0RhN3ofuJeiuJ+9u3iTuqHSbAR9IJ0JF5eDjpxlESbqXt1cxO6AJMY+/MnTtzyksTvb/RGc85S1H89gHo9v5nGQ791R/64yH+tByl8b1yEWd+KXou2go6DlSLnYjdIo7hhrvW6H2P3m41p97Q785I7jeVOhF7fTwZex3ckcASNATuxe8KB/wKcu9DrOYnv9fyu0+lBA84rvaG/7sVbfkqFWFH8bzDc6EGvoJbDvq90500fr0X3C++TNKYZDLuDCMqw73snKrpxsbvlr4Sbkb0ja9Ew7viGjhgbnGgUpb1c8nu9y9E9fy31Ut/cTSyCg6AfJf1Y9+N+AA0Y+tON4K/vLO9Yv4wKX14LkvScPInnnRU+BHzrLDihf99QqtmqOezyhVkMO9tRbJnbC8PE/qVkHmjFe5F5NZeiMGSkojYC6tMFH847uH9Xuok8QfhezIuxzmXYjH5cUqt8NrOer2LfKjB+2xv4Y+w8jiE3+n3bp5v2T8swDi/s+Jf72TDo760iSaPXrwyDbrOxdGZxaebs8pmp5QtnLk2dmTl7YerChZnTUzPLL525ODt74YcvzSw1RBVCyk2gVeujgd8EuMoLN3taSZaHXo/XysfMPjorEqFjNG5xEGiTyFEAPiwPB1Adduxr/mYqL6yhyLVga9tSBje+HQJ+Lam85uPBhhvJ/P2aP/CCGLfmauzfC/z7VcUWB4PeyDKYqAMzYunHdnR/1Qt9Szcu7nidFE62xE+bHCm6O5f7bYEh3dHlvrHiYi/YCm807d9umr9d8BJ/KRqMRGsbO1lbG6PsZ5q/TUdWOLgER4Vz2feSYeyvBmln2zK7Af7eGKa8EIc3wAfL5CxFUdwFIpf6iRnmlSHQYztu0ecS5KLv1wclH5ej+6ENo8IhUjNCTf4aaNqyn8CiEdtmrHZ14Mf0FY/CoWVYsL0HPR8myg9h+Fvr0SDqRVsWrBW8jUpCy0nP2QtLLy1fnF6e+uGPLpyZOoO/fnRxenFq6ezFs4s/vDh96fTMSxnpWY2jrZWuwnO5Epe02IU+vi5XWEJynVGkpvpI5GpxmEZFOmWi9s6cs7K8rrCUs+1adGwQB/cAc5xo4+8Qzl1vwEgVMcnWQt3uSrgSMnJeLMbaQm7XubsJ/xZLwLT3vbB7wYuduxteXFbgwjBNo9C5m0ZbWz2fPRXL39UrXLznh2lydwkG8yb9fhW+9vxYAOKPRUix73WjsDfKB5uMws4a/M+PY/ZeOcF51Y0o6vHyHCehyqbXSwxzxDGTlV6P3vRDKNtoVBQkzhALBtD5qsKXQRrxtqi4LAgcfHawf/jewf7BI7cEwoANAIj9sA+zdwWEgIoO8hqr0CSWvm4pTtyMwumez+rSI7E9Q4W7lasSiyQqXELejh1+gLDWiloX14YdkO4SOAo3gx1LN2E7Y5msjqAur/o9oE3ia80GReXVnheueul2vZkUta75ybCXltTLUBYkUX/HubsFBzj7yTCWfjezavjfXzaaL59LSVQ4f+tvTzZb7TunWidz3jFpvjx3270BheLo/s75291Trbdvu+yRnuBjq9FWYFIzVwdM4l8BGT72l+DcdN5WvyDZDoCCtaoH0sn6gwhTOaS/LfZfdFx0+ftH7rPO3N6Lgq5zNcybbnLCsZhT0rbj76R3eZHLUdd3pN9tQWkWBVVtw0RsOotx7I2czjBJo34ra3VX6b5MrmFmFk3Em5WTKTaWFM9quTQeObvAhoHMD0PbjpJUKUtv3KusuwtOuh0k886eAy12tqHengKLWuv11iW6LRNN/M/ILu7ZphhYoxwhmjij+Rua1Gt+H2gKm9O6MwgjVp7VryRmbTpN5fRxTrJt7/zgB9ppIr60CkBoEWQgLp1MztSC9UBicyE/meeZrRn1Eg9buXcn6Y0L0k6QDKIE8JcdyC5/hmm3Lp8EFk7obGR0XrvLPjJeZdVZX3T6KE2DmLKSIny6jSWwT6YPUrdVnM8GUMBvjZ3RkJyagGFaB6pvLUNn1V2qFrCiO2275PqgC5SxWUBnpR9qRThF43Q4EOzxWHUv+FtBuLY9TLvI0ptrFsi2mE8gP5ZdJvR/FbtMmSexXuk2nDlE9FfCe14v6GbCwcWdjk8Eutlg2s2DZwePnYNvgLf5/OCrg68PPzx8//AXB88aGtnB/2I/Hcahhd9Vt55hxDRbRgJnmQAxRdAco9NqYzn3mjgb+M+C05TetaCaKz2rlYEEAh5z5gFqC15NYvoapk3C9xC2d4tXuzNvITlSWRcQs8nLt53LSQQ9Wo2SAKfQ7dMjcC7wJUhQp+2+7gE70nZIvJqXJ7PeTgc64jRRHxXA55l5+HNugREhOEPTOOrh6TwM4XAKTp1qVWBZPoe8soNcvQLtVnBn3oidazTB7sW3QCJLmh133dtqK5PsMrnHZQjRaDusBu5DLw4SmJ2rJKf3WsXzYbf6xICOAv4kBdFo3lh1A3ipN4uf9kqOl+JBt2A7zvSONfVOtdQVQpQBTOHPJNz2s0dWo4Aw5Y8MnUqQyV3yBpzgluwEtQosqVZcW9OyymvpqIf7DncEvaEXtCPokfentH0QINNggFYl7MfBJ0DJvjp4ePDFwcPD9w5/jqTtIdI4IG0/d+oOius3kF+DOas6i4HM1palm1dDNi/0pVXWCcbtnCrndghnbN21UWGlDwU8dJbSuMe4QZLOl/CQ7i37mx6IVDZirRQqivDjcq5SWUuDOfPGd5zz9ttOgXcr7kLBY8Gi5TqXJrLl2mJgA5wZ5PMrOEHsnM6Wsy8XYpJBL8WwS80lFoETx4UonwOrphyOFX4KZx9ITTg105ovMih2bboNTgWYXOGeA8B3tfog6eMNtSsqy9r6vLaiwy+rblDm51Dyj6TQbDPkrQuQq/2N4AhQLXjCQiAtjLAZlE5Lvk+gprzDBJjGt7/5pQNU0UgEGePHySUUeOg2SpurZYzIh6AUZ+XIWlHWhDBb5FDoTbOx06hR8aah4qii4iQGj7wRrE1Ww/XYC5NNIiaERAgG62NFNG1UdWFcW0lpFzjijdMH1c4i7VDV/lKKxOWGGAm3tYKZqaYMumKzyWGpppwyAJJNx4yjUzPudNuZdqdrwClQMhnQGHDQSGQGMo1AZmoBYcakEjBTlXBqWJ1kEicV1m1TZa0UjFSW070XAevTzO0ILZsw2khQ/73QcE4p6v5TDhCyFE0E0idmMqBPfabnlz5yzb98KpdgosWKJmOlzdBWBjizuOWAuGNRQxEDczcGVlU9xFHy6wYxU/pNKF2LzwNmDUFhmlgXf1WZJGL9hH8NMIA9KEsaxnsMOYAT6me2hiYCa5nbSciPSLieABQs65KvReKupH4fIa0sN7ENV3FSsQBMFZ8eAPiKn0r1LozQj4V61HYE0JUu/43fADPySdRYQ5hgBp8KEmwCpzaq1boYIh0VHy/Fvs+bxwVrqVXdleU28aivesn2mi98WfSxiiOYdeFyX+sAyNqrQXij0XKm+Hd1mrPvZrCjUrA3K8DebOiyZm6LSrjXGCptaMIz/x2U9/34wqgJYzrv7LRAvsNqOjNtcK7iMFUXKxQgYdLlt3zSsy7o+nXCVnhfUY56wGbq1h3ROp3Cig9SVsI4ArZ9Re3LXgLdVKrzAjUqowBcpyqwB77X2eb6oS7gsjTEClWQullpc9p3atA1qBDlaSINB3ZXzBEQPRmdCGSGom3bN8TDPWtTfE6ZNoV+ow5OhtKy1qUppZpr3iY9ldXTtHQ4vUAHaYZogyMJJVXx9bAbreGXZkZfnPPOtPOyokWZcw5+Dbz5NwdPDt9BwzNXZxx+dPg+8PFfHnx1+MCBt9/A14fwd7/hzE1S/2t4wNraYEjw70T9fmAR5qttQDje5Wip323OTM+eMUyywKauOLy6ykHDPIDd7PQwaxhpanMITK+JhosMqdmr8XTijw4ew6w9O3xw8DUpyElM+hpfHH7ogLzE5hV+Pjr84OBzlKvg/2fw6iOT3jyne9A6I3rZqJDQ5N23Vc7pDEAYg8hYNjzrRl2NqlgnqDXJlsf/sl7b97yAXtjw6gfbbt8zjTtXgk+TElxHCoP+2z4NiG0SBbFMAZvaW8GdVivHQk6E4C0qqTJiMg4IokX4ztg32pFj4PcTkPefMpRFDAfsPnzn8CPA5P2Dr5zDfyJ0pu/M6cUhMvMkx3xOUaj+k3mH3uKOeXj4E9wEDnnLsAbw/4eNWivG+Q6UI+75y9xtQeANMJQwXc0BsgWDW9N3kPlQT5NCifmKFkZlLcxUtjBjbCEnRUyg3wEoYkSo/8gfQS5v9PumqQGGL+35tFaLm4A5r/hR3weKu7TthVukOizSQkB0j7l8h11y+chxnd5c3WS8s/ALb5npqQzjnDNdk2we/BaNiLDQcLAgOXzG+yIdN4g+jzIMOnjSKDkRoDXWTTup4ZtE6q5pNXI5loQUPGAaOAtzKPehw6J7xb9PjovIaDLbU7NxpTEWGcXlYuD9MA3SUdNOHdt5VwxNED/L/eOb2RxwkUR8aDs6M06fFed7A2yQLIPNEfG/dsg2QaRWCwaWPNsMtblyPqVm3DSCK5z4hW9mklkHr620VtDRb4jQPSbi+TWyDcghvAeEEKkeEsfHtKjl9FPZJHWIqbFbhjnL+LeiEUvSoHAbLZpBvLS5NOyxpdmM3KVhHANK81dtY7NMvfxf2QAeOofvGob50Nmd3nOdg9/AyN7FQ8XZndlzvv3Jx87u7N481vkcSj45+MzZPT037U5P7zkw5KfzfPqAQ4VqWBGB7XO+9Rmc33zPIYR9ONQ+F2psc28LDHeBg5ZYYkkX0JbEfSDiO60yl6NN3De9Ouwx7LxcGCBhoc0XrVXDsUJXAmWmlD/rf56z/kdWyjjR/ZDz4oquRlVrHFUVBI38yel+dBzJnJedhLtk46SpXwzuJwypcDqLe1q/uCdk7eIMFqoSf9ndMXzAoXdHxQ+1DzFt6dWdPH/saoJP6LQghp1I5JOxFQX1IJSpCrYEh3oklUFGkyqYvypGdtlPgVXLWCnPxO0Y2W5V9Ve6hQUNNysrBPOPHL+VzS9MWvGcPs6TRW2uQnuFzg9ahRMTSZwKcv2My5yPNcGAfBA/PfwAcGzfIVs0aWAOf0rl9wua5GoBaUx/ZdiFsZ+kwON3xYaG9bjGXiEJEgYcao4Wl6uHkWwdBy49J26M85Ly9E/Mi1Xwt/tcbYZqgw/aVqbtYH/O2T2zd/wsmsUIg/xau7C6rWqn8WaGxU7KV/9iHEdxlZacs2PAyA38MBEezEvi0RcnXpLLPMYbPrv8nDSpuyaWXmz7URMyYI1oUx4+IJb6a1rKn5vWlJ8VTGf0FSHHE8Q/EgNop7978AjEoy9wn6O89C6WxBtVj6E+dkKtso93rSQkBGbeAWndOBhlik9BsYNPOKwniOdzWFFdO5ebec24pxQ9USFh1eLJZQelCkacc9qLz4vTHosiKc5DHytK7oeo9X4X5FKJhPOp1kx5TDLHdSmqFNtOxm3Aav8UF+zwgxwIZ8Ab8nW7kmk2+iVJXkllToSXvXTbXdxI4LRuOeecGX/qR3gPJH89Eq/rKsP+Td9bdLw9hWH/HtGdTjrmm0oWBqRlMMNPGxZJ5ugSWm6ACMj6wI8SONNe8+/5vVK0YaLKlQgvymp8bmA2iqo6oKAu11yEVoc31jjZ/w0E5n1EpYMvJRryHKxb+m4KngeDOB6bU83ImGZdemVVG45f75hVT5wQmVd3zrkBHA1wKt/73vcYq9J2bgJPI78BdufjY2NeZpF5ccTajcVZcA4ezvYq/U+988Xg+seRe5D7DdbxJrQdTpKWIUVTxsaOXV+QonFjYzT/HZDYX5DLKjNrf+SgDvUn/IBib/BYAVRB4YI0g4/oGgCwMocfHr73Z0I7AaFFjKrpovAunHDZ+uzjXhWrAQ/11Q/lYP5QJB3xGeeirtlY9xOKO7Ut9xazU2Ay3ds7cDyOO5lwE3ees9+O2TZsGIUUwmAcrxHN9SSzlOZHc+ZNaVsUbozK71syOOP2QvZfyc1YwZguK2h7Ff4pjBoK88tHNf1TavqolNWUHFSgx0dEcJt7Sj0cz6yER0FzGIUdzdUWCphu+jwBsnNXBTp6qTtGDwjcjjUcHxSIIzPEGRvEGStEwFvJy6GbOTiU8LST8bWyXuWolvwKaz7uyle9pKZFvzWe+b9js/1XWdAnt5wXrOeq1TyoaS8f18XoeEzjCMbKBjw+Ns8jH9iFmuf5EUW6ydF/YhnuKHLc3ncj2e2ijrl0qeec//7VDU2oa8M7EPRmFUEPdcKcVdW5U4Z2TIds1IJmUt13KsMpF5iOriQ8igyi+JXDXp/QoTwYw5V8EidyNm89b8NH5UbunE1u2e56HPSbrdKABCvJFeDbrsZvbAdwTGOg3iZBA2ouoC5FIZyCaX6YEHSXRXCwI7TJsoNxjMmL/Gi2ne/hLtmd2SN9h4L086jvOC2/sRhXgm6bDTDjys28usK4tEp3g9AU02bbhz31OVO+A63/wMB/zt2Ob4d4ZvPJ+KsogDODXrbZTK1HFD5FuexSsntq3Fuz7Cle+J7HjlbtHpvzMlCQhhmbEJOomvuaH25hjLGF+q6SH6OmCWcJj0eHK5f2yQQD1A+dmHD23jdaShtVHTnvnD1TtyP/Wtkc11x/TsLF77Grku76c3j3hM7yx1Do7BlUtDwB3HtEpWFQps6epBBhsP8uo4mN9b2NYchu3R7svrYH/1zZuyP9vp24d19otk7dnrqzO90+e3rv+43WpIboj80z/IQN8BtgT0j5cPAUEffTwwcwA49QF0icxT8AI4N6QaYr/BRRup0fTw/bCOTx4T9AyXfbzgttQHCmevqKSvOl+2N2wDqKzwXfSVGvK28giTIz4PbNZCfLKsyJ1/7fxfiIIn1K9uRntPe+1DAe+EfAgwf073tQ+gGZbHCvHnzFzFWl27VhHx2PgqOOqO3wPVAIfKOdK5OO/LeV9EXRj7LRvisG/ACYoyfMNGX3gOtrwbfr+8HldzS40zoGK2K+51wTKWOjuLOBBarjFgnE7nhhN+gyhzMdt5sEy2JHySrmfmXZK3dl2cxg9CXrZ5h6QZg0JTjAX3TgdRCaWGe+i1IWySbbO1n1WpwNRzIEUhe18hCOrcldpW3Hye0GHvbsjD3lNG430KXg94iNQCmZ2urw5wdfsG1GZmXGEZIlWJq4Um+lnP6swR6n2cO/0jbT6YiRftFNI0t9GsHR7ZOfZEamByR62K7mja3eJoQl+bFL153G1H0bmPgyL8bqy2LJhMo3yyZgrL1duaEdIBf7g3REm6B0x0kNDilmIM5dSilLbA3xctmdGp2aV5Fx5zyyilYNS94N0dA1f9ArHoR8b1tmBNUZjN0qPVgJyVvOD35g7Q5TVyiURfSL0aJ2tukmOcGKo16N/cSP7/lXh8DlU28pjYpotZ3t0RJcOGnscNthNHGMAHPl+mYmD/K4Y7wRu0KZ781Tp+rqgPfMliexxa1YVJcXxmOf27cfmdl+6ToX+ugoHBCx/6hu+6ZA0EgTZ77fZVgdC4t4BLZoHM/UzBvNOoyMb8zCZH4NTNH77N7kszGZwYkcQ/8wt3gMM5Ld5ZkjfR05jM6gIyme/IqPhIgn+g0d8gCSOU04K/JtncMfcy78cdmNHQu3zPfBc9XTaSHGCywBf9+t1jSQsOv06d8FFiXbZQJwV1c4kDDcfPncBrBj591TrSn4fS/qpYArGEO8+fLcLbd9B0Nzv9z6fsPstUcNuTxiu/Myf34ljoaD5FYDITfusJiQzpzc/fkas2Aj0IIFi4Mtdg2Ev4jZ8YXx8K1OeMhGYfzdIuNyfzvo+U6TfT2XQRfajh/8wFna9mI43uSDjRe6RbXwEjX90CkvtuqHeOboUKdACjH1AkvD6c06U940FMWG4c/UlJHVHIg4+lnja8MN9q053WZtmJnUZLjJamJ3Tjkzhml52QSVF2+h9rthRBvep1PymsETa7CWLo4FXOMP3k6QPP/LZ0fRduNxlFnbYR5n62rOfsXOvkeHH3DHdKT23MAgrO6fEs3kSr6npClD1RIQU4cc1x7qTrEFU9Uf0CFILMBmEFO4bysXnxTNzcKnjLzws1tkBKlNSIHMS2OngRYaUjsjRprujNURrzR4qrD1Ma3PPtkePxLBYPedGwYXJEvRm8/BzaiuR8/zka/WZAV/6WqIO6+1rILjmzS/c5fUeu5dz8dxVUIvziEhB2UMtMGv4ywY7JoZrWIr565H1wdAnpBSxYGHEWcta/Z87ZdqgMhjMmAKnfZ5YpBzdyS/i18SGzmnwrlzw7gUncdF4V4KSMsPfwpk/TN26UEl6urqHX7gZCu8TxQexIQfC7EKJCeb02k6U65zRwpb78LzbBWgmXJA2fzxFle6OIVyVahScz7/S5YmleQCzMPawTgz75CtH925n/IrIPDiqeVGMoUIxVDhwmmY306eLV50Tmeyd2YGmWBJbkK0zxqqWTfbVUXDblkgxpIIqGWXUNjozo1hRvxPxMvcNocxV3Lb3KdMr4r3J/klk6Ln3zHzYBNsWLZZ10CsAjmo52+hx2Vmy+r5m0DnsscYw63WVflj3epQAliqdEPIIKn9aphUrBIoR0OGrXJnM7x1mcbDX484nivt29B7r4Iijs3ikh7kXTJ6Plbt+PWY3ArrNXRpg+iMIDOC8NiGsRiOmh10SuzkBIogtGpb31EhoVkB4beuAMtM3swWLK5r4TmAtIwbDhnNemxkXFGC49FBWd8vB6HoO75vWfaQdAEUpLBQdsBRPzfLglIkfO8xxZLVMJdw77XLXj6xuS6qVZJVhAdUk7CrXjIRzVTNlt2UPkSN41Eev2ODhe7I5/yUE1jUjwFeKx6X2QbJ+N74PUBFQrkrrtdJh0RN9EONxlw82LAftr1vvG/DG5jiBxCO3Z198WgOnmPwvnBIPWGb5gnxSWRbJoaqcGELC33BTdDPND8/OJnZQNp8HLVEkjoxVii2irZXWiWBJrNaKDUZQtGU2JqOPdANKeeAQmR+6lWRVCqjqVRHVDFGUsmiqZQjryX8jAXeyAivRtwZM7xjid1iOmINcTNoUdiBWzTT7NYyCJTTZUxFB1iGCVWz8Mh2LkPX7T8RFnjz4Y4HHgqh9PYhWec5h545O2Xs+uEHrsMYUXb/uw5frdtD6do+CbhHDqer6XR+qUUYKGVn7ILaMca3yVQ/pnBIQUjbedyzqcpvi4C7SxURc0qi5kgASmLnmDBZqllm4KrjVc9AYQRN/svuYb/3PzTOzoTorgTfeVgMvvOwJIz7pp5KeDLaZbFzqAmHJzdwGgjgsVI+lZVxHcPdArw1PrNnMHESxWw7+ZFhVlisdbb97rDniyhEPLuEsGswAG1tPdrqHNZ1p86SFxHhG7B0SVfDHuw4ehP7bw2D2F+Kws0A1+I7iTF4fGYekBhnxhOC2ZSISJS61LvPHN41daBN2VKptjcYVJjsl0Vfpev+TNMyEJHAgSNa7PW0MkadixABxSUPngvY7wrajuAuDINed0n/Qi5P1lsj60PASA5WBBYQf8+fR2vloBC3vLyO9aIJR1UBkl/eowuajQ1kCYDlaMDXBnBrNVKonoQ5yU49bhkRsEvdx9hVcH3+csdP8eqv/RETH5jLEMocOfyyBrJJIx6fZstdgklI/aafBe1Vrmxkc4JWHTYXaNkhRknYvbrFmx5l1W6KapVXQXA+fGkaMg64tpN2wTubYkFpdlI6schLmZxvPs00Mlg4Gwl3UOKEeD83sVahrmmnnc99UUsQ2FjTisX3vNjxB4i82Zy1avOPxZYcAmWCY+chSVphZGiFfMo4/alwmRQxP4TiYu2tOGU6h9XoPgC80e+DlOYPiLLNtlHpeMqRvt+Uv5/G72XXVlErjtmrxnTPM00RXQzkYUcNnzGBHp8KJ5uWtnONbrQPXPjbdnBs+AB/285N/nATH5CxwSSYl/FdFwN9Wn0BM1wy7Gs2KzPsFmOrNZm7oB7OTsJdqXGRaoczabRabj4MG4NGZC+HMv4+/x1PNfDU6GiIHKqiZZXYMXqRJ7Rn6O40v/3Z/3FmiPtqNep09jyUluPP5AVQA63PA+CqVGCmWACD10y70y/WDAzo9TeCrSG6wS2ot+DmHby8mnd23XvTb55tcX6aLZPKBpt1PCVWLIv73+703tR5xpsAn/pCvjkSd3d27y+zu4UgcZkhdDKs5bOT7R7xgnaPAclaxgt/495x0RBIhBJEpPkKX+2La4n0+hG7afw12XtBIDj8cRGpvn3nVw6KQmSYf4ou+kpcwy+Vk4WJTSRPHP4M06czfUi20qXHJh4EGz752SiIaBSLun7SiQORpXkMXSws8ZyTLbF8WNEat7lQxBx8YYOy6xv6rVLqqFjr7Le03NI7WnHpWVr04h6V5IyWfKcUGQFcOgzd9J7MirMZlqajCLNUUjFv0eXAA/nqmp9gFmMvTO5ThmceNPJCtMNy/yoY55BgKPVy7nbIrrjKa4V3X+D1wb9wufNhFjoTB/NyQ02LTtgnDRY+531gWZoT96afXInkDyuAxO7fDGHGi1dcxJzwMZ1cUIaKsPJpVwSeLJ4CorWT39gRF1e49GzQ3x1NfSeP/vidsORUG28E6fY11L8IbljGcYugVkT9lo77EzsXkb6iNO+BW477z9fdR+QlPi5Hnz92wZa0DhteV+b7WTbGktgJPL9ozfgJuVl1hsyqJXcf6997tKkamoHlvmOQGXuEnFqSBUfI4IP60ne5HGKUwgctTJhVV8bG6AZQpVVTfslNVllzVWJzKbxRPXiyPG2GhwxB6Huk1GfDfWPbj0U4pkxeo1hhGR9rFsJ2bNLXiMQu8jhyX7Jx+vL6YIcy9nlsaQz2D8k6pUG3xKahko217B5o0CUrEf6EKYWfcw5F/sRbo5lgQMcwHK4Ps4ukOkvXpgs7+bFWvObdOBZxC2cLx5tPVsEygp+rjXjsPjGfE1nMkg8KVA33fU6V5xzg3NCH+QNgaWGLDjtQ0OtNZWEL6KjmU1CUvdyGJQr0r3+nt6MLbUoDjDfTuo7RnFmA7qyccL3RPSnVsCGHH7hlQUOyZkhceqlVFUBEXGjRvNZUbzX5FLOddFI6W8kEMo5mejmgT148Okf4mfdmGAZvDUWKFGuxOrldRfvjeubIQSQyj2nbnT7W3YwqIzFW40W0+IhoayufmMG7TogZDoEuLiUGimVY42xQ9pAY381K56kEeh5Jehg38vgWD5jXPGO4ZeVMsbz0PAf+DmYe5130d+ZL6Vx2w8tLaD5YNTY0Cr+Fvu4oYT/icV15eMpv5Bj9eBhiRbeQf30c8b+YqGBfse6ZEtpQuDE9PtGHrjGHABtjm3o6AcYpSNZmwhAnN7A3LEin73rCv842MLCrHuJdxs7mry57gzLWmCCkEdriBNKKI6mCMMkQzjtbsTfYttAmpWQN+gTdaTGAt4LuHZOfYj0YzzHc2PPhefEMZs5WuYvjejwCBjL/IvHBdsZM1BaxaMt5X5w1mm7WAum6uW+XeGOvOCAss5ag++kZMrpsNESum0qTbSca5sDGvnj/wgvOosOCfvldtiOK6rsNvxeFWwnghuOhd6bjhYArSRlQD+kfl3XpENwAvqULmO06i+HIiVJgwi3NlYGVewItvDUMBnSzcgvv4847IeruesHf+06QYpl028O/g6ke7s8ywNH9EDqURLA0IMEjZhJf10SB0t/x0EPAuXbdWbviTMG2F/HhxRhaZaBhbdKgEwzIZoA7bNt3Eg/Yvx4qZ/j8uFYIiAkYcoItkeTEyI8jBRtK4kIwnUkZOpN7j4bO5Vi6Z99I0SCXK9UuopSlNkPC17iYm9E5YoPUJirGd0spfadcmBpfXjmpDF46nOr71asO9V9SSITDf2RJgXgyIZRNvoZ/hYSWoXnxKtxTB0r8GF8dftAoO886QJ1rHBtrqdd5k/Nw+JNXyV8X3ZDgi7s6TLbl6bBdT4eiFtnYnGysM0TpnrcRDWxBnU7i6BjPPIxL9RrKsRjinmVoA/XutCRY2RqH7GK8GGNY7qcmWbuZ00F2RjHG5Dz3QzRYx83laxzr2N//qee6dNgWoyIYTv+TnO0GOmU7grVTXjuEy6IAlZFyDWoJMecIUjR5o9pOOHnnTMH82DRMNDC+n9e/W27/KJfq5OudwumLXeg9/ClZy77kepWvsotB85qahFsF5X5q40TVX+bRywsWTIHZ1ZjKSwQMArdJWI4akkbYRaUsg57InWe8icmA3si0ndVtz7TKs81CYzdR5UBPQA+TAA0GIEYFYZCOzFW8HanKFbw8aK0yKW3R1bplgd2NEQwEZo6cczTGlhjpyFbuPA2sJYY3KlOLEKwpQPNpVyMQVPuU6Yt2mfaK72H6ItjW7Loq29PSyp1Wnqw4xMFue71NREaC/oIzq7ee61H6yr203KZC63IcAh9z+kSpSB5NrQs6ExwlNouCEenLTAZWNBI+V9yGLt8Zw9wLfE9a8C9PtCSqT9Facf3/NHnDjDC4DeEUPcAXQsUjxNf6LXmkMz8eERmL64A+46zik8OfYCQUifrOSQEgueKfWMPfoxJHIcJP6e3nhw94LDPS9tAFVHTxlpIT4gvb1sxm5BzD3qmK+cCHkxx7c2YKE0EInDaz5trW5UXp7rPZ5Vvc6GKeaYW+C/WpoyD4TNE75wK/YKtsalMp5c6XcdMXq/ELrnh8FD/mVlvmQafAROcQw5U94YaqFhbvTW3EPgs8S9yt8GjbQUvZTm5YKVa8LMWs5auh5+ku0fKRB4KZLTKo+riDgEXPVz8tdgVlEu2U3Ten450F00RRpToJbqZVZm4W5ZHSOJHST5XilPDrsjQ7yjU++zQJIKjLsU4Buwtucb2nhkqmT++I8YhLJBpPFSxEXkp+dD6j2kkxM9IY7gAwuMm9AZjeim7LVzsDiOuuVInfdi1MT8lRyswRAt2Yusluf9jNIRnK6M7G+S1pgivfM012bESeLj5PgzyQrQRR6W6lO3tefnw319pmCXYjmt8yepzJD0XFB9+KeacwpkC5PUKsv/HuevnGxCAFJSFLSGY4N9Z8PMwkI+HDn+X8e0gHflIMjDDxvmebjNU+D9tqGCouPOLLH+H+Y9sH51jdQrQNcYbYaJheqHJzVYnNDNb4QvNvzOmbE5652ezb/QSxnj4ZOMN9C75TDxUp2HYkI8N0cQeWN7fgc8ZaSh6GKVwmP4yjjb8DpsaJPWRpmKNU3ur1pmigDfvCehDnuWVWwvT0bBOAVQQfwpU57tMakVwgmK5SmHx+EKWkZUjz+/nXEz92ET0aFi2RZXaI7F9DHGjyeEotAZWmHmZdhu0yl9aV6+WXlczbQxC+oiMO9QUVaqtenPh53OJsxrLIxYwrXEtHPdzkYepv+XH58jJdHNvaIF/QFjovOfoUe1RXr1Wwi2V71ZLogrYkhUCTaHOj/Iy5F4GgZgi3UTxe0ox9UC3FjtfrRff97lU0aVmjho5vx55cd6B0SBP0no8O4fmroye2MMvq5VzXi8dRauDbJ1MW/EeWv3mfBZMqnC4icQRetaAonfBR1hWMoTIuR2It5KqKxspN5FqYKsxHJitVMQjl8bl9fPeJ2f6/85RgJvYFxaYiO7np1g/nZbnoLe3zHWeupq8FmusE2uTEh3rTOupG+1h1eaJULFl0ptygcfjh4YfCLPsVDynBrz/BofEh3b49/Ojgi8Ofuw671SLlcvmS3Y0Xsg4FpaAEoB+yRJ9P2Y0ZVN1Jqr+2c/g+GX8/xfNJBNwHGCJDCuUobRxtnxv3l2lH1XEMNALrewOLc5TFn+m5uP+z87GW8z/IEct+0oFdCSwJO/HQGUJEyooGdGUdhlXHSxOKVTMLphYzSYmhO/JMxDLwE55KId9gm/PJWdbqLFRZn+qkoqqO2SOEwQLY0pxUme8A1pZyUnEljbkCTMwtXgG967TZNNcxrQ5XthRWo4gV1beRdcbbgCXKASozeXV2pVI5Znf5ajkWjrcROWgSwwvl+GaDdTHLtKxutYM6jcHqaVxnNrIDndKaLtbMUU8aHqzBOb+33+ZXg/xeFky0tqrg37iI/5CFGMqdbrMYKpmnUPPwgxYLtCn8f4rxNceXA/TwMaUXueyIkA1+ootYWPvIF7CKzlqByenCTH90UljtsZYjGOc9ucaDNQ48HqH7fKknIK97UrBd+TDZFyvtMrvqmQV3c3nzbI3v0kYuIcT+vMNdPWScbRNTQ/rbd5jr2zOD6vcZsTJP6dWT/P4sS6W6L/nC0RRb0ycFXV0cxTc1bI6c8EDpmlQnowwy3TVcSdh9TluNx3+TKa4YqlakithWjZl4kvyOlirwrVwMh31Ajw3my1Yq94ma94m2Gsit5j/ISDActtT2Yq9XM7m2qMkjQ5Q5psyW624k4aogU5lVqFnoohLbQEVIJWHiLtyBEbHfyNa0xFWpLNdNnbBGWnCfF15wVuOgD5yiMP5Fm3j1Ot2ecyhVhROS15CwVCfAkPUETjmvry9D+dQPdZiJHwfksZ3kd6Np8te2fZjG2N/0gayhtW9jxIk/DQMoDHqQp9teASTVZMFoI6S1Cc4CRnUY9rzrjteLQt8JEieMiB+mEHBTibfpuxNakjtiwBJBpxfzkzHHVPeoTDEDw9hiBrCSHeb4sgn4jlNcnlIyshchQaNUJB//6BSdMuWS5yN0caNSfEwseL3KBkAJwuxnLRtgWXPr0fE1lvvb6/r6vLUcrWtmVqh/+peZjDMqpKYaFAvS1uiLPSeknBm3QlvEUryh9ecyT/N2N9e9Y0ty1je2UmUpLDNAIo1bHW1VTEdOXpVnfJu5I4BYV/Nlh5k3mG3DBOF1lnevdB2t4OfKwc/WAz9fZjRCNkM6y3adwv2mPJRXjIFpJF+j7HTZm1SS1en5Ja/X28BbBnQXJ7wXxFGIl34S5z7e5M8PnGgDs+l5/GboFpwo/b7fDeBk1sLP4v0kTKzEBhm5zjXf67J7Oexok06gTXZwON0ghkZ6I9fEE+mnPZIifuIUTuxJOQgZ5p8gM2E6adhoCuFmAAvErBvob24mTq431f60XHHM1yPI5WZfmgStCE8+iRRpC1ZGpkO8y4awAyf7OeGxTjDO4SbHdLaz+lmWSdhjOw074VEJTqHaRNRmzg6zMQmFEXwDofI1f1MZH3sr4Bozs8vTI1EjzYzPlifBjXvZkCA0a50Sg9L+vu02Mf/n9xttVvLqgEXxkk4rgy4nayBb2CqtaLHr8vxKAMc7JcpkVExcXZOFrRFfSHM5x776lSJpPZ7XpBKckO0VId+M2vpq3jdkRM3Gq0mlrpcUYyQstPGPoo8u45fqEaoSTY3a5PXqNq8fU6NSrnjOFYY0Immb1WAGnbfftvI6RejXxwVvZ6Q4DpMOpMB2ZxNWyXDXippP0Wd4e7J3mPU4sBANDqNwi2nvxJhsnA5bsHPSEVTJ1tkcx2QWYzJORTgv5a5PY4ZkrpN9uSQOvMFLQUsnRZkTkrY1fn/bGHrfNl4RjzLqDJGztYmeRNKWeaExyIcxaTLAumIhZIyayCXMXRmLmBhZrXptTNREpql408eAKg2h65lDB5dXhkHXveLfx78UM0pkWbmi64p7EUgezbteMgo7a/B/HX8nVnoVkBVgHuXSzyfM5o8mnsMHhz9j1332eTr5h4c/ofQTcqhLFjJVTTyRBfEyqcGXer4XDgdiD7zq96Afi3EabHogUpnOc2Vw1vCLrNQ6n3xaBFshlrcFVmjAYDZsBXlUGyxqSNCBEctZ4teDh65z8K94yYmMBuKCfCEbx5M8XJbmlEFRbIVTBnpUfPvOf5i6xXu8rO5beRvbK61KqJ9tA3txmqWkJIMdo0gtO4RLeoIRlXVT6VcJnDUtmYhC4WocS41vP/rMlFCITJnk+MIT+8IyKrgtrx/dX7OsHS6rWLsn+PNr2kQPDj+ELfSEpR3BPLTQPKwrQ84FpAoampbE7eRnhc+3gdg+zTEIfDlVrk5oyNZ7vlY2meqkMPNW2nl0cnhSJRlvv11Aam7NLNNJscQzvxV+tY9lbMBoujxOn0odD76UMchtmK6CKlvXtKMNmeKkrVvYzvOGUOUVW1edDpMMVb51LTscjkVNOjOA1lMDGXe54VoFp+wSndcMRtlhOFD3CDtiVuMIwduX3izorWFOSOFQKiDy7OdNeS3b+SK1M2aNOm2RALWzSAQvuhsTcPOxZD6a/m8dqqRFI35I0YifkBX7Q3FeyfEQnjpLVy/z0JOA2ejP+y4nYI1SXW6DBr9QHM+8Tvjwosm8iABJr5WxmcQcy3YvW3EXpYOdIPW7ddf8zytzHCujzSJw2sHmqC639Qm/Ko7U9iN5GowRtdVIpOXTXZwlre9CV4ykzTheuQANb9zw5ShO+oCRS1FXPgLM2HuRF5y3JaTYpuLXhKPcpaDnu1yG1SGzQqteum0++V5mtdE4sdjr0QUZOwiU1jsRfnOvr196yQxxzqizolRDYgLwbhQe0SflgbhEdxMM7t5srC6urTXsupfW5AKPVVXTOPhYiQ0jZDk+2xprePA1oefhu3gvB58/JT/pL+domWn/ZMM9ZW9znvsVUgV5NoxVWobjL0uhzjWqpI5Oot49/zX+xnZmWZzaaNcGflfkWjWHM6rKjMklhZrk93WiFEp2VzEekUBS/mgL661n2BQwjpRlk/WN+lSSYVO81NPxKoWVAAu2WOL69J9aMMwA12HX0Aqy7uMKsUjJQqrQJ9jEEuYeVnnhShEuJ5JI1jnr17CUyw8AlUekw6jWESgiWT/iORzp1uojurvwHn/xjETtPAdJcYqdRnk2jELcXUEcLsZxFFcaZpQZ2fSA4Hbvhr7fTe56aQobEyBWTpA5DxAG+jbeW9fkWLy1/k81OZPqOad0FuYOmWTufX58i6P7ocj1RkG5UEp+xss8wQ7Bwj8hX2J24fghkVmClgegYZdNviB/zHcopc8DbMIYDNh8VMgLaI5lrDEJ40qlug7LkPakyDPZOAwTy2RnV0r0Ro1GPW1RWblcTWQ0Kdh1QaXFdZWPqQfjaRL3Tpgv6d9FM7p8RfIkvXFXkuUgGUQJiA0Oe7PmpzjYYdKUJ7tlN1upbDcSG2nzE1GrZLvNy2p1gi0TVqvUQ+1S9ZD6VfaqNdsprNqdCoWVlyR+f6M3Wg7wzEY+033FT5fJFyaKR9iX5iIvg18u7vidYQo1xctmy30t6rB0USXWCMZeIXzRDJyFG0EI53reAzWtk6vNKEM419/xTWnrTsqMeN5aqyxBNFa5EqWX8La8HotEjsWgRy7UuFPglaUG50+YdXGbbGfRogDLP+h5Hb/ZmMMbnlMNizOF3x+oC7MOb/C3vtt0sWG154WmyeYQ6VYpTjRFKJ6iSBSsg3gaY3rkRkUDuVwyUROM8dYbYVSCFnLZJz6pRKJS6YA9uVAPOlUnsxCVY8lUlq8u3U6xx7nF6oKX+GfPcCOSIojhslwYwR5UWP1C8lcJ/OriKxcngZ8LD62KdE5KQgztY1OW62A/FS3q5pAyR5ZxJpFaiif7Cy+QrzmCShMWAtzHODFTXPCgqKIYvrzj4b2x+3GAcX18xCOffFQYtTbBzWzP3NMrQb9BIj3USBbunAVIp9Y2gzgB8QM+413ON30T2My04Hcxx1UzjFIg5CNn9swZlGAw3vj62pXZFjVCB5DjDVOAHqTM4Z5kjhPPX+CSXAk67A7dooBduO1QIo1Z7uJoILObcmbHZbmwK8cRN0t69eCgB0QGwiAU1hSYxdFJQP/ax7CUcmItw2TXnScxV1L6l6yVEkeXnLbYU1zWy22aiRIXl5FG7U7vwT8z+M8s/nN6r1Fer+7YJ5DYW7W0oBmRoZyFsOEoIiTuvIzEqNqMMR3Qsrh4JbsNW3PXqKBVsVHca8Y4DTxoHkGsgTcClBzgmr1S4pAQuOyFVIhchPh344bI9lWpez3fIG8WtoYyM/WHJW2HN/9ENkLZSNvqArTz+R7zcjhxSm/gCbfY672GY2/aGME2n5ss3ZeuTtbYVq4OJwmHtlCA/zCGQv9WdOWFaSbemom9OXNsKLcYbw2Zs/+C8zfDKPU5dPHeOqKWSHNXug71YMpsZbGL1xO8KoCeaij7+GZ1ApVkMdqvRG+IG41F35kKa6mYXKaQbyJUg7Azocl18kiMLGHzA6YnYtdwy0WiWg56xrXh3+55CnU2ug82bjeQi25SWSZ8tnLRCj6CEHL7NvwlXLkti6Y2kb5KyWEPmyH0G6VLk13rLjdCcVVIs0TZUYVHRX1P3kdx1Qtj8vZ6V+M3toGErA1w1qy7rVUql2XF7B2eqHlpY7YmEwxrSsm62qJU3q1AJMEr6GKSSQlUUPxUXZb2BgPmyG+W0ij6o1A72jLnMXd90Y+V3G1ffXVOyj4tQGYO/ErRMSJ7Sg78Klxy4Vegtqw22AxKiWKV4Zte8vl76xed5pU+tLX1n8jD3cyj6muftWvmrDbgsHpz/MQhWitHO2t+dbCPEbJEKiPdu+uJc/ApC5SFHp3c8IBOoF9h7IjD93hae1nvovExsqM3kkWl9y5uy8SyPbCGtDXyR/lWS7Ydss8TbAWuVWHwaBtk0GpuAZvR4GjbpfymyerYDuIlm2bczbo6ruf45Bv2uuJpdoT7LqVEYbwmSh0plUkqNcrUC0ekW/9qbFE5jjFPCmrSCtqYMKvZ3B5rxGgVsZ2lx6OJzPJNxH6Xpy+lsJWGjLL19G+IiDIsN0u7kF8pkiBpX5+LV84nlCrkaxZckNn40br8M54A9iOeTIRZmNW8UKTxL467zCHHoVA/T7nvPjn5zFFKKRREdID65JTAbTu8iwJM2SzbnH/M+8gSKZrrjbGjgoNcxAvpiGwaFhtw0Hq/G8MWMMhdpobHn4rnzqCe105BeTyYVHGcRVAUwUZLIen6Pg0YKe24lgR90a75cDCUe/6IXGg1PX0Mzk41pywPRUfzX0e+Rbrlhwm8EYtcCJdkd/wvDRklDD3ozwLnXB37VuGaLmuG756p/NbuefQ5Y7+npuoQQZ2CCtC3CMYdI68xptr16HiqchrLfgoHQHaJsdSaUXlNNvfUKlD7jLZYemMPMOgSqZhisJZ32o74OWo7jX6/YQG45qdpz6d4TURwXvGjPm6ipW0v3PKbllpHoCT6SkVxsIV7e70y3Z40TUpCpRKN+Zi0Qe/L2P6Ak1MLsz+gKYV8XeGO73RmQpYTdtlPWqfBeC+MjyC8Z8aX90TDck4XoYDDWMaKs9jBZ0UXtCc81aPFm/zwA93/L4P+8cFvD/7l4DcH/0x//xcwA8BmsIy36H0medJRGHSbuzoL2yz1dP/gSyljLrtuJC6mASQ2a5xf/yvApWbDeRvZiGwuMjV6S/dftAfMK9+YFmrPzN0vsABsaNIeDkh7UrBVO+SgBtxeGA2T3ojHv1HJiVsI+DbsD8jsfH3FeWvowyJtxIG/CdU3fGSSYSWmvMGgN2JRESzWaCUu4TTFJXTO1Ar6uTZKgB64jPYlZK0BBIcGA+ZR5C5HF++hdshEuHjl9W1g5smOwX65az3fHzRnXxyHZ6ODUzYZnneWvAGTK63B7ceJdahEYVXzOX5nIe4Ng1Ti/Ra/lwZYTLh1CyUmPqLaQV5rZRdbqRU1X2yE7yx2vrDJVtst/7RC6BfyNPII+hXdluI6i3gUmd3dHu9PmEadhQyP7AZVQ5gKe+FCKLOSjIwZ/8OMdaw4PJhD7I15eNaPXS1JjDXJjbqLybGoptA4bdnRRn8JDfDRNnWVW8TxukR8Z+4Q1fltqkRjpX3LxBQ5X+NE5PJw1mlTXi2GDadOzddC32p5V9LaHT8C/xGhqHQdyTL9Ns+O+TFz62gC6mRRdnixnWMI5TeqAeOmgHGzYcwGWkj4vGMI7GnL9TwylF0rAIM/ZWVGrMyohg5a3nQV09/WdnpbxBetWBeGQsewOKxZYdzJBdvEvUHazuh+bkIZI9occQVydjo+ury52tHh/10QQUsiNbqSkYPVRlkMCMmCQbLonoIp4gXk3lUv8xV0EMPw1GKtV70gBjlEIV9/3nUGmZSk0Z7vgUjoOX201TgzU8t5VzFB+BTG0OzOOTdAnuyAvAtSqtML4IDQHLAB4n1gY33nJow8gJOa53pJnNXFa83VK+tN13VbLZfHc6Vo0bDJkqDLXLO9bncKg70nOlSMAR77vQDPHFYr3fZSlJX7KH3j2pLiBANLikDlzkaUbkMPIjK7pX4BqBR1VsjJ/j0/Hone4b3C/gAFJOY3LmYkoTvWrBtR6OtgOxFGu0XHDKL9MJ9MnXofjnzMeNhBTQFiRQBA7gVJgGMaRElAkvIfhDDm3MgxU0g5xLghaDbf8WPGys7Vbj0vSenyodFDhqz/sX8viIYJUz9cDBGBuuQJoBSlcHg+lVkbDqBSkvhds4NgdZwC49WGBCkABoF2+sOU6GrCcJgj2yCOukPMbgz0FyuYbyBMDbhj2NLVy2K3DNCZiUBRizgvuKVVNZK4QeGZ4G7CeLehEO1ylNJgn2McZ+h6ts/5xkb6BMD6tKmzoP9d1zgJpOwSXh2Jo66Bl7Atn2uJpu4jHUjuY/p0GpAJaCKWJ2HrhVc3AEVfwMkgRSzda8NUBn/t+0wp1oGRQxM9PtVGqPx+5Qa6lWDnwq7gmPmdEZjZDJmYUyNyrXTNQ481zbaaGe/0HYCGA6XM2OHACxDMsQYMyM2cWu1xYAX9I78Z8XBuwTmbPdUP/Dp+JoHSE90eq7tM6NKr5VJWTKy9Pe6/pfflI9AlDXPjKF7EVsuFKsXZy+zZXfx1W0V27Bnu3dcfmEx6VYhlnbTnjcjctVCVTepn+nXOmWW/TKhWr6dHUk4fQVE9DhJVj+I4kakOQpUjlRGxEjKNVGBVvZHK2CWBnbS7e2Pn2qiw7ZWPQu69v1M30UeZDpKfMzVi+Ol0fgwC7ewaDxPjUVZuTd8riwExkStTg5keKcUYMwx+iq5F5Gj0hMcuecjjCVH+VObtdJade1NBEvU8zEZM5sFv0OcUPVbNoS2a0vpxjSMIaWRcxOYe8STN3FD6jRwrA2W4rHZmrC0qrLMyJyzeSeXKuRpSbVvhvSsZdUlpy+yD65VJh81nL+KgAkFS2srv1YTaktJWKcQ1t9jxjGLp8taKJMbJ2UKc3Njq7+A1DGBmQRLrGTNfMfZWB42snyHFSADybw9J/0i94es6ix3EYJAKsS8hZxtFNYoJ7tqmnZeyznu9VCW5d7cMTVoD5YN1EdRSlaugmBEL7CcjLdJ3nQkWiR+reF8rzSkkPTmehCfWiNvjZz0ZP+NJ+VD5LvF3yOir7NicZIVR6ONIzfvulNN4AfV1+oYrmxHeoIarxRYtWCaaLKDX/NgnxFEuhipxEsn1Jj9deKCmn2LS1jlhaNid3nN2Z/bmkZCwrPa7s3sv7J6GN9ybYvcM/FanZfdFeCVWfWH3rOmqaZLfLDVzcm1ppdvyKmQPrVpX9OTbu7RbEU3ZPe1xAv3zajXV0OS5RI5LHDrUey2678dZyWZ55/V4GMxBglFvvyvGRDcsxsqRLOB1BKjjCbGxSEfJOd6T86jZHLDkfibllPgmjFnna4S/FPhiu/dRRmTpUy0qa/F3EwmX5ksv7Cu0+OLz8epARZU1FlY+G7yY1fas9rE1X5F9T261JNMKK1b0FbFZnRkGkuOFEn4iIw1aN1vzx5zmuMquvUW5nux2bYvBpGjAIkDXJrRilZhVlJZuHmtLNtsZM75Q/FXD1xE3qlUsvmSx6UUdr3cDU0SzFy3VGMaac9nt1ZXr87XA3bSCG40JDhEDOzfNLjjdNKsYM0xkbd24uR7RfVk2tjbvVNtBIwhBzH/ebFX3AZH/BsfSG85fOLMvumfq1brJa92srKVTMTaUyahYPW1HIdefap3Nd32F+5Y2bnHi3sgsgWa49fPz1Gjs5gSNSWbPeo110RDKxzaVj7Ne3ZGoe1Oqe3O+coUuY2S0tbfitAnN/wX24RQCg1+jFqrEp93p2ValVstO7BUSW1z7+WPUbJn1NUe425GpbsmDkVkL2M8srTljPdTMcVSkTKvLOaSmWpvu1VLd1hiu+vqg9zSKfLy570TPLZntzBeSMuSoTlSfH3erjP9F3yvYeIu9nvYpqcUW24EW/YpNxZoVfLDX7dIsGFk26SNLG16PEQ4Q0xh2ce1BSUZDliMY1hR/wIqenqWf9c1XlaxNfEReo5KjOWoD47OHOuujuJ3UOY4kxxXBhijakXGZmpEN0NjszA7nZUbljAxrJONjdoCx4yzLDv87KiHNmkO1YeMAWVpjAjUif6Cmar7Rx+y1gx3Os7Sdm+zFiL8w+jFPRvzN0pNyHWSGroMoO04jhrCZsr3cVEow0tcqlSwL5Nl6MUXpiYkqKx0pkuCW9T5olXs3xx7G4Zi17+jg0cozExuxlcpkyCpYUmkG9PtGpa21RbdYoCXUARQbE1oomL57LHNvlkdv2v2e9F+jSjuJsbr6/YapuyJbo7dJ2iq1z9gxhlZialhxPjWkVyxoPsX9MXppbfCyl6R+TBGOLU2K131xxriszrxooS/rMJEhFb3rs8gYJZ2yZtaksAIYqzRINbeqsZNpNq4nfuxKIZUZ7Ear1nU1e0cURFrp2voFlD5BjWEUp+ivtsaoGPYJ5nP2zKy6n6KNv0O9FveoYQO55t3Ppn5N/tBU4bWdaYMto6DJ0kBX4Sy76shaB2rM29OarvCZrVoJCT5iTBcIeWFsjWK94oCV3WttTt7RPHoaW0NDgDQJPfLseL6Hxt1Oz0sS52I3SCN0rekD5uOfEyoOCIRCixdZtvhR5twFMhtIPgSFgritL0Q7zt2EAsCXlLyCNwqCzvXBcnQ/dO52d8YoO6pfdmMMuBtjwE3HgJuOAXeAvnB1Jjj2wyFe+yqWXQ8AIrTKw1fQoyT9DODwAHqQ40BTrC4tro0msKXH4F8qCtDNLWYkktHd+fadX2FUkGcsCUUeKerwA2am1cxsbwRditB2ZlZjz171g61thH72R3pK+SAM+sP+Gnr+MnkFfzZPvwSM3tlpfZtRWMZV7nSL6Z9g5Mo72IK4WdY6sa+nVsSyF6K4C1/TUc/ntaU3LrSMXhLrcBQwtyOt8e3o/kq47iVvbnix2cv0UhQKsQt/Nhtr/laE93uBZPzokjaY9WhwOUrSHJL61dvAq4AxHEuptyFuq0pvd51lTMuxQH/YAABiO5/rMz+a1lkyqE7hrpDqwO8cKHHKjYP/yiPI6HodUXXLj0w1C7lPbPU72z6mxS5C0Ix7hej0MAkuL82u4fNBAINa/MZ6afwkOtAqTnjPf80bgYSw6oV+jyaJYoLi06wuLdNXly8Gg3xhmKZ03+LXFKUpc3ChiJ3f/uSfAQmaSdtvLZy/NgybTfjL9qO7PGRubWRzbk7NtFqt9nR7+sgtflyzRWpwZqwGP5HiEeVhScsGiVfglfHNHENzH1c3xwc3TmsfY0ZoaO3rLNoqNPqhFGDp8IG1XXbnn1pmw5w1NowcXtQb9sO1gRc22btX8B31B004gqQ1EUQBSnZ0iH3EjxRGFRZymnApQGnjshdvBeECxQ+mfm41X2y1yfEloasMyP4sYPRZxB8K57BPkcW+IIep9/OEzlKQqYZOXgxzmvUTZuL0BAv+jB06MmJbp/4ab4omP2uYpBSGA6YOwLZXu0C90onDpV50X6YNqPllvzi1174biPOFCIbWl+jzzCyccViR5XvhJ5r8jAQdOYq2WDQRApov4QwwyNoSZB0zzSuczz6FGH548CVuIpFA7FOK1PH08AFZa0vmd+AFzJMbndDb7NxqFfJh1OgDA0XNYYrKGi1SW23yfi+2aFzIrBuVlB5Oi/w4Uj8ZFpLtKLZ7eVQW5wwpgcTTj8ZYsM0oZkqShen54NyZeVKEQIdcTh6wyURSR2Uvm8gorY9A7Fj14w6wPe3ZF/V5uUtmF+BOm1MvTk+38X8g8sh8G16ra0g9kGaTVMneht/bxf200PjvX91oO7A1nzbai8M0ws4s4OLssZOrCAD6YjhjarRz09LOrK2dUft0oR2GfE60uZn4LGiHtCEocZqIfMcyxr13sA+EDjOtYqwaOA0eQYnPrIh6EV0GrxLwplAfwYDd11Fv087fjNib4pbRR8E6yk5J+qoeGPzzGfMovZ0F+SzjxPMZ0G4c241G2zyIxV6wBVV2Gti9DNaoDNbNClijRvVQvR12ShqGCZ9mTWvsjWD1LVVGdFaq22BjZ4GwfXYaUJ3+oW2wMTK+Ts2lU1Pp8ZD54BdAer84eIhrUNg1p43YvLHDDq4xgN80bBULcNwqp8cexX8gb8QwqTCKM8aGUhzFmVqjEMBNo7AAx1FYtsJGZ6GUSUbPcoyhijP32IbMmB6K1P/rsRcm6MHHDsBsX28UdvrGSH+TFsqkNmog+t5fqGCAJ+09O0yfV/cLK7TRAcR40bhd4ZNxh2/0YbktVfqGHU4qF9qfM3SenZmuhWz/iTk4BVP7+OAr65F21oh51Cpg9lnzAvZ9LxnGfr6K/8ICrJKETMfMT7F9eeFWEeJlVq8pkeFukKQ5nN8B9r5LzNtjWVCRAS0HqCXeGKY+gWxWLhLvLEy7cazYAdhmlpGG+YkDMqAzw6ex+rCcQpbAgv+DHCgDyAS+aqAlMMOR1NFfjtHR6TbJreaOykB/MRbQmerdE+L5+EPTmgyQqhq/hHhAmusgsfyheRx06z5ZUHkjvHHDDhZGcjDa3z5g3ufs7gwpA0FAFhIzD01sG/1SfrG/WT101iEY/ktGSsA/nymCKQoDflQl05FiKKkv0DE54GgC3BkQwt+IvQH2Fe9pLRBlLsjV1LMSiU7WnXHKIuIr2jUVMJIUhA+DNGVoLqOceN1MJo6oW9gRKtyFXIH7IrJHbYfR2TUA2fcd1iIGg/wZxR2h8xgpGfLZlIv568MHQIofHjyZc4jj/gLEf7wg9nMWGhKxD8s/FGElP4UxfuEQHcyLfQaHIrsa8ETCzMOPWJuKyCta/if+yLXbbqNgpxdqQw1BaaoKpxEznNRUzQx7aYDpofh0XvO97tWwN+KPax1orHfBi5OF/Kf7uh/T5fi2c8HrvAlbIooX2EVX+p3we7Ni/mWdPk4P3aN75Dqk6fpUoA3X+hz+I8uVTYHkM0SiIJ4Ux5PF6oS5xsX5klX7igUFhRqfHz6gScd49G5BQ8RnxhUOM1LHWLbhhrm8qqjSzRSJqSrbt+yTrKqR93NhMfjGVBRlLxVkdgmoxhCwLzo+KGWkyhqKKcVQcW2zFEcpu/6AIdRjjL7AglbxtEVkyu7SAxrDbTE+Np1mVggvj6m2pixXUlWqb6WWuwaPpgvZWrE8w1JFSaPvmep1sgHsbQYwH/ZYU3c1RFvQUo+qNqXfdHt2Md5KHL9sIn0Xy/uwdRM8BBYc6RETmMUcHDo3QFkv7Pg92t/zzqtIwVvz0iWNwuDU3vmWoTGLoHAf4Lm766TzwgGshPeiN6HDbw3h6OpWLTq5ALMqzeZlP92OuuwpbnX9nr+FBsxdqRes+Xmj75PpRvuekQZwA6WUbqzakQKPvEvDsJPdHWKhVsoTiWkNsirNgiMUuZaoN86LlRvf/vp3FF/rUhz4Ybc3amJamRoh6EwsvL3XFQvG0SDzCxUcgNZAJtqRXMOlO8MWVYeo+2DJeMW96chGm2C8IuCQP0I1mi3NiiW5CgEQuRx4QhKYc6IRzVYZ9jzfVSrvV8mG+yOgttouK9BdZF3o965DYSXvUTh5YOwKh7ra3HoAjPKpBUeQgooxsTZS3qru8TDB8SCmOFVmFt3K5EnjT3KuvyN401s2mEids6qms7OFLKm5sUo2F8UsWxC5su+yYEjQ8vg7btxdV+LHf+TdZ3AuLewEzNfZqnUgqCqWo9JUdhxlK87hcoJtiErrd4I+bCRYhMTvmhF3mZVx1+PRKhZj52cbDTYb3FclcUHO9NJyHzpxUQtbarUcmapDh+lyzOUg5Fosl4txbf7B28k+MBeddgap8kRofPubXzqSsgt1AtyUQgovFuGfzRy6pqK6RM9C8B1Rcb6KWQ1zAJldSyS7zjCGzTbPwlBgwGNYA5BLsgInF/h1UihX/Gq+UDLMIpCUYnPBUincVCydLpQfLJgMnruaWIQuRcxivTA7O92WrJ4Ls21h8lw40zYJTjPTLW3XDiawar44jWrQiWua5nigO1rKE8t1YVyhJ24U0t19kgZe9QBR4GDZRgwUmnoaN3tgqmWqYBIx+WSefqlt9snQXDIQzt68swECBhyrpxa2M+/njfmqzpNy6EgDIIe+hdOnp8u7feao3Vb9J1GLL+hkPwjbGdHsezv5Q+Y5zwFjhxQ4u5xwLSAMTt0WEARRwAVGVDmtXcWkxQmg9ErYiX0MfLgw7b542bSCe/OZd+7eif8HMrizAiCHAQA=")))

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

            clsid = "{6BC8DE0D-79B4-4E0D-9E0A-C6E6A7E0F318}"
            progid = "EnergoLogic.VisioEditorAddinV318"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV318, Version=0.3.18.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.17 -> v3.18",
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
            progid = "EnergoLogic.VisioEditorAddinV318"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV318")
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
                "progid": "EnergoLogic.VisioEditorAddinV318",
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
            progid = "EnergoLogic.VisioEditorAddinV318"
            clsid = "{6BC8DE0D-79B4-4E0D-9E0A-C6E6A7E0F318}"
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

