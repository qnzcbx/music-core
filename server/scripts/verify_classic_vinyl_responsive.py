"""经典与大唱片的响应式FLIP过程验收，使用受控真实Audio。"""
import os
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'server/scripts'))

def main():
    path=ROOT/'server/scripts/verify_vue_player.py'
    source=path.read_text(encoding='utf-8').replace('8002','8006').replace('5175','5184')
    os.environ['MUSIC_CORE_VERIFY_OUT']=str(ROOT/'docs/archive/21-模板连续过渡/screenshots')
    sys.argv=[str(path),'--controlled']
    extra="""
            page.locator('audio').evaluate('a=>a.loop=true')
            page.get_by_role('button',name='打开沉浸式播放器',exact=True).click();page.locator('.immersive-player').wait_for();page.wait_for_timeout(700)
            page.evaluate('window.choose=value=>document.querySelector(".immersive-player").__vueParentComponent.setupState.selectLayout(value)')
            page.evaluate('window.oldRotor=document.querySelector(".record-art-rotor");window.oldLyric=document.querySelector(".lyric-scroll")')
            baseline=len(opened);records=[]
            for width,height in ((1440,900),(768,900),(390,900),(768,600)):
                page.set_viewport_size({'width':width,'height':height});page.wait_for_timeout(150)
                for target,start in (('vinyl-wide','classic'),('classic','vinyl-wide')):
                    print('CLASSIC_FLIP',width,height,target,flush=True)
                    for percent in (0,25,50,75,100):
                        page.evaluate('value=>choose(value)',start);page.wait_for_timeout(850)
                        before=page.locator('.turntable').bounding_box()
                        page.evaluate('value=>choose(value)',target);page.wait_for_timeout(900 if percent==100 else max(20,percent*7.6))
                        box=page.locator('.turntable').bounding_box();transform=page.locator('.turntable').evaluate('el=>getComputedStyle(el).transform')
                        if percent in (25,50):assert transform!='none', {'width':width,'height':height,'target':target,'percent':percent,'transform':transform}
                        if percent==100:assert transform=='none'
                        records.append({'width':width,'height':height,'target':target,'percent':percent,'before':before,'box':box,'transform':transform})
                        page.screenshot(path=str(OUT/f'classic-{width}-{height}-{target}-{percent}.png'));page.wait_for_timeout(850)
                    assert page.locator('audio').evaluate('a=>a===window.firstAudio&&!a.paused') and len(opened)==baseline
                    assert page.evaluate('oldRotor===document.querySelector(".record-art-rotor")&&oldLyric===document.querySelector(".lyric-scroll")')
            # 快速切换与暂停只作用于视觉，不改变媒体。
            page.set_viewport_size({'width':768,'height':900});page.get_by_role('button',name='暂停',exact=True).click()
            for value in ('classic','vinyl-wide','classic','vinyl-wide'):
                page.evaluate('value=>choose(value)',value);page.wait_for_timeout(100)
            page.wait_for_timeout(900)
            assert page.locator('audio').evaluate('a=>a.paused')
            assert page.locator('.turntable').evaluate('el=>!el.style.transform')
            page.evaluate('choose("classic")');page.wait_for_timeout(100);page.set_viewport_size({'width':390,'height':700});page.wait_for_timeout(150)
            assert page.locator('.turntable').evaluate('el=>!el.style.transform')
            page.emulate_media(reduced_motion='reduce');page.evaluate('choose("vinyl-wide")');page.wait_for_timeout(100)
            assert page.locator('.turntable').evaluate('el=>!el.style.transform')
            assert not errors,errors
            (OUT.parent/'classic-responsive.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
            print('CLASSIC_RESPONSIVE_PASS: 1440/768/390 and short height; both directions/intermediate transforms; single Audio, same rotor/lyrics, pause/rapid/resize/reduced cleanup',flush=True)
            browser.close()
            return
"""
    source=source.replace("            assert page.locator('audio').count()==1","            assert page.locator('audio').count()==1\n"+extra,1)
    exec(compile(source,str(path),'exec'),{'__name__':'__main__','__file__':str(path)})

if __name__=='__main__':main()
