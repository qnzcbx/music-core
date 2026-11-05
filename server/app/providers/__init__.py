"""平台实现独立持有请求上下文，不依赖旧项目。"""
from app.core.errors import CoreError,ErrorCode


def provider_for(state,source):
    # 固定三份实现，不动态扫描；保留测试对单个Provider的显式替换边界。
    if source not in ('kuwo','qq','netease'):raise CoreError(ErrorCode.PROVIDER_NOT_INTEGRATED)
    return getattr(state,source)
