"""连接真实 release WebView2 的临时 CDP 端口；不启动浏览器或后端。"""
import argparse
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument('--endpoint', default='http://127.0.0.1:9223')
parser.add_argument('--out', default='.runtime/desktop-stage2')
parser.add_argument('--check-metadata',action='store_true')
args = parser.parse_args()
out = Path(args.out)
out.mkdir(parents=True, exist_ok=True)
with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp(args.endpoint)
    page = browser.contexts[0].pages[0]
    page.goto('http://tauri.localhost/')
    page.wait_for_load_state('networkidle')
    def until(expression, arg=None, timeout=40):
        deadline = time.monotonic()+timeout
        while time.monotonic()<deadline:
            if page.evaluate(expression, arg): return
            page.wait_for_timeout(100)
        raise AssertionError('WebView condition timed out')
    assert page.url.startswith('http://tauri.localhost/')
    assert page.locator('audio').count() == 1
    for checkbox in page.get_by_role('checkbox').all():
        checkbox.check()
    page.locator('#query').fill('晴天')
    page.locator('#query').press('Enter')
    until("document.querySelectorAll('.song-row').length >= 40", timeout=45)
    print(page.locator('.song-row').evaluate_all("es=>es.slice(0,4).map(e=>({provider:e.dataset.provider,id:e.dataset.platformId}))"))
    for toggle in page.locator('.versions-toggle[aria-expanded=false]').all():
        toggle.click()
    def available(source):
        ids = page.locator(f'[data-provider="{source}"]').evaluate_all('es=>es.map(e=>e.dataset.platformId)')
        for identifier in ids[:10]:
            if page.evaluate('''async identity=>{try {
                const data=await window.__TAURI__.core.invoke('desktop_request',{path:'/api/playback/open',body:{identity}});
                await window.__TAURI__.core.invoke('desktop_request',{path:`/api/playback/${data.playbackId}/close`,body:null});
                return true;
            } catch {return false;}}''', {'providerId':source,'platformId':identifier}):
                return identifier
        raise AssertionError(f'{source}: no anonymously playable sample in visible results')
    targets = [('kuwo', None), ('netease', available('netease')), ('qq', available('qq')), ('migu', available('migu')), ('kuwo', None)]
    records = []
    previous = None
    for source, identifier in targets:
        selector = f'[data-provider="{source}"]'
        if identifier:
            selector += f'[data-platform-id="{identifier}"]'
        row = page.locator(selector).first
        row.wait_for(timeout=30000)
        identity = row.get_attribute('data-platform-id')
        row.locator('.action-play').click(position={'x':20,'y':20})
        until("!document.querySelector('audio').paused && document.querySelector('audio').currentTime>1", timeout=40)
        current = page.locator('audio').evaluate('a=>a.src')
        assert 'selected' in row.get_attribute('class')
        assert row.locator('.action-play').get_attribute('title') == '暂停'
        if previous and previous != current:
            assert page.request.head(previous).status == 410
        slider = page.get_by_role('slider', name='播放进度')
        box = slider.bounding_box()
        page.mouse.move(box['x'] + 2, box['y'] + box['height']/2)
        page.mouse.down()
        page.mouse.move(box['x'] + box['width']*.5, box['y'] + box['height']/2)
        page.mouse.up()
        until("()=>{const a=document.querySelector('audio');return !a.paused && a.currentTime>a.duration*.4 && a.currentTime<a.duration*.7}")
        before = page.locator('audio').evaluate('a=>a.currentTime')
        until('before=>document.querySelector("audio").currentTime>before+1', before)
        records.append({'source':source,'platformId':identity,'seekContinued':True,'previousReleased':previous is not None})
        page.screenshot(path=str(out/f'{len(records)}-{source}.png'))
        print(json.dumps(records[-1]), flush=True)
        previous = current
    # 连续跨来源切歌，最后一首稳定后再检查被替换会话。
    for source, identifier in targets[1:4]:
        page.locator(f'[data-provider="{source}"][data-platform-id="{identifier}"] .action-play').click(position={'x':20,'y':20})
    until("!document.querySelector('audio').paused && document.querySelector('audio').currentTime>1")
    selected = page.locator('.song-row.selected')
    assert selected.get_attribute('data-provider') == targets[3][0]
    assert selected.get_attribute('data-platform-id') == targets[3][1]
    assert selected.locator('.action-play').get_attribute('title') == '暂停'
    assert page.request.head(previous).status==410
    if args.check_metadata:
        identity={'providerId':targets[3][0],'platformId':targets[3][1]}
        lyric=page.evaluate('identity=>window.__TAURI__.core.invoke("desktop_request",{path:"/api/lyrics",body:identity})',identity)
        cover=selected.locator('img').get_attribute('src')
        page.get_by_role('button',name='打开沉浸式播放器',exact=True).click()
        until('count=>document.querySelectorAll(".lyric-line").length===count',len(lyric['lines']))
        until('url=>document.querySelector("[data-player-cover] img")?.src===url',cover)
        until('url=>document.querySelector("[data-palette-key]")?.dataset.paletteKey===url',cover)
        page.screenshot(path=str(out/'rapid-switch-metadata.png'))
    (out/'result.json').write_text(json.dumps({'actualWebView2':True,'records':records,'rapidSwitch':True},ensure_ascii=False,indent=2),encoding='utf-8')
    browser.close()
