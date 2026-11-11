"""实际Vue工程的搜索、响应隔离和响应式布局验收。"""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUTPUT=ROOT/'docs/archive/13-Vue客户端基础/screenshots'


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,executable_path='C:/Users/86151/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe')
        page=browser.new_page(viewport={'width':1440,'height':1000})
        errors=[];requests=[];console_errors=[];failed=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('console',lambda message:console_errors.append(message.text) if message.type=='error' else None)
        page.on('requestfailed',lambda request:failed.append({'path':request.url.split('?')[0],'reason':request.failure}))
        page.on('request',lambda request:requests.append(request.url) if '/api/' in request.url else None)
        page.goto('http://127.0.0.1:5174/');page.wait_for_load_state('networkidle')
        page.screenshot(path=str(OUTPUT/'desktop-home.png'))
        page.locator('#query').fill('齐豫');page.locator('#query').press('Enter')
        page.wait_for_selector('.song-row',timeout=30000)
        page.screenshot(path=str(OUTPUT/'desktop-search.png'))
        real_count=page.locator('.song-row').count();assert real_count>0
        more=page.get_by_role('button',name='加载更多',exact=True)
        if more.count():
            more.click();page.wait_for_function("document.querySelectorAll('.song-row').length>10",timeout=30000)
        for width in (390,768,1440):
            page.set_viewport_size({'width':width,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.set_viewport_size({'width':390,'height':844})
        page.screenshot(path=str(OUTPUT/'mobile-search.png'))
        page.goto('http://127.0.0.1:5174/');page.wait_for_load_state('networkidle')
        page.screenshot(path=str(OUTPUT/'mobile-home.png'))
        assert page.locator('.mobile-tabbar').is_visible()
        page.goto('http://127.0.0.1:5174/settings');page.wait_for_load_state('networkidle')
        page.locator('input[name="settings-theme"]').nth(1).check()
        assert page.evaluate("document.documentElement.dataset.theme==='dark' || document.documentElement.classList.contains('dark')")
        page.goto('http://127.0.0.1:5174/downloads');page.wait_for_load_state('networkidle')
        # 人工结果只用于验证多来源请求、分页和晚到响应隔离。
        held=[];seen=[]
        def search(route):
            body=route.request.post_data_json;seen.append(body)
            if body['query']=='旧查询':held.append(route);return
            if body['query']=='部分失败' and body['providerId']=='migu':route.fulfill(status=503,json={'error':{'message':'人工来源故障'}});return
            route.fulfill(json={'items':[{'identity':{'providerId':body['providerId'],'platformId':'1'},'title':body['query'],'artists':['人工'],'album':None,'durationSeconds':None,'cover':None}],'nextCursor':None})
        page.route('**/api/search',search)
        page.evaluate("localStorage.setItem('music-core.search.sources.v1',JSON.stringify(['kuwo','qq','netease','migu']))")
        page.goto('http://127.0.0.1:5174/search?q=旧查询');page.wait_for_timeout(300)
        page.locator('#query').fill('新查询');page.locator('#query').press('Enter')
        page.wait_for_function("document.querySelector('.song-row')?.textContent.includes('新查询')")
        for route in held:
            try:route.fulfill(json={'items':[],'nextCursor':None})
            except Exception:pass
        page.wait_for_timeout(200)
        assert '新查询' in page.locator('.song-row').first.inner_text()
        assert {b['providerId'] for b in seen if b['query']=='新查询'}=={'kuwo','qq','netease','migu'}
        page.locator('#query').fill('部分失败');page.locator('#query').press('Enter')
        page.wait_for_function("document.querySelector('[role=alert]')?.textContent.includes('部分来源')")
        assert page.locator('.song-row').count()>0
        assert not errors,errors
        print(json.dumps({'realRows':real_count,'screenshots':4,'widths':[390,768,1440],'lateResponseIgnored':True,'fourSources':True,'pageErrors':errors,'consoleErrors':console_errors,'failedRequests':failed,'apiRequests':len(requests)},ensure_ascii=False))
        browser.close()


if __name__=='__main__':main()
