from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in err["loc"]), "message": err["msg"], "type": err["type"]} for err in exc.errors()]
        return JSONResponse(status_code=422, content={"error": {"code": "validation_error", "message": "Проверь введённые данные", "details": details}})
    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else "Запрос не выполнен"
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": "http_error", "message": detail, "details": []}}, headers=exc.headers)
