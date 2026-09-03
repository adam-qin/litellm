"""FastAPI compatibility for management/v1 unknown-query rejection."""

from typing import Annotated

from fastapi import FastAPI, Header, Path, Query, Request

from litellm.proxy.management_endpoints.management_v1.common import (
    _declared_query_params,
)


def test_declared_query_params_ignore_path_and_header_names():
    """On FastAPI >= 0.141, get_flat_params mixes Query/Path/Header fields.

    reject_unknown_query_params must only allow declared Query names; otherwise
    a path param such as item_id would silently authorize a query key of the
    same name.
    """
    app = FastAPI()

    @app.get("/items/{item_id}")
    async def read_item(
        request: Request,
        item_id: Annotated[int, Path()],
        q: Annotated[str | None, Query()] = None,
        x_token: Annotated[str | None, Header()] = None,
    ):
        return {"ok": True}

    route = app.routes[-1]
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/items/1",
            "headers": [],
            "query_string": b"q=1",
            "route": route,
        }
    )

    declared = _declared_query_params(request)
    assert declared == frozenset({"q"})
    assert "item_id" not in declared
    assert "x-token" not in declared
