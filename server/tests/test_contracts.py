"""样本均为人工合成，不代表真实平台可用歌曲。"""
import asyncio
import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from app.models import (TrackIdentity, SongCandidate, ResolvedMedia, PublicMedia,
                        MediaRepresentation, DownloadOption, SearchPage, PlaybackLease)
from app.core.providers import MusicProvider


@pytest.fixture
def rows():
    return json.loads(Path(__file__).with_name('fixtures').joinpath('candidates.json').read_text(encoding='utf8'))


@pytest.mark.parametrize('pid,value', [('kuwo','1'),('qq','A0b'),('netease','9'*20),('migu','8'*32)])
def test_identity_valid(pid, value):
    assert TrackIdentity(providerId=pid, platformId=value).platformId == value


@pytest.mark.parametrize('pid,value', [('unknown','1'),('qq',''),('qq','x'*65),('qq','a-b'),
    ('kuwo','0'),('kuwo','1'*21),('netease','-1'),('migu','1'*33),('qq',' a'),('qq','中'),('kuwo',1),('migu',True)])
def test_identity_invalid(pid, value):
    with pytest.raises(ValidationError):
        TrackIdentity(providerId=pid, platformId=value)


def test_identity_namespace():
    assert TrackIdentity(providerId='kuwo', platformId='1').key != TrackIdentity(providerId='netease', platformId='1').key


def test_candidates_json_roundtrip(rows):
    for row in rows:
        candidate = SongCandidate.model_validate(row)
        assert candidate == SongCandidate.model_validate_json(candidate.model_dump_json())
        assert 'upstreamUrl' not in candidate.model_dump()
    assert len(SongCandidate.model_validate(rows[0]).artists) == 2
    assert SongCandidate.model_validate(rows[0]).durationSeconds is None
    assert SongCandidate.model_validate(rows[1]).album is None
    assert SongCandidate.model_validate(rows[3]).identity.platformId != 'copyrightId'


@pytest.mark.parametrize('change', [{'title':''},{'title':'  '},{'durationSeconds':-1},
    {'durationSeconds':float('nan')},{'headers':{}},{'playable':True},{'cover':'file:///private'}])
def test_bad_metadata(rows, change):
    with pytest.raises(ValidationError):
        SongCandidate.model_validate({**rows[0], **change})


def test_missing_identity_and_title():
    with pytest.raises(ValidationError):
        SongCandidate.model_validate({})


@pytest.fixture
def media():
    return ResolvedMedia(id='temporary-media', identity=TrackIdentity(providerId='qq',platformId='Stable1'),
        representation=MediaRepresentation(), resolvedAt=1000, validUntil=2000,
        upstreamUrl='https://example.invalid/media', headers={'Authorization':'synthetic-private-marker'})


def test_private_media_projection(media):
    public = media.public_view()
    assert public.id != public.identity.platformId
    assert isinstance(public, PublicMedia)
    for serialized in [media.model_dump_json(), public.model_dump_json(), repr(media)]:
        assert 'example.invalid' not in serialized
        assert 'synthetic-private-marker' not in serialized
        assert 'Authorization' not in serialized
    assert 'upstreamUrl' not in media.model_dump()
    assert public.representation.sizeBytes is None
    assert public.validUntil == 2000


@pytest.mark.parametrize('change',[{'validUntil':1000},{'validUntil':999},{'upstreamUrl':'file:///private'},
    {'upstreamUrl':'https://user:pass@example.invalid/a'}])
def test_invalid_media_window_and_url(media, change):
    values = {**media.model_dump(), 'upstreamUrl':media.upstreamUrl, **change}
    with pytest.raises(ValidationError):
        ResolvedMedia.model_validate(values)


def test_unknown_expiry(media):
    data = {**media.model_dump(),'upstreamUrl':media.upstreamUrl,'validUntil':None}
    assert ResolvedMedia.model_validate(data).validUntil is None


def test_download_representation_and_permission(media):
    option = DownloadOption(id='option1', mediaId=media.id, identity=media.identity, label='来源原生表示',
                            representation=media.representation, availability='unknown')
    assert option.estimatedSizeBytes is None and not option.downloadAllowed
    with pytest.raises(ValidationError):
        DownloadOption.model_validate({**option.model_dump(),'downloadAllowed':True})


def test_lease_token_private():
    lease = PlaybackLease(mediaId='temporary1',token='synthetic-lease',expiresAt=2000)
    assert 'synthetic-lease' not in lease.model_dump_json() + repr(lease)


def test_async_provider_contract(rows, media):
    class OfflineProvider:
        """只验证协议调用，不注册到应用。"""
        id = 'qq'

        async def search(self, query, limit, cursor=None):
            return SearchPage(items=(SongCandidate.model_validate(rows[1]),))

        async def resolve(self, identity, options=None):
            return media

    provider: MusicProvider = OfflineProvider()
    assert asyncio.run(provider.search('离线', 1)).nextCursor is None
    assert asyncio.run(provider.resolve(media.identity)) is media
