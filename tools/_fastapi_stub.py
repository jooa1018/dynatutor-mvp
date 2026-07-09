"""Minimal fastapi + starlette stand-in for offline handler-level testing.

Implements only what DynaTutor's app layer touches:
  fastapi: FastAPI, APIRouter, HTTPException, Query, middleware.cors.CORSMiddleware
  fastapi.testclient: TestClient (sync, in-process)
  starlette: middleware.base.BaseHTTPMiddleware, requests.Request, responses.JSONResponse

Fidelity notes (honest limits):
  - No real ASGI, no validation errors (422), no OpenAPI, no dependency injection.
  - Body binding: first parameter annotated with a (stub) pydantic BaseModel gets the
    JSON body; path params cast by annotation; Query defaults honored.
  - Passing tests here validates HANDLER + middleware dispatch logic, not FastAPI itself.
"""
from __future__ import annotations

import asyncio
import inspect
import json as _json
import re
import types
import urllib.parse
from dataclasses import is_dataclass, asdict


# --------------------------------------------------------------- starlette
class _Headers:
    def __init__(self, raw: dict | None):
        self._d = { (k or "").lower(): v for k, v in (raw or {}).items() }

    def get(self, key: str, default: str = "") -> str:
        return self._d.get(key.lower(), default)


class _URL:
    def __init__(self, path: str):
        self.path = path


class Request:
    def __init__(self, method: str, path: str, query: dict, headers: dict | None, body: object):
        self.method = method
        self.url = _URL(path)
        self.query_params = types.SimpleNamespace(get=lambda k, d="": query.get(k, d))
        self.headers = _Headers(headers)
        self._body = body


class JSONResponse:
    def __init__(self, content=None, status_code: int = 200, **kw):
        # starlette signature: JSONResponse(content, status_code=...) — also allow kw order used in app
        if "content" in kw:
            content = kw["content"]
        self.status_code = kw.get("status_code", status_code)
        self._content = content

    def json(self):
        return self._content


class BaseHTTPMiddleware:
    def __init__(self, app=None, **kw):
        self.app = app

    async def dispatch(self, request, call_next):  # pragma: no cover - overridden
        return await call_next(request)


def install_starlette_stub(sys_modules: dict) -> None:
    st = types.ModuleType("starlette")
    mid = types.ModuleType("starlette.middleware")
    mid_base = types.ModuleType("starlette.middleware.base")
    reqs = types.ModuleType("starlette.requests")
    resps = types.ModuleType("starlette.responses")
    mid_base.BaseHTTPMiddleware = BaseHTTPMiddleware
    reqs.Request = Request
    resps.JSONResponse = JSONResponse
    st.middleware = mid
    mid.base = mid_base
    sys_modules["starlette"] = st
    sys_modules["starlette.middleware"] = mid
    sys_modules["starlette.middleware.base"] = mid_base
    sys_modules["starlette.requests"] = reqs
    sys_modules["starlette.responses"] = resps


# --------------------------------------------------------------- fastapi
class HTTPException(Exception):
    def __init__(self, status_code: int, detail=None):
        self.status_code = status_code
        self.detail = detail


class _QueryDefault:
    def __init__(self, default, **kw):
        self.default = default


def Query(default=..., **kw):
    return _QueryDefault(default, **kw)


class APIRouter:
    def __init__(self, **kw):
        self.routes: list[tuple[str, str, object]] = []

    def _add(self, method: str, path: str):
        def deco(fn):
            self.routes.append((method, path, fn))
            return fn
        return deco

    def get(self, path: str, **kw):
        return self._add("GET", path)

    def post(self, path: str, **kw):
        return self._add("POST", path)

    def put(self, path: str, **kw):
        return self._add("PUT", path)

    def patch(self, path: str, **kw):
        return self._add("PATCH", path)

    def delete(self, path: str, **kw):
        return self._add("DELETE", path)


class FastAPI(APIRouter):
    def __init__(self, **kw):
        super().__init__()
        self.middlewares: list = []

    def include_router(self, router: APIRouter, prefix: str = "", **kw):
        for method, path, fn in router.routes:
            self.routes.append((method, prefix + path, fn))

    def add_middleware(self, cls, **kw):
        self.middlewares.append((cls, kw))


class CORSMiddleware(BaseHTTPMiddleware):
    pass


def _jsonable(obj):
    from pydantic import BaseModel as _BM  # the stub, installed by the sweep
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, _BM):
        return {k: _jsonable(v) for k, v in obj.__dict__.items()}
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(x) for x in obj]
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "__dict__"):
        return {k: _jsonable(v) for k, v in obj.__dict__.items()}
    return str(obj)


class _ClientResponse:
    def __init__(self, status_code: int, content):
        self.status_code = status_code
        self._content = content

    def json(self):
        return self._content

    @property
    def text(self):
        return _json.dumps(self._content, ensure_ascii=False)


def _match(route_path: str, path: str):
    pattern = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", route_path)
    m = re.fullmatch(pattern, path)
    return m.groupdict() if m else None


class TestClient:
    def __init__(self, app: FastAPI):
        self.app = app

    # ---- public verbs
    def get(self, url: str, headers=None):
        return self._request("GET", url, None, headers)

    def post(self, url: str, json=None, headers=None):
        return self._request("POST", url, json, headers)

    def patch(self, url: str, json=None, headers=None):
        return self._request("PATCH", url, json, headers)

    def delete(self, url: str, headers=None):
        return self._request("DELETE", url, None, headers)

    # ---- core
    def _request(self, method: str, url: str, body, headers):
        path, _, qs = url.partition("?")
        query = {k: v[0] for k, v in urllib.parse.parse_qs(qs, keep_blank_values=True).items()}
        request = Request(method, path, query, headers, body)

        async def route_call(req: Request):
            return self._dispatch_route(method, path, query, body)

        # middleware chain (outermost added last in FastAPI; order irrelevant for our two)
        handler = route_call
        for cls, kw in reversed(self.app.middlewares):
            inst = cls(None, **kw)
            if type(inst).dispatch is BaseHTTPMiddleware.dispatch:
                continue  # no-op middleware (e.g., CORS stub)
            prev = handler

            def make(inst, prev):
                async def wrapped(req: Request):
                    return await inst.dispatch(req, prev)
                return wrapped
            handler = make(inst, prev)

        result = asyncio.run(handler(request))
        if isinstance(result, _ClientResponse):
            return result
        if isinstance(result, JSONResponse):
            return _ClientResponse(result.status_code, result._content)
        return _ClientResponse(200, _jsonable(result))

    def _dispatch_route(self, method: str, path: str, query: dict, body):
        from pydantic import BaseModel as _BM
        # literal routes first, then parameterized
        routes = sorted(self.app.routes, key=lambda r: "{" in r[1])
        for m, rpath, fn in routes:
            if m != method:
                continue
            params = _match(rpath, path)
            if params is None:
                continue
            kwargs = {}
            sig = inspect.signature(fn)
            body_used = False
            for pname, p in sig.parameters.items():
                ann = p.annotation
                if pname in params:
                    val = params[pname]
                    if ann is int:
                        val = int(val)
                    elif ann is float:
                        val = float(val)
                    kwargs[pname] = val
                elif isinstance(ann, type) and issubclass(ann, _BM) and not body_used:
                    kwargs[pname] = ann(**(body or {}))
                    body_used = True
                elif ann is dict and not body_used and pname not in query:
                    kwargs[pname] = body or {}
                    body_used = True
                elif isinstance(p.default, _QueryDefault):
                    raw = query.get(pname, p.default.default)
                    if raw is ...:
                        return _ClientResponse(422, {"detail": f"missing query param {pname}"})
                    if ann is int and raw is not None:
                        raw = int(raw)
                    elif ann is float and raw is not None:
                        raw = float(raw)
                    kwargs[pname] = raw
                elif pname in query:
                    kwargs[pname] = query[pname]
                elif p.default is not inspect.Parameter.empty:
                    kwargs[pname] = p.default
            try:
                out = fn(**kwargs)
                if inspect.iscoroutine(out):
                    out = asyncio.get_event_loop().run_until_complete(out)
            except HTTPException as e:
                return _ClientResponse(e.status_code, {"detail": e.detail})
            return _ClientResponse(200, _jsonable(out))
        return _ClientResponse(404, {"detail": f"route not found: {method} {path}"})


def install_fastapi_stub(sys_modules: dict) -> None:
    fa = types.ModuleType("fastapi")
    fa.FastAPI = FastAPI
    fa.APIRouter = APIRouter
    fa.HTTPException = HTTPException
    fa.Query = Query
    mid = types.ModuleType("fastapi.middleware")
    cors = types.ModuleType("fastapi.middleware.cors")
    cors.CORSMiddleware = CORSMiddleware
    mid.cors = cors
    fa.middleware = mid
    tc = types.ModuleType("fastapi.testclient")
    tc.TestClient = TestClient
    fa.testclient = tc
    sys_modules["fastapi"] = fa
    sys_modules["fastapi.middleware"] = mid
    sys_modules["fastapi.middleware.cors"] = cors
    sys_modules["fastapi.testclient"] = tc
