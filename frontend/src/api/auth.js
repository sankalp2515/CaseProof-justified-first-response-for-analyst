// Staff credentials live only in this module's memory. Victim calls use cookies.
// access: "google" (verified Google ID token) or "practice" (labelled synthetic
// personas; the cloud server confines them to the visitor's own practice session).
export function createAuth(
  profile = "local",
  now = Date.now,
  access = "google",
) {
  let token = null,
    expires = 0;
  const personas = profile === "local" || access === "practice";
  return {
    profile,
    access: profile === "local" ? "local" : access,
    personas,
    accept(value, expiresAt) {
      token = value;
      expires = expiresAt;
    },
    clear() {
      token = null;
      expires = 0;
    },
    ready() {
      return personas || Boolean(token && now() < expires);
    },
    headers(persona) {
      if (!persona) return {};
      if (!personas) {
        if (!token || now() >= expires) {
          token = null;
          throw new Error("Sign in to the staff workspace again.");
        }
        return { Authorization: `Bearer ${token}` };
      }
      if (!["analyst", "reviewer", "admin"].includes(persona))
        throw new Error("Unsupported demo identity");
      return { "X-Demo-User": persona };
    },
  };
}
export const auth = createAuth(
  import.meta.env.VITE_AUTH_PROFILE === "cloud" ? "cloud" : "local",
  Date.now,
  import.meta.env.VITE_STAFF_ACCESS === "practice" ? "practice" : "google",
);
// Signed-in cloud permissions are enforced by the server. No role-discovery endpoint exists yet.
export const canRequestRole = (persona, role) =>
  !auth.personas || persona === role || persona === "admin";
