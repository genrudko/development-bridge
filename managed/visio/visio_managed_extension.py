from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.121"
CONSOLE_SOURCE_B64 = "__CONSOLE_SOURCE_B64__"
TOPOLOGY_HELPER_SOURCE_B64 = "H4sIAAAAAAAC/71YW2/bNhR+969g9dBKiKE2STcMVS5IHSczkNaBnawB0jwwEuNwk0mVpBJnrv/7DinKtmRJduZhejAs8vDc+J3Dj0olZSM0fJGKjINWuvTmd3gck1BRzqR/ThgRNCxJnMf8Hsf0b6yFSnO9fmlgkDJFx8TvMUUET4ZEPNGQyJLUFZmooNVieExkgkOCumB4xC/4iIZXPOExH70MiFRckNa0heChWh/DMZIExyRCYYylRN1oRMx0JqSfJL2Paajl0ZCnIiS9KChPSiW0M10WJRwEg6rFV1iMiKpYrCcH/Dkbn7VK3inIUmi9uxR8JPC47KCgT1iRXNT6ckpCHhHXvj3hOCXefMlisX4EUalg4D2sAGH/+ursN9g6NTRr3Q5nT0Qo/0zw8Wcsya8f7USm1FsEZJ2vcErH+AVTZv25vUOQDVnnkHVaEJnG6hKrR3Ro5P0LwkbwdoR20bEZud29Q5+Q4wSF9Uq8FN6L2k1+H5C7rPHNIdrzVqSMrkfBnxEjz6jHIGAa9RMiDHK7k5Ak+o/rXEs8Ip+WQeeXUPc7iWGdTyYEHSQxZkfoIAvvyIEErli2GdCSS/HffrgL6kQjHqZjwtRXKAEQL6dkWSn42iB1QaU60HVwhAj8ShDT0S+G3SqHHyBGHD6iHHACP8OmozMaE39AcHQSxxeUEenmIbWLePNWsz+t3A+9cxn+/J78msZxX3x7pIoMddm7YNbzUMihZ7CUBJUa5hBMsFA6PFjkD5OYKvfdd/XOC2rtmgU5ZA4BMujt20wL7IwecE77HacaR/op7ZEt0UzB7l2NYRJLsqH1y5PzboP5pY3f0vQvK6a7p7Wmp7UOGXz5J1HkaoRpcDUI6ydvwBABnAf7e/4lFnIRRht1oKJSQXrsgfu6XgXFTNlBr92oO2/eoDvTt3fXvCBv6JXO7G/nDJwHlWo/rlNbq3VWs8ez1upI63VFtwxrD/38iepFcwh6WzTbvLOa7oioRGMq5XILfK+tIBrBX6penIrAoxdgCnAs4SSBNH+BBD/iWB95J0Bcnkj//k9gMK7zB5WU+ycJ9IbQeNGkK7eu+yWEHVS1SORqgFEWkQmI7Qb278GhmfDAHf/UqpFApID6WJGdnU37Y+5OiFlEI30EH6Ki3h4QJtdobWh1dgu7P1IcyzkFuOL26J9r9/VuroN6ofG1LTw6fAyYppIzvy/gHMBxb8TgFOkAxfBe20mWkj93LaiVvoez6q/Ny6EqPwuD2XZvgWcYY8hAbREG4wrwkrIIyA3aKeSv6vTNN90A/9/jLzcDLUc35v8OgCXFaxFoSQTLDqvt0IeOjyt5TsnO9XpD11tYWq0pZlzPG+JGVQG9tRbTq8qvX6n9tTVnwfb/1FtmbOtay8rMKCuV2PxkaiK3hqJo1qK5rWEvm1ZF+UqyQUuzdSQN5zGsZET84SNObAXp+1jv1NVu+Dkx8oK1+pShLWv05dymQZ+tncy9DoljSy3N+gWZAm54T0aUOXBjcz7rfzeOvrKBxI2zVnvm7JJ2B2qU5Z8XbvTGGXvAlxZV21ikDSZNJL42Jq/dYlyefw533SvuZg7lQkX3vI0pln6AURhI5eA0gXSF4OK1hbgJ8ptpddY7zrgYY9WYvmbWqh+nO7GfLrKMoQcMd0AoMovj6YcZmu7OghyH073Z++n+zFmvuQD0dhFn9jWHbXuOijU8e5HzLdixueR+E0By4Zarv0S5iy8XbX0rGw6/qxyq9ljdEK3lW/Kql/bjzYfiTNHvVahNvDUfSKr6Vf2F/E3DjXyeCq/+crImg93BoD+wKZwsMrdBdlb3L8vFtGLGZnK3LpMz+4Fu1voH7OGKCv4UAAA="


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

            build_dir = workspace / "energologic_visio_editor_addin_v323"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV323.dll"
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

            clsid = "{3C74BB1A-284A-414B-BAE0-5D413682F323}"
            progid = "EnergoLogic.VisioEditorAddinV323"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV323, Version=0.3.23.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.22 -> v3.23",
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
            progid = "EnergoLogic.VisioEditorAddinV323"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV323")
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
                "progid": "EnergoLogic.VisioEditorAddinV323",
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
            progid = "EnergoLogic.VisioEditorAddinV323"
            clsid = "{3C74BB1A-284A-414B-BAE0-5D413682F323}"
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

