const token = location.pathname.split("/").pop();
const customer = (id) => document.getElementById(id);
const path = "/v1/customer/" + encodeURIComponent(token);
let entries = [],
  uploads = 0,
  sending = false;
async function call(url, options) {
  const response = await fetch(url, options);
  let value;
  try {
    value = await response.json();
  } catch {
    throw Error("The local service is unavailable. Please try again shortly.");
  }
  if (!response.ok) {
    if (response.status === 403) {
      customer("customer-form").hidden = true;
      throw Error(
        "This private link is closed or expired. Ask the fraud desk for a new link.",
      );
    }
    if (response.status === 413)
      throw Error("This file is too large. Choose a file smaller than 5 MiB.");
    if (response.status === 422)
      throw Error(
        "The evidence could not be accepted. Check the file format, size and remaining evidence slots. Use a new link if the case has reached its limit.",
      );
    if (response.status === 409)
      throw Error(
        "The complaint changed while you were submitting. Try again; files already received are kept.",
      );
    throw Error(
      "Your response was not confirmed. Please try again shortly or ask the fraud desk for help.",
    );
  }
  return value;
}
function listFiles() {
  customer("file-list").replaceChildren();
  for (const entry of entries) {
    const li = document.createElement("li");
    li.textContent =
      entry.file.name +
      " · " +
      (entry.file.size / 1024).toFixed(0) +
      " KiB · " +
      (entry.uploaded ? "Received" : "Ready to upload");
    if (!entry.uploaded && !sending) {
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "secondary";
      remove.textContent = "Remove";
      remove.setAttribute("aria-label", "Remove " + entry.file.name);
      remove.style.marginLeft = "12px";
      remove.onclick = () => {
        entries = entries.filter((x) => x !== entry);
        listFiles();
      };
      li.append(remove);
    }
    customer("file-list").append(li);
  }
  customer("file-help").textContent =
    "PNG, JPEG or UTF-8 text; up to 5 MiB each. " +
    Math.max(0, 4 - uploads) +
    " evidence slots remain on this link. A written response uses one slot.";
}
call(path)
  .then((data) => {
    customer("customer-request").textContent = data.request;
    customer("link-expiry").textContent =
      "Private link expires " +
      new Date(data.expires_at * 1000).toLocaleString() +
      ".";
    uploads = data.uploads;
    listFiles();
    customer("customer-form").hidden = false;
  })
  .catch((error) => {
    customer("customer-request").textContent = "This link is unavailable.";
    customer("customer-status").textContent = error.message;
  });
customer("customer-file").onchange = () => {
  customer("customer-error").textContent = "";
  for (const file of customer("customer-file").files) {
    const mime = file.type || (/\.txt$/i.test(file.name) ? "text/plain" : "");
    if (!["image/png", "image/jpeg", "text/plain"].includes(mime)) {
      customer("customer-error").textContent =
        "Choose a PNG, JPEG or UTF-8 text file. PDF documents are not supported.";
      continue;
    }
    if (!file.size || file.size > 5 * 1024 * 1024) {
      customer("customer-error").textContent =
        "Choose a nonempty file smaller than 5 MiB.";
      continue;
    }
    if (uploads + entries.filter((e) => !e.uploaded).length >= 4) {
      customer("customer-error").textContent =
        "This link has no more file slots. Remove a file or ask the fraud desk for help.";
      break;
    }
    entries.push({
      file,
      mime,
      kind: customer("customer-kind").value,
      uploaded: false,
    });
  }
  customer("customer-file").value = "";
  listFiles();
};
customer("customer-notes").oninput = () => {
  if (!sending && customer("customer-notes").value.trim())
    customer("customer-error").textContent = "";
};
customer("customer-form").onsubmit = async (event) => {
  event.preventDefault();
  if (sending) return;
  const notes = customer("customer-notes").value.trim(),
    unavailable = customer("customer-unavailable").checked;
  customer("customer-error").textContent = "";
  if (!entries.length && !uploads && !notes) {
    customer("customer-error").textContent =
      "Add a file or write a response before submitting.";
    customer("customer-notes").focus();
    return;
  }
  if (unavailable && !notes) {
    customer("customer-error").textContent =
      "Please explain why you cannot provide the evidence.";
    customer("customer-notes").focus();
    return;
  }
  if (
    uploads + entries.filter((e) => !e.uploaded).length + (notes ? 1 : 0) >
    4
  ) {
    customer("customer-error").textContent =
      "Leave one evidence slot for your written response. Remove a file or submit without a written response.";
    return;
  }
  sending = true;
  for (const control of customer("customer-form").elements)
    control.disabled = true;
  customer("customer-submit").setAttribute("aria-busy", "true");
  listFiles();
  try {
    const pending = entries.filter((e) => !e.uploaded);
    for (let i = 0; i < pending.length; i++) {
      customer("customer-status").textContent =
        "Uploading file " + (i + 1) + " of " + pending.length + "…";
      const entry = pending[i],
        form = new FormData();
      const file = entry.file.type
        ? entry.file
        : new Blob([entry.file], { type: entry.mime });
      form.append("file", file, entry.file.name);
      form.append("kind", entry.kind);
      await call(path + "/artifacts", { method: "POST", body: form });
      entry.uploaded = true;
      uploads += 1;
      listFiles();
    }
    customer("customer-status").textContent = "Submitting your response…";
    await call(path + "/complete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notes, unavailable }),
    });
    customer("customer-form").hidden = true;
    customer("request-section").hidden = true;
    customer("customer-intro").hidden = true;
    customer("customer-receipt").hidden = false;
    customer("customer-status").textContent =
      "Your response was received and queued for the analyst. This link is now closed.";
    customer("customer-receipt").setAttribute("tabindex", "-1");
    customer("customer-receipt").focus();
  } catch (error) {
    customer("customer-error").textContent = error.message;
    customer("customer-status").textContent =
      "Submission has not been confirmed. Any files marked Received are kept and will not be uploaded again from this page.";
  } finally {
    sending = false;
    for (const control of customer("customer-form").elements)
      control.disabled = false;
    customer("customer-submit").removeAttribute("aria-busy");
    listFiles();
  }
};
