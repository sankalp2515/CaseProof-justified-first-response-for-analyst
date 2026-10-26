import React from "react";
import { Check, Loader2 } from "lucide-react";
import { apiRequest } from "../../api/client.js";

// What the visitor watches while a fresh synthetic bank is generated and
// published. Steps 1-3 run while the server generates; step 4 is real
// BigQuery publication progress from /v1/victim/demo-session/progress.
export const BUILD_STEPS = [
  "Opening Cedar Demo Bank with 12 customer accounts",
  "Placing a scam payment at the time you chose",
  "Moving the money through mule accounts at other banks",
  "Publishing bank records to BigQuery",
  "Ready: choose a customer marked with a suspicious payment",
];

export async function waitForBank(onProgress, limitMs = 120000) {
  const started = Date.now();
  while (Date.now() - started < limitMs) {
    let p;
    try {
      p = await apiRequest("/v1/victim/demo-session/progress");
    } catch (error) {
      if (error.status === 404) return; // older backend without progress
      throw error;
    }
    onProgress(p);
    if (p.ready) return;
    await new Promise((r) => setTimeout(r, 1500));
  }
}

export default function BankBuilder({ stage, published = 0, total = 6, minutes }) {
  return (
    <div className="bank-builder" role="status" aria-live="polite">
      <div className="flow-visual" aria-hidden="true">
        <span className="bb-node victim">Victim</span>
        <span className="bb-lane">
          <i />
          <i />
          <i />
        </span>
        <span className="bb-node mule">Mule A</span>
        <span className="bb-lane">
          <i />
          <i />
        </span>
        <span className="bb-node layer">Mule B</span>
        <span className="bb-lane">
          <i />
        </span>
        <span className="bb-node atm">ATM</span>
      </div>
      <ol className="build-steps">
        {BUILD_STEPS.map((text, i) => (
          <li
            key={i}
            className={i < stage ? "done" : i === stage ? "now" : "todo"}
          >
            {i < stage ? (
              <Check size={14} />
            ) : i === stage ? (
              <Loader2 size={14} className="spin" />
            ) : (
              <span className="dot" />
            )}
            <span>
              {i === 1 && minutes ? `${text} (${minutes} minutes ago)` : text}
              {i === 3 &&
                stage >= 3 &&
                (published ? ` · ${published} of ${total} banks` : " · 6 banks in parallel")}
            </span>
          </li>
        ))}
      </ol>
      {stage === 3 && (
        <div className={"build-bar" + (published ? "" : " indeterminate")}>
          <span style={{ width: `${(100 * published) / (total || 6)}%` }} />
        </div>
      )}
      <p className="muted small">
        This is a real build, not a recording: every visitor gets new names,
        amounts and money movements. In a real scam, this is how fast money moves
        after the payment, and why the first hour matters.
      </p>
    </div>
  );
}
