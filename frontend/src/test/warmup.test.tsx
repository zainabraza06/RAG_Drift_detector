import { act, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BackendWarmup } from "@/components/BackendWarmup";
import { RunEvaluationButton } from "@/components/RunEvaluationButton";
import { api } from "@/lib/api";
import { WAKING_AFTER_MS } from "@/lib/warmup";

import { renderWithProviders } from "./render";

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** A fetch that hangs until the test decides the backend has woken. */
function sleepingBackend() {
  let wake: (response: Response) => void = () => {};
  const pending = new Promise<Response>((resolve) => (wake = resolve));
  vi.stubGlobal("fetch", vi.fn(() => pending));
  return () => wake(json(200, { status: "ok" }));
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("backend warm-up", () => {
  it("counts any HTTP answer as awake, even a 503", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(503, { status: "degraded" })));
    await expect(api.ping()).resolves.toBe(true);
  });

  it("does not count a network failure as awake", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("fail"))));
    await expect(api.ping()).rejects.toMatchObject({ code: "network_error" });
  });

  it("holds the run button until the API answers", async () => {
    const wake = sleepingBackend();
    renderWithProviders(<RunEvaluationButton />);

    const button = screen.getByRole("button", { name: /run evaluation/i });
    expect(button).toBeDisabled();

    await act(async () => wake());
    await waitFor(() => expect(button).toBeEnabled());
  });

  it("explains a slow start, and clears once the API is up", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const wake = sleepingBackend();
    renderWithProviders(
      <>
        <BackendWarmup />
        <RunEvaluationButton />
      </>,
    );

    // A warm API answers before the notice would appear, so it never flashes.
    expect(screen.queryByRole("status")).toBeNull();

    await act(async () => vi.advanceTimersByTime(WAKING_AFTER_MS + 100));
    expect(screen.getByRole("status")).toHaveTextContent(/waking the server/i);
    expect(screen.getByText("Waking server…")).toBeInTheDocument();

    await act(async () => wake());
    await waitFor(() => expect(screen.queryByRole("status")).toBeNull());
    expect(screen.getByText("Run evaluation")).toBeInTheDocument();
  });
});
