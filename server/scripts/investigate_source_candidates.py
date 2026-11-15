"""候选音源诊断：固定身份、小额请求；不注册或修改生产 Resolver。"""
import argparse
import asyncio
import json
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit, parse_qs

import httpx
from app.core.errors import CoreError
from app.models import MediaRepresentation
from app.download_quality import satisfies
from app.core.media_probe import verify_media

SAMPLES = ('004Yi5BD3ksoAN', '001bLkWD2EYA4P', '003MUDkf30pS5B')
CANDIDATES = ('mikus', 'yutangxiaowu', 'lzmhhh')


def candidate_request(candidate, mid):
    headers = {'User-Agent': 'Mozilla/5.0'}
    if candidate == 'mikus':
        return httpx.Request('GET', 'https://meting.mikus.ink/api',
                             params={'server': 'tencent', 'type': 'url', 'id': mid}, headers=headers)
    if candidate == 'yutangxiaowu':
        return httpx.Request('GET', 'https://api.yutangxiaowu.cn/api/v1/qqmusic/music',
                             params={'songmid': mid}, headers=headers)
    return httpx.Request('POST', 'https://music.lzmhhh.com/api/music/url',
                         data={'id': mid, 'type': 'qq'}, headers={**headers, 'Referer': 'https://music.lzmhhh.com/'})


async def bounded_body(response, limit):
    body = bytearray()
    async for chunk in response.aiter_bytes():
        body.extend(chunk[:max(0, limit - len(body))])
        if len(body) >= limit:
            break
    return bytes(body)


async def inspect_candidate_media(client, url, provider_id='qq', quality='standard', issued_urls=None):
    # 复用正式有界探测：目标/每跳、Content-Range 总长、编码与文件头均不放宽。
    observed = []
    async def observe(response):
        if issued_urls is not None:
            issued_urls.append(str(response.request.url))
        observed.append({'http': response.status_code,
                         'contentType': response.headers.get('content-type')})
    client.event_hooks['response'].append(observe)
    try:
        actual = await verify_media(client, url, provider_id, detail=True)
        return {'responses': observed, 'representation': actual.model_dump(),
                'classification': 'prefix_quality_match_identity_unconfirmed' if quality is None or satisfies(actual, quality) else 'quality_or_media_mismatch'}
    finally:
        client.event_hooks['response'].remove(observe)


async def attempt(client, candidate, mid):
    started = time.monotonic()
    record = {'candidate': candidate, 'providerId': 'qq', 'platformId': mid,
              'requiredQuality': 'standard', 'credentialConfigured': False}
    response = None
    try:
        request = candidate_request(candidate, mid)
        record['apiHost'] = request.url.host
        response = await client.send(request, stream=True, follow_redirects=False, auth=None)
        record['apiHttp'] = response.status_code
        record['contentType'] = response.headers.get('content-type')
        if response.status_code in (401, 403):
            record['classification'] = ('endpoint_challenge' if response.headers.get('cf-mitigated') == 'challenge' else 'access_denied_scope_unknown')
            return record
        url = None
        if response.status_code in (301,302,303,307,308):
            url = urljoin(str(request.url), response.headers.get('location', ''))
        elif response.status_code == 200:
            raw = await bounded_body(response, 131072)
            try:
                data = json.loads(raw)
            except (ValueError, UnicodeError):
                record['classification'] = 'non_json_api_response'
                return record
            if not isinstance(data, dict):
                record['classification'] = 'invalid_payload'
                return record
            record['responseKeys'] = [key for key in ('code','success','detail','songmid','mid','url','lyric','cache','msg','data','error') if key in data]
            record['businessCode'] = data.get('code') if isinstance(data.get('code'), (int, str)) else None
            if record['businessCode'] in (401,403,'401','403'):
                record['classification'] = 'explicit_denial'
                return record
            detail = data.get('detail') if isinstance(data.get('detail'), dict) else {}
            record['metadata'] = {k:detail.get(k) for k in ('songName','singer','duration') if isinstance(detail.get(k), (str,int,float))}
            echoed = data.get('songmid') or data.get('mid')
            record['responseMid'] = mid if echoed == mid else None
            if echoed is not None and echoed != mid:
                record['classification'] = 'version_mismatch'
                return record
            url = data.get('url') if candidate == 'yutangxiaowu' else data.get('data')
        else:
            record['classification'] = 'endpoint_failure'
            return record
        if not isinstance(url, str) or not url.startswith(('http://', 'https://')):
            record['classification'] = 'no_media_url'
            return record
        record['returnedUrl'] = True
        record['media'] = await inspect_candidate_media(client, url)
        record['classification'] = record['media']['classification']
    except CoreError as error:
        record['classification'] = error.code.value
    except httpx.TimeoutException as error:
        record['classification'] = 'timeout'
        record['errorType'] = type(error).__name__
    except httpx.HTTPError as error:
        record['classification'] = type(error).__name__
    finally:
        if response is not None:
            await response.aclose()
        record['seconds'] = round(time.monotonic() - started, 3)
    return record


NETEASE_SAMPLES = ('167691', '28188434', '30352891')
NETEASE_CANDIDATES = ('lzmhhh', 'ffapi', 'tmetu')


def netease_request(candidate, identifier):
    headers = {'User-Agent': 'Mozilla/5.0'}
    # 默认档不擅自填入源码循环中的 jymaster，保持本次 API 自身默认。
    if candidate == 'lzmhhh':
        return httpx.Request('POST', 'https://music.lzmhhh.com/api/music/url',
                             data={'id': identifier, 'type': 'wy'},
                             headers={**headers, 'Referer': 'https://music.lzmhhh.com/'})
    if candidate == 'ffapi':
        return httpx.Request('GET', 'https://ffapi.cn/int/v1/netease_url',
                             params={'id': identifier}, headers=headers)
    return httpx.Request('GET', 'https://music.tmetu.cn/api/',
                         params={'miss': 'songAll', 'id': identifier, 'withLyric': 'true'},
                         headers={**headers, 'Referer': 'https://music.tmetu.cn/'})


async def attempt_netease(client, candidate, identifier, quality=None):
    record = {'candidate': candidate, 'providerId': 'netease', 'platformId': identifier,
              'requestedQuality': quality or 'API_default_omitted', 'credentialConfigured': False,
              'identityEvidence': 'request_bound_only', 'streamSuccess': False}
    started = time.monotonic()
    response = None
    issued_urls = []
    media_url = None
    try:
        request = netease_request(candidate, identifier)
        if quality is not None:
            if candidate != 'ffapi' or quality not in ('high', 'lossless'):
                raise ValueError('Only documented FFAPI qualities are supported')
            request.url = request.url.copy_set_param('quality', 'exhigh' if quality == 'high' else quality)
        response = await client.send(request, stream=True, follow_redirects=False, auth=None)
        record['apiHttp'] = response.status_code
        record['contentType'] = response.headers.get('content-type')
        if response.headers.get('cf-mitigated') == 'challenge':
            record['classification'] = 'endpoint_challenge'
            return record, None
        if response.status_code in (401, 403, 429):
            record['classification'] = ('rate_limited' if response.status_code == 429 else
                                        'endpoint_challenge' if response.headers.get('cf-mitigated') == 'challenge'
                                        else 'access_denied_scope_unknown')
            return record, None
        if response.status_code != 200:
            record['classification'] = 'endpoint_failure'
            return record, None
        raw = await bounded_body(response, 131072)
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeError):
            record['classification'] = 'non_json_api_response'
            return record, None
        if not isinstance(data, dict):
            record['classification'] = 'invalid_payload'
            return record, None
        record['businessCode'] = data.get('code') if isinstance(data.get('code'), (int, str)) else None
        if record['businessCode'] in (429, '429'):
            record['classification'] = 'rate_limited'
            return record, None
        if record['businessCode'] in (401, 403, '401', '403'):
            record['classification'] = 'explicit_denial'
            return record, None
        detail = data.get('data') if isinstance(data.get('data'), dict) else {}
        # 平台链接只是服务回显依据，不冒充独立音频身份；不记录完整链接。
        link = data.get('links')
        if isinstance(link, str):
            parsed = urlsplit(link)
            echoed_link = parse_qs(parsed.query).get('id', [None])[0]
            if parsed.hostname == 'music.163.com' and echoed_link:
                record['platformLinkIdMatches'] = echoed_link == identifier
                if echoed_link != identifier:
                    record['classification'] = 'version_mismatch'
                    return record, None
        echoed = data.get('id') if data.get('id') is not None else detail.get('id')
        if echoed is not None:
            if str(echoed) != identifier:
                record['classification'] = 'version_mismatch'
                return record, None
            record['identityEvidence'] = 'response_id_matched'
        # 只保存明确的曲目元数据，不输出原始 API 正文和未知字段。
        record['metadata'] = {key: detail[key] for key in ('name', 'artists', 'artist', 'duration')
                              if isinstance(detail.get(key), (str, int, float))}
        if candidate == 'lzmhhh':
            url = data.get('data')
        elif candidate == 'ffapi':
            url = data.get('url')
        else:
            url = detail.get('audioUrl')
        if not isinstance(url, str) or not url.startswith(('https://', 'http://')):
            record['classification'] = 'no_media_url'
            return record, None
        record['returnedUrl'] = True
        record['media'] = await inspect_candidate_media(client, url, 'netease', quality, issued_urls)
        representation = record['media']['representation']
        record['streamSuccess'] = representation.get('codec') in ('mp3', 'aac', 'alac', 'flac')
        record['qualityMatched'] = satisfies(MediaRepresentation(**representation), quality) if quality else None
        record['classification'] = ('stream_success_quality_mismatch' if quality and not record['qualityMatched'] else
                                    'stream_success_identity_unconfirmed') if record['streamSuccess'] else 'format_not_confirmed'
        media_url = issued_urls[-1] if record['streamSuccess'] and issued_urls else None
    except CoreError as error:
        record['classification'] = error.code.value
    except httpx.TimeoutException as error:
        record['classification'] = 'timeout'
        record['errorType'] = type(error).__name__
    except httpx.HTTPError as error:
        record['classification'] = type(error).__name__
        # 仅保留已知环境错误分类，不输出可能包含私有 URL 的异常文本。
        if 'CERTIFICATE_VERIFY_FAILED' in str(error):
            record['transportDetail'] = 'certificate_verification_failed_TLS_not_relaxed'
    finally:
        if response is not None:
            await response.aclose()
        record['seconds'] = round(time.monotonic() - started, 3)
    return record, media_url


def play_candidate_media(url, candidate, identifier, output):
    """只装载该次候选媒体；无 API、无生产 Resolver、无失败后的其他音源。"""
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout, Error as PlaywrightError
    record = {'candidate': candidate, 'platformId': identifier, 'success': False,
              'noFallback': True, 'responses': [], 'blockedOtherRequests': 0}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 850, 'height': 420})
        page = context.new_page()
        def permit(route):
            if route.request.url == url and route.request.method in ('GET', 'HEAD'):
                route.continue_()
            else:
                record['blockedOtherRequests'] += 1
                route.abort()
        context.route('**/*', permit)
        page.on('response', lambda response: record['responses'].append({'http': response.status,
                         'contentType': response.headers.get('content-type')}) if response.url == url else None)
        try:
            page.set_content('<main><h1>候选独立播放验证</h1><p id="label"></p>'
                             '<audio id="audio" controls preload="metadata"></audio>'
                             '<button onclick="audio.play().catch(()=>{})">播放候选</button></main>')
            page.locator('#label').evaluate('(e,text)=>e.textContent=text', candidate + ' / netease / ' + identifier)
            page.locator('#audio').evaluate('(audio,url)=>audio.src=url', url)
            page.get_by_role('button', name='播放候选', exact=True).click()
            page.wait_for_function('!audio.paused && audio.currentTime>1 && !audio.error', timeout=30000)
            record['start'] = page.locator('#audio').evaluate('a=>({currentTime:a.currentTime,duration:a.duration,readyState:a.readyState,paused:a.paused,error:a.error?.code??null})')
            page.wait_for_function('(time)=>audio.currentTime>time+1', arg=record['start']['currentTime'], timeout=15000)
            record['advanced'] = page.locator('#audio').evaluate('a=>({currentTime:a.currentTime,duration:a.duration,readyState:a.readyState,paused:a.paused,error:a.error?.code??null})')
            record['success'] = True
        except PlaywrightTimeout:
            record['failure'] = 'playback_did_not_advance_within_budget'
            record['audio'] = page.locator('#audio').evaluate('a=>({currentTime:a.currentTime,duration:Number.isFinite(a.duration)?a.duration:null,readyState:a.readyState,paused:a.paused,error:a.error?.code??null})')
        except PlaywrightError as error:
            record['failure'] = 'isolated_browser_action_failed'
            record['errorType'] = type(error).__name__
        finally:
            output.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(output / (candidate + '-' + identifier + '.png')))
            browser.close()
    return record


async def investigate_netease(args):
    results = []
    players = []
    stop_classes = {'explicit_denial', 'access_denied_scope_unknown', 'endpoint_challenge',
                    'rate_limited', 'ConnectError'}
    async with httpx.AsyncClient(timeout=httpx.Timeout(12, connect=5), follow_redirects=False) as client:
        for candidate in NETEASE_CANDIDATES:
            stopped = None
            successful_id = None
            for identifier in NETEASE_SAMPLES:
                if stopped:
                    results.append({'candidate': candidate, 'platformId': identifier, 'attempted': False,
                                    'classification': 'not_tested', 'reason': stopped})
                    continue
                record, url = await attempt_netease(client, candidate, identifier)
                record['attempted'] = True
                results.append(record)
                print(json.dumps(record, ensure_ascii=False), flush=True)
                (args.output / 'netease-candidates.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
                if record['streamSuccess'] and successful_id is None:
                    successful_id = identifier
                if record['classification'] in stop_classes:
                    stopped = record['classification']
            if successful_id:
                # 每个成功候选再取一次同身份的 URL，复测不复用旧地址或默认链。
                recheck, url = await attempt_netease(client, candidate, successful_id)
                recheck['round'] = 'recheck'
                results.append(recheck)
                if url and args.player:
                    playback = await asyncio.to_thread(play_candidate_media, url, candidate, successful_id,
                                                        args.output / 'screenshots')
                    players.append(playback)
                    print(json.dumps(playback, ensure_ascii=False), flush=True)
                if candidate == 'ffapi':
                    explicit, _ = await attempt_netease(client, candidate, successful_id, 'lossless')
                    explicit['round'] = 'explicit_lossless'
                    results.append(explicit)
                    print(json.dumps(explicit, ensure_ascii=False), flush=True)
            (args.output / 'netease-candidates.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
            (args.output / 'candidate-players.json').write_text(json.dumps(players, ensure_ascii=False, indent=2), encoding='utf-8')


async def main(args):
    args.output.mkdir(parents=True, exist_ok=True)
    if args.provider == 'netease':
        await investigate_netease(args)
        return
    results = []
    async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=5), follow_redirects=False) as client:
        for candidate in CANDIDATES:
            for mid in SAMPLES:
                result = await attempt(client, candidate, mid)
                results.append(result)
                (args.output / 'candidate-results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
                print(json.dumps(result, ensure_ascii=False), flush=True)
                # 明确拒绝、挑战和端点故障后不继续对该服务逐首试探。
                if result['classification'] in ('explicit_denial','access_denied_scope_unknown','endpoint_challenge','ConnectError','timeout','endpoint_failure'):
                    break


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--provider', choices=('qq', 'netease'), default='qq')
    parser.add_argument('--player', action='store_true', help='仅用候选本次媒体做隔离 Chromium 播放')
    asyncio.run(main(parser.parse_args()))
