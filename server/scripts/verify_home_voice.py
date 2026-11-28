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


# 生产 Vue 不在元素上保留 __vueParentComponent。验收通过现有 VNode 树取得
# defineExpose 的正式接口，不为测试在产品中增加调试节点或全局状态。
VOICE_HANDLE = r"""() => {
  const visit = node => {
    if (!node) return;
    if (node.component?.exposed?.getState) return node.component.exposed;
    const mounted = visit(node.component?.subTree);
    if (mounted) return mounted;
    if (Array.isArray(node.children)) {
      for (const child of node.children) {
        const found = visit(child);
        if (found) return found;
      }
    }
  };
  return visit(document.querySelector('#app')?.__vue_app__?._container?._vnode);
}"""


def verify_home_voice(browser, url, app, out):
    out = Path(out)
    screenshots = out / 'screenshots'
    screenshots.mkdir(parents=True, exist_ok=True)
    verify_text_melody(browser, url, out)
    results = []
    for width, height in [(1440, 1000), (390, 844)]:
        context = browser.new_context(viewport={'width': width, 'height': height}, has_touch=width < 600)
        context.add_init_script('(' + AUDIO_PROBE + ')()')
        context.add_init_script('window.findVoiceHandle = ' + VOICE_HANDLE)
        page = context.new_page()
        errors, loaded = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: loaded.append(request.url))
        def go(path):
            page.evaluate('path => document.querySelector("#app").__vue_app__.config.globalProperties.$router.push(path)', path)
            page.wait_for_url(lambda current: unquote(current) == url + path)
        def count():
            return page.evaluate('findVoiceHandle().getState().counter')
        def wait_piano():
            page.locator('.typing-piano-host .shell').wait_for(state='attached')
            page.wait_for_function('!!findVoiceHandle()?.getState()')
            assert page.locator('.home-instrument .instrument-controls,.home-instrument .piano-caption,.home-instrument #instrumentMode,.home-instrument #noteCounter,.home-instrument #lastPlayed,.home-instrument #velocityFill,.home-instrument #soundToggle').count() == 0
            assert page.locator('.home-instrument [data-control="mute"]').count() == 1
            if page.locator('.home-instrument .stage-piano').count():
                assert page.locator('.home-instrument .fascia-console').is_visible()
                assert page.locator('.home-instrument .fascia-console button:visible').count() > 0
            assert page.locator('.home-instrument .instrument-shell').evaluate('el => getComputedStyle(el).overflow === "visible"')
            assert page.locator('.typing-piano-host').evaluate('host => { const shell=host.shadowRoot.querySelector(".shell"); const style=getComputedStyle(shell); return style.backgroundImage === "none" && style.backgroundColor === "rgba(0, 0, 0, 0)" && getComputedStyle(host).backgroundColor === "rgba(0, 0, 0, 0)"; }')
        def snapshot():
            return page.evaluate('Object.fromEntries(Object.entries(localStorage).filter(([key]) => key !== "music-core.home-background.v1"))')
        page.goto(url + '/')
        page.wait_for_load_state('networkidle')
        assert page.locator('.home-ink-background').count() == 1
        assert page.locator('.home-instrument').count() == 0
        assert not any('HomeVoiceBetween-' in request for request in loaded)
        go('/settings')
        page.get_by_role('radio', name='深色', exact=True).check()
        before_preferences = snapshot()
        page.get_by_role('radio', name='弦外之音', exact=True).check()
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
        before_timbre = page.evaluate('findVoiceHandle().getState().timbre')
        page.keyboard.press('Tab')
        assert page.evaluate('findVoiceHandle().getState().timbre') == before_timbre
        query.click()
        for key, name in [('2', 'felt'), ('3', 'celesta'), ('1', 'grand')]:
            page.keyboard.press('Alt+' + key)
            assert name == page.evaluate('findVoiceHandle().getState().timbre')
        labels = page.locator('.home-instrument [data-control="labels"]').get_attribute('aria-pressed')
        page.keyboard.press('Alt+k')
        assert page.locator('.home-instrument [data-control="labels"]').get_attribute('aria-pressed') != labels
        assert count() == 2
        # 首页不展示控件；通过组件原 API 回归内部静音契约，不增加宿主静音状态。
        page.evaluate('findVoiceHandle().setMuted(true)')
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
        assert page.evaluate('localStorage.getItem("music-core.home-background.v1")') == 'voice'
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
                # AudioParam 按音频渲染量子应用调度值，不能紧随点击只读一次。
                page.wait_for_function('expected => Math.abs(voiceContexts.filter(context => context.state !== "closed").at(-1).gains[0].gain.value - expected) < .0001', arg=gain)
                actual = page.evaluate('voiceContexts.filter(context => context.state !== "closed").at(-1).gains[0].gain.value')
                assert abs(actual - gain) < 0.0001, (actual,gain)
            assert page.locator('audio').evaluate('audio => audio.volume') == music_volume
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(screenshots / f'voice-{width}-light.png'))
        if width == 1440:
            page.set_viewport_size({'width':900,'height':900})
            page.locator('.home-instrument .shell[data-active-instrument="guqin"]').wait_for()
            assert page.locator('.home-instrument .instrument-controls,.home-instrument .piano-caption,.home-instrument #instrumentMode,.home-instrument #noteCounter,.home-instrument #lastPlayed,.home-instrument #velocityFill,.home-instrument #soundToggle').count() == 0
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
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
                        'mutePreventsNewAudioButSearchWorks':True,'nativeNavigationKeys':True,'physicalPinyinEachKeyNoCommitEcho':True,'demoPanelAbsentFromDOMAndBackgroundTransparent':True,'bodyVolumeCapsuleRestored':width == 1440,
                        'backgroundPersistsAndOtherPreferencesPreserved':True,'lazyLoadedOnlyWhenSelectedOnHome':True,
                        'disposedAfterLeavingAndSwitching':True,'musicPlaybackUnchanged':True,'pageErrors':errors})
        context.close()
    result = {'cases':results,'realWindowsIME':False,'realPhoneTouchscreen':False,
              'audioEvidence':'native running AudioContext and nonzero analyser waveform; no hardware listening claim'}
    (out/'voice-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))



def verify_text_melody(browser, url, out):
    """复用同一生产预览与受控媒体，验收正式安装包的琴面播放入口。"""
    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
    context.add_init_script('(' + AUDIO_PROBE + ')()')
    context.add_init_script('window.findVoiceHandle = ' + VOICE_HANDLE)
    context.add_init_script("localStorage.setItem('music-core.home-background.v1', 'voice')")
    page = context.new_page()
    errors, searches = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda request: searches.append(request.url) if '/api/search' in request.url else None)
    screenshots = Path(out) / 'screenshots'
    def go(path):
        page.evaluate('path => document.querySelector("#app").__vue_app__.config.globalProperties.$router.push(path)', path)
        page.wait_for_url(lambda current: unquote(current) == url + path)
    def count():
        return page.evaluate('findVoiceHandle().getState().counter')
    def wait_ready():
        page.locator('.typing-piano-host .shell').wait_for(state='attached')
    play = page.locator('.home-instrument [data-control="replay"]')
    query = page.locator('#query')
    page.goto(url + '/')
    page.wait_for_load_state('networkidle')
    wait_ready()
    assert page.locator('.deck-brand-silk').inner_text() == 'VOICE BETWEEN'
    assert page.locator('.deck-model-silk').inner_text() == 'STAGE PIANO'
    assert page.locator('.home-instrument .instrument-controls,.home-instrument .piano-caption,.home-instrument #instrumentMode,.home-instrument #noteCounter,.home-instrument #lastPlayed,.home-instrument #velocityFill,.home-instrument #soundToggle').count() == 0
    k, button = page.locator('[data-control="labels"]').bounding_box(), play.bounding_box()
    assert button['x'] > k['x'] and abs(button['y'] - k['y']) < 1
    assert play.locator('..').locator('.deck-led').count() == 1
    assert page.evaluate('voiceContexts.length') == 0 and count() == 0
    play.click()
    assert count() >= 1
    page.wait_for_function('voiceContexts.length === 1 && voiceContexts[0].state === "running"')
    page.wait_for_function("""() => voiceContexts[0].meters.some(m => {
        const samples = new Float32Array(m.fftSize); m.getFloatTimeDomainData(samples);
        return samples.some(n => Math.abs(n) > .00001);
    })""")
    page.wait_for_function("document.querySelector('.typing-piano-host').shadowRoot.querySelector('[data-control=replay]').textContent === '▶'")
    assert count() == 7 and query.input_value() == ''
    # 保存位置与尺寸，用 0.2.2 已验收的琴体截图做同坐标比较。
    metrics = {name: page.locator(selector).bounding_box() for name, selector in {
        'instrument': '.home-instrument', 'piano': '#pianoOuter', 'console': '.fascia-console',
        'keyboard': '#piano', 'play': '[data-control="replay"]', 'labels': '[data-control="labels"]',
    }.items()}
    (Path(out) / 'desktop-layout.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
    page.screenshot(path=str(screenshots / 'melody-desktop.png'))
    query.fill('一生所爱')
    before, search_before = count(), len(searches)
    play.click()
    assert play.inner_text() == '■'
    assert not query.evaluate('el => el === document.activeElement')
    page.wait_for_function("document.querySelector('.typing-piano-host').shadowRoot.querySelector('[data-control=replay]').textContent === '▶'")
    assert count() == before + 4
    assert query.input_value() == '一生所爱' and page.url == url + '/' and len(searches) == search_before
    query.fill('一生所爱' * 12)
    play.click()
    play.click()
    stopped = page.evaluate('voiceStarts')
    page.wait_for_timeout(800)
    assert page.evaluate('voiceStarts') == stopped and play.inner_text() == '▶'
    play.click()
    page.locator('[data-control="mute"]').click()
    muted = page.evaluate('voiceStarts')
    play.click()
    page.wait_for_timeout(800)
    assert page.evaluate('voiceStarts') == muted
    assert page.locator('[data-control="mute"]').get_attribute('aria-pressed') == 'false'
    page.locator('[data-control="mute"]').click()
    # 有播放队列的真实宿主页面：组件按钮不会触碰唯一 Audio、来源、音量或队列。
    go('/search?q=人工')
    page.locator('.song-row[data-platform-id="1"] .action-play').click()
    page.wait_for_function('!document.querySelector("audio").paused')
    page.evaluate('window.melodyAudio = document.querySelector("audio")')
    source = page.locator('audio').evaluate('el => el.src')
    volume = page.locator('audio').evaluate('el => el.volume')
    # 播放器会异步把真实时长写入队列元数据；等正常更新结束再做不变性快照。
    page.wait_for_function('JSON.parse(localStorage.getItem("music-core.queue.v1")).queue[0].metadata.durationSeconds === document.querySelector("audio").duration')
    queue = page.evaluate('JSON.parse(localStorage.getItem("music-core.queue.v1")).queue')
    go('/')
    wait_ready()
    query.fill('一生所爱' * 12)
    play.click()
    page.wait_for_timeout(250)
    assert page.locator('audio').evaluate('el => el === window.melodyAudio && !el.paused')
    assert page.locator('audio').evaluate('el => el.src') == source
    assert page.locator('audio').evaluate('el => el.volume') == volume
    assert page.evaluate('JSON.parse(localStorage.getItem("music-core.queue.v1")).queue') == queue
    go('/settings')
    page.wait_for_function('voiceContexts.every(context => context.state === "closed")')
    after_leave = page.evaluate('voiceStarts')
    page.wait_for_timeout(900)
    assert page.evaluate('voiceStarts') == after_leave
    assert page.locator('audio').evaluate('el => el === window.melodyAudio && !el.paused')
    assert page.locator('audio').evaluate('el => el.src') == source
    assert page.locator('audio').evaluate('el => el.volume') == volume
    assert page.evaluate('JSON.parse(localStorage.getItem("music-core.queue.v1")).queue') == queue
    assert not errors, errors
    result = {'emptyFirstClickHasRunningContextAndWaveform': True, 'sevenNoteArpeggio': True,
              'textSnapshotMelodyNoSearchOrInputFocus': True, 'stopAndMuteCancelRemainingNotes': True,
              'leaveHomeDisposesAudioAndScheduling': True, 'playingSongAudioSourceVolumeQueueUnchanged': True,
              'brand': 'VOICE BETWEEN', 'model': 'STAGE PIANO', 'buttonRightOfK': True,
              'softwareChromiumOnly': True, 'physicalWindowsIME': False, 'physicalPhoneTouch': False,
              'pageErrors': errors}
    (Path(out) / 'text-melody-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    context.close()
