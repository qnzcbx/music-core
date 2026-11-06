"""通过正常API执行一首真实下载，仅输出安全摘要；不会打印上游地址。"""
import argparse
import asyncio
import ctypes
import hashlib
import json
from pathlib import Path
import time
import httpx
from app.main import create_app
from app.downloads import DownloadSettings


def rss_bytes():
    class Memory(ctypes.Structure):
        _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(n,ctypes.c_size_t) for n in
            ('peak','working','quotaPeakPaged','quotaPaged','quotaPeakNonPaged','quotaNonPaged','pagefile','peakPagefile')]
    data=Memory();data.cb=ctypes.sizeof(data)
    ctypes.windll.kernel32.GetCurrentProcess.restype=ctypes.c_void_p
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong]
    if not ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(),ctypes.byref(data),data.cb):
        raise OSError('无法读取进程内存')
    return data.working


async def main():
    parser=argparse.ArgumentParser(description='单曲下载真实验收，不扫描曲库')
    parser.add_argument('--provider',required=True,choices=['kuwo','qq','netease','migu'])
    parser.add_argument('--track')
    parser.add_argument('--title',default='飞鸟与鱼')
    parser.add_argument('--artist',default='齐豫')
    parser.add_argument('--browser')
    parser.add_argument('--preview',action='store_true',help='沿用现有开发试听路线配置，不自动启用路线')
    args=parser.parse_args()
    app=create_app(dev_player=args.preview)
    summary={'provider':args.provider,'title':args.title,'artist':args.artist,'observations':[]}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            track=args.track
            if not track:
                response=await client.post('/api/search',json={'providerId':args.provider,'query':args.title,'limit':10})
                if response.status_code!=200:
                    print(json.dumps({'searchError':response.json()},ensure_ascii=False));return
                rows=response.json()['items']
                exact=[r for r in rows if r['title']==args.title and args.artist in r['artists']]
                if not exact:
                    print(json.dumps({'noExactMatch':True,'candidates':rows},ensure_ascii=False));return
                track=exact[0]['identity']['platformId']
            summary['platformId']=track
            response=await client.post('/api/downloads',json={'identity':{'providerId':args.provider,'platformId':track},'title':args.title,'artist':args.artist})
            assert response.status_code==202
            identifier=response.json()['id'];summary['created']=True
            start=time.monotonic();rss=[rss_bytes()];previous=None
            while time.monotonic()-start<1800:
                task=(await client.get('/api/downloads/'+identifier)).json()
                point=(task['status'],task['receivedBytes'])
                if point!=previous:
                    summary['observations'].append({'seconds':round(time.monotonic()-start,2),'status':point[0],'bytes':point[1]})
                    print(json.dumps(summary['observations'][-1]),flush=True)
                    previous=point
                rss.append(rss_bytes())
                if task['status'] in ('completed','failed','cancelled'):break
                await asyncio.sleep(.25)
            else:
                await client.post('/api/downloads/'+identifier+'/cancel');raise RuntimeError('验收超时')
            summary['task']=task
            summary['rssStartBytes']=rss[0];summary['rssPeakBytes']=max(rss);summary['rssEndBytes']=rss[-1]
            await asyncio.sleep(.05)
            summary['activeWorkers']=sum(j.worker is not None for j in app.state.downloads.jobs.values())
            summary['mediaRecords']=len(app.state.media_store.records)
            summary['playbackLeases']=len(app.state.playback_leases.entries)
            summary['parts']=len(list(app.state.downloads.root.glob('.music-core-*.part')))
            if task['status']=='completed':
                path=app.state.downloads.root/task['filename']
                digest=hashlib.sha256()
                with path.open('rb') as stream:
                    prefix=stream.read(16);digest.update(prefix)
                    while chunk:=stream.read(65536):digest.update(chunk)
                summary['file']={'path':str(path),'bytes':path.stat().st_size,'prefixHex':prefix.hex(),'sha256':digest.hexdigest()}
                assert path.stat().st_size==task['receivedBytes']
                if task['totalBytes'] is not None:assert task['totalBytes']==path.stat().st_size
                if args.browser:
                    from playwright.async_api import async_playwright
                    async with async_playwright() as playwright:
                        browser=await playwright.chromium.launch(executable_path=args.browser,headless=True)
                        try:
                            page=await browser.new_page()
                            await page.goto(path.as_uri())
                            await page.wait_for_function("() => {const a=document.querySelector('audio,video');return a && a.readyState>=1 && Number.isFinite(a.duration)}")
                            summary['localAudio']=await page.evaluate("() => {const a=document.querySelector('audio,video');return {duration:a.duration,error:a.error?.code??null}}")
                        finally:await browser.close()
    summary['task'].pop('id',None)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':asyncio.run(main())
