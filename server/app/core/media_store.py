"""进程内私有媒体与播放租约；短锁只保护元数据，不跨网络等待。"""
from dataclasses import dataclass, field
from secrets import token_urlsafe
from threading import RLock
from time import monotonic
from app.models import ResolvedMedia
from app.core.errors import CoreError, ErrorCode


@dataclass(frozen=True)
class MediaSettings:
    media_ttl: float = 300
    lease_ttl: float = 180
    capacity: int = 128
    lease_capacity: int = 256
    sweep_interval: float = 30


@dataclass
class MediaRecord:
    media: ResolvedMedia = field(repr=False)
    created_at: float
    last_accessed_at: float
    expires_at: float
    leases: set[str] = field(default_factory=set, repr=False)
    streams: set[str] = field(default_factory=set, repr=False)


class MediaStore:
    def __init__(self, settings=MediaSettings(), clock=monotonic):
        self.settings, self.clock = settings, clock
        self.records = {}
        self.lock = RLock()

    def sweep(self):
        with self.lock:
            for key,record in list(self.records.items()):
                if record.expires_at <= self.clock() and not record.leases and not record.streams:
                    del self.records[key]

    def put(self, media):
        with self.lock:
            self.sweep()
            if len(self.records) >= self.settings.capacity:
                raise CoreError(ErrorCode.MEDIA_CAPACITY)
            key = token_urlsafe(32)
            now = self.clock()
            # 只替换临时ID，不复制私有对象图；媒体ID从此归Store分配。
            stored = media.model_copy(update={'id':key})
            self.records[key] = MediaRecord(stored,now,now,now+self.settings.media_ttl)
            return stored

    def get(self, key):
        with self.lock:
            record = self.records.get(key)
            if record is None:
                raise CoreError(ErrorCode.MEDIA_EXPIRED)
            if record.expires_at <= self.clock() and not record.leases and not record.streams:
                del self.records[key]
                raise CoreError(ErrorCode.MEDIA_EXPIRED)
            record.last_accessed_at = self.clock()
            return record

    def acquire(self, key):
        with self.lock:
            record = self.get(key)
            ticket = token_urlsafe(16)
            record.streams.add(ticket)
            return record.media,ticket

    def release(self, key, ticket):
        with self.lock:
            if key in self.records:
                self.records[key].streams.discard(ticket)
            self.sweep()


@dataclass
class Lease:
    media_id: str
    expires_at: float
    state: str = 'active'


class PlaybackLeases:
    def __init__(self, store):
        self.store = store
        self.entries = {}

    def sweep(self):
        with self.store.lock:
            now = self.store.clock()
            for key,lease in list(self.entries.items()):
                if lease.state == 'active' and lease.expires_at <= now:
                    self._retire(key,lease,'expired')
                if lease.state != 'active' and lease.expires_at + self.store.settings.lease_ttl <= now:
                    del self.entries[key]
            self.store.sweep()

    def _retire(self, key, lease, state):
        lease.state = state
        lease.expires_at = self.store.clock()
        record = self.store.records.get(lease.media_id)
        if record:
            record.leases.discard(key)

    def create(self, media_id):
        with self.store.lock:
            self.sweep()
            if len(self.entries) >= self.store.settings.lease_capacity:
                raise CoreError(ErrorCode.MEDIA_CAPACITY)
            record = self.store.get(media_id)
            key = token_urlsafe(32)
            self.entries[key] = Lease(media_id,self.store.clock()+self.store.settings.lease_ttl)
            record.leases.add(key)
            return key

    def use(self, key, *, stream=False):
        with self.store.lock:
            self.sweep()
            lease = self.entries.get(key)
            if lease is None:
                raise CoreError(ErrorCode.PLAYBACK_MISSING)
            if lease.state != 'active':
                raise CoreError(ErrorCode.PLAYBACK_CLOSED if lease.state=='closed' else ErrorCode.PLAYBACK_EXPIRED)
            record = self.store.get(lease.media_id)
            lease.expires_at = self.store.clock()+self.store.settings.lease_ttl
            return self.store.acquire(lease.media_id) if stream else record.media

    def close(self, key):
        with self.store.lock:
            lease = self.entries.get(key)
            if lease and lease.state == 'active':
                self._retire(key,lease,'closed')
            self.sweep()
