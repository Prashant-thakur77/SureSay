/**
 * Read-back. The hub's voice (`POST /device/speak`, MP3) when it is available,
 * the browser's own voice when it is not. `say` resolves when speech has ended,
 * so the app can start listening for the answer right after.
 */

import type { HubApi } from "./api";
import { bytesToBase64, encodeWav } from "./audio";

export type VoiceSource = "hub" | "browser" | "none";

/**
 * Browsers block sound until the person interacts with the page. Call this
 * from a click: it plays a moment of silence through each audio path, so later
 * read-back is allowed to play.
 */
export function unlockAudio(): void {
  try {
    const silent = new Audio(`data:audio/wav;base64,${bytesToBase64(encodeWav(new Float32Array(800)))}`);
    silent.volume = 0;
    void silent.play()?.catch(() => undefined);
  } catch {
    /* no media element */
  }
  try {
    const w = window as unknown as { AudioContext?: typeof AudioContext; webkitAudioContext?: typeof AudioContext };
    const Ctor = w.AudioContext ?? w.webkitAudioContext;
    if (Ctor) {
      const ctx = new Ctor();
      const src = ctx.createBufferSource();
      src.buffer = ctx.createBuffer(1, 1, 22050);
      src.connect(ctx.destination);
      src.start(0);
      void ctx.resume().then(() => setTimeout(() => void ctx.close(), 200));
    }
  } catch {
    /* no Web Audio */
  }
  try {
    if (window.speechSynthesis && typeof SpeechSynthesisUtterance !== "undefined") {
      const u = new SpeechSynthesisUtterance(" ");
      u.volume = 0;
      window.speechSynthesis.speak(u);
    }
  } catch {
    /* no speech synthesis */
  }
}

export class Speaker {
  private audio: HTMLAudioElement | null = null;
  private token = 0;
  private cache = new Map<string, string>();
  lastSource: VoiceSource = "none";
  lastVoice = "";
  /** Told when read-back starts and stops (the orb holds still while SureSay speaks). */
  onSpeaking?: (speaking: boolean) => void;

  constructor(private readonly hub: Pick<HubApi, "speak">) {}

  cancel(): void {
    this.token += 1;
    this.onSpeaking?.(false);
    if (this.audio) {
      this.audio.pause();
      this.audio.src = "";
      this.audio = null;
    }
    try {
      window.speechSynthesis?.cancel();
    } catch {
      /* not supported */
    }
  }

  async say(text: string): Promise<void> {
    const clean = text.trim();
    if (!clean) return;
    this.cancel();
    const my = this.token;
    const limit = Math.max(6000, clean.length * 140);
    try {
      let b64 = this.cache.get(clean);
      if (!b64) {
        const res = await this.hub.speak(clean);
        b64 = res.audio_b64;
        this.lastVoice = res.voice;
        if (this.cache.size > 40) this.cache.clear();
        this.cache.set(clean, b64);
      }
      if (my !== this.token) return;
      this.lastSource = "hub";
      this.onSpeaking?.(true);
      await this.playMp3(b64, my, limit);
    } catch {
      if (my !== this.token) return;
      this.onSpeaking?.(true);
      await this.browserSay(clean, my, limit);
    } finally {
      if (my === this.token) this.onSpeaking?.(false);
    }
  }

  private playMp3(b64: string, my: number, limit: number): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      const audio = new Audio(`data:audio/mpeg;base64,${b64}`);
      this.audio = audio;
      let settled = false;
      const end = (ok: boolean) => {
        if (settled) return;
        settled = true;
        clearTimeout(guard);
        if (ok || my !== this.token) resolve();
        else reject(new Error("playback failed"));
      };
      const guard = setTimeout(() => end(true), limit);
      audio.onended = () => end(true);
      audio.onpause = () => {
        if (my !== this.token) end(true);
      };
      audio.onerror = () => end(false);
      audio.play().catch(() => end(false));
    });
  }

  private browserSay(text: string, my: number, limit: number): Promise<void> {
    const synth = typeof window !== "undefined" ? window.speechSynthesis : undefined;
    if (!synth || typeof SpeechSynthesisUtterance === "undefined") {
      this.lastSource = "none";
      return Promise.resolve();
    }
    this.lastSource = "browser";
    return new Promise<void>((resolve) => {
      const u = new SpeechSynthesisUtterance(text);
      u.lang = "en-IN";
      u.rate = 0.95;
      const guard = setTimeout(resolve, limit);
      const end = () => {
        clearTimeout(guard);
        resolve();
      };
      u.onend = end;
      u.onerror = end;
      if (my === this.token) synth.speak(u);
      else end();
    });
  }
}
