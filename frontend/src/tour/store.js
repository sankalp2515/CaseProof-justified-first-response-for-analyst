// Tour state shared by the launcher buttons and the overlay. Kept in sessionStorage
// so a reload or route change mid-tour resumes the same step and case.
import { useSyncExternalStore } from "react";
import { STEPS } from "./steps.js";

const KEY = "cp-demo-tour-v3";
const listeners = new Set();
let state = load();

function load() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(KEY) || "null");
    if (saved && Number.isInteger(saved.index)) {
      return {
        active: !!saved.active,
        index: Math.min(Math.max(saved.index, 0), STEPS.length - 1),
        caseId: typeof saved.caseId === "string" ? saved.caseId : null,
      };
    }
  } catch {
    /* storage unavailable: start fresh */
  }
  return { active: false, index: 0, caseId: null };
}

function set(patch) {
  state = { ...state, ...patch };
  try {
    sessionStorage.setItem(KEY, JSON.stringify(state));
  } catch {
    /* tour still works for this page view */
  }
  listeners.forEach((listener) => listener());
}

export const tour = {
  get: () => state,
  start: (index = 0) => set({ active: true, index }),
  restart: (caseId = null) =>
    set({ active: true, index: 0, caseId, launch: (state.launch || 0) + 1 }),
  stop: () => set({ active: false }),
  goTo: (index) =>
    set({ index: Math.min(Math.max(index, 0), STEPS.length - 1) }),
  next: () => tour.goTo(state.index + 1),
  back: () => tour.goTo(state.index - 1),
  setCase: (caseId) => caseId !== state.caseId && set({ caseId }),
  reset: () => set({ active: false, index: 0, caseId: null }),
  subscribe(listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};

export function useTour() {
  return useSyncExternalStore(tour.subscribe, tour.get);
}

// Case created during the tour: from the victim confirmation or an opened case.
export function caseFromRoute(route) {
  const match = route.match(
    /^\/(?:victim\/complaints|staff\/cases)\/([A-Za-z0-9_-]+)/,
  );
  return match ? match[1] : null;
}
