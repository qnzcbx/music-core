"""复核已保存成品及真实在线转换取消；不重新生成既有成品。"""
import asyncio
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
    records=json.loads((OUT/'real-saving.json').read_text(encoding='utf-8'));results=[];processes=[]
    original=asyncio.create_subprocess_exec
    async def tracked(*args,**kwargs):
        process=await original(*args,**kwargs)
        if Path(str(args[0])).name.lower() in ('ffmpeg.exe','ffprobe.exe','ffmpeg','ffprobe'):processes.append(process)
        return process
    asyncio.create_subprocess_exec=tracked
    app=create_app(download_settings=DownloadSettings(directory=ROOT/'downloads/40-E-2B'))
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8014,log_level='critical',access_log=False));thread=threading.Thread(target=server.run,daemon=True);thread.start()
    for _ in range(100):
        if server.started:break
        time.sleep(.1)
    vite=subprocess.Popen(['cmd','/c','pnpm dev --port 5191 --strictPort'],cwd=ROOT/'web',env={**os.environ,'MUSIC_CORE_API_TARGET':'http://127.0.0.1:8014'},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    url='http://127.0.0.1:5191'
    try:
        for _ in range(100):
            try:
                if httpx.get(url).status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.2)
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,executable_path='C:/Users/86151/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe',args=['--autoplay-policy=no-user-gesture-required'])
            page=browser.new_page(viewport={'width':1440,'height':1000});page.goto(url+'/downloads');page.wait_for_load_state('networkidle');page.evaluate('window.originalAudio=document.querySelector("audio")')
            for record in records:
                if record.get('task',{}).get('format')!='mp3':continue
                name=record['task']['filename'];item=next(item for item in page.locator('.saved-row').all() if item.get_attribute('data-filename')==name)
                item.locator('.download-identity').click();page.wait_for_function('document.querySelector("audio").currentTime>.1')
                page.get_by_role('button',name='暂停',exact=True).click();assert page.locator('audio').evaluate('a=>a.paused')
                page.get_by_role('button',name='播放',exact=True).click();page.get_by_label('播放进度',exact=True).evaluate('el=>{el.value=Number(el.max)*.5;el.dispatchEvent(new Event("input",{bubbles:true}));el.dispatchEvent(new Event("change",{bubbles:true}));}')
                page.wait_for_function('!document.querySelector("audio").seeking&&document.querySelector("audio").currentTime>100')
                assert page.locator('audio').evaluate('a=>a===window.originalAudio');record['localPlayPauseSeek']=True
            # 当前本地播放保持，正常搜索并从同一Vue入口创建新的在线任务。
            page.locator('#query').fill('许嵩 天龙八部之宿敌');page.locator('#query').press('Enter');page.wait_for_timeout(1000)
            page.locator('.source-selector input[value="netease"]').check();page.locator('.source-selector input[value="kuwo"]').uncheck();page.wait_for_timeout(4000)
            row=page.locator('.song-row[data-platform-id="167691"]').first
            with page.expect_response(lambda r:r.url.endswith('/api/downloads/options'),timeout=35000) as response:row.locator('.action-download').click()
            with page.expect_response(lambda r:r.url.endswith('/api/downloads/options'),timeout=35000) as response:page.locator('input[name="download-quality"][value="lossless"]').check()
            assert response.value.json()['representation']['codec']=='flac'
            page.locator('input[value="mp3_192"]').check()
            before={p.name for p in app.state.downloads.root.iterdir()}
            with page.expect_response(lambda r:r.url.endswith('/api/downloads') and r.request.method=='POST') as response:page.get_by_role('button',name='确认下载').click()
            task=response.value.json();identifier=task['id']
            page.evaluate("history.pushState({},'', '/downloads');dispatchEvent(new PopStateEvent('popstate'))");page.get_by_role('tab',name='正在下载').click()
            for _ in range(3000):
                task=page.request.get(url+'/api/downloads/'+identifier).json()
                if task.get('phase')=='transcoding':break
                assert task['status'] not in ('completed','failed','cancelled'),task
                page.wait_for_timeout(30)
            assert task['phase']=='transcoding'
            page.locator(f'.download-row[data-task-id="{identifier}"]').get_by_role('button',name='取消',exact=True).click();page.wait_for_timeout(500)
            task=page.request.get(url+'/api/downloads/'+identifier).json();assert task['status']=='cancelled' and not task.get('fileId')
            assert {p.name for p in app.state.downloads.root.iterdir()}==before
            assert all(process.returncode is not None for process in processes)
            assert page.locator('audio').evaluate('a=>a===window.originalAudio&&!a.paused')
            results.append({'realOnlineCancel':True,'phaseAtCancel':'transcoding','temporaryFilesCleaned':True,'processesExited':len(processes),'sameAudioContinues':True})
            page.screenshot(path=str(OUT/'screenshots/cancelled-conversion.png'));browser.close()
    finally:
        asyncio.create_subprocess_exec=original;server.should_exit=True;thread.join(10);subprocess.run(['taskkill','/PID',str(vite.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        (OUT/'real-saving.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8');(OUT/'followup.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(results),flush=True)

if __name__=='__main__':main()
