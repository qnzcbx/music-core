// 从 Dead Air 视觉基线迁入；仅在尺寸或应用主题改变时绘制，无逐帧动画。
function hash(n: number) {
  const value = Math.sin(n * 127.1 + 78.233) * 43758.5453;
  return value - Math.floor(value);
}
function arc(
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  radius: number,
  start: number,
  end: number,
) {
  context.beginPath();
  context.arc(x, y, radius, start, end);
  context.stroke();
}
export function drawDeadAirCover(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  dark: boolean,
) {
  const m = Math.min(w, h);
  ctx.clearRect(0, 0, w, h);
  const bg = ctx.createLinearGradient(0, 0, w, h);
  bg.addColorStop(0, dark ? '#414c43' : '#847563');
  bg.addColorStop(0.45, dark ? '#455149' : '#897b66');
  bg.addColorStop(1, dark ? '#272f2e' : '#3a413a');
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, w, h);
  const gl = ctx.createRadialGradient(w * 0.24, h * 0.22, w * 0.035, w * 0.55, h * 0.52, w * 0.82);
  gl.addColorStop(0, dark ? 'rgba(239,189,130,.35)' : 'rgba(253,206,148,.47)');
  gl.addColorStop(0.48, 'rgba(227,173,107,.08)');
  gl.addColorStop(1, 'rgba(18,33,31,.44)');
  ctx.fillStyle = gl;
  ctx.fillRect(0, 0, w, h);
  const cx = w * 0.51,
    cy = h * 0.49,
    r = m * 0.365;
  ctx.save();
  ctx.shadowColor = 'rgba(12,18,17,.65)';
  ctx.shadowBlur = m * 0.072;
  ctx.shadowOffsetX = m * 0.018;
  ctx.shadowOffsetY = m * 0.028;
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fillStyle = '#1b2927';
  ctx.fill();
  ctx.restore();
  const disc = ctx.createRadialGradient(cx - r * 0.35, cy - r * 0.48, r * 0.06, cx, cy, r);
  disc.addColorStop(0, dark ? '#6c7766' : '#6a6c5b');
  disc.addColorStop(0.38, dark ? '#2e3f38' : '#37463f');
  disc.addColorStop(0.72, dark ? '#1b2b29' : '#263531');
  disc.addColorStop(1, '#111c1a');
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fillStyle = disc;
  ctx.fill();
  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, r * 0.992, 0, Math.PI * 2);
  ctx.clip();
  const shimmer = ctx.createLinearGradient(cx - r, cy - r, cx + r, cy + r);
  shimmer.addColorStop(0, 'rgba(255,234,192,0)');
  shimmer.addColorStop(0.29, 'rgba(251,210,154,.05)');
  shimmer.addColorStop(0.45, 'rgba(243,210,163,.20)');
  shimmer.addColorStop(0.53, 'rgba(234,213,180,.02)');
  shimmer.addColorStop(1, 'rgba(250,219,160,.03)');
  ctx.fillStyle = shimmer;
  ctx.fillRect(cx - r, cy - r, r * 2, r * 2);
  const a0 = -0.18,
    a1 = 0.2;
  for (let i = 0; i < 62; i++) {
    const rr = r * (0.295 + i * 0.0109);
    ctx.strokeStyle = `rgba(239,218,178,${0.025 + hash(i + 35) * 0.095})`;
    ctx.lineWidth = i % 8 === 0 ? 0.9 : 0.5;
    arc(ctx, cx, cy, rr, a1, Math.PI * 2 + a0);
  }
  ctx.lineWidth = m * 0.0024;
  for (let i = 0; i < 200; i++) {
    const a = (i / 200) * Math.PI * 2 - 0.12;
    if (a > -0.2 && a < 0.22) continue;
    const waveVal =
      0.52 * Math.sin(i * 0.76) + 0.26 * Math.sin(i * 0.21) + 0.25 * Math.sin(i * 1.61);
    const rr = r * (0.76 + waveVal * 0.034);
    const aa = (i / 200) * Math.PI * 2 - 0.12;
    const ab = aa + 0.021;
    ctx.strokeStyle = `rgba(238,195,143,${0.22 + 0.12 * Math.sin(i * 0.31) ** 2})`;
    arc(ctx, cx, cy, rr, aa, ab);
  }
  ctx.restore();
  ctx.save();
  ctx.shadowBlur = 10;
  ctx.shadowColor = 'rgba(10,17,12,.22)';
  ctx.beginPath();
  ctx.arc(cx, cy, r * 0.284, 0, Math.PI * 2);
  ctx.fillStyle = dark ? '#c4b79b' : '#dcd1bc';
  ctx.fill();
  ctx.restore();
  ctx.strokeStyle = 'rgba(37,43,34,.38)';
  ctx.lineWidth = 1.2;
  arc(ctx, cx, cy, r * 0.262, 0, Math.PI * 2);
  ctx.strokeStyle = 'rgba(37,43,34,.18)';
  arc(ctx, cx, cy, r * 0.225, 0, Math.PI * 2);
  const discSubLabel = 'NO SIGNAL';
  ctx.fillStyle = '#313d32';
  ctx.font = `${Math.round(m * 0.02)}px ui-monospace,Consolas,monospace`;
  ctx.textAlign = 'center';
  ctx.fillText('AFTERTONE', cx, cy - r * 0.135);
  ctx.font = `italic ${Math.round(m * 0.078)}px Georgia,serif`;
  ctx.fillText('404', cx, cy + r * 0.037);
  ctx.font = `${Math.round(m * 0.016)}px ui-monospace,Consolas,monospace`;
  ctx.fillText(discSubLabel, cx, cy + r * 0.143);
  ctx.beginPath();
  ctx.arc(cx, cy, r * 0.014, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(23,29,24,.90)';
  ctx.fill();
  ctx.strokeStyle = 'rgba(255,230,180,.14)';
  ctx.lineWidth = m * 0.004;
  ctx.lineCap = 'round';
  arc(ctx, cx, cy, r * 0.945, -2.1, -1.18);
  ctx.lineWidth = m * 0.0025;
  arc(ctx, cx, cy, r * 0.91, 0.85, 1.56);
  for (let i = 0; i < 265; i++) {
    const px = hash(i + 57) * w,
      py = hash(i + 812) * h;
    if (Math.hypot(px - cx, py - cy) < r * 0.9) continue;
    ctx.fillStyle = `rgba(253,230,191,${0.03 + hash(i + 351) * 0.085})`;
    ctx.fillRect(px, py, Math.max(0.5, m * 0.0015), Math.max(0.5, m * 0.0015));
  }
}
