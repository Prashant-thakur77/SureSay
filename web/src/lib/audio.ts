/**
 * Microphone capture for SureSay.
 *
 * Tap to start, tap to stop. It also stops by itself after ~1.2 s of quiet that
 * follows speech, or after 8 s. Audio is downsampled to 16 kHz mono and sent
 * as a PCM16 WAV, base64 encoded.
 */

export const TARGET_RATE = 16000;

export type StopReason = "silence" | "max" | "user";

export interface Recording {
  wavBase64: string;
  durationMs: number;
  heardSpeech: boolean;
  stoppedBy: StopReason;
}

export interface RecordOptions {
  onLevel?: (level: number) => void;
  silenceMs?: number;
  maxMs?: number;
}

export interface RecordingSession {
  /** Stop now and send what was recorded. */
  stop(): void;
  /** Stop now and throw the recording away. */
  cancel(): void;
  /** Resolves with the recording, or null when cancelled. */
  done: Promise<Recording | null>;
}

// pure helpers (unit tested) -----------------------------------------------------------

export function rms(frame: Float32Array): number {
  if (frame.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < frame.length; i++) sum += frame[i] * frame[i];
  return Math.sqrt(sum / frame.length);
}

/** Box-filter decimation: each output sample is the mean of the input samples it covers. */
export function downsample(input: Float32Array, fromRate: number, toRate = TARGET_RATE): Float32Array {
  if (fromRate === toRate) return input.slice();
  if (fromRate < toRate) {
    const ratio = fromRate / toRate;
    const out = new Float32Array(Math.floor(input.length / ratio));
    for (let i = 0; i < out.length; i++) {
      const x = i * ratio;
      const j = Math.floor(x);
      const frac = x - j;
      const a = input[j] ?? 0;
      const b = input[j + 1] ?? a;
      out[i] = a + (b - a) * frac;
    }
    return out;
  }
  const ratio = fromRate / toRate;
  const out = new Float32Array(Math.floor(input.length / ratio));
  for (let i = 0; i < out.length; i++) {
    const start = Math.floor(i * ratio);
    const end = Math.min(input.length, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let j = start; j < end; j++) sum += input[j];
    out[i] = end > start ? sum / (end - start) : 0;
  }
  return out;
}

/** 16-bit PCM mono WAV. */
export function encodeWav(samples: Float32Array, rate = TARGET_RATE): Uint8Array {
  const bytes = new Uint8Array(44 + samples.length * 2);
  const v = new DataView(bytes.buffer);
  const ascii = (off: number, s: string) => {
    for (let i = 0; i < s.length; i++) v.setUint8(off + i, s.charCodeAt(i));
  };
  ascii(0, "RIFF");
  v.setUint32(4, 36 + samples.length * 2, true);
  ascii(8, "WAVE");
  ascii(12, "fmt ");
  v.setUint32(16, 16, true); // fmt chunk size
  v.setUint16(20, 1, true); // PCM
  v.setUint16(22, 1, true); // mono
  v.setUint32(24, rate, true);
  v.setUint32(28, rate * 2, true); // byte rate
  v.setUint16(32, 2, true); // block align
  v.setUint16(34, 16, true); // bits per sample
  ascii(36, "data");
  v.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return bytes;
}

export function bytesToBase64(bytes: Uint8Array): string {
  let bin = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    bin += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(bin);
}

/**
 * A simple energy VAD. The first ~300 ms set the noise floor (its quietest
 * frames, so a user who starts talking at once still works). Speech is ~100 ms
 * above the threshold; after speech, `silenceMs` below it ends the recording.
 */
export class SilenceDetector {
  private elapsed = 0;
  private floor = Number.POSITIVE_INFINITY;
  private loud = 0;
  private quiet = 0;
  heardSpeech = false;

  constructor(
    private readonly silenceMs = 1200,
    private readonly maxMs = 8000,
    private readonly minThreshold = 0.012,
  ) {}

  get threshold(): number {
    const floor = Number.isFinite(this.floor) ? Math.min(this.floor, 0.05) : 0;
    return Math.max(this.minThreshold, floor * 2.5);
  }

  push(level: number, frameMs: number): "continue" | "silence" | "max" {
    this.elapsed += frameMs;
    if (this.elapsed <= 300) this.floor = Math.min(this.floor, level);
    if (level > this.threshold) {
      this.loud += frameMs;
      this.quiet = 0;
      if (this.loud >= 100) this.heardSpeech = true;
    } else {
      this.loud = Math.max(0, this.loud - frameMs / 2);
      if (this.heardSpeech) this.quiet += frameMs;
    }
    if (this.heardSpeech && this.quiet >= this.silenceMs) return "silence";
    if (this.elapsed >= this.maxMs) return "max";
    return "continue";
  }
}

// capture -----------------------------------------------------------------------------

export class MicError extends Error {
  constructor(
    readonly kind: "blocked" | "missing" | "insecure" | "other",
    message: string,
  ) {
    super(message);
    this.name = "MicError";
  }
}

const WORKLET = `
class SureSayTap extends AudioWorkletProcessor {
  constructor() { super(); this.buf = new Float32Array(2048); this.n = 0; }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) {
      for (let i = 0; i < ch.length; i++) {
        this.buf[this.n++] = ch[i];
        if (this.n === this.buf.length) { this.port.postMessage(this.buf.slice(0)); this.n = 0; }
      }
    }
    return true;
  }
}
registerProcessor("suresay-tap", SureSayTap);
`;

type AudioCtor = typeof AudioContext;

function audioContextCtor(): AudioCtor | null {
  const w = window as unknown as { AudioContext?: AudioCtor; webkitAudioContext?: AudioCtor };
  return w.AudioContext ?? w.webkitAudioContext ?? null;
}

export function micSupported(): boolean {
  return typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia && !!audioContextCtor();
}

async function openMic(): Promise<MediaStream> {
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    throw new MicError("insecure", "The microphone only works on a secure page (https or this computer).");
  }
  try {
    return await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  } catch (err) {
    const name = err instanceof DOMException ? err.name : "";
    if (name === "NotAllowedError" || name === "SecurityError") {
      throw new MicError("blocked", "The microphone is blocked. Allow it in your browser, or type instead.");
    }
    if (name === "NotFoundError" || name === "OverconstrainedError") {
      throw new MicError("missing", "No microphone was found. You can type instead.");
    }
    throw new MicError("other", "The microphone could not start. You can type instead.");
  }
}

/** Start recording. Rejects with MicError when the microphone cannot be used. */
export async function startRecording(opts: RecordOptions = {}): Promise<RecordingSession> {
  const Ctor = audioContextCtor();
  if (!Ctor) throw new MicError("other", "This browser cannot record audio. You can type instead.");
  const stream = await openMic();
  const ctx = new Ctor();
  if (ctx.state === "suspended") await ctx.resume().catch(() => undefined);
  const rate = ctx.sampleRate;
  const source = ctx.createMediaStreamSource(stream);
  const sink = ctx.createGain();
  sink.gain.value = 0;
  sink.connect(ctx.destination);

  const chunks: Float32Array[] = [];
  const vad = new SilenceDetector(opts.silenceMs ?? 1200, opts.maxMs ?? 8000);
  const started = performance.now();
  let finished = false;
  let resolve!: (r: Recording | null) => void;
  const done = new Promise<Recording | null>((r) => (resolve = r));
  let node: AudioNode | null = null;
  let workletUrl: string | null = null;

  const cleanup = () => {
    try {
      source.disconnect();
      node?.disconnect();
      sink.disconnect();
    } catch {
      /* already disconnected */
    }
    stream.getTracks().forEach((t) => t.stop());
    void ctx.close().catch(() => undefined);
    if (workletUrl) URL.revokeObjectURL(workletUrl);
  };

  const finish = (reason: StopReason | null) => {
    if (finished) return;
    finished = true;
    cleanup();
    opts.onLevel?.(0);
    if (reason === null) {
      resolve(null);
      return;
    }
    let total = 0;
    for (const c of chunks) total += c.length;
    const all = new Float32Array(total);
    let off = 0;
    for (const c of chunks) {
      all.set(c, off);
      off += c.length;
    }
    const wav = encodeWav(downsample(all, rate));
    resolve({
      wavBase64: bytesToBase64(wav),
      durationMs: Math.round(performance.now() - started),
      heardSpeech: vad.heardSpeech,
      stoppedBy: reason,
    });
  };

  const onFrame = (frame: Float32Array) => {
    if (finished) return;
    chunks.push(frame);
    const level = rms(frame);
    opts.onLevel?.(level);
    const verdict = vad.push(level, (frame.length / rate) * 1000);
    if (verdict !== "continue") finish(verdict);
  };

  let usedWorklet = false;
  if (ctx.audioWorklet && typeof AudioWorkletNode !== "undefined") {
    try {
      workletUrl = URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" }));
      await ctx.audioWorklet.addModule(workletUrl);
      const w = new AudioWorkletNode(ctx, "suresay-tap", { numberOfInputs: 1, numberOfOutputs: 1, channelCount: 1 });
      w.port.onmessage = (e: MessageEvent<Float32Array>) => onFrame(e.data);
      source.connect(w);
      w.connect(sink);
      node = w;
      usedWorklet = true;
    } catch {
      usedWorklet = false;
    }
  }
  if (!usedWorklet) {
    const sp = ctx.createScriptProcessor(2048, 1, 1);
    sp.onaudioprocess = (e) => onFrame(new Float32Array(e.inputBuffer.getChannelData(0)));
    source.connect(sp);
    sp.connect(sink);
    node = sp;
  }

  return { stop: () => finish("user"), cancel: () => finish(null), done };
}
