from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.119"
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

            build_dir = workspace / "energologic_visio_editor_addin_v321"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV321.dll"
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

            clsid = "{9D1B5AC1-0C47-4C18-BB03-7ED263E8F321}"
            progid = "EnergoLogic.VisioEditorAddinV321"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV321, Version=0.3.21.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.20 -> v3.21",
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
            progid = "EnergoLogic.VisioEditorAddinV321"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV321")
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
                "progid": "EnergoLogic.VisioEditorAddinV321",
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
            progid = "EnergoLogic.VisioEditorAddinV321"
            clsid = "{9D1B5AC1-0C47-4C18-BB03-7ED263E8F321}"
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

