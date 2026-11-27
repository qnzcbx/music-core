"""Core 只抛业务类别，HTTP 状态由 API 层决定。"""
from enum import Enum


class ErrorCode(str, Enum):
    INVALID_INPUT = 'invalid_input'
    UNSUPPORTED_PROVIDER = 'unsupported_provider'
    TRACK_NOT_FOUND = 'track_not_found'
    MEDIA_UNAVAILABLE = 'media_unavailable'
    UPSTREAM_FAILURE = 'upstream_failure'
    MEDIA_EXPIRED = 'media_expired'
    INTERNAL_ERROR = 'internal_error'
    UPSTREAM_TIMEOUT = 'upstream_timeout'
    ACCESS_DENIED = 'access_denied'
    UPSTREAM_INVALID_RESPONSE = 'upstream_invalid_response'
    PROVIDER_NOT_INTEGRATED = 'provider_not_integrated'
    CAPABILITY_UNSUPPORTED = 'capability_unsupported'
    PLAYBACK_MISSING = 'playback_missing'
    PLAYBACK_CLOSED = 'playback_closed'
    PLAYBACK_EXPIRED = 'playback_expired'
    MEDIA_CAPACITY = 'media_capacity'
    UNTRUSTED_MEDIA = 'untrusted_media'
    INVALID_RANGE = 'invalid_range'
    UPSTREAM_MEDIA_EXPIRED = 'upstream_media_expired'
    PROVIDER_CONTEXT_REJECTED = 'provider_context_rejected'


def may_try_another_route(code: ErrorCode) -> bool:
    return code in (ErrorCode.UPSTREAM_FAILURE, ErrorCode.UPSTREAM_TIMEOUT, ErrorCode.MEDIA_UNAVAILABLE)


class CoreError(Exception):
    def __init__(self, code: ErrorCode):
        self.code = code
        super().__init__(code.value)
