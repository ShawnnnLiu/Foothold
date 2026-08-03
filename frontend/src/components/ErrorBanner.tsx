import "./ErrorBanner.css";

// The app-shell error surface (doc 03): every fetch error or non-2xx renders
// this slate banner with the error text and a retry affordance.
export default function ErrorBanner({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="errorbanner" role="alert">
      <span className="errorbanner__text">{message}</span>
      <button className="errorbanner__retry" onClick={onRetry}>
        Retry
      </button>
    </div>
  );
}
