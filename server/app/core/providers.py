"""只固定异步能力边界；本期不创建伪造结果的 Provider 实现。"""
from typing import Protocol
from app.models import ProviderId, TrackIdentity, SearchPage, ResolveOptions, ResolvedMedia


class MusicProvider(Protocol):
    id: ProviderId

    async def search(self, query: str, limit: int, cursor: str | None = None) -> SearchPage:
        """只获取元数据，不取媒体地址或执行 probe。"""
        ...

    async def resolve(self, identity: TrackIdentity, options: ResolveOptions | None = None) -> ResolvedMedia:
        """返回私有媒体；所需平台上下文由 Adapter 持有，不进入公共 DTO。"""
        ...
