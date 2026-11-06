"""真实网易云歌词与单audio同步，另以人工响应验证切歌竞争。"""
import argparse
import json
import socket
import threading
import time
import httpx
import uvicorn
from playwright.sync_api import sync_playwright
from app.main import create_app


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--browser',required=True);args=parser.parse_args()
    app=create_app(dev_player=True)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,access_log=False,log_level='critical'))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    try:
        for _ in range(100):
            if server.started:break
            time.sleep(.05)
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,executable_path=args.browser,args=['--autoplay-policy=no-user-gesture-required'])
            try:
                page=browser.new_page();page.goto(f'http://127.0.0.1:{port}/dev/player')
                page.locator('#provider').select_option('netease');page.locator('#rid').fill('284617')
                page.locator('#open').click()
                page.wait_for_function("document.querySelector('audio').currentTime>1 && document.querySelector('#lyrics-state').textContent==='同步歌词'",timeout=30000)
                with httpx.Client() as c:doc=c.get(f'http://127.0.0.1:{port}/api/lyrics',params={'providerId':'netease','platformId':'284617'}).json()
                page.evaluate("window.originalAudio=document.querySelector('audio')")
                page.locator('#pause').click();page.locator('audio').evaluate('a=>a.currentTime=120')
                expected=max(i for i,l in enumerate(doc['lines']) if l['startMs']<=120000)
                page.wait_for_function("index=>document.querySelector('#lyrics').dataset.index===String(index)",arg=expected)
                before=page.locator('#lyrics').get_attribute('data-index');page.wait_for_timeout(500)
                assert page.locator('#lyrics').get_attribute('data-index')==before
                for target in (40,180,60):page.locator('audio').evaluate('(a,t)=>a.currentTime=t',target)
                expected=max(i for i,l in enumerate(doc['lines']) if l['startMs']<=60000)
                page.wait_for_function("index=>document.querySelector('#lyrics').dataset.index===String(index)",arg=expected)
                page.locator('#retry').click();page.wait_for_function("document.body.dataset.phase==='ready'",timeout=30000)
                assert page.locator('audio').evaluate('a=>a===window.originalAudio')
                assert page.locator('#lyrics-state').text_content()=='同步歌词'
                held=[]
                def intercept(route):
                    if 'platformId=1' in route.request.url:held.append(route)
                    else:route.fulfill(json={'identity':{'providerId':'netease','platformId':'2'},'status':'synced','lines':[{'startMs':0,'text':'人工新歌曲','translation':'人工翻译'}]})
                page.route('**/api/lyrics?*',intercept)
                page.locator('#rid').fill('1');page.locator('#load-lyrics').click();page.wait_for_timeout(100)
                page.locator('#rid').fill('2');page.locator('#load-lyrics').click()
                page.wait_for_function("document.querySelector('#lyrics').textContent.includes('人工翻译')")
                assert held
                held[0].fulfill(json={'status':'plain','plainText':'人工旧歌曲','lines':[]})
                page.wait_for_timeout(100);assert '人工旧歌曲' not in page.locator('#lyrics').text_content()
                page.locator('#close').click()
                print(json.dumps({'realProvider':'netease','platformId':'284617','lines':len(doc['lines']),'seek120Index':int(before),'rapidSeek60Index':expected,'pauseStable':True,'sameAudioAfterRecovery':True,'lateOldResponseIgnored':True,'translationDisplayed':True}))
            finally:browser.close()
    finally:server.should_exit=True;thread.join(timeout=10)


if __name__=='__main__':main()
