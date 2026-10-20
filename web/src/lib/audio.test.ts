import { describe, expect, it } from "vitest";
import { bytesToBase64, downsample, encodeWav, rms, SilenceDetector } from "./audio";

describe("audio helpers", () => {
  it("downsamples 48 kHz to 16 kHz", () => {
    const input = new Float32Array(48000).fill(0.5);
    const out = downsample(input, 48000);
    expect(out.length).toBe(16000);
    expect(out[100]).toBeCloseTo(0.5);
  });

  it("writes a 16 kHz mono PCM16 WAV header", () => {
    const wav = encodeWav(new Float32Array([0, 1, -1, 0.5]));
    const v = new DataView(wav.buffer);
    const tag = (o: number) => String.fromCharCode(...wav.subarray(o, o + 4));
    expect(tag(0)).toBe("RIFF");
    expect(tag(8)).toBe("WAVE");
    expect(v.getUint16(20, true)).toBe(1);
    expect(v.getUint16(22, true)).toBe(1);
    expect(v.getUint32(24, true)).toBe(16000);
    expect(v.getUint16(34, true)).toBe(16);
    expect(v.getUint32(40, true)).toBe(8);
    expect(v.getInt16(46, true)).toBe(32767);
    expect(v.getInt16(48, true)).toBe(-32768);
    expect(wav.length).toBe(52);
  });

  it("base64 encodes large buffers", () => {
    const bytes = new Uint8Array(100000).map((_, i) => i % 256);
    expect(atob(bytesToBase64(bytes)).length).toBe(100000);
  });

  it("rms of a constant frame is its value", () => {
    expect(rms(new Float32Array(64).fill(0.25))).toBeCloseTo(0.25);
  });

  it("stops after 1.2 s of quiet that follows speech", () => {
    const vad = new SilenceDetector(1200, 8000);
    const frame = 50;
    for (let t = 0; t < 300; t += frame) expect(vad.push(0.002, frame)).toBe("continue");
    for (let t = 0; t < 600; t += frame) expect(vad.push(0.2, frame)).toBe("continue");
    expect(vad.heardSpeech).toBe(true);
    let verdict = "continue";
    let quiet = 0;
    while (verdict === "continue") {
      verdict = vad.push(0.002, frame);
      quiet += frame;
    }
    expect(verdict).toBe("silence");
    expect(quiet).toBe(1200);
  });

  it("gives up after 8 s with no speech", () => {
    const vad = new SilenceDetector(1200, 8000);
    let verdict = "continue";
    let t = 0;
    while (verdict === "continue") {
      verdict = vad.push(0.001, 100);
      t += 100;
    }
    expect(verdict).toBe("max");
    expect(t).toBe(8000);
    expect(vad.heardSpeech).toBe(false);
  });
});
