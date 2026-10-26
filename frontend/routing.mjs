export function studioRedirect(url) {
  if (url === "/app") return "/app/";
  const match = /^\/customer\/([A-Za-z0-9_-]+)$/.exec(url);
  return match ? "/app/#/victim/reply/" + match[1] : null;
}
export function studioRoutes() {
  return {
    name: "studio-entry-routes",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (req.url === "/") req.url = "/app/landing/index.html";
        const target = studioRedirect(req.url);
        if (!target) return next();
        res.statusCode = 302;
        res.setHeader("Location", target);
        res.setHeader("Cache-Control", "no-store");
        res.setHeader("Referrer-Policy", "no-referrer");
        res.end();
      });
    },
  };
}
