"""品质弹窗的受控 HTTP 验收，不将夹具记录当作真实下载。"""
import argparse
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(os.environ.get('MUSIC_CORE_VERIFY_OUT',ROOT/'.runtime/verify-download-quality-ui'))

def main():
    parser=argparse.ArgumentParser(description='受控验证下载音质选择界面')
    parser.add_argument('--url',default=os.environ.get('MUSIC_CORE_WEB_URL','http://127.0.0.1:5174'),help='已运行的 Vue 客户端地址')
    args=parser.parse_args()
    screenshots=OUT/'screenshots';screenshots.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH'))
        page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        state={'mode':'hold','posts':[]};held=[];tasks=[];files=[];options=[]
        def option(route):
            body=route.request.post_data_json;options.append(body)
            if state['mode']=='hold':held.append(route);return
            if state['mode']=='error':route.abort('failed');return
            quality=body.get('quality','auto');available=quality!='lossless'
            route.fulfill(json={'quality':quality,'availability':'available' if available else 'unavailable','representation':{'codec':'mp3','container':'mpeg-audio','bitrateBps':320000,'sizeBytes':10000,'lossless':False} if available else None,'errorCode':None if available else 'media_unavailable'})
        def downloads(route):
            if route.request.method=='GET':route.fulfill(json=tasks);return
            body=route.request.post_data_json;state['posts'].append(body)
            task={'id':'new-task','identity':body['identity'],'title':body['title'],'artist':body['artist'],'quality':body['quality'],'status':'queued','createdAt':1,'updatedAt':1};tasks.append(task);route.fulfill(status=202,json=task)
        page.route('**/api/search',lambda r:r.fulfill(json={'items':[{'identity':{'providerId':'kuwo','platformId':str(i)},'title':f'交互歌曲{i}','artists':['人工']} for i in (1,2)]}))
        page.route('**/api/downloads/options',option);page.route('**/api/downloads',downloads);page.route('**/api/downloads/files',lambda r:r.fulfill(json=files))
        # 本夹具验收本地成品与通知，不能依赖被测服务当前的 browser/local 配置。
        page.route('**/api/downloads/settings', lambda r: r.fulfill(json={'mode':'local','canManage':False,'deploymentLocked':False}))
        page.goto(args.url.rstrip('/')+'/search?q=交互');page.wait_for_load_state('networkidle')
        first=page.locator('.song-row[data-platform-id="1"]');second=page.locator('.song-row[data-platform-id="2"]')
        page.evaluate('window.firstAudio=document.querySelector("audio")')
        first.locator('.action-download').click();page.wait_for_timeout(100);assert '正在检测' in page.locator('.quality-dialog').inner_text()
        assert page.get_by_role('button',name='确认下载').is_disabled()
        page.get_by_role('button',name='关闭音质选择').click();state['mode']='ok';second.locator('.action-download').click();page.wait_for_timeout(200)
        for route in held:
            try:route.fulfill(json={'quality':'auto','availability':'unavailable','representation':None,'errorCode':'media_unavailable'})
            except Exception:pass
        page.wait_for_timeout(200);assert '交互歌曲2' in page.locator('.quality-song').inner_text();assert page.get_by_role('button',name='确认下载').is_enabled()
        page.locator('input[value="lossless"]').check();page.wait_for_timeout(150);assert page.get_by_role('button',name='确认下载').is_disabled()
        state['mode']='error';page.locator('input[value="standard"]').check();page.wait_for_timeout(150);assert '暂时无法检测音质' in page.locator('.quality-dialog').inner_text()
        state['mode']='ok';page.locator('input[value="high"]').check();page.wait_for_timeout(150)
        for width in (1440,768,390):
            page.set_viewport_size({'width':width,'height':500})
            for theme in ('light','dark'):
                page.evaluate('theme=>document.documentElement.dataset.theme=theme',theme);page.wait_for_timeout(150)
                assert page.locator('.quality-dialog').evaluate('el=>el.scrollWidth<=el.clientWidth&&el.getBoundingClientRect().height<=innerHeight-30')
                page.screenshot(path=str(screenshots/f'preaudit-controlled-dialog-{width}-{theme}.png'))
        page.get_by_role('button',name='确认下载').evaluate('el=>{el.click();el.click()}');page.wait_for_timeout(250)
        assert len(state['posts'])==1 and state['posts'][0]['quality']=='high' and state['posts'][0]['identity']['platformId']=='2'
        assert page.locator('audio').evaluate('a=>a===window.firstAudio&&a.paused&&!a.getAttribute("src")')
        page.locator('.mobile-tabbar').get_by_role('link',name='下载',exact=True).click();page.wait_for_timeout(150)
        tasks[0].update(status='completed',fileId='new-file',updatedAt=2)
        files.append({'fileId':'new-file','filename':'new.mp3','format':'mp3','sizeBytes':10000,'modifiedAt':2})
        page.get_by_role('button',name='刷新下载列表').click();page.wait_for_timeout(200)
        assert '下载成功' in page.locator('.client-notice').inner_text()
        assert not errors,errors
        print('QUALITY_UI_PASS: loading, close/abort, stale identity, unavailable, network error, correct quality, duplicate suppression, themes/scroll, same Audio, completion notification')
        browser.close()

if __name__=='__main__':main()
