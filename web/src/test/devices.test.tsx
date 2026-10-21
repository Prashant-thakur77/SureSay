import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { describe, expect, it, vi } from "vitest";
import { DevicesSection } from "../components/DevicesSection";
import type { PairedDevice } from "../lib/types";

const DEVICES: PairedDevice[] = [
  { device_id: "d_me", name: "Kitchen tablet", kind: "screen", paired_at: 1, this_device: true },
  { device_id: "d_alexa", name: "Alexa skill", kind: "voice", paired_at: 2, this_device: false },
  { device_id: "d_link", name: "Linked: Alexa+", kind: "link", paired_at: 3, this_device: false },
];

function setup(list = DEVICES) {
  const load = vi.fn(async () => list);
  const unpair = vi.fn(async () => undefined);
  const utils = render(<DevicesSection load={load} unpair={unpair} />);
  return { load, unpair, ...utils };
}

describe("Your devices", () => {
  it("lists devices and assistant links in plain words, marking this one", async () => {
    setup();
    const list = await screen.findByRole("list", { name: /your devices/i });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0].textContent).toMatch(/Kitchen tablet/);
    expect(items[0].textContent).toMatch(/this device/i);
    expect(within(items[0]).queryByRole("button", { name: /unpair/i })).toBeNull(); // this one is unpaired below
    expect(items[1].textContent).toMatch(/voice/i);
    expect(items[2].textContent).toMatch(/Alexa\+/);
    expect(items[2].textContent).toMatch(/assistant link/i);
  });

  it("asks before unpairing, then removes the device", async () => {
    const { unpair } = setup();
    fireEvent.click(await screen.findByRole("button", { name: /unpair Alexa\+/i }));
    expect(unpair).not.toHaveBeenCalled();
    expect(screen.getByText(/can no longer suggest actions/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /yes, end the link/i }));
    await waitFor(() => expect(unpair).toHaveBeenCalledWith("d_link"));
    await waitFor(() => expect(screen.queryByText(/Linked: Alexa\+|^Alexa\+$/)).toBeNull());
    expect(screen.getByRole("status").textContent).toMatch(/unpaired/i);
  });

  it("keeps a device when the user changes their mind", async () => {
    const { unpair } = setup();
    fireEvent.click(await screen.findByRole("button", { name: /unpair Alexa skill/i }));
    fireEvent.click(screen.getByRole("button", { name: /keep it/i }));
    expect(unpair).not.toHaveBeenCalled();
    expect(screen.getByText("Alexa skill")).toBeTruthy();
  });

  it("has no axe violations", async () => {
    const { container } = setup();
    await screen.findByRole("list", { name: /your devices/i });
    const results = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(results.violations).toEqual([]);
  });
});
