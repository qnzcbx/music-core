"""真实酷我与人工四来源响应分别验收，不请求任何播放或解析接口。"""
import argparse
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright,Error

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(os.environ.get('MUSIC_CORE_VERIFY_OUT',ROOT/'.runtime/verify-infinite-search'))
URL=os.environ.get('MUSIC_CORE_WEB_URL','http://127.0.0.1:5181')


def verify_clear_search(page, url, out):
    """正常页面与可控迟到响应共用现有浏览器；只有竞态请求使用夹具。"""
    from urllib.parse import urlsplit, parse_qs
    requests, opened = [], []
    page.add_init_script("localStorage.setItem('music-core.search.sources.v1',JSON.stringify(['qq']))")
    page.on('request', lambda r: requests.append(r.post_data_json) if r.url.endswith('/api/search') else None)
    def observe(response):
        if response.url.endswith('/api/playback/open') and response.status == 200:
            opened.append(response.json())
    page.on('response', observe)
    shots = out / 'screenshots'
    shots.mkdir(parents=True, exist_ok=True)
    results = {}
    def go(path):
        page.evaluate('path => document.querySelector("#app").__vue_app__.config.globalProperties.$router.push(path)', path)
    def empty():
        page.wait_for_function('location.pathname === "/search" && !new URLSearchParams(location.search).has("q")')
        assert page.locator('#query').input_value() == ''
        assert page.locator('#query').evaluate('e=>document.activeElement===e')
        assert page.locator('.song-row').count() == 0
        assert '0 首' in page.locator('.results-count').inner_text()
        assert page.locator('.search-pagination').inner_text().strip() == ''
        assert not page.locator('.search-view [role=alert]:visible').count()
        assert '搜索后，歌曲会出现在这里。' in page.locator('.search-view').inner_text()
    try:
        page.goto(url.rstrip('/') + '/search?q=逃亡 尤长靖')
        page.wait_for_load_state('networkidle')
        row = page.locator('.song-row[data-provider="qq"][data-platform-id="0047EPNp3buJRe"]')
        row.wait_for(timeout=30000)
        row.locator('.action-play').click()
        page.wait_for_function('!document.querySelector("audio").paused && document.querySelector("audio").currentTime>1', timeout=40000)
        go('/search?q=一生所爱&keep=1&tag=a&tag=b#retained')
        page.locator('.song-row').first.wait_for(timeout=30000)
        page.wait_for_function('document.querySelector("#query").value === "一生所爱"')
        before = page.evaluate('({length:history.length,position:history.state.position,back:history.state.back,sources:localStorage.getItem("music-core.search.sources.v1"),time:document.querySelector("audio").currentTime,src:document.querySelector("audio").src})')
        page.evaluate('window.clearTestAudio=document.querySelector("audio")')
        page.screenshot(path=str(shots/'clear-before.png'))
        count = len(requests)
        page.get_by_role('button', name='清空输入', exact=True).click()
        empty()
        page.wait_for_timeout(250)
        after = page.evaluate('({length:history.length,position:history.state.position,back:history.state.back,sources:localStorage.getItem("music-core.search.sources.v1"),time:document.querySelector("audio").currentTime,src:document.querySelector("audio").src,same:document.querySelector("audio")===window.clearTestAudio,paused:document.querySelector("audio").paused})')
        assert after['length'] == before['length'] and after['position'] == before['position'] and after['back'] == before['back']
        assert after['sources'] == before['sources'] and after['src'] == before['src']
        assert after['same'] and not after['paused'] and after['time'] > before['time']
        parsed = urlsplit(page.url)
        assert parse_qs(parsed.query) == {'keep':['1'],'tag':['a','b']} and parsed.fragment == 'retained'
        assert len(requests) == count
        page.screenshot(path=str(shots/'clear-empty-playing.png'))
        results['realSearchClear'] = {'url':page.url,'before':{k:v for k,v in before.items() if k!='src'},'after':{k:v for k,v in after.items() if k!='src'},'noNewRequest':True}
        held = []
        def intercept(route):
            body = route.request.post_data_json
            if body['query'].startswith('慢'):
                held.append((route, body))
            else:
                route.continue_()
        page.route('**/api/search', intercept)
        race_results = []
        for word in ['慢结果', '慢错误']:
            go('/search?q=' + word)
            for _ in range(200):
                if held: break
                page.wait_for_timeout(25)
            assert held
            page.get_by_role('button', name='清空输入', exact=True).click()
            empty()
            route, body = held.pop(0)
            try:
                if word == '慢结果':
                    route.fulfill(json={'items':[{'identity':{'providerId':'qq','platformId':'LateResult'},'title':'不应回填','artists':['夹具']}],'nextCursor':'2:15'})
                else:
                    route.fulfill(status=503,json={'error':{'message':'不应回填错误'}})
            except Error:
                pass  # 被 AbortController 取消的请求可能已无法履行。
            page.wait_for_timeout(250)
            empty()
            race_results.append({'query':word,'lateResponseDidNotRestoreState':True})
        results['races'] = race_results
        page.locator('#query').fill('牵丝戏')
        page.locator('#query').press('Enter')
        page.locator('.song-row').first.wait_for(timeout=30000)
        assert '牵丝戏' in page.locator('.page-title').inner_text()
        results['newSearchWorks'] = True
        page.set_viewport_size({'width':390,'height':844})
        page.get_by_role('button', name='清空输入', exact=True).click()
        empty()
        assert page.locator('audio').evaluate('a=>a===window.clearTestAudio&&!a.paused')
        page.screenshot(path=str(shots/'clear-empty-mobile.png'))
        assert all(body['query'].strip() for body in requests)
        results['noEmptySearch'] = True
        go('/')
        page.locator('.home-view').wait_for()
        page.locator('#query').fill('首页草稿')
        page.get_by_role('button', name='清空输入', exact=True).click()
        assert urlsplit(page.url).path == '/' and page.locator('#query').input_value() == ''
        results['homeClearUnchanged'] = True
        (out/'clear-result.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        print('CLEAR_SEARCH_PASS: URL replace, params/hash, empty state, focus, playback, slow results/errors, new query, mobile, home')
    finally:
        for session in opened:
            page.request.post(url.rstrip('/')+'/api/playback/'+session['playbackId']+'/close')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--clear',action='store_true');parser.add_argument('--controlled',action='store_true');parser.add_argument('--url',default=URL);args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH'))
        page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];console=[];requests=[];responses=[];held=[];fail_qq=[True];hold_second=[args.controlled]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('console',lambda m:console.append(m.text) if m.type=='error' else None)
        page.on('request',lambda r:requests.append(r.post_data_json) if r.url.endswith('/api/search') else None)
        page.on('response',lambda r:responses.append(r.json()) if r.url.endswith('/api/search') and r.status==200 else None)
        if args.clear:
            verify_clear_search(page,args.url,OUT)
            browser.close()
            return
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
            page.screenshot(path=str(OUT/'search-controlled-four-sources.png'))
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
            page.screenshot(path=str(OUT/'search-real-desktop-search.png'))
            count=len(requests);submit('洛神赋 银临');settle();assert len(requests)>count
        page.set_viewport_size({'width':390,'height':844});settle()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(OUT/('search-controlled-mobile.png' if args.controlled else 'search-real-mobile-search.png')))
        assert page.locator('audio').count()==1
        assert not errors,errors
        result={'controlled':args.controlled,'requests':requests,'batches':[{'count':len(response['items']),'nextCursor':response.get('nextCursor')} for response in responses],'pageErrors':errors,'consoleErrors':console,'originalFirstPage':not args.controlled,'realScrollContainer':'#app-content'}
        if not args.controlled:result['firstPageOriginal']=next(row for row in responses[0]['items'] if row['identity']['platformId']=='235133157')
        (OUT/('controlled-result.json' if args.controlled else 'real-result.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'controlled':args.controlled,'requests':len(requests),'pageErrors':errors,'consoleErrors':console}));browser.close()

if __name__=='__main__':main()
