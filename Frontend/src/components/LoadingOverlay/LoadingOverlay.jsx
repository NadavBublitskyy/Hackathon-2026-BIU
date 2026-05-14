import { Loader2 } from "lucide-react";

export function LoadingOverlay({ title, detail }) {
  return (
    <div className="loading-overlay" role="status" aria-live="polite">
      <div className="loading-dialog">
        <Loader2 size={26} className="spin" />
        <div>
          <h2>{title}</h2>
          <p>{detail}</p>
        </div>
      </div>
    </div>
  );
}
