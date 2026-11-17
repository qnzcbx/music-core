"""真实 WebView2 的下载入口受控回归，不进行文件保存。"""
import json,time
from pathlib import Path
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser=p.chromium.connect_over_cdp('http://127.0.0.1:9223')
    page=browser.contexts[0].pages[0]
    page.goto('http://tauri.localhost/')
    page.evaluate("localStorage.setItem('music-core.search.sources.v1',JSON.stringify(['kuwo']))")
    page.reload();page.wait_for_load_state('networkidle')
    page.evaluate("""()=>{
      const original=window.__TAURI__.core.invoke;
      window.__TAURI__={...window.__TAURI__,core:{...window.__TAURI__.core}};
      window.probeCalls=0;
      window.__TAURI__.core.invoke=async(command,args)=>{
        if(args.path==='/api/search') return {items:[
          {identity:{providerId:'kuwo',platformId:'123'},title:'未知甲',artists:['夹具'],downloadAllowed:null},
          {identity:{providerId:'kuwo',platformId:'124'},title:'未知乙',artists:['夹具'],downloadAllowed:null},
          {identity:{providerId:'kuwo',platformId:'125'},title:'禁止',artists:['夹具'],downloadAllowed:false}]};
        if(args.path==='/api/downloads/options'){
          window.probeCalls++;
          if(window.probeMode==='late'&&args.body.identity.platformId==='123') {
            await new Promise(resolve=>setTimeout(resolve,1500));
            return {quality:'standard',availability:'unavailable',errorCode:'access_denied'};
          }
          if(window.probeCalls===1) return {quality:'standard',availability:'unavailable',errorCode:'upstream_timeout'};
          return {quality:'standard',availability:'available',representation:{codec:'mp3',bitrateBps:128000,sampleRateHz:44100,lossless:false}};
        }
        return original(command,args);
      };
    }""")
    page.locator('#query').fill('夹具');page.locator('#query').press('Enter')
    a=page.locator('[data-platform-id="123"] .action-download');a.wait_for()
    assert not a.is_disabled()
    assert page.locator('[data-platform-id="125"] .action-download').is_disabled()
    assert page.evaluate('window.probeCalls')==0
    a.click(position={'x':20,'y':20})
    page.get_by_role('button',name='重新检测',exact=True).wait_for()
    page.get_by_role('button',name='重新检测',exact=True).click()
    confirm=page.get_by_role('button',name='确认下载',exact=True)
    for _ in range(100):
        if confirm.is_enabled():break
        time.sleep(.05)
    assert confirm.is_enabled()
    page.get_by_role('button',name='关闭音质选择',exact=True).click()
    page.evaluate("window.probeMode='late'")
    a.click(position={'x':20,'y':20})
    page.get_by_role('button',name='关闭音质选择',exact=True).click()
    page.locator('[data-platform-id="124"] .action-download').click(position={'x':20,'y':20})
    page.wait_for_timeout(1800)
    assert '未知乙' in page.locator('dialog[open]').inner_text()
    assert confirm.is_enabled()
    page.get_by_role('button',name='关闭音质选择',exact=True).click()
    Path('.runtime/task19/entry-fixture.json').write_text(json.dumps({'missingFieldsCanCheck':True,'explicitDenialDisabled':True,'noBatchProbes':True,'timeoutRetry':True,'lateResultIsolated':True}),encoding='utf-8')
    page.reload();browser.close()
