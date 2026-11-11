"""正常 Vue 保存方式验收：真实在线下载与转换，不替换媒体响应。"""
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import httpx
import uvicorn
from playwright.sync_api import sync_playwright
from app.main import create_app
from app.downloads import DownloadSettings

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'docs/migration/40-E-2B'

def main():
    shots=OUT/'screenshots';shots.mkdir(parents=True,exist_ok=True)
    app=create_app(download_settings=DownloadSettings(directory=ROOT/'downloads/40-E-2B'))
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8014,log_level='critical',access_log=False));thread=threading.Thread(target=server.run,daemon=True);thread.start()
    for _ in range(100):
        if server.started:break
        time.sleep(.1)
    vite=subprocess.Popen(['cmd','/c','pnpm dev --port 5191 --strictPort'],cwd=ROOT/'web',env={**os.environ,'MUSIC_CORE_API_TARGET':'http://127.0.0.1:8014'},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    url='http://127.0.0.1:5191';records=[];errors=[]
    try:
        for _ in range(100):
            try:
                if httpx.get(url).status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.2)
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,executable_path='C:/Users/86151/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe',args=['--autoplay-policy=no-user-gesture-required'])
            page=browser.new_page(viewport={'width':1440,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
            opens=[];page.on('response',lambda r:opens.append(r.status) if r.url.endswith('/api/playback/open') else None)
            page.goto(url);page.wait_for_load_state('networkidle');page.locator('input[value="netease"]').check()
            for provider in ('kuwo','qq','migu'):page.locator(f'.primary-sources input[value="{provider}"]').uncheck()
            page.locator('#query').fill('许嵩 天龙八部之宿敌');page.locator('#query').press('Enter');page.wait_for_timeout(4000)
            row=page.locator('.song-row[data-platform-id="167691"]').first
            if not row.count():
                for button in page.locator('.versions-toggle').all():button.click()
            row.locator('.action-play').click();page.wait_for_function('document.querySelector("audio").currentTime>1',timeout=45000)
            page.evaluate('window.originalAudio=document.querySelector("audio")');open_count=len(opens)
            for quality,mode in [('auto','original'),('auto','mp3_320'),('auto','mp3_192'),('high','original'),('lossless','mp3_320')]:
                record={'quality':quality,'outputMode':mode};records.append(record)
                with page.expect_response(lambda r:r.url.endswith('/api/downloads/options'),timeout=35000) as response:row.locator('.action-download').click()
                option=response.value.json()
                if quality!='auto':
                    with page.expect_response(lambda r:r.url.endswith('/api/downloads/options'),timeout=35000) as response:page.locator(f'input[name="download-quality"][value="{quality}"]').check()
                    option=response.value.json()
                record['preview']=option
                if option['availability']!='available':record['unavailable']=True;page.get_by_role('button',name='关闭音质选择').click();continue
                if mode!='original':
                    assert option['representation']['codec']=='flac' and option['conversion']['available']
                    page.locator(f'input[name="output-mode"][value="{mode}"]').check()
                elif quality=='high':assert not page.locator('.save-options').count()
                if quality=='auto' and mode=='original':
                    assert option['representation']['codec']=='flac'
                    for width in (1440,768,390):
                        page.set_viewport_size({'width':width,'height':600})
                        for theme in ('light','dark'):
                            page.evaluate('theme=>document.documentElement.dataset.theme=theme',theme);page.wait_for_timeout(150)
                            assert page.locator('.quality-dialog').evaluate('el=>el.scrollWidth<=el.clientWidth&&el.getBoundingClientRect().height<=innerHeight-30')
                            page.screenshot(path=str(shots/f'save-options-{width}-{theme}.png'))
                    page.set_viewport_size({'width':1440,'height':1000})
                with page.expect_response(lambda r:r.url.endswith('/api/downloads') and r.request.method=='POST') as created:page.get_by_role('button',name='确认下载').click()
                task=created.value.json();record['id']=task['id'];phases=[]
                page.evaluate("history.pushState({},'', '/downloads');dispatchEvent(new PopStateEvent('popstate'))")
                for _ in range(1800):
                    task=page.request.get(url+'/api/downloads/'+record['id']).json()
                    phase=task.get('phase') or task['status']
                    if phase not in phases:phases.append(phase)
                    if phase=='transcoding' and not record.get('transcodingShot'):
                        assert task['status']=='downloading' and task['fileId'] is None and task['progress'] is None
                        page.wait_for_timeout(150);page.screenshot(path=str(shots/f'transcoding-{mode}.png'));record['transcodingShot']=True
                    if task['status'] in ('completed','failed','cancelled'):break
                    assert page.locator('audio').evaluate('a=>a===window.originalAudio&&!a.paused')
                    page.wait_for_timeout(200)
                record.update(task=task,phases=phases,resolution=app.state.netease.last_resolution)
                assert task['status']=='completed',task
                path=app.state.downloads.root/task['filename'];record['diskBytes']=path.stat().st_size
                probe=subprocess.run(['C:/tool/ffmpeg/bin/ffprobe.exe','-v','error','-show_entries','stream=codec_name,sample_rate,channels,bit_rate:format=duration,size','-of','json',str(path)],capture_output=True,text=True)
                record['ffprobe']=json.loads(probe.stdout);assert probe.returncode==0
                assert len(opens)==open_count and page.locator('audio').evaluate('a=>a===window.originalAudio&&!a.paused')
                page.get_by_role('button',name='刷新下载列表').click();page.wait_for_timeout(200)
                page.screenshot(path=str(shots/f'completed-{quality}-{mode}.png'))
                print(json.dumps(record,ensure_ascii=False),flush=True);(OUT/'real-saving.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
                page.evaluate("history.pushState({},'', '/search?q=许嵩%20天龙八部之宿敌');dispatchEvent(new PopStateEvent('popstate'))");page.wait_for_timeout(300)
            page.evaluate("history.pushState({},'', '/downloads');dispatchEvent(new PopStateEvent('popstate'))");page.wait_for_timeout(300)
            for record in records:
                if record.get('task',{}).get('format')!='mp3':continue
                task=record['task'];next(item for item in page.locator('.saved-row').all() if item.get_attribute('data-filename')==task['filename']).locator('.download-identity').click()
                page.wait_for_function('document.querySelector("audio").currentTime>.1',timeout=10000)
                page.get_by_role('button',name='暂停',exact=True).click();assert page.locator('audio').evaluate('a=>a.paused')
                page.get_by_role('button',name='播放',exact=True).click()
                page.get_by_label('播放进度',exact=True).evaluate('el=>{el.value=Number(el.max)*.5;el.dispatchEvent(new Event("input",{bubbles:true}));el.dispatchEvent(new Event("change",{bubbles:true}));}')
                page.wait_for_function('!document.querySelector("audio").seeking&&document.querySelector("audio").currentTime>100');record['localPlayPauseSeek']=True
            assert not errors,errors;browser.close()
    finally:
        (OUT/'real-saving.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8');server.should_exit=True;thread.join(10);subprocess.run(['taskkill','/PID',str(vite.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

if __name__=='__main__':main()
