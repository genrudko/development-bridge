from __future__ import annotations

import base64
import uuid
from pathlib import Path

from mcp import types

MANAGED_EXTENSION_VERSION = "2026.10.04.145"
CONSOLE_SOURCE_B64 = "__CONSOLE_SOURCE_B64__"
TOPOLOGY_HELPER_SOURCE_B64 = "H4sIAAAAAAAC/71a7XPaOBP/zl+h+sPFnlDnpXfP3JQmN2mS9phpm0wgvXZ6+SBsAXoqLGrJCVyO//1ZyRbYxjImpA8fGLBXu6t9+e1q7UTQaIR6cyHJpNNKcv/8c84YCSTlkfDfk4jENChRvGd8gBn9Byui0r3uVenCTRJJOiF+N5Ik5tMeie9pQESJqk9msnxpHBMcwoVOqxXhCRFTHBB0CQqN+Ac+okGfTznjo/kNEZLHpPXYQvChSk6EGRIEMxKigGEh0GU4Ivp2SqQ+02TAaKDoUY8ncUC6Yad8U8hYaXQZhVMOhJ2qxX0cj4isWKxu3vCH9PqiVdJOgvWCTLvrmI9iPCkrGNN7LIkhzXS5IAEPiZv9u8csId5yyWqx+sREJnEE2sMKIPZv++9+B5fKnl7rnvPonsTSfxfzyVssyH9+zW6kTL3VhjLlK5QacM7QOx5PEoZvyJDEJALnpiZxC8pkCg9T2nbhXjgHBwM3qdcV7ykrxvyhXcUMz6iwbT5vIHRi5KI//kCO06miBCEqCoEWfvl9bqyUMLAi6UZDDjF8j2OKI5ld9KoYfbtDIhkO6YwI4BWRB7hQVE19nBdg/sjkmYP2l/L3kaP/q821G6xTdKvlhQWLon4fqJBvUiVPITiGmX6F625pT4rMPwtD1+mNCZFaogmcPoekfnXspm7zuxdtVGuthkYtaSDjeeH/ui0zByqQgB2ttMuEZep9gtsbFKyKDh2DQ+S+SLn5XfEpYewq/mtMJekpTHKVYM9bmUr/L3JZFP4FWAZj9Fi6utVGbzfs9PbnbfW2vNfbhpstXIaEJBhuGCRLdQcMgYzX7L0NxigzSJNOrTbp562tWeeSM2tIY8grsOtKlf2MV6du3Y+ESyg0J8jZU9mRX51eqeOh7K0xClwUktnV0E3VaKPUCed8MgXPCR75VzGgOGbdUQQ7PwfA9tDpCTpE//5byVl9ipxTRZtz9qx8s8oi44Ssb2tREwzZwiFmgjSuL13xHrZxzmNlGNcUiykeQT6rwo4IfNnqwOasMgyF7gLAj4qz3xvjKRF+F1oRVSC7F66S4ptWwetY+aQBsIGP6Roq+GRhNfuU4pkmNx0IOoEwG5ARjRwECfxW/frioNfIAYovjpXZvCmzr4bZVzuzWVbwqyAoNaJ/ThgTt67eg+dn9E/FJLOHxmLnTxK7JvfgAJ2pFKIhOnp5gVQQokkiJBrQKERvr/p/ooBznTsSir3kSI4hcpWlg2WRruKqre+j/hgqd0gYHZAYOLA5pMd/YZVAn/sXewKNMRu+1FJVNhD0MIb+Cn1BVFQxjZKJ6tXRIJHoK6ygjCk1JKYRdJhnN+71p77r+77n+S1LPtsaOePwtunQ0jiC5raNnC+Oh375xQYVNpbzOpZfnUYVpQAmORo7nNxz8KWy6FkUfgZrDefbwslzgMVzAIUpelqCCvud0aJQh3McnXzD+UXVM+OppzXJhUwt6u/5yjd9bhqZjKioUrk/1B1LsUSkvtRuXK9hcgytsu57laaQ3FdTlX6wvctZQKbqh1sZzVlXpAIXS9daG+ts0bauci5n2ckwNcHywHKvwpQGWkEIdQpn2tcm+h4PF+jxaNExkfR4vDh4fLVw7GIKYbmBzETRBjIToBvIIF4qCdYd1OjgqaL7I0Cbuzx0gRqbDoMxEeCHayzHENeK3v9AohH8O0VHkCDqyrejO5UfzrZnEBWFeY4vTtBxdf/UJP6cWwEh/Do/7fBL444/CYN1PpkR9GbKcHSK3qTbO1XgaauhijK3/2+Hd9ZyG/IAKkokDQzYC7NKtxoqfbxUwHqqI6Fw6tSX3SqFy+19jB9Ub/8OEsC/ITg8Y+wDjYhwzZbaxUGH17T7V56zH3hALBx3VB2lUVWzWzj3Qz8t1fZgkd+bMirdvb/lnmfv/PUCEzIA1sdQSVMu4BmN3hdX5469Dy/5KJsNpQyO7iyCCZTLhtKvz95f1ojPOX5H0b+tib68sIp+rEWa7FwKEaaLuZ1YY3oGhbADPcvwr3EsVtvY0Dm2a3mvqnC2s+O7+gUGSSuVebWbMgC/lWx/3cTWynVh8fGi4kDY2i7p8mHtwfkW2UlNCHo7gK1BVo2O0F2jCRUiD4EHSgqiIfykcu7UnP3wdApm/ggGhuZdzVrPoHG6J1cD1de7zmcqKPfPpoANaUWv42WkK7yEbXeqIBK5KsCoOuAD2VEn+/nmRN/wQB3/ImMj/HOeRDIj2d9vio9GnQBHIQ1VCT5BRb6qZXU11xqoy1x4+SOBdt1dO8AtuTeZ07ULwNdooLEtkuSMv1StY6UeQK363jwdquyzEpi6e4d4hmsR0qG22kbEJcRLEkHzqFr4QoZVVN/8qWiH+DNiAHIUMD9fAJYYb4zADSPiraLPNqZoMqEtCrrdQdJ6TkVadQOIzcZ8NbPDdea3W3LfNueyYPv/5FsqbOdcS9NMMyul2LIyVaSXfqhFppjGenB82KmkSI9+miJtbNL8qaQNGMHRjZIu7AzjmvvQ4gqZKfYjUYqdF1j+XrdkgmdLwuNa5lBp2UfKGBXQMGYLfjus7v+Ru1QYkCX7DdCylGYuNseSvOHV+E3zSQ1SSb88hSwHQ+oQor2xbXSXz5DNVj1lwtGcs/oUx2E5xp2NS40l9/eb0y6tvmnRorX9nXQy6C7zU2/kMo557D3R9k+eFtknR08bENmHRZlpdx8O2QdFpYFQafCzHPB4m3mvHNLZ0r+L6gw9OEBp6OrhewD1iBFoEchsCnkC2ClNc4+HYDOEGcvsJVQmy3HFMD1jq7HFNxPsl9rGhWlcblq/mtX7PxtHdkGDnxDNjaLpOUN+6dCKyWjm5NTBPyUTmi/ZPD59wii18Vi1fsRqGbc2SDcVfRUFtPZpca43sYG+Ggw1WV9TqpVmecrTk6pOxtvUU9rQoA/oMtYzVxQnkUA8kYgP0TTmARECPYwh/jQE4TB8CbkdANIMcPAdkMGKMJipV9zm2YMsAmDTY4RM1QlCP+oDte+JSI9yewLddg8U1ExAHh4RG1PG+RQNY0LUA0mjXkgYnkN+xOQhpuph5YAoSNIKR+qto2BMgu/V2JW+iOdr1dxy/+Z1mo578r5509w1O0FWBWrA0UJ36kLiAWX0H/I6ja8T6NmbRGDDh141zJwD/brXugGegbXpiE/SN8q24NqyYMPadT2B/0tF0Rlj6pWzavOvnrVUo5lzfdbr/S1tVjcY09gmyLEzMwepZ2EWb+erOlbbh1W1LQsPPloNAD57cn64+Sl7vpeebXolq+qIY3/oUvOa2Sp4ahqa9UDMxRyk/s3N1Y22PWi+Mq9Xfk7UaTAwqH5hL2fJI5slF9nbv4vW/wDkuOPZcy0AAA=="


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

            build_dir = workspace / "energologic_visio_editor_addin_v345"
            build_dir.mkdir(parents=True, exist_ok=True)
            source_path = build_dir / "EnergoLogicVisioEditorAddin.cs"
            dll_path = build_dir / "EnergoLogic.VisioEditorAddinV345.dll"
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

            clsid = "{0E77C5C8-611C-4B8F-AD4E-AD1F1E8CF345}"
            progid = "EnergoLogic.VisioEditorAddinV345"
            class_name = "EnergoLogicVisioEditor.Connect"
            assembly_name = "EnergoLogic.VisioEditorAddinV345, Version=0.3.45.0, Culture=neutral, PublicKeyToken=null"
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
                "ui": "native RibbonX + drawing context menu + modeless WinForms parameter panel",
                "tabs": ["Ячейки", "Геометрия", "Проверка"],
                "removed_legacy_versions": removed_legacy,
                "migration": "v3.1-v3.44 -> v3.45",
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
            progid = "EnergoLogic.VisioEditorAddinV345"
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
            addin = addins.Item("EnergoLogic.VisioEditorAddinV345")
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
                "progid": "EnergoLogic.VisioEditorAddinV345",
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
            progid = "EnergoLogic.VisioEditorAddinV345"
            clsid = "{0E77C5C8-611C-4B8F-AD4E-AD1F1E8CF345}"
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

