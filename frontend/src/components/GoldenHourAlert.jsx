import React from "react";
import { AlertCircle, Clock, ArrowRight } from "lucide-react";
import { formatMinor, remaining, time } from "../models/caseView.js";
import { useDisplayClock } from "../state/resources.jsx";
export default function GoldenHourAlert({ item, onOpen, onLater }) {
  const minutes = useDisplayClock(item.clock);
  if (minutes == null || minutes <= 0) return null;
  const selected = item.selected_bank_amount_minor;
  return (
    <section
      className="golden-alert"
      role="status"
      aria-label="Golden-hour priority alert"
    >
      <div className="golden-alert-head">
        <AlertCircle size={24} />
        <div className="grow">
          <b>
            {item.type === "arrived"
              ? "NEW COMPLAINT · GOLDEN HOUR"
              : "GOLDEN-HOUR PRIORITY"}
          </b>
          <small>Customer report · {time(item.reported_at)}</small>
        </div>
      </div>
      <small className="mono muted">{item.case_id}</small>
      <div className="golden-alert-amount">
        <strong>
          {selected != null
            ? formatMinor(selected)
            : item.amount_minor != null
              ? formatMinor(item.amount_minor)
              : "Assessment pending"}
        </strong>
        <span>
          {selected != null ? "selected bank payments" : "reported amount"}
        </span>
      </div>
      <p className="golden-alert-summary">
        {item.victim_summary ||
          "A customer has reported a payment scam. Assessment is in progress."}
      </p>
      <div className="golden-alert-payment">
        <b>Prompt analyst response</b>
        <small>
          Account {item.customer_account} · inspect the brief and sources
        </small>
      </div>
      <div className="golden-alert-actions">
        <span>
          <Clock size={14} /> {remaining(minutes)} response window
        </span>
        <button className="btn sm ghost" onClick={onLater}>
          Later
        </button>
        <button className="btn sm primary" onClick={onOpen}>
          Open case <ArrowRight size={13} />
        </button>
      </div>
      <small className="muted">
        Priority uses bank time. Availability of funds requires bank
        confirmation.
      </small>
    </section>
  );
}
