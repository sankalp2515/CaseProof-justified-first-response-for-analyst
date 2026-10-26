import { useState, useEffect } from "react";
export const go = (path) => {
  location.hash = path;
};
export function useRoute() {
  const [route, set] = useState(() => location.hash.slice(1) || "/staff/queue");
  useEffect(() => {
    const change = () => set(location.hash.slice(1) || "/staff/queue");
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  return route;
}
