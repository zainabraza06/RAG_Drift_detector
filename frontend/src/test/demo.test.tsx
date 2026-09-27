import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DemoPanel } from "@/components/DemoPanel";
import type { DemoIndexState } from "@/lib/types";

import { renderWithProviders } from "./render";

const HEALTHY: DemoIndexState = {
  enabled: true,
  document_count: 32,
  corpus_size: 32,
  missing_documents: 0,
  fragment_documents: 0,
  healthy: true,
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Serves the demo state, and records which scenarios were posted. */
function backend(initial: DemoIndexState, after: DemoIndexState = initial) {
  const posted: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.includes("/demo/scenarios/") && init?.method === "POST") {
        posted.push(url.split("/").pop() ?? "");
        return json(after);
      }
      if (url.endsWith("/demo")) return json(initial);
      return json({ status: "ok" });
    }),
  );
  return posted;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("simulate drift panel", () => {
  it("stays hidden unless the deployment enables it", async () => {
    backend({ ...HEALTHY, enabled: false });
    renderWithProviders(<DemoPanel />);
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    // Let the response land, so this asserts the enabled flag and not just
    // the loading state.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByText(/simulate drift/i)).toBeNull();
  });

  it("offers to break a healthy index, not to restore it", async () => {
    backend(HEALTHY);
    renderWithProviders(<DemoPanel />);

    expect(await screen.findByText(/Healthy · 32 documents/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /delete 6 documents/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /botched re-chunk/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /restore/i })).toBeDisabled();
  });

  it("says what is wrong with a broken index", async () => {
    backend({
      ...HEALTHY,
      document_count: 161,
      missing_documents: 6,
      fragment_documents: 135,
      healthy: false,
    });
    renderWithProviders(<DemoPanel />);

    expect(await screen.findByText(/6 expected documents missing/)).toBeInTheDocument();
    expect(screen.getByText(/135 re-chunk fragments added/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /restore/i })).toBeEnabled();
  });

  it("applies a scenario and shows the index it produced", async () => {
    const posted = backend(HEALTHY, {
      ...HEALTHY,
      document_count: 26,
      missing_documents: 6,
      healthy: false,
    });
    renderWithProviders(<DemoPanel />);

    fireEvent.click(await screen.findByRole("button", { name: /delete 6 documents/i }));

    expect(await screen.findByText(/6 expected documents missing/)).toBeInTheDocument();
    expect(posted).toEqual(["delete-documents"]);
    expect(screen.getByText(/now run an evaluation/i)).toBeInTheDocument();
  });
});
