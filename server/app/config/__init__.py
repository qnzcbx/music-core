"""配置只影响产品偏好，不声称平台在线可用率。"""
import json
import logging
import os
from pathlib import Path
from pydantic import Field, model_validator
from app.models import DTO, ProviderId

IDS = ('kuwo', 'qq', 'netease', 'migu')
NAMES = {'kuwo': '酷我音乐', 'qq': 'QQ音乐', 'netease': '网易云音乐', 'migu': '咪咕音乐'}


class SourcePolicy(DTO):
    sourceOrder: tuple[ProviderId, ...] = IDS
    defaultSelectedSources: tuple[ProviderId, ...] = ('kuwo',)

    @model_validator(mode='after')
    def valid_sources(self):
        if len(self.sourceOrder) != 4 or set(self.sourceOrder) != set(IDS):
            raise ValueError('来源顺序必须恰好包含四个正式来源')
        selected = self.defaultSelectedSources
        if not selected or len(set(selected)) != len(selected):
            raise ValueError('默认来源不能为空或重复')
        return self


def load_policy(path: Path | None = None) -> tuple[SourcePolicy, bool]:
    target = path or Path(os.environ.get('MUSIC_CORE_SOURCE_CONFIG', Path(__file__).with_name('sources.json')))
    try:
        value = json.loads(target.read_text(encoding='utf8'))
        if not value:
            raise ValueError('空配置使用内置默认值')
        return SourcePolicy.model_validate(value), False
    except (OSError, ValueError, UnicodeError):
        logging.getLogger(__name__).warning('来源配置无效，已采用内置安全默认配置')
        return SourcePolicy(), True


class Capabilities(DTO):
    search: bool = False
    resolve: bool = False
    lyrics: bool = False
    download: bool = False


class ProviderInfo(DTO):
    id: ProviderId
    name: str
    order: int
    defaultSelected: bool
    implementationStatus: str = 'not_integrated'
    capabilities: Capabilities = Field(default_factory=Capabilities)


def provider_info(policy: SourcePolicy) -> list[ProviderInfo]:
    return [ProviderInfo(id=pid, name=NAMES[pid], order=i, defaultSelected=pid in policy.defaultSelectedSources,
            implementationStatus='implemented_sample_media_verified',
            capabilities=Capabilities(search=pid in IDS,resolve=pid in IDS))
            for i, pid in enumerate(policy.sourceOrder)]
