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


class UnsupportedRouteFormat(CoreError):
    def __init__(self):
        super().__init__(ErrorCode.CAPABILITY_UNSUPPORTED)


def check_access(payload):
    if any(payload.get(field) in (301,401,403,'301','401','403') for field in ('code','status')):
        raise CoreError(ErrorCode.ACCESS_DENIED)
    for field in ('freeTrialInfo','freeListenType','drm','encrypted','requiresLogin','requiresPayment','regionBlocked'):
        if payload.get(field) not in (None,False,0,'0'):
            raise CoreError(ErrorCode.ACCESS_DENIED)
