"use strict";
const $ = (id) => document.getElementById(id);
const newSubmissionId = () =>
  [...crypto.getRandomValues(new Uint32Array(4))]
    .map((n) => n.toString(16))
    .join("-");
let account,
  currentCase,
  submissionId = newSubmissionId();
const message = (text) => {
  $("victim-status").textContent = text;
};
const money = (n) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(
    n / 100,
  );
async function api(path, options = {}) {
  const response = await fetch(path, { cache: "no-store", ...options });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      data.error ||
        data.detail ||
        "Could not complete this action. Retry; your complaint is kept.",
    );
  return data;
}
const post = (path, body) =>
  api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
function node(tag, text) {
  const n = document.createElement(tag);
  n.textContent = text;
  return n;
}
async function receipt(cid) {
  currentCase = cid;
  const data = await api("/v1/victim/complaints/" + encodeURIComponent(cid));
  $("complaint-receipt").hidden = false;
  $("receipt-id").textContent =
    "Bank complaint reference: CEDAR-" + cid.slice(5);
  $("receipt-state").textContent =
    data.status + " · " + data.evidence_count + " evidence items received";
  $("victim-inbox").replaceChildren();
  for (const item of data.messages) {
    const section = node("section", "");
    section.append(
      node("h3", "Your analyst needs information"),
      node("p", item.text),
    );
    if (item.reply_url) {
      const a = node("a", "Answer this request / upload evidence");
      a.href = new URL(item.reply_url).pathname;
      section.append(a);
    } else
      section.append(
        node("p", "The reply link expired. Ask the fraud desk to renew it."),
      );
    $("victim-inbox").append(section);
  }
  if (data.messages.length)
    for (const tx of data.candidate_payments) {
      const section = node("section", "");
      section.append(
        node(
          "p",
          money(tx.amount_minor) +
            " · " +
            new Date(tx.ts).toLocaleString() +
            " · " +
            tx.payee,
        ),
      );
      for (const [label, disputed] of [
        ["Yes, include this payment", true],
        ["No, this payment is unrelated", false],
      ]) {
        const button = node("button", label);
        button.onclick = async () => {
          button.disabled = true;
          try {
            await post("/v1/victim/complaints/" + cid + "/payments", {
              transaction_id: tx.txn_id,
              disputed,
            });
            message(
              "Your answer is received. The analyst will see the updated assessment.",
            );
            await receipt(cid);
          } catch (error) {
            message(error.message);
          } finally {
            button.disabled = false;
          }
        };
        section.append(button);
      }
      $("victim-inbox").append(section);
    }
}
async function loadAccount() {
  account = await api("/v1/victim/me");
  $("demo-entry").hidden = true;
  $("victim-account").hidden = false;
  $("victim-name").textContent = account.customer.display_name;
  $("demo-time").textContent =
    "Demo time: " +
    new Date(account.demo_time).toLocaleString() +
    " · Original payment times remain unchanged.";
  $("victim-cases").replaceChildren();
  if (!account.complaints.length)
    $("victim-cases").append(node("p", "No complaints submitted yet."));
  for (const cid of account.complaints) {
    const b = node("button", "Open " + cid);
    b.className = "secondary";
    b.onclick = () => receipt(cid).catch((e) => message(e.message));
    $("victim-cases").append(b);
  }
  $("victim-transactions").replaceChildren();
  for (const tx of [...account.transactions].sort((a, b) =>
    b.ts.localeCompare(a.ts),
  )) {
    const row = node("div", "");
    row.className = "payment-choice";
    const label = node("label", "");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.name = "payment";
    input.value = tx.txn_id;
    label.append(
      input,
      document.createTextNode(money(tx.amount_minor) + " · " + tx.payee),
    );
    row.append(
      label,
      node("small", new Date(tx.ts).toLocaleString() + " · " + tx.reference),
    );
    const download = node("a", "View bank receipt");
    download.href = "/v1/victim/receipts/" + encodeURIComponent(tx.txn_id);
    download.target = "_blank";
    download.rel = "noopener";
    row.append(download);
    $("victim-transactions").append(row);
  }
}
$("victim-enter").onclick = async () => {
  try {
    await post("/v1/victim/sessions", {
      customer_id: $("victim-person").value,
    });
    await loadAccount();
    $("victim-form").hidden = false;
    $("complaint-receipt").hidden = true;
    currentCase = null;
  } catch (e) {
    message(e.message);
  }
};
$("victim-switch").onclick = () => {
  $("demo-entry").hidden = false;
  $("victim-account").hidden = true;
  currentCase = null;
  $("victim-form").reset();
  submissionId = newSubmissionId();
};
$("victim-new").onclick = () => {
  $("victim-form").hidden = false;
  $("victim-form").reset();
  $("complaint-receipt").hidden = true;
  currentCase = null;
  submissionId = newSubmissionId();
};
$("receipt-refresh").onclick = () =>
  receipt(currentCase).catch((e) => message(e.message));
$("victim-form").onsubmit = async (event) => {
  event.preventDefault();
  $("victim-submit").disabled = true;
  try {
    const files = [...$("victim-files").files];
    if (
      files.length > 4 ||
      files.some(
        (f) =>
          f.size > 5 * 1024 * 1024 ||
          !["image/png", "image/jpeg", "text/plain"].includes(f.type),
      )
    )
      throw new Error(
        "Use up to four PNG, JPEG or text files, no larger than 5 MiB each. Your text is kept.",
      );
    if (!currentCase) {
      const result = await post("/v1/victim/complaints", {
        submission_id: submissionId,
        narrative: $("victim-story").value,
        transaction_ids: [
          ...document.querySelectorAll('input[name="payment"]:checked'),
        ].map((n) => n.value),
        payment_authorisation: $("victim-authorisation").value,
        first_contact: $("victim-contact").value
          ? $("victim-contact").value + ":00+05:30"
          : null,
        bank_reference: $("victim-bank-ref").value,
        ncrp_reference: $("victim-ncrp-ref").value,
        fir_reference: $("victim-fir-ref").value,
      });
      currentCase = result.case_id;
    }
    message("Complaint received. Sending available evidence…");
    for (const file of files) {
      const form = new FormData();
      form.append("file", file);
      form.append("kind", file.type === "text/plain" ? "narrative" : "receipt");
      await api("/v1/victim/complaints/" + currentCase + "/artifacts", {
        method: "POST",
        body: form,
      });
    }
    await loadAccount();
    await receipt(currentCase);
    $("victim-form").hidden = true;
    message(
      "Your complaint and evidence are received. Keep your bank complaint reference.",
    );
  } catch (e) {
    message(
      e.message +
        (currentCase
          ? " Your complaint exists; retry to finish attaching evidence."
          : ""),
    );
  } finally {
    $("victim-submit").disabled = false;
  }
};
(async () => {
  try {
    const data = await api("/v1/victim/demo-customers");
    for (const p of data.customers) {
      const n = node("option", p.display_name);
      n.value = p.account;
      $("victim-person").append(n);
    }
    try {
      await loadAccount();
    } catch {}
  } catch (e) {
    message(e.message);
  }
})();
setInterval(() => {
  if (currentCase && !document.hidden)
    receipt(currentCase).catch((e) => message(e.message));
}, 5000);

$("practice-session").onclick = async () => {
  $("practice-session").disabled = true;
  try {
    await post("/v1/victim/demo-session", {});
    location.reload();
  } catch (e) {
    message(e.message);
    $("practice-session").disabled = false;
  }
};
