/**
 * Read-back. The hub's voice (`POST /device/speak`, MP3) when it is available,
 * the browser's own voice when it is not. `say` resolves when speech has ended,
 * so the app can start listening for the answer right after.
 */

import type { HubApi } from "./api";

export type VoiceSource = "hub" | "browser" | "none";

export class Speaker {
  private audio: HTMLAudioElement | null = null;
  private token = 0;
  private cache = new Map<string, string>();
  lastSource: VoiceSource = "none";
  lastVoice = "";

  constructor(private readonly hub: Pick<HubApi, "speak">) {}

  cancel(): void {
    this.token += 1;
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
      await this.playMp3(b64, my, limit);
    } catch {
      if (my !== this.token) return;
      await this.browserSay(clean, my, limit);
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
