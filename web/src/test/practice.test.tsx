import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { describe, expect, it, vi } from "vitest";
import { PracticePanel } from "../components/PracticePanel";
import type { PracticeState } from "../lib/types";

const STATE: PracticeState = { today: ["Thank you so much.", "Good morning."], attempts: 3, streak_days: 2,
  days: [{ day: "2026-10-20", average: 60, attempts: 2 }, { day: "2026-10-21", average: 80, attempts: 1 }],
  best: { "Thank you so much.": 80 }, recent: [] };

function setup() {
  const load = vi.fn(async () => STATE);
  const submit = vi.fn(async (target: string) => ({ score: 75, heard: "thank you much", target, learned: true,
    words: [{ word: "thank", heard: true }, { word: "you", heard: true }, { word: "so", heard: false }, { word: "much", heard: true }] }));
  const record = vi.fn(async () => ({ wavBase64: "UklGRg==" }));
  const utils = render(<PracticePanel load={load} submit={submit} record={record} stop={() => undefined} recording={false} announce={() => undefined} />);
  return { load, submit, record, ...utils };
}

describe("Practice", () => {
  it("shows today's sentences, the streak and the best score", async () => {
    setup();
    await screen.findByText(/2-day streak/);
    expect(screen.getByRole("button", { name: /Thank you so much\. best 80%/ })).toBeTruthy();
    expect(screen.getByRole("img").getAttribute("aria-label")).toMatch(/2026-10-21: 80%/);
  });

  it("records a sentence, scores it, marks the missed word and says SureSay learned it", async () => {
    const { submit } = setup();
    fireEvent.click(await screen.findByRole("button", { name: /Good morning\./ }));
    await waitFor(() => expect(submit).toHaveBeenCalledWith("Good morning.", "UklGRg=="));
    await screen.findByText("75%");
    expect(screen.getByText("so").className).toMatch(/pw--miss/);
    expect(screen.getByText(/learned your way of saying this/)).toBeTruthy();
    expect(screen.getByText(/not a medical test/)).toBeTruthy();
  });

  it("has no axe violations", async () => {
    const { container } = setup();
    await screen.findByText(/2-day streak/);
    const r = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(r.violations.map((v) => v.id)).toEqual([]);
  });
});
