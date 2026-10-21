/**
 * Sound effects: one soft two-note chime when something is done. Web Audio
 * sine tones, quiet, about 150 ms. The caller decides when sounds are allowed.
 */

let ctx: AudioContext | null = null;

function audio(): AudioContext | null {
  try {
    const w = window as unknown as { AudioContext?: typeof AudioContext; webkitAudioContext?: typeof AudioContext };
    const Ctor = w.AudioContext ?? w.webkitAudioContext;
    if (!Ctor) return null;
    ctx ??= new Ctor();
    if (ctx.state === "suspended") void ctx.resume().catch(() => undefined);
    return ctx;
  } catch {
    return null;
  }
}

function tone(c: AudioContext, freq: number, start: number, length: number, peak: number): void {
  const osc = c.createOscillator();
  const gain = c.createGain();
  osc.type = "sine";
  osc.frequency.setValueAtTime(freq, start);
  gain.gain.setValueAtTime(0.0001, start);
  gain.gain.exponentialRampToValueAtTime(peak, start + 0.012);
  gain.gain.exponentialRampToValueAtTime(0.0001, start + length);
  osc.connect(gain).connect(c.destination);
  osc.start(start);
  osc.stop(start + length + 0.02);
}

/** A gentle rising chime (E6 then A6), after `delayMs`. */
export function playChime(delayMs = 0): void {
  const c = audio();
  if (!c) return;
  const t = c.currentTime + Math.max(0, delayMs) / 1000;
  tone(c, 1318.5, t, 0.09, 0.05);
  tone(c, 1760, t + 0.065, 0.09, 0.045);
}
