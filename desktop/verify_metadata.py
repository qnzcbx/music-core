"""真实 WebView2 的封面像素、歌词同步及版本隔离验收。"""
import argparse
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

parser=argparse.ArgumentParser()
parser.add_argument('--pixel-failure',action='store_true')
parser.add_argument('--image-failure',action='store_true')
parser.add_argument('--out',default='.runtime/desktop-stage5')
args=parser.parse_args()
out=Path(args.out)
out.mkdir(parents=True,exist_ok=True)
with sync_playwright() as pw:
    browser=pw.chromium.connect_over_cdp('http://127.0.0.1:9223')
    page=browser.contexts[0].pages[0]
    page.wait_for_load_state('networkidle')
    if args.pixel_failure:
        page.add_init_script("CanvasRenderingContext2D.prototype.getImageData=function(){throw new DOMException('controlled pixel rejection','SecurityError')}")
    if args.image_failure:
        page.route('http://127.0.0.1:*/covers/*',lambda route:route.abort())
    def until(expression,arg=None,timeout=35):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if page.evaluate(expression,arg):return
            page.wait_for_timeout(100)
        raise AssertionError('WebView2 metadata condition timed out')
    def ipc(path,body):
        return page.evaluate('args=>window.__TAURI__.core.invoke("desktop_request",args)',{'path':path,'body':body})
    def pixels(url):
        return page.evaluate('''url=>new Promise(resolve=>{
            const image=new Image();image.crossOrigin='anonymous';
            image.onload=()=>{try {const c=document.createElement('canvas');c.width=c.height=2;
                const ctx=c.getContext('2d');ctx.drawImage(image,0,0,2,2);
                resolve({loaded:image.naturalWidth>0,pixels:ctx.getImageData(0,0,2,2).data.length});
            }catch{resolve({loaded:true,pixels:0});}};
            image.onerror=()=>resolve({loaded:false,pixels:0});image.src=url;
        })''',url)
    records=[]
    for source,mid,query in [('qq','0027oMO61wWi55','发如雪 周杰伦'),('qq','0037WF7I0yUPLu','发如雪 周杰伦'),('kuwo','228908','晴天'),('kuwo','668816586','test'),('netease','2668397359','晴天'),('migu','600919000007741344','晴天')]:
        identity={'providerId':source,'platformId':mid}
        record={'identity':identity}
        try:
            doc=ipc('/api/lyrics',identity)
            record.update(lyrics=doc['status'],lines=len(doc['lines']))
        except Exception:
            record['lyrics']='request-error'
        songs=ipc('/api/search',{'providerId':source,'query':query,'limit':15})['items']
        row=next((r for r in songs if r['identity']==identity),None)
        record['cover']=pixels(row['cover']) if row and row.get('cover') else {'loaded':False,'pixels':0}
        records.append(record)
        print(json.dumps(record,ensure_ascii=False),flush=True)
    page.evaluate("localStorage.setItem('music-core.search.sources.v1',JSON.stringify(['qq']))")
    page.reload();page.wait_for_load_state('networkidle')
    page.locator('#query').fill('发如雪 周杰伦');page.locator('#query').press('Enter')
    row=page.locator('.song-row[data-provider=qq][data-platform-id="0027oMO61wWi55"]')
    row.wait_for()
    if args.image_failure:
        until("!document.querySelector('.song-row[data-platform-id=\"0027oMO61wWi55\"] img')")
        assert row.locator('.cover-fallback').is_visible()
        page.screenshot(path=str(out/'image-failure-placeholder.png'))
        browser.close()
        raise SystemExit(0)
    until('()=>{const i=document.querySelector(\'.song-row[data-platform-id="0027oMO61wWi55"] img\');return i?.complete&&i.naturalWidth>0;}')
    row.locator('.action-play').click(position={'x':20,'y':20})
    until("!document.querySelector('audio').paused&&document.querySelector('audio').currentTime>1")
    until("()=>{const i=document.querySelector('footer.player .cover-art img');return i?.complete&&i.naturalWidth>0}")
    page.screenshot(path=str(out/'qq-list-footer.png'))
    page.get_by_role('button',name='打开沉浸式播放器',exact=True).click()
    until("document.querySelectorAll('.lyric-line').length===69")
    until("()=>{const i=document.querySelector('[data-player-cover] img');return i?.complete&&i.naturalWidth>0}")
    if args.pixel_failure:
        until("document.querySelector('[data-palette-status]')?.dataset.paletteStatus?.includes('canvas-cors-denied')")
        assert page.locator('[data-player-cover] img').evaluate('i=>i.complete&&i.naturalWidth>0')
        page.screenshot(path=str(out/'pixel-failure-cover-displayed.png'))
        browser.close()
        raise SystemExit(0)
    until("document.querySelector('[data-palette-status]')?.dataset.paletteStatus==='success'")
    assert page.locator('audio').count()==1
    for ratio in [.55,.2]:
        box=page.get_by_role('slider',name='播放进度').bounding_box()
        page.mouse.move(box['x']+2,box['y']+box['height']/2);page.mouse.down()
        page.mouse.move(box['x']+box['width']*ratio,box['y']+box['height']/2);page.mouse.up()
        until("ratio=>{const a=document.querySelector('audio');return !a.paused&&Math.abs(a.currentTime/a.duration-ratio)<.08}",ratio)
        until("()=>{const a=document.querySelector('audio');const li=document.querySelector('.lyric-current [data-time]');return li&&Number(li.dataset.time)<=a.currentTime&&a.currentTime-Number(li.dataset.time)<15}")
    page.screenshot(path=str(out/'qq-player-lyrics.png'))
    (out/'results.json').write_text(json.dumps({'samples':records,'qqListFooterPlayerImages':True,'qqForwardBackwardLyrics':True,'qqPalette':True},ensure_ascii=False,indent=2),encoding='utf-8')
    browser.close()
