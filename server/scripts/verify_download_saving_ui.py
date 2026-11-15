"""保存方式与处理阶段的浏览器HTTP夹具验收，不冒充真实转换。"""
import argparse
import os
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(os.environ.get('MUSIC_CORE_VERIFY_OUT',ROOT/'.runtime/verify-download-saving-ui'))

def main():
    parser=argparse.ArgumentParser(description='受控验证下载保存方式和转换界面')
    parser.add_argument('--url',default=os.environ.get('MUSIC_CORE_WEB_URL','http://127.0.0.1:5174'),help='已运行的 Vue 客户端地址')
    args=parser.parse_args()
    screenshots=OUT/'screenshots';screenshots.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH'))
        page=browser.new_page(viewport={'width':1440,'height':800});state={'available':False};tasks=[];files=[];posts=[]
        page.route('**/api/search',lambda r:r.fulfill(json={'items':[{'identity':{'providerId':'kuwo','platformId':'1'},'title':'保存方式验收','artists':['人工'],'durationSeconds':240}]}))
        def options(r):
            q=r.request.post_data_json.get('quality','auto');flac=q=='auto'
            r.fulfill(json={'quality':q,'availability':'available','representation':{'codec':'flac' if flac else 'mp3','lossless':flac,'sizeBytes':50000000,'sampleRateHz':44100,'bitrateBps':None if flac else 320000},'conversion':{'available':state['available'],'reason':'本机暂不可转换，仍可保留原格式'},'errorCode':None})
        def operations(r):
            if r.request.method=='GET':r.fulfill(json=tasks);return
            body=r.request.post_data_json;posts.append(body)
            task={'id':'converting','identity':body['identity'],'quality':body['quality'],'outputMode':body['outputMode'],'expectedSourceCodec':body['expectedSourceCodec'],'title':'保存方式验收','artist':'人工','status':'downloading','phase':'transcoding','receivedBytes':50000000,'totalBytes':50000000,'createdAt':1,'updatedAt':1};tasks.append(task);r.fulfill(status=202,json=task)
        page.route('**/api/downloads/options',options);page.route('**/api/downloads',operations);page.route('**/api/downloads/files',lambda r:r.fulfill(json=files))
        page.route('**/api/downloads/converting/cancel',lambda r:(tasks[0].update(status='cancelled',updatedAt=2),r.fulfill(json=tasks[0])))
        # 本夹具验收本地成品与通知，不能依赖被测服务当前的 browser/local 配置。
        page.route('**/api/downloads/settings', lambda r: r.fulfill(json={'mode':'local','canManage':False,'deploymentLocked':False}))
        page.goto(args.url.rstrip('/')+'/search?q=保存');page.wait_for_load_state('networkidle')
        page.locator('.action-download').click();page.wait_for_timeout(150)
        summary = page.locator('.quality-dialog').inner_text()
        assert 'FLAC · 47.7 MB' in summary and 'kHz' not in summary and '响应大小' not in summary
        assert page.locator('input[value="mp3_320"]').is_disabled() and page.locator('input[value="original"]').is_enabled()
        page.get_by_role('button',name='关闭音质选择').click();state['available']=True
        page.locator('.action-download').click();page.wait_for_timeout(150)
        page.locator('input[value="mp3_192"]').check();assert '预计' in page.locator('.save-options').inner_text()
        page.locator('input[name="download-quality"][value="high"]').check();page.wait_for_timeout(150);assert not page.locator('.save-options').count()
        page.locator('input[name="download-quality"][value="auto"]').check();page.wait_for_timeout(150);assert page.locator('input[value="original"]').is_checked()
        page.locator('input[value="mp3_192"]').check()
        for width in (1440,768,390):
            page.set_viewport_size({'width':width,'height':500})
            for theme in ('light','dark'):
                page.evaluate('theme=>document.documentElement.dataset.theme=theme',theme);page.wait_for_timeout(150)
                assert page.locator('.quality-dialog').evaluate('el=>el.scrollWidth<=el.clientWidth&&el.scrollHeight>el.clientHeight')
                page.locator('.quality-dialog').evaluate('el=>el.scrollTop=el.scrollHeight')
                page.screenshot(path=str(screenshots/f'conversion-controlled-saving-{width}-{theme}.png'))
        page.get_by_role('button',name='确认下载').click();page.wait_for_timeout(200)
        assert posts[0]['outputMode']=='mp3_192' and posts[0]['expectedSourceCodec']=='flac'
        page.locator('.mobile-tabbar').get_by_role('link',name='下载',exact=True).click();page.wait_for_timeout(200)
        page.get_by_role('tab',name='正在下载').click();assert '转换中' in page.locator('.download-row').inner_text()
        assert not page.locator('.download-row progress').get_attribute('value')
        assert '下载成功' not in page.locator('.client-notice').all_text_contents()
        page.get_by_role('button',name='取消',exact=True).click();page.wait_for_timeout(200);assert '已取消' in page.locator('.download-row').inner_text()
        tasks[0].update(status='downloading',phase='transcoding',updatedAt=3)
        page.get_by_role('button',name='刷新下载列表').click();page.wait_for_timeout(150)
        tasks[0].update(status='failed',errorCode='upstream_invalid_response',updatedAt=4)
        page.get_by_role('button',name='刷新下载列表').click();page.wait_for_timeout(150);assert '下载失败' in page.locator('.client-notice').inner_text()
        tasks[0].update(status='downloading',phase='verifying',updatedAt=5)
        page.get_by_role('button',name='刷新下载列表').click();page.wait_for_timeout(150);assert '正在验证最终文件' in page.locator('.download-row').inner_text()
        tasks[0].update(status='completed',phase='completed',fileId='final-file',format='mp3',filename='final.mp3',finalSizeBytes=6000000,updatedAt=6)
        files.append({'fileId':'final-file','filename':'final.mp3','format':'mp3','sizeBytes':6000000,'modifiedAt':6})
        page.get_by_role('button',name='刷新下载列表').click();page.wait_for_timeout(200);assert '下载成功' in page.locator('.client-notice').inner_text()
        assert '5.7 MB' in page.locator('.download-row').inner_text()
        page.get_by_role('button',name='关闭提示').click();page.get_by_role('button',name='刷新下载列表').click();page.wait_for_timeout(150);assert not page.locator('.client-notice').count()
        # 同一受控夹具继续验证失败保底与重试反馈，不冒充在线来源。
        tasks[0].update(status='downloading',phase='source_verifying',updatedAt=7)
        page.get_by_role('button',name='刷新下载列表').click();page.wait_for_timeout(200)
        assert '正在校验源文件' in page.locator('.download-row').inner_text()
        tasks[0].update(status='failed',phase='output_verifying',sourcePreserved=True,errorCode='conversion_failed',fileId='kept',filename='kept.flac',format='flac',updatedAt=8)
        files.append({'fileId':'kept','filename':'kept.flac','format':'flac','sizeBytes':50000000,'modifiedAt':8})
        page.get_by_role('button',name='刷新下载列表').click();page.wait_for_timeout(250)
        assert '转换失败，已保留 FLAC' in page.locator('.download-row').inner_text()
        assert '转换失败，已保留 FLAC' in page.locator('.client-notice').inner_text()
        page.screenshot(path=str(screenshots/'conversion-preserved-flac.png'))
        page.get_by_role('tab',name='下载歌曲',exact=True).click()
        assert page.locator('[data-filename="kept.flac"]').count()==1
        assert '转换失败，已保留 FLAC' in page.locator('[data-filename="kept.flac"]').inner_text(), page.locator('[data-filename="kept.flac"]').inner_text()
        # 自有合法FLAC验证原生Audio本地播放，不写用户下载目录。
        import subprocess
        from app.transcode import tools
        executable, _ = tools()
        fixture = OUT/'playback-fixture.flac'
        subprocess.run([executable,'-nostdin','-v','error','-y','-f','lavfi','-i','sine=frequency=440:duration=4','-c:a','flac',str(fixture)],check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        page.route('**/api/downloads/files/kept/stream',lambda r:r.fulfill(body=fixture.read_bytes(),content_type='audio/flac'))
        page.set_viewport_size({'width':390,'height':844})
        page.locator('[data-filename="kept.flac"] .download-identity').click()
        page.wait_for_function('document.querySelector("audio") && !document.querySelector("audio").paused && document.querySelector("audio").currentTime>0')
        page.screenshot(path=str(screenshots/'conversion-preserved-local-play.png'))
        page.get_by_role('tab',name='正在下载').click()
        def retry(r):
            task={**tasks[0],'id':'retry','status':'downloading','phase':'transcoding','sourcePreserved':False,'fileId':None,'filename':None,'updatedAt':9}
            tasks.append(task);r.fulfill(status=202,json=task)
        page.route('**/api/downloads/converting/retry',retry)
        page.get_by_role('button',name='重试',exact=True).click();page.wait_for_timeout(250)
        assert '已发起重试，请查看新任务' in page.locator('.downloads-view').inner_text()
        assert '转换中' in page.locator('.downloads-view').inner_text()
        print('SAVING_UI_PASS: missing encoder, lossless-only choices, reset, estimate, short scroll/theme, same task stages/cancel/failure, final size, one success notification')
        browser.close()

if __name__=='__main__':main()
