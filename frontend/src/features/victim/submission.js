import { apiRequest, post, evidenceForm } from "../../api/client.js";
export function validateFiles(files, narrative, limits, inventory = []) {
  const max = limits?.max_artifacts ?? 6,
    existingBytes = inventory.reduce((a, f) => a + f.byte_count, 0),
    narrativeBytes = new TextEncoder().encode(narrative).length;
  if (files.length + inventory.length + (inventory.length ? 0 : 1) > max)
    return `Choose at most ${max - 1} initial attachments; the narrative uses one evidence slot.`;
  if (
    files.some(
      (f) => !["image/png", "image/jpeg", "text/plain"].includes(f.type),
    )
  )
    return "Use PNG, JPEG or UTF-8 text. PDF is not supported.";
  if (
    files.some(
      (f) =>
        f.size === 0 || f.size > (limits?.max_file_bytes ?? 5 * 1024 * 1024),
    )
  )
    return "Each attachment must be non-empty and at most 5 MiB.";
  if (
    files.reduce((a, f) => a + f.size, 0) + existingBytes + narrativeBytes >
    (limits?.max_case_bytes ?? 20 * 1024 * 1024)
  )
    return "The case evidence limit is 20 MiB, including the narrative.";
  return null;
}
export const reconcileUploads = (intended, inventory) =>
  intended.map((f) => ({
    ...f,
    state: inventory.some((a) => a.sha256 === f.sha256)
      ? "received"
      : "pending",
  }));
export async function hashFile(file) {
  return [
    ...new Uint8Array(
      await crypto.subtle.digest("SHA-256", await file.arrayBuffer()),
    ),
  ]
    .map((n) => n.toString(16).padStart(2, "0"))
    .join("");
}
const key = (account) => "cp-studio-report:" + account;
export function readJournal(account) {
  try {
    return JSON.parse(sessionStorage.getItem(key(account)) || "null");
  } catch {
    return null;
  }
}
export function clearJournal(account) {
  sessionStorage.removeItem(key(account));
}
export function saveJournal(account, journal) {
  sessionStorage.setItem(key(account), JSON.stringify(journal));
}
export async function prepareJournal(account, payload, files) {
  const old = readJournal(account);
  if (old) return old;
  const journal = {
    payload: { ...payload, submission_id: crypto.randomUUID() },
    files: await Promise.all(
      files.map(async (f) => ({
        name: f.file.name,
        sha256: await hashFile(f.file),
        size: f.file.size,
        type: f.file.type,
        kind: f.kind,
        state: "pending",
      })),
    ),
    caseId: null,
  };
  saveJournal(account, journal);
  return journal;
}
export async function submitReport(
  account,
  journal,
  files,
  onProgress = () => {},
) {
  if (!journal.caseId) {
    const receipt = await post("/v1/victim/complaints", journal.payload);
    journal = {
      ...journal,
      caseId: receipt.case_id,
      bankReference: receipt.bank_reference,
    };
    saveJournal(account, journal);
    onProgress(journal);
  }
  let inventory = await apiRequest(`/v1/victim/complaints/${journal.caseId}`);
  journal = {
    ...journal,
    files: reconcileUploads(journal.files, inventory.artifacts || []),
  };
  saveJournal(account, journal);
  onProgress(journal);
  const available = await Promise.all(
    files.map(async (f) => ({ ...f, sha256: await hashFile(f.file) })),
  );
  for (let i = 0; i < journal.files.length; i++) {
    const item = journal.files[i];
    if (item.state === "received") continue;
    const chosen = available.find((f) => f.sha256 === item.sha256);
    if (!chosen) {
      journal.files[i] = {
        ...item,
        state: "pending",
        error: "Reselect this file to continue.",
      };
      continue;
    }
    try {
      await apiRequest(`/v1/victim/complaints/${journal.caseId}/artifacts`, {
        method: "POST",
        body: evidenceForm(chosen.file, item.kind),
      });
      journal.files[i] = { ...item, state: "received" };
    } catch (error) {
      try {
        inventory = await apiRequest(`/v1/victim/complaints/${journal.caseId}`);
        if (inventory.artifacts?.some((a) => a.sha256 === item.sha256))
          journal.files[i] = { ...item, state: "received" };
        else
          journal.files[i] = {
            ...item,
            state: "pending",
            error: error.message,
          };
      } catch {
        journal.files[i] = {
          ...item,
          state: "pending",
          error:
            "Could not confirm receipt. Check for updates before retrying.",
        };
      }
    }
    saveJournal(account, journal);
    onProgress({ ...journal, files: [...journal.files] });
  }
  saveJournal(account, journal);
  onProgress(journal);
  return journal;
}
