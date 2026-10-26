import React, { useEffect, useRef, useState } from "react";
import { auth } from "../api/auth.js";
import { LogoMark, ErrorBanner } from "./live.jsx";
export default function StaffSignIn({ onReady }) {
  const mount = useRef(null),
    [error, setError] = useState(null);
  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
  useEffect(() => {
    if (!clientId) return;
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.onload = () => {
      if (!mount.current) return;
      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: (response) => {
          if (!response.credential) {
            setError(new Error("Google did not return a staff credential."));
            return;
          }
          // The server verifies signature, audience and role mapping. Decoding is only for expiry.
          try {
            const part = response.credential
              .split(".")[1]
              .replace(/-/g, "+")
              .replace(/_/g, "/");
            const expiry = JSON.parse(atob(part)).exp * 1000;
            if (!Number.isFinite(expiry) || expiry <= Date.now())
              throw new Error();
            auth.accept(response.credential, expiry);
            onReady();
          } catch {
            setError(
              new Error(
                "Sign-in credential expired or unavailable. Try again.",
              ),
            );
          }
        },
      });
      window.google.accounts.id.renderButton(mount.current, {
        theme: "outline",
        size: "large",
      });
    };
    script.onerror = () =>
      setError(
        new Error(
          "Google sign-in could not load. Check your connection and retry.",
        ),
      );
    document.head.appendChild(script);
    return () => {
      script.remove();
    };
  }, [clientId, onReady]);
  return (
    <div className="staff-signin">
      <span className="logo-mark">
        <LogoMark />
      </span>
      <h1>Staff sign-in</h1>
      <p>CaseProof · bank payment-scam response</p>
      <ErrorBanner error={error} />
      {clientId ? (
        <div ref={mount} />
      ) : (
        <div className="banner warn">
          Cloud staff sign-in is unavailable. A public Google OAuth client ID
          must be configured.
        </div>
      )}
      <p className="muted">
        Your institution assigns access on the server. Cloud authentication has
        not been verified live.
      </p>
      <a className="btn" href="#/victim/start">
        Open reporting portal
      </a>
    </div>
  );
}
