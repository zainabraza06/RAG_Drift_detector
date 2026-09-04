import { RefreshCw, TriangleAlert } from "lucide-react";
import { Component, type ErrorInfo, type ReactNode } from "react";

import { Button } from "@/components/ui/Button";

interface Props {
  children: ReactNode;
  /** Shown instead of the generic copy when the cause is known. */
  title?: string;
  description?: string;
}

interface State {
  error: Error | null;
}

/**
 * Stops one broken subtree from taking the whole application down.
 *
 * The case that motivated this is real and routine: a deploy replaces the
 * content-hashed asset files while a browser is still holding the previous
 * `index.html`, so the next lazy route it requests 404s. React's default
 * behaviour is to unmount the entire tree — the user loses the sidebar, the
 * header and any way to navigate, and is left staring at a blank page.
 *
 * Reloading is the correct remedy for a stale chunk (it fetches the current
 * index.html), so the fallback offers exactly that rather than a "try again"
 * that would re-render the same failing import.
 */
export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo) {
    // Kept as console.error rather than swallowed: without a reporting
    // backend, the browser console is where a developer will actually look.
    console.error("Unhandled error in React tree:", error, info.componentStack);
  }

  override render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    const isStaleChunk = /dynamically imported module|Failed to fetch/i.test(
      error.message,
    );

    return (
      <div
        role="alert"
        className="mx-auto flex max-w-lg animate-fade-in flex-col items-center rounded-xl border border-line bg-surface px-6 py-14 text-center shadow-card"
      >
        <span className="mb-4 grid h-12 w-12 place-items-center rounded-xl border border-critical/25 bg-critical-soft">
          <TriangleAlert className="h-5 w-5 text-critical" aria-hidden />
        </span>
        <h2 className="text-base font-semibold text-content">
          {this.props.title ??
            (isStaleChunk ? "This page needs a refresh" : "Something broke here")}
        </h2>
        <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-content-muted">
          {this.props.description ??
            (isStaleChunk
              ? "The application was updated while this tab was open, so part of it could not be loaded. Reloading will pick up the new version."
              : "This section failed to render. The rest of the application is still usable.")}
        </p>
        <div className="mt-5 flex gap-2">
          <Button
            variant="primary"
            icon={<RefreshCw className="h-3.5 w-3.5" aria-hidden />}
            onClick={() => window.location.reload()}
          >
            Reload
          </Button>
          {!isStaleChunk ? (
            <Button onClick={() => this.setState({ error: null })}>Dismiss</Button>
          ) : null}
        </div>
        <details className="mt-5 w-full text-left">
          <summary className="cursor-pointer text-2xs text-content-subtle hover:text-content-muted">
            Technical detail
          </summary>
          <pre className="mt-2 overflow-x-auto rounded-lg bg-surface-muted p-3 font-mono text-2xs text-content-muted">
            {error.message}
          </pre>
        </details>
      </div>
    );
  }
}
