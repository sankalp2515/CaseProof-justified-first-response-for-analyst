"use strict";
const $ = (id) => document.getElementById(id);
let network;
$("network-id").value = "BANK-" + Date.now();
async function action(button, path, body) {
  button.disabled = true;
  $("simulator-status").textContent = "Working…";
  try {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Demo-User": "admin" },
      body: JSON.stringify(body || {}),
    });
    const result = await response.json();
    if (!response.ok)
      throw Error(
        response.status === 409
          ? "This dataset identity already has different content. Choose a new name."
          : "The local simulator could not accept the request. Check the dataset name and services, then retry.",
      );
    return result;
  } catch (error) {
    $("simulator-status").textContent = error.message;
  } finally {
    button.disabled = false;
  }
}
$("network-create").onclick = async () => {
  const id = $("network-id").value.trim();
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(id)) {
    $("simulator-status").textContent =
      "Use 1–64 letters, numbers, hyphens or underscores.";
    return;
  }
  const result = await action($("network-create"), "/v1/local/bank-network", {
    network_id: id,
    seed: 35,
  });
  if (!result) return;
  network = result;
  $("bank-account").value = result.customer_account;
  $("bank-contact").value = result.first_contact;
  $("bank-reported").value = result.reported_at;
  $("initial-statement").value = result.initial_statement;
  $("followup-statement").value = result.followup_statement;
  $("receipt-download").href = result.receipt_url;
  $("dataset-download").href = result.dataset_url;
  $("network-summary").textContent =
    result.customers.length +
    " customers with pre-existing bank records. No complaint or customer evidence was created.";
  $("simulator-status").textContent =
    "Bank dataset ready. Next, open a complaint for Maya Synthetic.";
  $("new-complaint").href =
    "/inspector#new-complaint=" +
    encodeURIComponent(result.customer_account) +
    "&reported=" +
    encodeURIComponent(result.reported_at) +
    "&contact=" +
    encodeURIComponent(result.first_contact);
  $("network-result").hidden = false;
};
$("publish-reports").onclick = async () => {
  if (!network) return;
  const result = await action(
    $("publish-reports"),
    "/v1/local/bank-network/" +
      encodeURIComponent(network.network_id) +
      "/reports",
  );
  if (result)
    $("simulator-status").textContent =
      result.update_ids.length +
      " bank reports accepted. " +
      result.reprocess_jobs.length +
      " complaint(s) queued. Return to the analyst case for the updated revision.";
};
$("refresh-bank-data").onclick = async () => {
  if (!network) return;
  const result = await action($("refresh-bank-data"), "/v1/local/bank-network/" +
    encodeURIComponent(network.network_id) + "/refresh");
  if (result) $("simulator-status").textContent =
    "Fresh synthetic bank observations accepted. Return to the analyst case and review the new revision.";
};
