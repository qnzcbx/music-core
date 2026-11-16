"""真实 release WebView2：固定 QQ MID，检查备用播放、seek 和切回原生。"""
import json
import argparse
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

parser=argparse.ArgumentParser()
parser.add_argument('--out',default='.runtime/desktop-stage3')
parser.add_argument('--expect-disabled',action='store_true')
args=parser.parse_args()
out = Path(args.out)
out.mkdir(parents=True, exist_ok=True)
with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:9223')
    page = browser.contexts[0].pages[0]
    page.wait_for_load_state('networkidle')
    assert page.url.startswith('http://tauri.localhost/')
    if args.expect_disabled:
        result=page.evaluate('''async()=>{
            try {
                const data=await window.__TAURI__.core.invoke('desktop_request',{path:'/api/playback/open',body:{identity:{providerId:'qq',platformId:'0027oMO61wWi55'}}});
                await window.__TAURI__.core.invoke('desktop_request',{path:`/api/playback/${data.playbackId}/close`,body:null});
                return {resolver:data.resolver};
            } catch(error) {return {error:String(error)};}
        }''')
        assert '未提供匿名可播放媒体' in result.get('error',''),result
        (out/'disabled.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
        print('Explicit disable: original QQ sample remains native unavailable',flush=True)
        browser.close()
        raise SystemExit(0)
    page.evaluate("localStorage.setItem('music-core.search.sources.v1',JSON.stringify(['qq']))")
    page.reload()
    page.wait_for_load_state('networkidle')
    def until(expression, arg=None):
        deadline = time.monotonic()+40
        while time.monotonic()<deadline:
            if page.evaluate(expression,arg): return
            page.wait_for_timeout(100)
        raise AssertionError('WebView2 playback condition timed out')
    page.locator('#query').fill('发如雪 周杰伦')
    page.locator('#query').press('Enter')
    page.locator('.song-row').first.wait_for()
    for toggle in page.locator('.versions-toggle[aria-expanded=false]').all():
        toggle.click()
    records=[]
    previous=None
    for mid, route in [('0027oMO61wWi55','tang'),('0037WF7I0yUPLu','native')]:
        row=page.locator(f'.song-row[data-provider="qq"][data-platform-id="{mid}"]')
        result=page.evaluate('''async identity=>{
            const data=await window.__TAURI__.core.invoke('desktop_request',{path:'/api/playback/open',body:{identity}});
            await window.__TAURI__.core.invoke('desktop_request',{path:`/api/playback/${data.playbackId}/close`,body:null});
            return {resolver:data.resolver};
        }''',{'providerId':'qq','platformId':mid})
        assert result['resolver']==route
        row.locator('.action-play').click(position={'x':20,'y':20})
        until("!document.querySelector('audio').paused && document.querySelector('audio').currentTime>1")
        assert 'selected' in row.get_attribute('class')
        assert row.locator('.action-play').get_attribute('title')=='暂停'
        if previous:
            assert page.request.head(previous).status==410
        box=page.get_by_role('slider',name='播放进度').bounding_box()
        page.mouse.move(box['x']+2,box['y']+box['height']/2)
        page.mouse.down()
        page.mouse.move(box['x']+box['width']*.5,box['y']+box['height']/2)
        page.mouse.up()
        until("()=>{const a=document.querySelector('audio');return !a.paused&&a.currentTime>a.duration*.4&&a.currentTime<a.duration*.7}")
        before=page.locator('audio').evaluate('a=>a.currentTime')
        until('before=>document.querySelector("audio").currentTime>before+1',before)
        previous=page.locator('audio').evaluate('a=>a.src')
        records.append({'provider':'qq','platformId':mid,'preflightResolver':route,'seekContinued':True})
        page.screenshot(path=str(out/f'{route}.png'))
        print(json.dumps(records[-1]),flush=True)
    assert page.locator('audio').count()==1
    (out/'result.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    browser.close()
