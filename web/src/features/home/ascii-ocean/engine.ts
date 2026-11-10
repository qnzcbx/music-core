import { HOME_SHARKS } from './config.ts';
import { World, type SharkSpec } from './world.ts';
import { AsciiRenderer } from './renderer.ts';

/** One canvas, one RAF. Reduced motion is owned by the Vue boundary. */
export class HomeOceanEngine {
  readonly model: World;
  readonly renderer: AsciiRenderer;
  frames = 0; disposed = false;
  private pixelRatio = 0;
  private frame = 0; private previous = 0; private remainder = 0; private inView = true;
  private resizeObserver: ResizeObserver; private intersection: IntersectionObserver;
  private themeObserver: MutationObserver; private resolution?: MediaQueryList;
  constructor(private canvas: HTMLCanvasElement, specs: readonly SharkSpec[] = HOME_SHARKS) {
    this.model = new World([...specs]); this.renderer = new AsciiRenderer(canvas);
    this.renderer.setFontFamily(getComputedStyle(canvas).fontFamily);
    this.resizeObserver = new ResizeObserver(this.resize); this.resizeObserver.observe(canvas);
    this.intersection = new IntersectionObserver(entries => { this.inView = entries.some(entry => entry.isIntersecting); this.resume(); }); this.intersection.observe(canvas);
    this.themeObserver = new MutationObserver(this.color); this.themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    document.addEventListener('visibilitychange', this.resume); window.addEventListener('resize', this.resize);
    window.addEventListener('pointermove', this.pointer, { passive: true }); window.addEventListener('pointerdown', this.splash, { passive: true });
    window.addEventListener('blur', this.leave); document.documentElement.addEventListener('pointerleave', this.leave);
    this.watchResolution(); this.resize(); this.color(); this.resume();
  }
  private watchResolution = () => {
    this.resolution?.removeEventListener('change', this.resolutionChanged);
    this.resolution = window.matchMedia(`(resolution: ${window.devicePixelRatio}dppx)`);
    this.resolution.addEventListener('change', this.resolutionChanged);
  };
  private resolutionChanged = () => { this.resize(); this.watchResolution(); };
  private color = () => {
    const css = getComputedStyle(this.canvas);
    this.renderer.setTheme(css.getPropertyValue('--app-bg').trim(), css.getPropertyValue('--app-ocean-grid').trim(), css.getPropertyValue('--app-ocean-fish').trim(), css.getPropertyValue('--app-ocean-ink').trim());
  };
  private resize = () => {
    if (this.disposed) return;
    const box = this.canvas.getBoundingClientRect(); if (box.width <= 0 || box.height <= 0) return;
    this.pixelRatio = Math.min(2, window.devicePixelRatio || 1);
    this.renderer.resize(box.width, box.height, this.pixelRatio);
    this.model.resize(box.width, box.height, this.renderer.cellWidth, this.renderer.cellHeight); this.color();
    // alpha:false canvases reset to black on backing-store resize. Paint now, not next RAF.
    this.renderer.render(this.model, 0);
  };
  private resume = () => {
    cancelAnimationFrame(this.frame); this.frame = 0; this.previous = 0; this.remainder = 0;
    if (this.disposed || document.hidden || !this.inView) return;
    // Some display/emulation changes update DPR without a resize/media event.
    if (this.pixelRatio !== Math.min(2, window.devicePixelRatio || 1)) this.resize();
    this.frame = requestAnimationFrame(this.tick);
  };
  private tick = (now: number) => {
    this.frame = 0;
    if (this.disposed || document.hidden || !this.inView) return;
    if (this.pixelRatio !== Math.min(2, window.devicePixelRatio || 1)) this.resize();
    const dt = this.previous ? Math.min(.1, (now - this.previous) / 1000) : 0;
    this.remainder += dt;
    this.previous = now;
    let steps = 0;
    while (this.remainder >= 1 / 60 && steps < 4) { this.model.step(1 / 60); this.remainder -= 1 / 60; steps++; }
    if (steps === 4) this.remainder = 0;
    this.renderer.render(this.model, dt); this.frames++;
    this.frame = requestAnimationFrame(this.tick);
  };
  private point(event: PointerEvent) { const box = this.canvas.getBoundingClientRect(); const x = event.clientX - box.x, y = event.clientY - box.y; return { x, y, inside: x >= 0 && x <= box.width && y >= 0 && y <= box.height }; }
  private pointer = (event: PointerEvent) => { const p = this.point(event); Object.assign(this.model.pointer, { x: p.x, y: p.y, active: p.inside && event.pointerType !== 'touch' }); };
  private splash = (event: PointerEvent) => { const p = this.point(event); if (p.inside) this.model.splash(p.x, p.y); };
  private leave = () => { this.model.pointer.active = false; };
  destroy() {
    if (this.disposed) return; this.disposed = true; cancelAnimationFrame(this.frame); this.frame = 0;
    this.resizeObserver.disconnect(); this.intersection.disconnect(); this.themeObserver.disconnect();
    this.resolution?.removeEventListener('change', this.resolutionChanged);
    document.removeEventListener('visibilitychange', this.resume); window.removeEventListener('resize', this.resize);
    window.removeEventListener('pointermove', this.pointer); window.removeEventListener('pointerdown', this.splash);
    window.removeEventListener('blur', this.leave); document.documentElement.removeEventListener('pointerleave', this.leave);
  }
}
