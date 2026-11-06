"""只固定异步能力边界；本期不创建伪造结果的 Provider 实现。"""
from typing import Protocol
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.lyrics import LyricDocument
from app.models import ProviderId, TrackIdentity, SearchPage, ResolveOptions, ResolvedMedia


class MusicProvider(Protocol):
    id: ProviderId

    async def get_lyrics(self, identity: TrackIdentity) -> 'LyricDocument':
        """按稳定身份独立取得歌词，不创建媒体或租约。"""
        ...

    async def search(self, query: str, limit: int, cursor: str | None = None) -> SearchPage:
        """只获取元数据，不取媒体地址或执行 probe。"""
        ...

    async def resolve(self, identity: TrackIdentity, options: ResolveOptions | None = None) -> ResolvedMedia:
        """返回私有媒体；所需平台上下文由 Adapter 持有，不进入公共 DTO。"""
        ...
