"""任务01真实Chromium过渡采样；受控音频不冒充在线取链成功。"""
import os
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'server/scripts'))

def main():
    path=ROOT/'server/scripts/verify_vue_player.py'
    source=path.read_text(encoding='utf-8').replace('8002','8006').replace('5175','5184')
    out=ROOT/'docs/archive/21-模板连续过渡/screenshots'
    os.environ['MUSIC_CORE_VERIFY_OUT']=str(out);sys.argv=[str(path),'--controlled']
    source=source.replace('from app.lyrics import LyricDocument','from app.lyrics import LyricDocument,LyricLine')
    source=source.replace("title=f'人工测试{i}',artists=('人工',)","title=f'人工测试{i}',artists=('人工',),cover='http://p2.music.126.net/Qs9WYbQu3TR7zOF3WdRtZw==/109951173976591536.jpg' if i==1 else None")
    source=source.replace("return LyricDocument(identity=identity,status='unavailable')","return LyricDocument(identity=identity,status='synced',lines=tuple(LyricLine(startMs=i*2000,endMs=(i+1)*2000,text=f'过渡歌词{i}') for i in range(20)))")
    extra="""
            print('AUDIO_READY',flush=True)
            page.get_by_role('button',name='打开沉浸式播放器',exact=True).click();page.locator('.immersive-player').wait_for();page.wait_for_timeout(1000)
            page.evaluate('window.choose=value=>document.querySelector(".immersive-player").__vueParentComponent.setupState.selectLayout(value)')
            page.evaluate('window.originalLyric=document.querySelector(".lyric-scroll");window.originalCover=document.querySelector("[data-player-cover]")')
            page.locator('audio').evaluate('a=>a.loop=true')
            baseline=len(opened);counts=[]
            for width in (1440,768,390):
                page.set_viewport_size({'width':width,'height':900});page.wait_for_timeout(200)
                page.evaluate('choose("square-cover")');page.wait_for_timeout(850)
                for target in ('vinyl-wide','square-cover'):
                    print('SAMPLING',width,target,flush=True)
                    for sample in (0,25,50,75,100):
                        page.evaluate('value=>choose(value)','square-cover' if target=='vinyl-wide' else 'vinyl-wide');page.wait_for_timeout(850)
                        page.evaluate('value=>choose(value)',target);page.wait_for_timeout(900 if sample==100 else max(20,sample*7.6))
                        if sample<100:
                            assert page.locator('.layout-cover-flight').count()==1, {'errors':errors,'layout':page.locator('.immersive-player').get_attribute('data-player-layout'),'sample':sample,'scroll':page.locator('.immersive-player').evaluate('el=>el.scrollTop')}
                            box=page.locator('.layout-cover-flight').bounding_box()
                            counts.append({'width':width,'target':target,'sample':sample,'box':box})
                        else:assert not page.locator('.layout-cover-flight').count()
                        page.screenshot(path=str(OUT/f'{width}-{target}-{sample}.png'))
                        page.wait_for_timeout(850)
                    assert page.evaluate('document.querySelector(".lyric-scroll")===originalLyric&&document.querySelector("[data-player-cover]")===originalCover')
                    assert page.locator('audio').evaluate('a=>a===window.firstAudio&&!a.paused') and len(opened)==baseline
                for layout in ('classic','vinyl-wide','classic'):
                    page.evaluate('value=>choose(value)',layout);page.wait_for_timeout(850)
            page.set_viewport_size({'width':1440,'height':1000})
            for value in ('square-cover','vinyl-wide','square-cover','vinyl-wide'):
                page.evaluate('value=>choose(value)',value);page.wait_for_timeout(110)
            page.wait_for_timeout(900);assert not page.locator('.layout-cover-flight').count()
            page.get_by_role('button',name='暂停',exact=True).click();page.evaluate('choose("square-cover")');page.wait_for_timeout(850)
            assert page.locator('audio').evaluate('a=>a.paused')
            page.evaluate('choose("vinyl-wide")');page.wait_for_timeout(100);page.set_viewport_size({'width':768,'height':900});page.wait_for_timeout(150)
            assert not page.locator('.layout-cover-flight').count()
            page.emulate_media(reduced_motion='reduce');page.evaluate('choose("square-cover")');page.wait_for_timeout(100);assert not page.locator('.layout-cover-flight').count()
            page.emulate_media(reduced_motion='no-preference')
            # 切换到无封面的第二首，随后使用真实缺省封面过渡。
            page.get_by_role('button',name='收起歌曲详情页',exact=True).first.click();page.wait_for_timeout(600)
            page.locator('.song-row[data-platform-id="2"] .action-play').click();page.wait_for_timeout(500)
            page.get_by_role('button',name='打开沉浸式播放器',exact=True).click();page.wait_for_timeout(700)
            for theme in ('light','dark'):
                page.evaluate('theme=>document.documentElement.dataset.theme=theme',theme)
                for value in ('vinyl-wide','square-cover'):
                    page.evaluate('value=>choose(value)',value);page.wait_for_timeout(100);assert page.locator('.layout-cover-flight').count()==1
                    page.screenshot(path=str(OUT/f'fallback-{theme}-{value}.png'));page.wait_for_timeout(850)
            # 动画中换歌由既有世代重置清理代理，正常切歌仍可执行。
            page.evaluate('choose("vinyl-wide")');page.wait_for_timeout(100)
            page.evaluate('document.querySelector(".immersive-player").__vueParentComponent.setupState.player.queue.previous()');page.wait_for_timeout(500)
            assert not page.locator('.layout-cover-flight').count()
            assert page.locator('audio').evaluate('a=>a===window.firstAudio')
            pending=[];page.route('https://example.invalid/pending-cover',lambda route:pending.append(route))
            page.locator('[data-player-cover] img').evaluate('el=>el.src="https://example.invalid/pending-cover"');page.wait_for_timeout(50)
            page.evaluate('choose("square-cover")');page.wait_for_timeout(80)
            assert not page.locator('.layout-cover-flight').count()
            for route in pending:route.abort()
            page.wait_for_timeout(300)
            assert not errors,errors
            result=OUT.parent/'frames.json'
            if result.exists():
                previous=json.loads(result.read_text(encoding='utf-8'));widths={item['width'] for item in counts};counts=[item for item in previous if item['width'] not in widths]+counts
            result.write_text(json.dumps(counts,ensure_ascii=False,indent=2),encoding='utf-8')
            print('LAYOUT_PASS: frame samples, 1440/768/390, real/fallback covers, classic regression, rapid reversal, resize, reduced motion, paused, same Audio/lyrics/cover; no extra Open',flush=True)
            browser.close()
            return
"""
    source=source.replace("            assert page.locator('audio').count()==1","            assert page.locator('audio').count()==1\n"+extra,1)
    if os.environ.get('LAYOUT_WIDTH'):source=source.replace('for width in (1440,768,390):',f'for width in ({int(os.environ["LAYOUT_WIDTH"])},):')
    exec(compile(source,str(path),'exec'),{'__name__':'__main__','__file__':str(path)})

if __name__=='__main__':main()
