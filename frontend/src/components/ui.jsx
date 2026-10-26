import React, { useEffect } from "react";
import { Check, X, AlertTriangle, Info, Sparkles } from "lucide-react";
import { cx } from "../lib/format.js";

export const Badge = ({ tone, mono, pip, dash, children, className }) => (
  <span
    className={cx("badge", tone, mono && "mono", dash && "dash", className)}
  >
    {pip && <span className="pip" />}
    {children}
  </span>
);

export const Card = ({ className, children, ...p }) => (
  <div className={cx("card", className)} {...p}>
    {children}
  </div>
);

// Guided-tour anchor: an explicit `tour` id, else a slug of a plain-text title.
const tourId = (title, tour) =>
  tour ||
  (typeof title === "string"
    ? title
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "")
    : undefined);

export function CardH({ title, sub, children, icon, tour }) {
  return (
    <div className="card-h" data-tour={tourId(title, tour)}>
      {icon}
      <div className="col">
        <h3>{title}</h3>
        {sub && <span className="sub">{sub}</span>}
      </div>
      <div className="right row gap8">{children}</div>
    </div>
  );
}

export function LogoMark({ size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path
        d="M17.5 6.8A7.5 7.5 0 1 0 17.5 17.2"
        stroke="currentColor"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
      <path
        d="M9.2 12.2l2.2 2.2 4.4-4.6"
        stroke="#8fa2ff"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function StatusIcon({ status, size = 22 }) {
  if (status === "verified")
    return (
      <span
        className="st"
        style={{
          background: "var(--ok)",
          color: "#fff",
          width: size,
          height: size,
        }}
      >
        <Check size={13} strokeWidth={3} />
      </span>
    );
  if (status === "rejected")
    return (
      <span
        className="st"
        style={{
          background: "var(--warn)",
          color: "#fff",
          width: size,
          height: size,
        }}
      >
        <AlertTriangle size={12} strokeWidth={2.6} />
      </span>
    );
  if (status === "draft")
    return (
      <span
        className="st"
        style={{
          background: "var(--ai-soft)",
          color: "var(--ai)",
          width: size,
          height: size,
          border: "1px dashed var(--ai-line)",
        }}
      >
        <Sparkles size={12} />
      </span>
    );
  return (
    <span
      className="st"
      style={{ border: "1.5px solid var(--line)", width: size, height: size }}
    />
  );
}

export function Ring({
  value,
  size = 190,
  stroke = 12,
  color = "var(--warn)",
  track = "var(--bg-2)",
  children,
}) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  return (
    <div className="ring-wrap" style={{ width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke={track}
          strokeWidth={stroke}
          fill="none"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke={color}
          strokeWidth={stroke}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - Math.max(0, Math.min(1, value)))}
          style={{ transition: "stroke-dashoffset 1s linear" }}
        />
      </svg>
      <div className="ring-mid">{children}</div>
    </div>
  );
}

export function Modal({ title, children, onClose, footer, width }) {
  useEffect(() => {
    const k = (e) => e.key === "Escape" && onClose?.();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div
      className="scrim"
      onMouseDown={(e) => e.target === e.currentTarget && onClose?.()}
    >
      <div
        className="modal"
        style={width ? { width } : null}
        role="dialog"
        aria-label={title}
      >
        <div className="modal-h row">
          <h3>{title}</h3>
          <button
            className="btn ghost sm right"
            onClick={onClose}
            aria-label="Close"
          >
            <X size={14} />
          </button>
        </div>
        <div className="modal-b">{children}</div>
        {footer && <div className="modal-f">{footer}</div>}
      </div>
    </div>
  );
}

const TOAST_IC = {
  ok: [Check, "var(--ok)"],
  warn: [AlertTriangle, "var(--warn)"],
  crit: [AlertTriangle, "var(--crit)"],
  info: [Info, "var(--brand)"],
};
export function Toasts({ toasts }) {
  return (
    <div className="toasts">
      {toasts.map((t) => {
        const [Ic, c] = TOAST_IC[t.tone] || TOAST_IC.info;
        return (
          <div className="toast" key={t.id}>
            <span className="ic" style={{ background: c }}>
              <Ic size={13} color="#fff" strokeWidth={2.6} />
            </span>
            <div>
              <b>{t.title}</b>
              {t.body && <p>{t.body}</p>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function SimTag({ children = "Simulated" }) {
  return (
    <Badge tone="warn" mono dash>
      {children}
    </Badge>
  );
}

export function AiTag({ children = "AI draft" }) {
  return (
    <span className="ai-tag">
      <Sparkles size={11} />
      {children}
    </span>
  );
}
