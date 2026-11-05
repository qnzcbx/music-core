"""API 仅提供本期真实实现的健康状态与来源信息。"""
import logging
from contextlib import asynccontextmanager
import httpx
from pydantic import Field, field_validator
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from app.models import DTO, SearchPage
from app.providers.kuwo import KuwoProvider
from app.config import load_policy, provider_info, ProviderInfo
from app.core.errors import CoreError, ErrorCode

ERRORS = {
    ErrorCode.INVALID_INPUT: (422, '输入参数无效', False),
    ErrorCode.UNSUPPORTED_PROVIDER: (400, '不支持此音乐来源', False),
    ErrorCode.TRACK_NOT_FOUND: (404, '未找到原平台歌曲', False),
    ErrorCode.MEDIA_UNAVAILABLE: (409, '当前媒体暂不可用', True),
    ErrorCode.UPSTREAM_FAILURE: (502, '上游请求失败，请稍后重试', True),
    ErrorCode.MEDIA_EXPIRED: (410, '媒体能力已过期，请重新解析', True),
    ErrorCode.INTERNAL_ERROR: (500, '内部服务异常', False),
    ErrorCode.UPSTREAM_TIMEOUT: (504, '上游请求超时', True),
    ErrorCode.ACCESS_DENIED: (403, '平台拒绝访问或需要认证', False),
    ErrorCode.UPSTREAM_INVALID_RESPONSE: (502, '上游响应结构异常', True),
    ErrorCode.PROVIDER_NOT_INTEGRATED: (501, '此来源尚未接入', False),
    ErrorCode.CAPABILITY_UNSUPPORTED: (415, '尚不支持此媒体能力或解析选项', False),
}


class SearchRequest(DTO):
    providerId: str = Field(min_length=1,max_length=32)
    query: str = Field(min_length=1,max_length=80)
    limit: int = Field(default=10,ge=1,le=10,strict=True)
    cursor: str | None = Field(default=None,max_length=20)

    @field_validator('query')
    @classmethod
    def nonempty(cls,value):
        if not value.strip():
            raise ValueError('搜索词不能为空白')
        return value.strip()


class ErrorDetail(DTO):
    code: str
    message: str
    retryable: bool


class ErrorResponse(DTO):
    error: ErrorDetail


class Health(DTO):
    status: str
    version: str
    configurationFallback: bool


def error_response(code):
    status, message, retryable = ERRORS[code]
    return JSONResponse(status_code=status, content=ErrorResponse(error=ErrorDetail(
        code=code.value, message=message, retryable=retryable)).model_dump())


def create_app(config_path=None, *, transport=None) -> FastAPI:
    policy, fallback = load_policy(config_path)
    @asynccontextmanager
    async def lifespan(api):
        async with httpx.AsyncClient(timeout=httpx.Timeout(12,connect=5),
                limits=httpx.Limits(max_connections=10,max_keepalive_connections=5),
                follow_redirects=False,transport=transport) as client:
            api.state.kuwo = KuwoProvider(client)
            yield

    api = FastAPI(title='Music Core 本地后端', version='0.1.0', responses={
        422: {'model': ErrorResponse}, 500: {'model': ErrorResponse}},lifespan=lifespan)
    api.state.source_policy = policy

    @api.exception_handler(CoreError)
    async def core_error(request: Request, exc: CoreError):
        return error_response(exc.code)

    @api.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return error_response(ErrorCode.INVALID_INPUT)

    @api.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        # 不回显路径、参数或外部异常 detail，仍保留标准 HTTP 状态。
        return JSONResponse(status_code=exc.status_code, headers=exc.headers, content={
            'error': {'code': 'route_not_found' if exc.status_code == 404 else 'http_error',
                      'message': '接口不存在' if exc.status_code == 404 else 'HTTP 请求未被接受', 'retryable': False}})

    @api.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logging.getLogger(__name__).error('内部请求失败，异常类型=%s', type(exc).__name__)
        return error_response(ErrorCode.INTERNAL_ERROR)

    @api.get('/api/health', response_model=Health)
    async def health():
        return Health(status='degraded' if fallback else 'ok', version='0.1.0', configurationFallback=fallback)

    @api.get('/api/providers', response_model=list[ProviderInfo])
    async def providers():
        return provider_info(policy)

    @api.post('/api/search',response_model=SearchPage,responses={
        status:{'model':ErrorResponse} for status in (400,403,404,501,502,504)})
    async def search(body: SearchRequest):
        if body.providerId not in policy.sourceOrder:
            raise CoreError(ErrorCode.UNSUPPORTED_PROVIDER)
        if body.providerId != 'kuwo':
            raise CoreError(ErrorCode.PROVIDER_NOT_INTEGRATED)
        return await api.state.kuwo.search(body.query,body.limit,body.cursor)

    return api


app = create_app()
