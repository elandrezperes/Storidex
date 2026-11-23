const responseHeaders = {
  "Cache-Control": "no-store",
  "X-Content-Type-Options": "nosniff",
  "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'",
};

function error(status, message) {
  return Response.json({ error: message }, { status, headers: responseHeaders });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const user = request.headers.get("oai-authenticated-user-id");
    const cookie = request.headers.get("Cookie") ?? "";
    const guest = cookie.match(/(?:^|;\s*)__Host-storidex=([a-f0-9]{32})(?:;|$)/)?.[1];
    if (request.method === "GET" && Object.hasOwn(assets, url.pathname)) {
      const [mime, body] = assets[url.pathname];
      const headers = new Headers({ ...responseHeaders, "Content-Type": mime });
      if (url.pathname === "/" && !guest) {
        const id = crypto.randomUUID().replaceAll("-", "");
        headers.append("Set-Cookie",
          `__Host-storidex=${id}; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=31536000`);
      }
      return new Response(body, { headers });
    }
    const read = /^\/api\/proyectos(?:\/[a-f0-9]{32}(?:\/(?:pdf|audio))?)?$/;
    const write = /^\/api\/proyectos(?:\/[a-f0-9]{32}\/(?:investigar|persona|premisas|escaleta|preparar|editar|revisar|voz|canva))?$/;
    const post = request.method === "POST";
    if (!(post ? write.test(url.pathname) : request.method === "GET" && read.test(url.pathname))) {
      return error(404, "Página o acción no encontrada.");
    }
    if (!user && !guest) return error(400, "Abre Storidex con las cookies habilitadas.");
    if (post && (request.headers.get("Origin") !== url.origin ||
        request.headers.get("Content-Type") !== "application/json")) {
      return error(403, "Solicitud de otro origen.");
    }
    if (!env.STORIDEX_BACKEND_URL || !env.STORIDEX_PROXY_SECRET) {
      return error(503, "Falta configurar el servicio de Storidex.");
    }
    try {
      const backend = new URL(env.STORIDEX_BACKEND_URL);
      if (backend.protocol !== "https:" || backend.username || backend.password) {
        return error(503, "El servicio de Storidex requiere HTTPS.");
      }
      const viewer = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(user ?? `guest:${guest}`));
      const scope = Array.from(new Uint8Array(viewer), byte => byte.toString(16).padStart(2, "0")).join("");
      const headers = {
        Authorization: `Bearer ${env.STORIDEX_PROXY_SECRET}`,
        "X-Storidex-Viewer": scope,
      };
      let body;
      if (post) {
        const length = Number(request.headers.get("Content-Length"));
        if (!Number.isSafeInteger(length) || length < 1 || length > 98304) {
          return error(413, "El tamaño del formulario no es válido.");
        }
        body = await request.arrayBuffer();
        if (body.byteLength !== length) return error(400, "El formulario llegó incompleto.");
        headers["Content-Type"] = "application/json";
      }
      const reply = await fetch(new URL(url.pathname, backend), {
        method: request.method, headers, body, redirect: "manual",
      });
      if (reply.status >= 300 && reply.status < 400) {
        return error(502, "El servicio intentó redirigir la solicitud.");
      }
      const type = reply.headers.get("Content-Type");
      if (!["application/json", "application/pdf", "audio/mpeg"].includes(type?.split(";")[0])) {
        return error(502, "El servicio devolvió una respuesta inesperada.");
      }
      const outgoing = new Headers({ ...responseHeaders, "Content-Type": type });
      const attachment = reply.headers.get("Content-Disposition");
      if (attachment) outgoing.set("Content-Disposition", attachment);
      return new Response(reply.body, { status: reply.status, headers: outgoing });
    } catch (cause) {
      console.error("Error de conexión con Railway", cause?.name);
      return error(502, "No se pudo contactar con el servicio de Storidex.");
    }
  },
};
