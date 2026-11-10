"""真实酷我与人工四来源响应分别验收，不请求任何播放或解析接口。"""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,Error

OUT=Path(__file__).resolve().parents[2]/'docs/migration/40-D-3-1'
URL='http://127.0.0.1:5181'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--controlled',action='store_true');parser.add_argument('--url',default=URL);args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,executable_path='C:/Users/86151/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe')
        page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];console=[];requests=[];responses=[];held=[];fail_qq=[True];hold_second=[args.controlled]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('console',lambda m:console.append(m.text) if m.type=='error' else None)
        page.on('request',lambda r:requests.append(r.post_data_json) if r.url.endswith('/api/search') else None)
        page.on('response',lambda r:responses.append(r.json()) if r.url.endswith('/api/search') and r.status==200 else None)
        if args.controlled:
            page.add_init_script("localStorage.setItem('music-core.search.sources.v1',JSON.stringify(['kuwo','qq','netease','migu']))")
            def document(body):
                source=body['providerId'];query=body['query'];number=int((body.get('cursor') or '0:15').split(':')[0])
                if query=='短':ids=[number+1];next_cursor=f'{number+1}:15' if number<4 else None
                else:ids=list(range(1,16)) if number==0 else list(range(15,30)) if number==1 else list(range(30,34));next_cursor=f'{number+1}:15' if number<2 else None
                rows=[{'identity':{'providerId':source,'platformId':str(i)},'title':f'{query}同曲' if i in (1,2,33) else f'{query}{source}{i}','artists':['人工'],'album':'人工专辑'} for i in ids]
                return {'items':rows,'nextCursor':next_cursor}
            def fulfill(route,body):
                if body['query']=='人工' and body['providerId']=='qq' and body.get('cursor')=='1:15' and fail_qq[0]:
                    fail_qq[0]=False;route.fulfill(status=503,json={'error':{'message':'人工分页失败'}})
                else:route.fulfill(json=document(body))
            def intercept(route):
                body=route.request.post_data_json
                if body['query']=='慢' or (hold_second[0] and body.get('cursor')=='1:15'):held.append((route,body));return
                fulfill(route,body)
            page.route('**/api/search',intercept)
        page.goto(args.url);page.wait_for_load_state('networkidle')
        def submit(query):page.locator('#query').fill(query);page.locator('#query').press('Enter')
        def settle():page.wait_for_timeout(700)
        def scroll():
            page.locator('#app-content').hover();page.mouse.wheel(0,100000);settle()
        submit('人工' if args.controlled else '洛神赋 银临')
        page.locator('.song-row').first.wait_for(timeout=30000);settle()
        assert all(r['limit']==15 for r in requests)
        assert page.get_by_role('button',name='加载更多',exact=True).count()==0
        if args.controlled:
            scroll()
            for _ in range(100):
                if len(held)>=4:break
                page.wait_for_timeout(30)
            assert len(held)==4,requests
            count=len(requests)
            for _ in range(3):scroll()
            assert len(requests)==count
            page.evaluate("window.anchor=[...document.querySelectorAll('.song-group')].find(el=>el.getBoundingClientRect().bottom>document.querySelector('#app-content').getBoundingClientRect().top+8);window.anchorY=anchor.getBoundingClientRect().top")
            hold_second[0]=False
            for route,body in held:fulfill(route,body)
            held.clear();settle()
            assert abs(page.evaluate('anchor.getBoundingClientRect().top-anchorY'))<3,page.evaluate('({delta:anchor.getBoundingClientRect().top-anchorY,scroll:document.querySelector("#app-content").scrollTop})')
            assert page.locator('#app-content').evaluate('el=>el.scrollTop<el.scrollHeight-el.clientHeight-100')
            assert page.get_by_role('button',name='重试此来源',exact=True).count()==1
            scroll();settle()
            assert any(r['providerId']=='kuwo' and r.get('cursor')=='2:15' for r in requests)
            assert sum(r['providerId']=='qq' and r.get('cursor')=='1:15' for r in requests)==1
            page.get_by_role('button',name='重试此来源',exact=True).click();settle();scroll();settle()
            page.get_by_text('已全部加载',exact=True).wait_for();count=len(requests);scroll();scroll();assert len(requests)==count
            # 每个来源总计33个稳定版本，分页重叠记录不会重复追加。
            assert '132 首' in page.locator('.results-count').inner_text()
            versions=page.get_by_role('button',name='展开同曲版本',exact=False)
            if not versions.count():versions=page.locator('.versions-toggle')
            assert versions.count()>0
            versions.first.click();assert page.locator('.version-row').count()>0;versions.first.click()
            page.screenshot(path=str(OUT/'controlled-four-sources.png'))
            submit('人工');settle();assert '60 首' in page.locator('.results-count').inner_text()
            submit('慢');settle();assert held
            submit('新');settle()
            for route,body in held:
                try:fulfill(route,body)
                except Error:pass
            held.clear();settle();assert '慢' not in page.locator('.results').inner_text()
            # 来源变化直接重置代次，只保留新的来源集合。
            scroll();assert page.locator('#app-content').evaluate('el=>el.scrollTop>0')
            page.get_by_role('checkbox',name='QQ音乐',exact=True).uncheck();settle();assert '45 首' in page.locator('.results-count').inner_text()
            assert page.locator('#app-content').evaluate('el=>el.scrollTop===0')
            page.get_by_role('checkbox',name='网易云音乐',exact=True).uncheck();page.get_by_role('checkbox',name='咪咕音乐',exact=True).uncheck();settle()
            before=len(requests);submit('短');settle();settle();assert len(requests)-before==3
            page.wait_for_timeout(1000);assert len(requests)-before==3
            scroll();assert len(requests)-before==4;scroll();assert len(requests)-before==5
            page.get_by_text('已全部加载',exact=True).wait_for();scroll();assert len(requests)-before==5
        else:
            original=page.locator('.song-row[data-platform-id="235133157"]');original.wait_for(timeout=30000)
            assert '洛神赋' in original.locator('h3').inner_text() and '银临' in original.inner_text()
            first=responses[0]['items'];assert len(first)==15 and first[0]['identity']['platformId']=='235133157'
            before=sum(bool(r.get('cursor')) for r in requests)
            scroll();scroll();assert sum(bool(r.get('cursor')) for r in requests)>=before+2
            # 搜索结果可能同曲折叠，按已加载稳定身份而非可见行数检查。
            ids=[(item['identity']['providerId'],item['identity']['platformId']) for response in responses for item in response['items']]
            assert f'{len(set(ids))} 首' in page.locator('.results-count').inner_text()
            page.screenshot(path=str(OUT/'real-desktop-search.png'))
            count=len(requests);submit('洛神赋 银临');settle();assert len(requests)>count
        page.set_viewport_size({'width':390,'height':844});settle()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(OUT/('controlled-mobile.png' if args.controlled else 'real-mobile-search.png')))
        assert page.locator('audio').count()==1
        assert not errors,errors
        result={'controlled':args.controlled,'requests':requests,'batches':[{'count':len(response['items']),'nextCursor':response.get('nextCursor')} for response in responses],'pageErrors':errors,'consoleErrors':console,'originalFirstPage':not args.controlled,'realScrollContainer':'#app-content'}
        if not args.controlled:result['firstPageOriginal']=next(row for row in responses[0]['items'] if row['identity']['platformId']=='235133157')
        (OUT/('controlled-result.json' if args.controlled else 'real-result.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'controlled':args.controlled,'requests':len(requests),'pageErrors':errors,'consoleErrors':console}));browser.close()

if __name__=='__main__':main()
