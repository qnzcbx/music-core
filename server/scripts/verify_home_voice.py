"""由 verify_vue_queue --home-voice 调用，复用服务与 Chromium 生命周期。"""
import json
from urllib.parse import unquote
from pathlib import Path

AUDIO_PROBE = r"""() => {
  window.voiceContexts = [];
  window.voiceStarts = 0;
  const Original = window.AudioContext;
  window.AudioContext = class extends Original {
    constructor(...args) { super(...args); this.meters = []; this.gains = []; window.voiceContexts.push(this); }
    createGain() { const node = super.createGain(); this.gains.push(node); return node; }
    createAnalyser() { const meter = super.createAnalyser(); this.meters.push(meter); return meter; }
    createOscillator() { return this.observe(super.createOscillator()); }
    createBufferSource() { return this.observe(super.createBufferSource()); }
    observe(node) {
      const start = node.start.bind(node);
      node.start = (...args) => { window.voiceStarts++; return start(...args); };
      return node;
    }
  };
}"""


def verify_home_voice(browser, url, app, out):
    out = Path(out)
    screenshots = out / 'screenshots'
    screenshots.mkdir(parents=True, exist_ok=True)
    results = []
    for width, height in [(1440, 1000), (390, 844)]:
        context = browser.new_context(viewport={'width': width, 'height': height}, has_touch=width < 600)
        context.add_init_script('(' + AUDIO_PROBE + ')()')
        page = context.new_page()
        errors, loaded = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: loaded.append(request.url))
        def go(path):
            page.evaluate('path => document.querySelector("#app").__vue_app__.config.globalProperties.$router.push(path)', path)
            page.wait_for_url(lambda current: unquote(current) == url + path)
        def count():
            return int(page.locator('.home-instrument #noteCounter').inner_text().split('·')[-1].strip())
        def wait_piano():
            page.locator('.home-instrument #noteCounter').wait_for(state='attached')
            page.wait_for_function('document.querySelector(".typing-piano-host")?.dataset.controls === "hidden"')
            assert page.locator('.home-instrument .instrument-controls:visible,.home-instrument .piano-caption:visible').count() == 0
            assert page.locator('.home-instrument #soundOn path').count() == 1
            if page.locator('.home-instrument .stage-piano').count():
                assert page.locator('.home-instrument .fascia-console').is_visible()
                assert page.locator('.home-instrument .fascia-console button:visible').count() > 0
            assert page.locator('.home-instrument .instrument-shell').evaluate('el => getComputedStyle(el).overflow === "visible"')
            assert page.locator('.typing-piano-host').evaluate('host => { const shell=host.shadowRoot.querySelector(".shell"); const style=getComputedStyle(shell); return style.backgroundImage === "none" && style.backgroundColor === "rgba(0, 0, 0, 0)" && getComputedStyle(host).backgroundColor === "rgba(0, 0, 0, 0)"; }')
        def snapshot():
            return page.evaluate('Object.fromEntries(Object.entries(localStorage).filter(([key]) => key !== "media-lab.home-background.v1"))')
        page.goto(url + '/')
        page.wait_for_load_state('networkidle')
        assert page.locator('.home-ink-background').count() == 1
        assert page.locator('.home-instrument').count() == 0
        assert not any('HomeVoiceBetween-' in request for request in loaded)
        go('/settings')
        page.get_by_role('radio', name='深色', exact=True).check()
        before_preferences = snapshot()
        page.get_by_role('radio', name='字里弦间', exact=True).check()
        assert snapshot() == before_preferences
        assert not any('HomeVoiceBetween-' in request for request in loaded)
        go('/')
        wait_piano()
        assert any('HomeVoiceBetween-' in request for request in loaded)
        assert page.locator('.home-ink-background').count() == 0
        assert page.locator('.home-instrument textarea,.home-instrument input[type=text]').count() == 0
        assert page.locator('.typing-piano-host').get_attribute('data-theme') == 'dark'
        assert count() == 0
        assert page.evaluate('voiceContexts.length') == 0
        # 不先点击乐器，真实可信的搜索输入触发第一声；没有禁用 autoplay 策略。
        page.locator('#query').click()
        page.keyboard.type('a')
        assert count() == 1
        page.wait_for_function('voiceContexts.length === 1 && voiceContexts[0].state === "running"')
        page.wait_for_function("""() => voiceContexts.some(context => context.meters.some(meter => {
          const data = new Float32Array(meter.fftSize); meter.getFloatTimeDomainData(data);
          return data.some(sample => Math.abs(sample) > 0.00001);
        }))""")
        assert page.evaluate('voiceStarts') > 0
        first_starts = page.evaluate('voiceStarts')
        page.screenshot(path=str(screenshots / f'voice-{width}-dark.png'))
        # 通过 Chromium 原生 IME 通道重现真实事件序列，不再人工补发最终 input。
        cdp = context.new_cdp_session(page)
        page.locator('#query').evaluate('input => { window.imeTrace=[]; for (const type of ["compositionstart","compositionend","input"]) input.addEventListener(type,e => imeTrace.push({type:e.type,data:e.data,inputType:e.inputType,isComposing:e.isComposing,trusted:e.isTrusted})); }')
        cdp.send('Input.imeSetComposition', {'text':'ni','selectionStart':2,'selectionEnd':2})
        assert count() == 2 and page.evaluate('voiceStarts') > first_starts
        cdp.send('Input.insertText', {'text':'你'})
        page.wait_for_timeout(50)
        assert count() == 2
        (out/f'native-ime-{width}.json').write_text(json.dumps(page.evaluate('imeTrace'),ensure_ascii=False,indent=2),encoding='utf-8')
        # 粘贴、删除、清空、程序回填均不转交乐器。
        page.locator('#query').evaluate("""input => {
          input.value = '粘贴文本';
          input.dispatchEvent(new InputEvent('input',{data:'粘贴文本',inputType:'insertFromPaste',bubbles:true}));
          input.value = '回填'; input.dispatchEvent(new Event('input',{bubbles:true}));
          input.dispatchEvent(new InputEvent('input',{data:null,inputType:'deleteContentBackward',bubbles:true}));
        }""")
        assert count() == 2
        page.get_by_role('button', name='清空输入', exact=True).click()
        assert count() == 2
        page.locator('#query').click()
        page.keyboard.press('Space')
        page.keyboard.press('ArrowLeft')
        page.keyboard.press('ArrowRight')
        page.keyboard.press('Tab')
        assert count() == 2
        assert page.locator('#query').input_value() == ' '
        assert not page.locator('#query').evaluate('input => input === document.activeElement')
        # Tab 仅导航；音色和键位提示的快捷键由已安装组件绑定处理。
        query = page.locator('#query')
        query.click()
        before_timbre = page.locator('.home-instrument #timbreText').inner_text()
        page.keyboard.press('Tab')
        assert page.locator('.home-instrument #timbreText').inner_text() == before_timbre
        query.click()
        for key, name in [('2', '毛毡'), ('3', '八音盒'), ('1', '三角')]:
            page.keyboard.press('Alt+' + key)
            assert name in page.locator('.home-instrument #timbreText').inner_text()
        labels = page.locator('.home-instrument #labelToggle').get_attribute('aria-pressed')
        page.keyboard.press('Alt+k')
        assert page.locator('.home-instrument #labelToggle').get_attribute('aria-pressed') != labels
        assert count() == 2
        # 首页不展示控件；通过组件原 API 回归内部静音契约，不增加宿主静音状态。
        page.locator('.home-instrument #soundToggle').dispatch_event('click')
        muted_starts = page.evaluate('voiceStarts')
        page.locator('#query').click()
        page.keyboard.type('人工')
        assert count() == 2 and page.evaluate('voiceStarts') == muted_starts
        page.keyboard.press('Enter')
        page.wait_for_url('**/search?q=*')
        page.locator('.song-row[data-platform-id="1"]').wait_for()
        page.wait_for_function('voiceContexts.every(context => context.state === "closed")')
        assert page.locator('.home-instrument').count() == 0
        starts_after_leave = page.evaluate('voiceStarts')
        page.locator('#query').click()
        page.keyboard.type('b')
        assert page.evaluate('voiceStarts') == starts_after_leave
        go('/')
        wait_piano()
        page.reload()
        page.wait_for_load_state('networkidle')
        wait_piano()
        assert page.locator('.home-ink-background').count() == 0
        assert page.locator('html').get_attribute('data-theme') == 'dark'
        assert page.evaluate('localStorage.getItem("media-lab.home-background.v1")') == 'voice'
        # 刷新后首次拼音预编辑直接发声，不先用英文或琴键解锁音频。
        page.locator('#query').click()
        cdp.send('Input.imeSetComposition', {'text':'ni','selectionStart':2,'selectionEnd':2})
        assert count() == 1 and page.evaluate('voiceContexts.length') == 1
        cdp.send('Input.insertText', {'text':'你'})
        assert count() == 1
        page.wait_for_function('voiceContexts.length === 1 && voiceContexts[0].state === "running"')
        page.wait_for_function('() => voiceContexts[0].meters.some(m => {const a=new Float32Array(m.fftSize);m.getFloatTimeDomainData(a);return a.some(v=>Math.abs(v)>0.00001)})')

        # 主题由宿主设置驱动，不创建独立的琴音主题或搜索声音偏好。
        go('/settings')
        page.get_by_role('radio', name='浅色', exact=True).check()
        go('/')
        wait_piano()
        assert page.locator('.typing-piano-host').get_attribute('data-theme') == 'light'
        # 物理拼音逐键响，汉字提交不额外响；移动视口也覆盖外接键盘路径。
        query = page.locator('#query')
        query.click()
        def physical(code, pressed):
            cdp.send('Input.dispatchKeyEvent', {'type':'keyDown' if pressed else 'keyUp','key':'Process','code':code,'windowsVirtualKeyCode':229})
        physical('KeyN', True)
        assert count() == 1
        cdp.send('Input.imeSetComposition', {'text':'n','selectionStart':1,'selectionEnd':1})
        assert count() == 1
        physical('KeyN', False)
        physical('KeyI', True)
        assert count() == 2
        cdp.send('Input.imeSetComposition', {'text':'ni','selectionStart':2,'selectionEnd':2})
        physical('KeyI', False)
        cdp.send('Input.insertText', {'text':'你'})
        page.wait_for_timeout(50)
        assert count() == 2
        page.get_by_role('button',name='清空输入',exact=True).click()
        query.click();page.keyboard.type('a')
        assert count() == 3
        page.get_by_role('button',name='清空输入',exact=True).click()
        if width == 1440:
            music_volume = page.locator('audio').evaluate('audio => audio.volume')
            assert page.locator('.home-instrument [data-volume-led].led-white').count() == 3
            for direction, lights, gain in [('down',2,0.64),('down',1,0.38),('down',1,0.38),('up',2,0.64),('up',3,0.88),('up',3,0.88)]:
                page.locator('.home-instrument [data-control="volume-'+direction+'"]').click()
                assert page.locator('.home-instrument [data-volume-led].led-white').count() == lights
                actual = page.evaluate('voiceContexts.filter(context => context.state !== "closed").at(-1).gains[0].gain.value')
                assert abs(actual - gain) < 0.0001, (actual,gain)
            assert page.locator('audio').evaluate('audio => audio.volume') == music_volume
        page.screenshot(path=str(screenshots / f'voice-{width}-light.png'))
        if width == 1440:
            page.set_viewport_size({'width':900,'height':900})
            page.locator('.home-instrument .shell[data-active-instrument="guqin"]').wait_for()
            assert page.locator('.home-instrument .instrument-controls:visible,.home-instrument .piano-caption:visible').count() == 0
            page.screenshot(path=str(screenshots / 'voice-guqin-light.png'))
            page.set_viewport_size({'width':width,'height':height})

        # 实际播放媒体期间切换首页背景与打字，不改变已有 Audio 或播放源。
        go('/search?q=人工')
        page.locator('.song-row[data-platform-id="1"] .action-play').click()
        page.wait_for_function('!document.querySelector("audio").paused')
        page.evaluate('window.originalAudio = document.querySelector("audio")')
        source = page.locator('audio').evaluate('audio => audio.src')
        go('/')
        wait_piano()
        page.locator('#query').click()
        page.keyboard.type('c')
        assert count() == 1
        assert page.locator('audio').evaluate('audio => audio === window.originalAudio && !audio.paused')
        assert page.locator('audio').evaluate('audio => audio.src') == source
        # 琴体容器由首页滚动区域承载，不侵占底栏。
        assert page.locator('.home-view').evaluate('el => el.getBoundingClientRect().bottom <= document.querySelector(".workspace-player").getBoundingClientRect().top + 1')
        page.screenshot(path=str(screenshots / f'voice-{width}-playing.png'))
        go('/settings')
        page.get_by_role('radio', name='墨息', exact=True).check()
        go('/')
        page.locator('.home-ink-background').wait_for()
        assert page.locator('.home-instrument').count() == 0
        page.wait_for_function('voiceContexts.every(context => context.state === "closed")')
        starts_after_ink = page.evaluate('voiceStarts')
        page.locator('#query').click()
        page.keyboard.type('x')
        assert page.evaluate('voiceStarts') == starts_after_ink
        assert page.locator('audio').evaluate('audio => audio === window.originalAudio && !audio.paused')
        assert page.locator('audio').evaluate('audio => audio.src') == source
        assert not errors, errors
        results.append({'width':width,'firstTrustedInputProducedWaveform':True,'noPianoClickBeforeFirstNote':True,
                        'imePreeditSoundsFinalCommitNoEcho':True,'nativeChromiumIMEFirstChineseWaveform':True,'pasteClearProgramFillSilent':True,
                        'mutePreventsNewAudioButSearchWorks':True,'nativeNavigationKeys':True,'physicalPinyinEachKeyNoCommitEcho':True,'controlsHiddenAndBackgroundTransparent':True,'bodyVolumeCapsuleRestored':width == 1440,
                        'backgroundPersistsAndOtherPreferencesPreserved':True,'lazyLoadedOnlyWhenSelectedOnHome':True,
                        'disposedAfterLeavingAndSwitching':True,'musicPlaybackUnchanged':True,'pageErrors':errors})
        context.close()
    result = {'cases':results,'realWindowsIME':False,'realPhoneTouchscreen':False,
              'audioEvidence':'native running AudioContext and nonzero analyser waveform; no hardware listening claim'}
    (out/'voice-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
