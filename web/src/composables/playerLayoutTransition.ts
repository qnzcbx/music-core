import { nextTick, type Ref } from 'vue';
import gsap from 'gsap';
import { Flip } from 'gsap/Flip';
import type { PlayerLayout } from '../appearance/player-layout';

export type PlayerVisualPhase = 'idle' | 'opening' | 'closing' | 'layout';

/** Geometry only. The root coordinates this owner with the mini/large flight. */
export function createPlayerLayoutTransition(
  panel: Ref<HTMLElement | undefined>,
  reduced: Ref<boolean>,
  phase: Ref<PlayerVisualPhase>,
) {
  let generation = 0;
  let flight:HTMLElement|undefined;
  let handoff:{box:DOMRect;radius:string;angle:number;copy:HTMLElement;host:HTMLElement|undefined}|undefined;
  function preserve(){if(flight?.firstElementChild?.firstElementChild)handoff={box:flight.getBoundingClientRect(),radius:getComputedStyle(flight).borderRadius,angle:angle(flight.firstElementChild as HTMLElement),copy:flight.firstElementChild.firstElementChild.cloneNode(true) as HTMLElement,host:panel.value};}
  const boxOK=(box:DOMRect)=>Number.isFinite(box.x+box.y+box.width+box.height)&&box.width>1&&box.height>1;
  const angle=(node:HTMLElement|null)=>{if(!node)return 0;const matrix=getComputedStyle(node).transform;return matrix==='none'?0:Math.atan2(new DOMMatrixReadOnly(matrix).b,new DOMMatrixReadOnly(matrix).a)*180/Math.PI;};
  let context = gsap.context(() => {});
  let restoreCapturedStyles: (() => void) | undefined;
  function cancel() {
    generation++;
    context.revert();
    flight?.remove();flight=undefined;
    restoreCapturedStyles?.();
    restoreCapturedStyles = undefined;
    context = gsap.context(() => {});
    if (phase.value === 'layout') phase.value = 'idle';
  }
  function capture(nextLayout: PlayerLayout) {
    const host = panel.value;
    const previous=handoff;handoff=undefined;
    if (reduced.value || !host?.isConnected) return;
    // Never animate the rotor/reflection: their transform belongs to CSS spin.
    const record = host.querySelector<HTMLElement>('.turntable');
    const cover = host.querySelector<HTMLElement>('[data-cover-role=large]');
    const reading = host.querySelector<HTMLElement>('.listening-column');
    const squarePair=(host.classList.contains('square-layout')&&nextLayout==='vinyl-wide')||(host.classList.contains('wide-layout')&&nextLayout==='square-cover');
    const art=host.querySelector<HTMLElement>('[data-player-cover]');
    const source=host.classList.contains('square-layout')?host.querySelector<HTMLElement>('.square-cover-surface'):cover;
    const img=art?.querySelector('img');
    const morph=squarePair&&art&&source&&boxOK(source.getBoundingClientRect())&&(!img||img.complete);
    const sourceBox=morph?(previous?.host===host?previous.box:source!.getBoundingClientRect()):undefined;
    const sourceRadius=morph?(previous?.host===host?previous.radius:getComputedStyle(source!).borderRadius):'0px';
    const sourceAngle=previous?.host===host?previous.angle:host.classList.contains('square-layout')?0:angle(host.querySelector('.record-art-rotor'));
    const vinylPair = (host.classList.contains('classic-layout') || host.classList.contains('wide-layout')) &&
      (nextLayout === 'classic' || nextLayout === 'vinyl-wide');
    const targets = [record, cover, reading].filter((node): node is HTMLElement => !!node);
    const measured = vinylPair ? targets : [reading].filter((node): node is HTMLElement => !!node);
    if (!reading || (vinylPair && targets.length !== 3) || measured.some(node => {
      const box = node.getBoundingClientRect();
      return !Number.isFinite(box.x + box.y + box.width + box.height) || box.width <= 1 || box.height <= 1;
    })) return;
    const surface = host.querySelector<HTMLElement>('.square-cover-surface');
    const styles = [...targets, ...(surface ? [surface] : []), ...(art ? [art] : [])].map(node => [node, node.getAttribute('style')] as const);
    restoreCapturedStyles = () => {
      for (const [node, style] of styles) {
        if (style === null) node.removeAttribute('style');
        else node.setAttribute('style', style);
      }
    };
    const readingFirst=morph&&reading?Flip.getState([reading]):undefined;
    // 连续形变由实际几何决定，不再按视口宽高退化为淡入。
    const vinylFlip = vinylPair;
    let first: ReturnType<typeof Flip.getState> | undefined;
    try { if (vinylFlip) first = Flip.getState(targets, { props: 'borderRadius,backgroundColor' }); }
    catch { cancel(); return; }
    return {
      token: ++generation, host, targets,
      first, vinylFlip, nextLayout, reading, morph, art, sourceBox, sourceRadius, sourceAngle, readingFirst,
      textureBox:record?.getBoundingClientRect(), textureBackground:host.querySelector('.vinyl-grooves')?getComputedStyle(host.querySelector('.vinyl-grooves')!).background:'none',
      artCopy:morph?(previous?.host===host?previous.copy:art!.cloneNode(true) as HTMLElement):undefined,
    };
  }
  async function play(work: ReturnType<typeof capture>) {
    if (!work) return;
    phase.value = 'layout';
    await nextTick();
    if (work.token !== generation) return;
    if (reduced.value || panel.value !== work.host || !work.host.isConnected) { cancel(); return; }
    const done = () => { if (work.token === generation) cancel(); };
    context.add(() => {
      if(work.morph&&work.artCopy&&work.sourceBox){
        const target=work.host.querySelector<HTMLElement>(work.nextLayout==='square-cover'?'.square-cover-surface':'[data-cover-role=large]');
        if(!target||!boxOK(target.getBoundingClientRect())){cancel();return;}
        const end=target.getBoundingClientRect();
        const proxy=document.createElement('div');flight=proxy;
        proxy.className='layout-cover-flight';proxy.setAttribute('aria-hidden','true');
        Object.assign(proxy.style,{position:'fixed',zIndex:'26',pointerEvents:'none',overflow:'hidden',left:`${work.sourceBox.x}px`,top:`${work.sourceBox.y}px`,width:`${work.sourceBox.width}px`,height:`${work.sourceBox.height}px`,borderRadius:work.sourceRadius});
        const rotor=document.createElement('div');Object.assign(rotor.style,{width:'100%',height:'100%',transform:`rotate(${work.sourceAngle}deg)`});
        rotor.append(work.artCopy);proxy.append(rotor);document.body.append(proxy);
        gsap.set(work.art!,{visibility:'hidden'});
        const square=work.host.querySelector<HTMLElement>('.square-cover-surface');
        if(square)gsap.set(square,{background:'transparent',boxShadow:'none'});
        // 旋转器不卸载、不改animation/currentTime；代理仅对齐其当前角度。
        const live=work.host.querySelector<HTMLElement>('.record-art-rotor');
        const timeline=gsap.timeline({onComplete:done});
        timeline.to(proxy,{left:end.x,top:end.y,width:end.width,height:end.height,borderRadius:work.nextLayout==='square-cover'?getComputedStyle(target).borderRadius:'50%',duration:.76,ease:'power2.inOut'},0);
        const rotation={progress:0};
        let lastAngle=angle(live),continuousAngle=lastAngle;
        timeline.to(rotation,{progress:1,duration:.76,ease:'power2.inOut',onUpdate:()=>{
          const now=angle(live);continuousAngle+=((now-lastAngle+540)%360)-180;lastAngle=now;
          const desired=work.nextLayout==='square-cover'?0:continuousAngle;
          const degrees=work.sourceAngle+(desired-work.sourceAngle)*rotation.progress;
          const radius=getComputedStyle(proxy).borderTopLeftRadius;
          const ratio=Math.min(.5,parseFloat(radius)/(radius.includes('%')?100:proxy.offsetWidth));
          const radians=degrees*Math.PI/180;
          // 旋转中的矩形需覆盖圆角裁切轮廓，避免图片四角露出透明三角。
          const fill=1+(1-2*ratio)*(Math.abs(Math.cos(radians))+Math.abs(Math.sin(radians))-1);
          rotor.style.transform=`rotate(${degrees}deg) scale(${fill})`;
        }},0);
        Flip.from(work.readingFirst!,{duration:.76,ease:'power2.inOut',scale:true,absolute:false});
        const shell=work.host.querySelector<HTMLElement>('.turntable');
        if(shell&&work.nextLayout==='vinyl-wide')timeline.fromTo(shell,{opacity:0,scale:.72},{opacity:1,scale:1,duration:.76,ease:'power2.inOut'},0);
        if(shell&&work.nextLayout==='square-cover'){
          // 保留布局隐藏的原唱片，让纹理在原几何位置收敛；封面本体由代理唯一呈现。
          const texture=document.createElement('div');
          const grooves=work.host.querySelector<HTMLElement>('.vinyl-grooves');
          if(grooves){
            const box=work.textureBox!;
            Object.assign(texture.style,{position:'fixed',zIndex:'25',pointerEvents:'none',borderRadius:'50%',left:`${box.x}px`,top:`${box.y}px`,width:`${box.width}px`,height:`${box.height}px`,background:work.textureBackground});
            document.body.append(texture);
            timeline.to(texture,{opacity:0,scale:.72,duration:.76,ease:'power2.inOut',onComplete:()=>texture.remove()},0);
            const restore=restoreCapturedStyles;restoreCapturedStyles=()=>{texture.remove();restore?.();};
          }
        }
      } else if (work.vinylFlip) {
        // Last is now measured from Vue's final CSS (including fixed parents).
        // Nested cover correction prevents the record scale being applied twice.
        const motion = Flip.from(work.first!, {
          duration: 0.76, ease: 'power2.inOut', scale: true,
          nested: true, absolute: false, onComplete: done,
        });
        // Reflow once into the destination; soften text while the columns cross.
        motion.to(work.targets[2]!, { opacity: 0.5, duration: 0.2 }, 0)
          .to(work.targets[2]!, { opacity: 1, duration: 0.32 }, 0.44);
        if (!work.host.classList.contains('wide-layout')) {
          const details = work.host.querySelectorAll('.tonearm, .turntable-mark, .turntable-light, .vinyl-caption');
          motion.fromTo(details, { opacity: 0 }, { opacity: 1, duration: 0.3 }, 0.46);
        }
      } else {
        // New templates have different/no cover surfaces: never invent a target.
        const surface = work.nextLayout === 'lyrics-only' ? null : work.host.querySelector<HTMLElement>(
          work.nextLayout === 'square-cover' ? '.square-cover-surface' : '.turntable');
        gsap.fromTo([work.reading, ...(surface ? [surface] : [])], { opacity: 0.72, y: 6 }, {
          opacity: 1, y: 0, duration: 0.22, ease: 'power2.out', onComplete: done,
        });
      }
    });
  }
  function dispose() { cancel(); context.revert(); }
  return { capture, play, cancel, preserve, dispose };
}
