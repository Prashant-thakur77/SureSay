import { fireEvent, render, screen } from "@testing-library/react";
import axe from "axe-core";
import { describe, expect, it, vi } from "vitest";
import { App } from "../App";

const PAIR_LABEL = "Enter the 6-digit code shown where SureSay is running";

function stored(key: string): unknown {
  const raw = window.localStorage.getItem(key);
  return raw ? JSON.parse(raw) : null;
}

describe("first-run gate", () => {
  it("asks how to start, with the first choice focused and no axe violations", async () => {
    render(<App />);
    expect(screen.getByRole("heading", { level: 1, name: "Say it your way. Nothing happens until you choose." })).toBeTruthy();
    expect(screen.getByRole("heading", { level: 2, name: "How would you like to start?" })).toBeTruthy();
    const voice = screen.getByRole("button", { name: "Start with voice" });
    const quiet = screen.getByRole("button", { name: "Start quietly" });
    // native buttons: Enter and Space work on them without extra code
    expect(voice.tagName).toBe("BUTTON");
    expect(quiet.getAttribute("type")).toBe("button");
    expect(document.activeElement).toBe(voice);
    expect(voice.getAttribute("aria-describedby")).toBeTruthy();
    expect(screen.getByText("You can change this any time in Settings.")).toBeTruthy();
    const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations.map((v) => v.id)).toEqual([]);
  });

  it("“Start quietly” turns read-aloud and auto-listen off, remembers it, and moves on to pairing", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Start quietly" }));
    expect(stored("suresay.start")).toBe("quiet");
    expect(stored("suresay.settings")).toMatchObject({ readAloud: false, autoVoice: false });
    expect(await screen.findByLabelText(PAIR_LABEL)).toBeTruthy();
  });

  it("“Start with voice” turns both on and unlocks audio with the click", () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play");
    window.localStorage.setItem("suresay.settings", JSON.stringify({ readAloud: false, autoVoice: false }));
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Start with voice" }));
    expect(stored("suresay.start")).toBe("voice");
    expect(stored("suresay.settings")).toMatchObject({ readAloud: true, autoVoice: true });
    expect(play).toHaveBeenCalled();
    play.mockRestore();
  });

  it("is skipped once a choice is saved", async () => {
    window.localStorage.setItem("suresay.start", JSON.stringify("quiet"));
    render(<App />);
    expect(screen.queryByRole("button", { name: "Start with voice" })).toBeNull();
    expect(await screen.findByLabelText(PAIR_LABEL)).toBeTruthy();
  });

  it("Calm mode from saved settings is applied to the page", () => {
    window.localStorage.setItem("suresay.start", JSON.stringify("quiet"));
    window.localStorage.setItem("suresay.settings", JSON.stringify({ calm: true }));
    render(<App />);
    expect(document.documentElement.dataset.calm).toBe("1");
  });
});
