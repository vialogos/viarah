from django.db import connections
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie


@ensure_csrf_cookie
def index(_request):
    html = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>ViaRah</title>
    <link rel="manifest" href="/manifest.webmanifest" />
    <style>
      body {
        font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
        padding: 24px;
        max-width: 720px;
        margin: 0 auto;
      }
      button {
        padding: 10px 14px;
        border-radius: 8px;
        border: 1px solid #ccc;
        background: #fff;
        cursor: pointer;
      }
      button.primary { background: #111827; color: #fff; border-color: #111827; }
      .row { display: flex; gap: 12px; flex-wrap: wrap; }
      .muted { color: #6b7280; }
      pre { background: #f3f4f6; padding: 12px; border-radius: 8px; overflow: auto; }
    </style>
  </head>
  <body>
    <h1>ViaRah</h1>
    <p class="muted">Web Push/PWA v1 smoke page (service worker + subscribe/unsubscribe).</p>

    <div class="row">
      <button id="enable" class="primary" type="button">Enable notifications</button>
      <button id="disable" type="button">Disable notifications</button>
    </div>

    <p id="status" class="muted"></p>
    <pre id="log"></pre>

    <script>
      function log(msg) {
        const el = document.getElementById("log");
        el.textContent = (el.textContent || "") + String(msg) + "\\n";
      }

      function getCookie(name) {
        const value = "; " + document.cookie;
        const parts = value.split("; " + name + "=");
        if (parts.length === 2) return parts.pop().split(";").shift();
        return "";
      }

      function base64UrlToUint8Array(base64Url) {
        const padding = "=".repeat((4 - (base64Url.length % 4)) % 4);
        const base64 = (base64Url + padding).replace(/-/g, "+").replace(/_/g, "/");
        const rawData = atob(base64);
        const outputArray = new Uint8Array(rawData.length);
        for (let i = 0; i < rawData.length; i++) {
          outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
      }

      async function fetchJson(url, opts) {
        const res = await fetch(url, Object.assign({ credentials: "include" }, opts || {}));
        const body = await res.json().catch(() => ({}));
        if (!res.ok) {
          throw new Error((body && body.error) ? body.error : ("HTTP " + res.status));
        }
        return body;
      }

      async function registerServiceWorker() {
        if (!("serviceWorker" in navigator)) {
          throw new Error("serviceWorker not supported in this browser");
        }
        const reg = await navigator.serviceWorker.register("/service-worker.js");
        await navigator.serviceWorker.ready;
        return reg;
      }

      async function enable() {
        const status = document.getElementById("status");
        status.textContent = "";

        if (!("Notification" in window)) {
          throw new Error("Notifications not supported");
        }

        const perm = await Notification.requestPermission();
        if (perm !== "granted") {
          throw new Error("Notification permission not granted");
        }

        const reg = await registerServiceWorker();
        const keyRes = await fetchJson("/api/push/vapid_public_key");
        const appServerKey = base64UrlToUint8Array(String(keyRes.public_key || ""));

        const sub = await reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: appServerKey,
        });
        const subJson = sub.toJSON();

        const csrf = getCookie("csrftoken");
        const saved = await fetchJson("/api/push/subscriptions", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
          body: JSON.stringify({ subscription: subJson, user_agent: navigator.userAgent }),
        });

        log("Subscribed and saved subscription: " + saved.subscription.id);
        status.textContent = "Enabled.";
      }

      async function disable() {
        const status = document.getElementById("status");
        status.textContent = "";

        const reg = await registerServiceWorker();
        const sub = await reg.pushManager.getSubscription();
        if (!sub) {
          status.textContent = "No subscription found in this browser.";
          return;
        }

        const subJson = sub.toJSON();
        const list = await fetchJson("/api/push/subscriptions");
        const match = (list.subscriptions || []).find((r) => r.endpoint === subJson.endpoint);
        if (match && match.id) {
          const csrf = getCookie("csrftoken");
          const res = await fetch("/api/push/subscriptions/" + match.id, {
            method: "DELETE",
            headers: { "X-CSRFToken": csrf },
            credentials: "include",
          });
          if (res.ok) {
            log("Deleted server subscription id: " + match.id);
          } else {
            log("Server delete failed: HTTP " + res.status);
          }
        } else {
          log("Could not match server subscription row to delete.");
          log("Server cleanup may occur on 404/410.");
        }

        await sub.unsubscribe();
        log("Unsubscribed in browser.");
        status.textContent = "Disabled.";
      }

      document.getElementById("enable").addEventListener("click", () => {
        enable().catch((e) => {
          log(e);
          document.getElementById("status").textContent = String(e.message || e);
        });
      });
      document.getElementById("disable").addEventListener("click", () => {
        disable().catch((e) => {
          log(e);
          document.getElementById("status").textContent = String(e.message || e);
        });
      });

      registerServiceWorker()
        .then(() => log("Service worker registered."))
        .catch((e) => log("Service worker registration failed: " + e));
    </script>
  </body>
</html>
"""
    return HttpResponse(html, content_type="text/html; charset=utf-8")


def manifest_webmanifest(_request):
    return JsonResponse(
        {
            "name": "ViaRah",
            "short_name": "ViaRah",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#111827",
            "theme_color": "#111827",
            "icons": [],
        },
        content_type="application/manifest+json",
    )


def service_worker_js(_request):
    js = """self.addEventListener('push', function (event) {
  let data = {};
  try {
    data = event && event.data ? event.data.json() : {};
  } catch (e) {
    data = {};
  }

  const title = (data && data.title) ? String(data.title) : 'ViaRah';
  const body = (data && data.body) ? String(data.body) : 'You have a new notification.';
  const url = (data && data.url) ? String(data.url) : '/';

  event.waitUntil(
    self.registration.showNotification(title, { body: body, data: { url: url } })
  );
});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  const url = (event.notification && event.notification.data && event.notification.data.url)
    ? event.notification.data.url
    : '/';
  event.waitUntil(clients.openWindow(url));
});
"""
    res = HttpResponse(js, content_type="application/javascript; charset=utf-8")
    res["Cache-Control"] = "no-cache"
    return res


def healthz(_request):
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1;")
            cursor.fetchone()
    except Exception:
        return HttpResponse("unhealthy", status=503, content_type="text/plain")

    return HttpResponse("ok", content_type="text/plain")
