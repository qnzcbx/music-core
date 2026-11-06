"""自有受控下载与WAV同时运行，验证取消和断流不改变真实audio。"""
import argparse
import asyncio
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import httpx
import uvicorn
from playwright.sync_api import sync_playwright
from app.main import create_app
from app.models import ResolvedMedia, MediaRepresentation
from app.downloads import DownloadSettings
from app.core.media_store import MediaSettings
from recovery_fixture import FaultUpstream, allow_fixture_target


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--browser',required=True);args=parser.parse_args()
    upstream=FaultUpstream();closed=[]
    async def resolve(identity,options=None):
        if options and options.purpose=='download':
            return ResolvedMedia(id='fixture',identity=identity,resolvedAt=1,representation=MediaRepresentation(),
                                 upstreamUrl='https://fixture.kuwo.cn/download/'+identity.platformId)
        return await upstream.resolve(identity)
    async def handle(request):
        if '/download/' not in request.url.path:return await upstream.handle(request)
        identifier=request.url.path.rsplit('/',1)[1]
        class Slow(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'ID3'+b'x'*65533
                for _ in range(1000):
                    await asyncio.sleep(.05)
                    if identifier=='2':raise httpx.ReadError('自有流受控断开')
                    yield b'x'*65536
            async def aclose(self):closed.append(identifier)
        return httpx.Response(200,stream=Slow())
    with tempfile.TemporaryDirectory(prefix='music-download-browser-') as directory:
        app=create_app(dev_player=True,transport=httpx.MockTransport(handle),target_check=allow_fixture_target,
                       download_settings=DownloadSettings(directory=Path(directory)),
                       media_settings=MediaSettings(media_ttl=.4,sweep_interval=.1))
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,access_log=False,log_level='critical'))
        thread=threading.Thread(target=server.run,daemon=True);thread.start()
        try:
            for _ in range(100):
                if server.started:break
                time.sleep(.05)
            assert server.started
            app.state.kuwo.resolve=resolve
            with sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True,executable_path=args.browser,args=['--autoplay-policy=no-user-gesture-required'])
                try:
                    page=browser.new_page();page.goto(f'http://127.0.0.1:{port}/dev/player')
                    page.locator('#rid').fill('1');page.locator('#open').click()
                    page.wait_for_function("document.querySelector('audio').currentTime>1")
                    page.evaluate("window.originalAudio=document.querySelector('audio')")
                    leases=set(app.state.playback_leases.entries);opens=len(upstream.opens)
                    before=page.locator('audio').evaluate('a=>a.currentTime')
                    def create(track):
                        return page.evaluate("async track=>(await fetch('/api/downloads',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({identity:{providerId:'kuwo',platformId:track}})})).json()",track)
                    job=create('1')
                    page.wait_for_timeout(600)
                    progress=page.evaluate("async id=>(await fetch('/api/downloads/'+id)).json()",job['id'])
                    assert progress['status']=='downloading' and progress['receivedBytes']>0
                    result=page.evaluate("async id=>(await fetch('/api/downloads/'+id+'/cancel',{method:'POST'})).json()",job['id'])
                    assert result['status']=='cancelled' and '1' in closed
                    failed=create('2');page.wait_for_timeout(400)
                    failure=page.evaluate("async id=>(await fetch('/api/downloads/'+id)).json()",failed['id'])
                    assert failure['status']=='failed' and '2' in closed
                    after=page.locator('audio').evaluate("a=>({time:a.currentTime,paused:a.paused,error:a.error?.code??null,same:a===window.originalAudio})")
                    assert after['time']>before and not after['paused'] and after['error'] is None and after['same']
                    assert set(app.state.playback_leases.entries)==leases and len(upstream.opens)==opens
                    assert not list(Path(directory).iterdir())
                    page.locator('#close').click();page.wait_for_timeout(700)
                    assert not app.state.media_store.records
                    print(json.dumps({'cancelledAfterBytes':progress['receivedBytes'],'cancelledStreamClosed':True,
                        'failedStreamClosed':True,'beforeTime':before,'afterAudio':after,'playbackOpensUnchanged':True,
                        'leaseUnchangedDuringDownload':True,'filesAfterCancelAndFailure':0,'remainingRecords':0},ensure_ascii=False))
                finally:browser.close()
        finally:
            server.should_exit=True;thread.join(timeout=10);assert not thread.is_alive()


if __name__=='__main__':main()
