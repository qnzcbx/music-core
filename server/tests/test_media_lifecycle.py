"""虚拟时钟验证本地记录、租约与请求引用，不连接网络。"""
from concurrent.futures import ThreadPoolExecutor
import pytest
from app.core.media_store import MediaStore,PlaybackLeases,MediaSettings
from app.core.errors import CoreError,ErrorCode
from app.models import ResolvedMedia,MediaRepresentation,TrackIdentity


def media():
    return ResolvedMedia(id='provider-temporary',identity=TrackIdentity(providerId='kuwo',platformId='1'),
        representation=MediaRepresentation(),resolvedAt=1,upstreamUrl='https://media.kuwo.cn/audio')


@pytest.fixture
def lifecycle():
    now=[0.0]
    store=MediaStore(MediaSettings(media_ttl=10,lease_ttl=5,capacity=2,lease_capacity=4),lambda:now[0])
    return now,store,PlaybackLeases(store)


def test_store_identity_expiry_capacity(lifecycle):
    now,store,leases=lifecycle
    item=store.put(media())
    assert item.id!='provider-temporary' and store.get(item.id).media is item
    store.put(media())
    with pytest.raises(CoreError) as error:store.put(media())
    assert error.value.code==ErrorCode.MEDIA_CAPACITY
    now[0]=11
    with pytest.raises(CoreError):store.get(item.id)
    store.sweep()
    assert not store.records


def test_lease_and_stream_are_independent(lifecycle):
    now,store,leases=lifecycle
    item=store.put(media());key=leases.create(item.id)
    first,ticket=leases.use(key,stream=True)
    leases.close(key);leases.close(key)
    now[0]=20;leases.sweep()
    assert item.id in store.records
    with pytest.raises(CoreError):leases.use(key,stream=True)
    store.release(item.id,ticket);store.release(item.id,ticket)
    assert not store.records


def test_renew_pause_and_lost_close(lifecycle):
    now,store,leases=lifecycle
    item=store.put(media());key=leases.create(item.id)
    now[0]=4;leases.use(key)
    now[0]=8;assert leases.use(key) is item
    now[0]=11;assert leases.use(key) is item
    now[0]=17;leases.sweep()
    with pytest.raises(CoreError) as error:leases.use(key)
    assert error.value.code==ErrorCode.PLAYBACK_EXPIRED
    assert not store.records
    now[0]=23;leases.sweep();assert not leases.entries


def test_two_sessions_and_ranges(lifecycle):
    now,store,leases=lifecycle
    item=store.put(media());a=leases.create(item.id);b=leases.create(item.id)
    for _ in range(3):
        value,ticket=leases.use(a,stream=True);store.release(item.id,ticket)
    leases.close(a)
    assert leases.use(b).id==item.id and not store.records[item.id].streams
    assert len(store.records)==1
    with pytest.raises(CoreError) as error:leases.use(a)
    assert error.value.code==ErrorCode.PLAYBACK_CLOSED
    with pytest.raises(CoreError):PlaybackLeases(MediaStore()).use(b)


def test_threads_release_consistency(lifecycle):
    _,store,leases=lifecycle
    item=store.put(media());key=leases.create(item.id)
    def request(_):
        result,ticket=leases.use(key,stream=True)
        store.release(result.id,ticket);store.release(result.id,ticket)
    with ThreadPoolExecutor(max_workers=8) as executor:list(executor.map(request,range(100)))
    assert store.records[item.id].streams==set()


def test_missing_and_lease_cap(lifecycle):
    _,store,leases=lifecycle
    leases.close('absent')
    with pytest.raises(CoreError):leases.use('absent')
    with pytest.raises(CoreError):store.get('absent')
    item=store.put(media())
    for _ in range(4):leases.create(item.id)
    with pytest.raises(CoreError):leases.create(item.id)
