import {
  computed,
  inject,
  nextTick,
  onUnmounted,
  provide,
  ref,
  shallowRef,
  watch,
  type InjectionKey,
  type Ref,
} from "vue";
import { useRouter } from "vue-router";
import gsap from "gsap";
import { Flip } from "gsap/Flip";
import type { PlayableSong as Song } from "../types/music";
import { isPlayerPath } from "../utils/player-view-song";
import { useReducedMotion } from "./useReducedMotion";
import { useCoverPalette } from "./useCoverPalette";
import { isPlayerLayout, isLyricAlignment, startPlayerLayoutSelection } from "../appearance/player-layout";
import { createPlayerLayoutTransition, type PlayerVisualPhase } from "./playerLayoutTransition";
gsap.registerPlugin(Flip);

function createPlayerVisuals(current: Ref<Song | null>, queueKey: Ref<string | null>) {
  const router = useRouter();
  const reduced = useReducedMotion();
  const immersive = computed(() => isPlayerPath(router.currentRoute.value.path));
  const palette = useCoverPalette(computed(() => current.value?.cover));
  const phase = ref<PlayerVisualPhase>("idle"),
    miniHeight = ref(116);
  const selection = startPlayerLayoutSelection();
  const { layout, lyricAlignment } = selection;
  const mini = shallowRef<HTMLElement>(),
    large = shallowRef<HTMLElement>(),
    panel = shallowRef<HTMLElement>(),
    backButton = shallowRef<HTMLElement>();
  const layoutMotion = createPlayerLayoutTransition(panel, reduced, phase);
  function selectLayout(value: unknown) {
    if (!isPlayerLayout(value) || value === layout.value) return false;
    // 快速换模板先交接当前代理几何，再清理上一轮动画。
    layoutMotion.preserve();
    reset();
    const first = immersive.value ? layoutMotion.capture(value) : undefined;
    selection.selectLayout(value);
    void layoutMotion.play(first);
    return true;
  }
  function selectLyricAlignment(value: unknown) {
    if (!isLyricAlignment(value) || value === lyricAlignment.value) return false;
    reset();
    return selection.selectLyricAlignment(value);
  }
  let origin = "/",
    wanted = immersive.value,
    navigationPending = false,
    generation = 0,
    clone: HTMLElement | undefined;
  let prepared:
    | {
        token: number;
        direction: "opening" | "closing";
        state: ReturnType<typeof Flip.getState> | null;
        pose?: DOMRect;
        radius?: string;
        scroll?: [number, number];
      }
    | undefined;
  let context = gsap.context(() => {});
  const hidden = new Map<HTMLElement, string>();
  const valid = (element?: HTMLElement) =>
    !!element?.isConnected &&
    element.getBoundingClientRect().width > 1 &&
      element.getBoundingClientRect().height > 1 && getComputedStyle(element).visibility !== 'hidden';
  function hide(element?: HTMLElement) {
    if (element && !hidden.has(element)) {
      hidden.set(element, element.style.visibility);
      element.style.visibility = "hidden";
    }
  }
  function restore() {
    for (const [element, visibility] of hidden) element.style.visibility = visibility;
    hidden.clear();
  }
  function reset() {
    layoutMotion.cancel();
    generation++;
    prepared = undefined;
    context.revert();
    context = gsap.context(() => {});
    clone?.remove();
    clone = undefined;
    restore();
    phase.value = "idle";
  }
  function place(element: HTMLElement, box: DOMRect) {
    Object.assign(element.style, {
      left: `${box.left}px`,
      top: `${box.top}px`,
      width: `${box.width}px`,
      height: `${box.height}px`,
      transform: "none",
    });
  }
  function prepare(direction: "opening" | "closing") {
    layoutMotion.cancel();
    // Freeze the current visual pose before killing an interrupted Flip (which otherwise completes by default).
    const movingBox = clone?.getBoundingClientRect();
    const radius = clone ? getComputedStyle(clone).borderRadius : undefined;
    if (clone) Flip.killFlipsOf(clone, false);
    context.revert();
    context = gsap.context(() => {});
    restore();
    const token = ++generation;
    phase.value = direction;
    const source = direction === "opening" ? mini.value : large.value;
    if (layout.value === "lyrics-only" || reduced.value || (!clone && (!valid(source) || !current.value))) {
      clone?.remove();
      clone = undefined;
      prepared = { token, direction, state: null };
      return;
    }
    if (!clone && source) {
      clone = document.createElement("div");
      clone.className = "shared-cover-flight";
      clone.setAttribute("aria-hidden", "true");
      const art = source.querySelector(".cover-art");
      clone.appendChild((art ?? source).cloneNode(true));
      Object.assign(clone.style, {
        position: "fixed",
        zIndex: "90",
        pointerEvents: "none",
        margin: "0",
        padding: "0",
        border: "0",
        overflow: "hidden",
        borderRadius: getComputedStyle(source).borderRadius,
        boxShadow: "0 18px 38px #243d2926",
        background: "#dce4d5",
      });
      document.body.appendChild(clone);
      place(clone, source.getBoundingClientRect());
    } else if (clone && movingBox) {
      place(clone, movingBox);
      clone.style.borderRadius = radius ?? "8px";
    }
    if (!clone) {
      prepared = { token, direction, state: null };
      return;
    }
    clone.dataset.flight = direction;
    hide(mini.value);
    hide(large.value);
    prepared = {
      token,
      direction,
      state: Flip.getState(clone, { props: "borderRadius" }),
      pose: clone.getBoundingClientRect(),
      radius: clone.style.borderRadius,
      scroll: [window.scrollX, window.scrollY],
    };
  }
  function focus(direction: "opening" | "closing") {
    const target = direction === "opening" ? backButton.value : mini.value?.parentElement;
    if (target?.isConnected) target.focus({ preventScroll: true });
  }
  async function animate() {
    const work = prepared;
    await nextTick();
    if (work && work.token !== generation) return;
    const direction = work?.direction ?? (immersive.value ? "opening" : "closing");
    const target = direction === "opening" ? large.value : mini.value;
    const done = () => {
      if (work && work.token !== generation) return;
      reset();
      focus(direction);
    };
    if (!work?.state || !clone || !valid(target)) {
      reset();
      if (panel.value && !reduced.value)
        context.add(() => {
          gsap.fromTo(
            panel.value!,
            { opacity: 0.6 },
            {
              opacity: 1,
              duration: 0.18,
              clearProps: "opacity",
              onComplete: () => focus(direction),
            },
          );
        });
      else focus(direction);
      return;
    }
    // Flip matrices include document scroll, while this proxy uses viewport coordinates.
    // Route unmount may shorten the document and clamp scroll. Rebase the SAVED
    // First pose into the new document space; never query the unmounted source.
    let first = work.state;
    if (
      work.pose &&
      work.scroll &&
      (work.scroll[0] !== window.scrollX || work.scroll[1] !== window.scrollY)
    ) {
      place(clone, work.pose);
      clone.style.borderRadius = work.radius ?? "8px";
      first = Flip.getState(clone, { props: "borderRadius" });
    }
    hide(target);
    const box = target!.getBoundingClientRect();
    place(clone, box);
    clone.style.borderRadius = getComputedStyle(target!).borderRadius;
    context.add(() => {
      Flip.from(first!, {
        duration: 0.72,
        ease: "power2.inOut",
        scale: true,
        absolute: false,
        onComplete: done,
      });
      if (direction === "opening" && panel.value)
        gsap.fromTo(
          panel.value,
          { opacity: 0.5, y: 9 },
          {
            opacity: 1,
            y: 0,
            duration: 0.42,
            delay: 0.12,
            ease: "power2.out",
            clearProps: "opacity,transform",
          },
        );
    });
  }
  const removeBefore = router.beforeEach((to, from) => {
    const entering = isPlayerPath(to.path) && !isPlayerPath(from.path),
      leaving = !isPlayerPath(to.path) && isPlayerPath(from.path);
    if (entering) {
      navigationPending = true;
      origin = from.fullPath || "/";
      prepare("opening");
    } else if (leaving) {
      navigationPending = true;
      prepare("closing");
    } else if (phase.value !== "idle") reset();
  });
  const removeAfter = router.afterEach((_to, _from, failure) => {
    navigationPending = false;
    wanted = immersive.value;
    if (failure) {
      reset();
      return;
    }
    if (prepared || (immersive.value && !isPlayerPath(_from.path))) void animate();
  });
  function close() {
    if (navigationPending) return;
    navigationPending = true;
    wanted = false;
    if (window.history.state?.back === origin && immersive.value) router.back();
    else void router.replace(origin);
  }
  function open() {
    if (!current.value || navigationPending) return;
    const identity = queueKey.value ?? current.value.id;
    if (
      immersive.value &&
      (router.currentRoute.value.params.id === identity ||
        router.currentRoute.value.params.id === current.value.id)
    )
      return;
    navigationPending = true;
    wanted = true;
    if (!immersive.value) origin = router.currentRoute.value.fullPath;
    void router.push(`/player/${encodeURIComponent(identity)}`);
  }
  function toggle() {
    if (navigationPending) return;
    wanted || immersive.value ? close() : open();
  }
  const resized = () => {
    if (phase.value !== "idle") reset();
  };
  window.addEventListener("resize", resized, { passive: true });
  const scrolled = (event: Event) => {
    // Lyric following scrolls its own viewport; it must not cancel the layout.
    const target = event.target;
    if (phase.value === "layout" && (target === document || target === document.documentElement ||
      target === panel.value?.closest(".immersive-player") ||
      (target instanceof HTMLElement && target.classList.contains("app-shell")))) reset();
  };
  document.addEventListener("scroll", scrolled, { passive: true, capture: true });
  watch(reduced, () => {
    if (phase.value !== "idle") reset();
  });
  watch(
    () => [queueKey.value, current.value?.source, current.value?.cover],
    () => {
      reset();
      if (
        immersive.value &&
        current.value &&
        queueKey.value &&
        router.currentRoute.value.params.id !== queueKey.value
      )
        void router.replace(`/player/${encodeURIComponent(queueKey.value)}`);
    },
    { flush: "sync" },
  );
  // Legacy media-ID routes normalize without replaying the visual transition.
  watch(
    () => current.value?.id,
    (_id, previous) => {
      if (immersive.value && queueKey.value && router.currentRoute.value.params.id === previous)
        void router.replace(`/player/${encodeURIComponent(queueKey.value)}`);
    },
  );
  const footerObserver = new ResizeObserver((entries) => {
    for (const entry of entries)
      if(entry.target.getBoundingClientRect().height>0)miniHeight.value = Math.round(entry.target.getBoundingClientRect().height);
  });
  function setMiniFooter(value: unknown) {
    footerObserver.disconnect();
    if (value instanceof HTMLElement) footerObserver.observe(value);
  }
  function setMiniCover(value: unknown) {
    mini.value = value instanceof HTMLElement ? value : undefined;
  }
  function setLargeCover(value: unknown) {
    large.value = value instanceof HTMLElement ? value : undefined;
    if (clone && phase.value === "opening") hide(large.value);
  }
  function setPanel(value: unknown) {
    const element = value instanceof HTMLElement ? value : undefined;
    if (panel.value !== element) layoutMotion.cancel();
    panel.value = element;
  }
  function setBackButton(value: unknown) {
    backButton.value = value instanceof HTMLElement ? value : undefined;
  }
  onUnmounted(() => {
    removeBefore();
    removeAfter();
    reset();
    context.revert();
    layoutMotion.dispose();
    footerObserver.disconnect();
    window.removeEventListener("resize", resized);
    document.removeEventListener("scroll", scrolled, true);
  });
  return {
    immersive,
    phase,
    palette,
    layout,
    selectLayout,
    lyricAlignment,
    selectLyricAlignment,
    miniHeight,
    toggle,
    open,
    close,
    setMiniCover,
    setLargeCover,
    setMiniFooter,
    setPanel,
    setBackButton,
  };
}
const key: InjectionKey<ReturnType<typeof createPlayerVisuals>> = Symbol("player-visuals");
export function providePlayerVisuals(current: Ref<Song | null>, queueKey: Ref<string | null>) {
  const state = createPlayerVisuals(current, queueKey);
  provide(key, state);
  return state;
}
export function usePlayerVisuals() {
  const state = inject(key);
  if (!state) throw new Error("player visuals not initialized");
  return state;
}
