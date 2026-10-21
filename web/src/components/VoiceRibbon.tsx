import { useEffect, useRef } from "react";

const POINTS = 72;

/**
 * A live waveform of the last few seconds of mic level, drawn in the dawn
 * gradient. Decorative (aria-hidden): the labelled meter carries the level
 * for screen readers. Not drawn at all when motion is off.
 */
export function VoiceRibbon({ level, active }: { level: number; active: boolean }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const ring = useRef<number[]>(new Array(POINTS).fill(0));

  useEffect(() => {
    if (!active) ring.current = new Array(POINTS).fill(0);
  }, [active]);

  useEffect(() => {
    const c = canvas.current;
    if (!c || !active) return;
    ring.current.push(Math.min(1, Math.sqrt(level * 14)));
    ring.current.splice(0, ring.current.length - POINTS);
    const ctx = c.getContext?.("2d");
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    const w = c.clientWidth || 320;
    const h = c.clientHeight || 64;
    if (c.width !== Math.round(w * dpr)) c.width = Math.round(w * dpr);
    if (c.height !== Math.round(h * dpr)) c.height = Math.round(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const grad = ctx.createLinearGradient(0, 0, w, 0);
    grad.addColorStop(0, "#FFB547");
    grad.addColorStop(0.5, "#FF6B5A");
    grad.addColorStop(1, "#7B5CFF");
    const mid = h / 2;
    const step = w / (POINTS - 1);
    // a mirrored, smoothed ribbon: newest on the right
    ctx.beginPath();
    ring.current.forEach((v, i) => {
      const x = i * step;
      const amp = Math.max(1.5, v * (mid - 4)) * (0.6 + 0.4 * Math.sin(i * 0.9));
      if (i === 0) ctx.moveTo(x, mid - amp);
      else ctx.lineTo(x, mid - amp);
    });
    for (let i = POINTS - 1; i >= 0; i--) {
      const v = ring.current[i];
      const amp = Math.max(1.5, v * (mid - 4)) * (0.6 + 0.4 * Math.sin(i * 0.9));
      ctx.lineTo(i * step, mid + amp);
    }
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.globalAlpha = 0.85;
    ctx.fill();
    ctx.globalAlpha = 1;
  }, [level, active]);

  if (!active) return null;
  return <canvas ref={canvas} className="ribbon" aria-hidden="true" />;
}
