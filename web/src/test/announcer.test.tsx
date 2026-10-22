import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useAnnouncer } from "../hooks/useAnnouncer";

afterEach(() => vi.useRealTimers());

describe("the announcer", () => {
  it("clears a stale polite message when an assertive one arrives", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useAnnouncer());
    act(() => { result.current.announce("Working it out.", "polite"); vi.advanceTimersByTime(100); });
    expect(result.current.polite).toBe("Working it out.");
    act(() => { result.current.announce("Done: Turn on the bedroom fan.", "assertive"); vi.advanceTimersByTime(100); });
    expect(result.current.assertive).toBe("Done: Turn on the bedroom fan.");
    expect(result.current.polite).toBe("");
  });

  it("a pending polite message never lands after a newer assertive one", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useAnnouncer());
    act(() => { result.current.announce("Working it out.", "polite"); result.current.announce("Done.", "assertive"); vi.advanceTimersByTime(100); });
    expect(result.current.polite).toBe("");
  });
});
