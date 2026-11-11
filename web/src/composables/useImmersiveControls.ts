import {nextTick,onMounted,onUnmounted,ref,watch,type Ref} from 'vue';

/** 只控制沉浸操作层的可见性，不拥有音频、路由或播放状态。 */
export function useImmersiveControls(root:Ref<HTMLElement|undefined>,controls:Ref<HTMLElement|undefined>,eligible:Readonly<Ref<boolean>>){
 const hidden=ref(false),locked=ref(false),hovered=ref(false),focused=ref(false);
 let timer:ReturnType<typeof setTimeout>|undefined,lastActivity=0,suppressUntil=0;
 const blocked=()=>!eligible.value||locked.value||hovered.value||focused.value;
 function clear(){clearTimeout(timer);timer=undefined;}
 function check(){timer=undefined;if(blocked())return;const remaining=4000-(performance.now()-lastActivity);if(remaining>0)timer=setTimeout(check,remaining);else hidden.value=true;}
 function wake(){lastActivity=performance.now();if(hidden.value)hidden.value=false;if(!timer&&!blocked())timer=setTimeout(check,4000);}
 function hold(value:boolean){hovered.value=value;clear();wake();}
 function focus(event:FocusEvent){focused.value=!!controls.value?.contains(event.relatedTarget as Node)&&!!controls.value?.querySelector(':focus-visible');clear();wake();}
 function move(event:PointerEvent){if(event.pointerType==='mouse'&&root.value?.contains(event.target as Node))wake();}
 function down(event:PointerEvent){if(!root.value?.contains(event.target as Node))return;const consume=hidden.value&&event.pointerType==='touch';suppressUntil=consume?performance.now()+700:0;wake();if(consume){event.preventDefault();event.stopPropagation();}}
 function click(event:MouseEvent){if(performance.now()<suppressUntil&&root.value?.contains(event.target as Node)){suppressUntil=0;event.preventDefault();event.stopImmediatePropagation();}}
 function key(event:KeyboardEvent){if(!root.value)return;const wasHidden=hidden.value;if(controls.value?.contains(document.activeElement))focused.value=true;wake();if(wasHidden&&event.key==='Tab'){event.preventDefault();void nextTick(()=>controls.value?.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus());}}
 const stop=watch([eligible,locked],()=>{clear();wake();});
 onMounted(()=>{wake();document.addEventListener('pointermove',move,{passive:true});document.addEventListener('pointerdown',down,true);document.addEventListener('click',click,true);document.addEventListener('keydown',key,true);});
 onUnmounted(()=>{clear();stop();document.removeEventListener('pointermove',move);document.removeEventListener('pointerdown',down,true);document.removeEventListener('click',click,true);document.removeEventListener('keydown',key,true);});
 return {hidden,locked,wake,hold,focusIn:()=>{focused.value=!!controls.value?.querySelector(':focus-visible');clear();wake();},focusOut:focus};
}
