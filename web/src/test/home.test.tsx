import { fireEvent, render, screen } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, describe, expect, it } from "vitest";
import { App } from "../App";

const PAIR_LABEL = "Enter the 6-digit code shown where SureSay is running";

afterEach(() => window.history.replaceState(null, "", "/"));

describe("the home page", () => {
  it("tells the story in chapters, with a site navigation and no axe violations", async () => {
    render(<App />);
    const nav = screen.getByRole("navigation", { name: "SureSay" });
    for (const name of ["How it works", "Safety", "For people", "Proof", "Alexa+", "Developers"]) {
      expect(nav.querySelector(`a[href^="#"]`)).toBeTruthy();
      expect(screen.getAllByRole("link", { name }).length).toBeGreaterThan(0);
    }
    for (const name of [/The AI can ask/, /Measured, not promised/, /On Alexa\+/, /The gate is open source/, /And this time, he is heard/]) {
      expect(screen.getByRole("heading", { level: 2, name })).toBeTruthy();
    }
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    const result = await axe.run(document.body, { rules: { "color-contrast": { enabled: false } } });
    expect(result.violations.map((v) => v.id)).toEqual([]);
  });

  it("shows every number from the report as plain text for screen readers", () => {
    render(<App />);
    expect(screen.getByRole("article", { name: /Misheard words taken as a “yes” or a choice: from 62.8% to 2.3%/ })).toBeTruthy();
    expect(screen.getByRole("article", { name: /Attacks that changed anything: 0 \/ 50/ })).toBeTruthy();
  });

  it("“Open the Alexa+ view” starts quietly and goes on to pairing, remembering where to go", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /Open the Alexa\+ view/ }));
    expect(new URLSearchParams(window.location.search).get("alexa")).toBe("1");
    expect(await screen.findByLabelText(PAIR_LABEL)).toBeTruthy();
  });

  it("comes back with ?home after the first run, and a start choice moves on again", async () => {
    window.localStorage.setItem("suresay.start", JSON.stringify("quiet"));
    window.history.replaceState(null, "", "/?home");
    render(<App />);
    expect(screen.getByRole("heading", { level: 1, name: "Say it your way. Nothing happens until you choose." })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Start quietly" }));
    expect(window.location.search).toBe("");
    expect(await screen.findByLabelText(PAIR_LABEL)).toBeTruthy();
  });
});
