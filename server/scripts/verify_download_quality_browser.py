"""正常 Vue 下载入口的四来源真实品质验收，不替换上游响应。"""
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
OUT=ROOT/'docs/migration/40-E-2A'
QUALITIES=('auto','standard','high','lossless')
SAMPLES=[('kuwo','银临 东风志','9942644'),('qq','周杰伦 蒲公英的约定','004Yi5BD3ksoAN'),('netease','许嵩 天龙八部之宿敌','167691'),('migu','许嵩 庐州月','600902000009209221')]

def main():
    shots=OUT/'screenshots';shots.mkdir(parents=True,exist_ok=True)
    app=create_app(download_settings=DownloadSettings(directory=ROOT/'downloads/40-E-2A'))
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8012,log_level='critical',access_log=False))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    for _ in range(100):
        if server.started:break
        time.sleep(.1)
    vite=subprocess.Popen(['cmd','/c','pnpm dev --port 5190 --strictPort'],cwd=ROOT/'web',env={**os.environ,'MUSIC_CORE_API_TARGET':'http://127.0.0.1:8012'},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    url='http://127.0.0.1:5190';results=[]
    try:
        for _ in range(100):
            try:
                if httpx.get(url).status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.2)
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,executable_path='C:/Users/86151/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe',args=['--autoplay-policy=no-user-gesture-required'])
            for provider,query,mid in SAMPLES:
                page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                record={'provider':provider,'platformId':mid,'options':[]};results.append(record)
                try:
                    page.goto(url);page.wait_for_load_state('networkidle')
                    page.locator(f'.primary-sources input[value="{provider}"]').check()
                    for other in ('kuwo','qq','netease','migu'):
                        if other!=provider:page.locator(f'.primary-sources input[value="{other}"]').uncheck()
                    page.locator('#query').fill(query);page.locator('#query').press('Enter');page.wait_for_timeout(4000)
                    row=page.locator(f'.song-row[data-platform-id="{mid}"]').first
                    if not row.count():
                        for button in page.locator('.versions-toggle').all():button.click()
                    for quality in QUALITIES:
                        with page.expect_response(lambda r:r.url.endswith('/api/downloads/options'),timeout=25000) as response:
                            row.locator('.action-download').click(timeout=15000)
                        option=response.value.json()
                        if quality!='auto':
                            with page.expect_response(lambda r:r.url.endswith('/api/downloads/options'),timeout=25000) as response:
                                page.locator(f'input[name="download-quality"][value="{quality}"]').check()
                            option=response.value.json()
                        item={'requested':quality,'preview':option};record['options'].append(item)
                        print(json.dumps({'provider':provider,'quality':quality,'preview':option},ensure_ascii=False),flush=True)
                        page.screenshot(path=str(shots/f'{provider}-{quality}.png'))
                        if provider=='netease' and quality=='auto':
                            for width in (1440,768,390):
                                page.set_viewport_size({'width':width,'height':844})
                                for theme in ('light','dark'):
                                    page.evaluate('theme=>document.documentElement.dataset.theme=theme',theme);page.wait_for_timeout(200)
                                    assert page.locator('.quality-dialog').evaluate('el=>el.scrollWidth<=el.clientWidth')
                                    page.screenshot(path=str(shots/f'dialog-{width}-{theme}.png'))
                            page.set_viewport_size({'width':1440,'height':1000})
                        if option['availability']!='available':
                            assert page.get_by_role('button',name='确认下载',exact=True).is_disabled();page.get_by_role('button',name='关闭音质选择').click();continue
                        with page.expect_response(lambda r:r.url.endswith('/api/downloads') and r.request.method=='POST') as created:
                            page.get_by_role('button',name='确认下载',exact=True).click()
                        task=created.value.json();identifier=task['id']
                        for _ in range(360):
                            task=page.request.get(url+'/api/downloads/'+identifier).json()
                            if task['status'] in ('completed','failed','cancelled'):break
                            page.wait_for_timeout(500)
                        item['task']=task;item['resolution']=getattr(getattr(app.state,provider),'last_resolution',None)
                        if task['status']=='completed':
                            path=app.state.downloads.root/task['filename'];item['diskBytes']=path.stat().st_size
                            probe=subprocess.run(['C:/tool/ffmpeg/bin/ffprobe.exe','-v','error','-show_entries','stream=codec_name,sample_rate,bit_rate:format=duration,size','-of','json',str(path)],capture_output=True,text=True)
                            item['ffprobe']=json.loads(probe.stdout) if probe.returncode==0 else {'error':probe.stderr[:300]}
                        print(json.dumps({'provider':provider,'quality':quality,'task':task},ensure_ascii=False),flush=True)
                        (OUT/'real-quality.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
                    record['pageErrors']=errors
                except Exception as e:record['error']=str(e)[:700];print(json.dumps({'provider':provider,'error':record['error']},ensure_ascii=False),flush=True)
                finally:page.close();(OUT/'real-quality.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
            browser.close()
    finally:
        server.should_exit=True;thread.join(10);subprocess.run(['taskkill','/PID',str(vite.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

if __name__=='__main__':main()
