"""稳定公开契约与私有媒体分开建模，所有时间戳使用 epoch 毫秒。"""
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr, field_validator, model_validator

ProviderId = Literal['kuwo', 'qq', 'netease', 'migu']


class DTO(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, populate_by_name=True, allow_inf_nan=False)


class TrackIdentity(DTO):
    providerId: ProviderId
    platformId: str = Field(min_length=1, max_length=64)

    @model_validator(mode='after')
    def valid_platform_id(self):
        pattern = r'[A-Za-z0-9]{1,64}' if self.providerId == 'qq' else r'[1-9][0-9]{0,31}' if self.providerId == 'migu' else r'[1-9][0-9]{0,19}'
        if not re.fullmatch(pattern, self.platformId):
            raise ValueError('平台歌曲身份格式无效')
        return self

    @property
    def key(self) -> tuple[str, str]:
        return self.providerId, self.platformId


class SongCandidate(DTO):
    identity: TrackIdentity
    title: str = Field(min_length=1, max_length=500)
    artists: tuple[str, ...] = ()
    album: str | None = None
    durationSeconds: float | None = Field(default=None, ge=0)
    cover: HttpUrl | None = None

    @field_validator('title')
    @classmethod
    def meaningful_title(cls, value):
        if not value.strip():
            raise ValueError('歌曲名不能为空白')
        return value


class SearchPage(DTO):
    items: tuple[SongCandidate, ...]
    nextCursor: str | None = None


class ResolveOptions(DTO):
    purpose: Literal['playback', 'download'] = 'playback'
    providerQualityId: str | None = None


class MediaRepresentation(DTO):
    container: str | None = None
    codec: str | None = None
    contentType: str | None = None
    providerQualityId: str | None = None
    sizeBytes: int | None = Field(default=None, strict=True, gt=0)
    bitrateBps: int | None = Field(default=None, strict=True, gt=0)
    lossless: bool | None = None


class PublicMedia(DTO):
    id: str = Field(min_length=1)
    identity: TrackIdentity
    protocol: Literal['progressive'] = 'progressive'
    representation: MediaRepresentation
    resolvedAt: int = Field(ge=0, strict=True)
    validUntil: int | None = Field(default=None, ge=0, strict=True)

    @model_validator(mode='after')
    def valid_window(self):
        if self.validUntil is not None and self.validUntil <= self.resolvedAt:
            raise ValueError('资源有效期必须晚于解析时间')
        return self


class ResolvedMedia(PublicMedia):
    # 私有字段既排除序列化，也隐藏在 repr 中；API只能使用 PublicMedia。
    upstreamUrl: SecretStr = Field(exclude=True, repr=False)
    headers: dict[str, SecretStr] = Field(default_factory=dict, exclude=True, repr=False)

    @field_validator('upstreamUrl')
    @classmethod
    def http_media_only(cls, value):
        from urllib.parse import urlsplit
        parsed = urlsplit(value.get_secret_value())
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('私有媒体地址必须为无用户信息的 HTTP 地址')
        return value

    def public_view(self) -> PublicMedia:
        return PublicMedia.model_validate(self.model_dump())


class DownloadOption(DTO):
    id: str = Field(min_length=1)
    mediaId: str = Field(min_length=1)
    identity: TrackIdentity
    label: str
    representation: MediaRepresentation
    availability: Literal['available', 'unknown', 'unavailable', 'stale']
    downloadAllowed: bool = False
    estimatedSizeBytes: int | None = Field(default=None, strict=True, gt=0)

    @model_validator(mode='after')
    def available_permission(self):
        if self.downloadAllowed and self.availability != 'available':
            raise ValueError('未确认可用的选项不能声明允许下载')
        return self


class QueueEntry(DTO):
    identity: TrackIdentity
    title: str
    artists: tuple[str, ...] = ()


class PlaybackLease(DTO):
    mediaId: str
    token: SecretStr = Field(exclude=True, repr=False)
    expiresAt: int = Field(ge=0, strict=True)
