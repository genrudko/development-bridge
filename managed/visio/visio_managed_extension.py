from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.120"
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

            build_dir = workspace / "energologic_visio_editor_addin_v322"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV322.dll"
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

            clsid = "{D65447E9-8176-4EBB-8CC4-4DAA1C3AF322}"
            progid = "EnergoLogic.VisioEditorAddinV322"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV322, Version=0.3.22.0, Culture=neutral, PublicKeyToken=null"
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
                "migration": "v3.1-v3.21 -> v3.22",
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
            progid = "EnergoLogic.VisioEditorAddinV322"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV322")
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
                "progid": "EnergoLogic.VisioEditorAddinV322",
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
            progid = "EnergoLogic.VisioEditorAddinV322"
            clsid = "{D65447E9-8176-4EBB-8CC4-4DAA1C3AF322}"
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

