/* global self, clients */

self.addEventListener("push", function (event) {
  let data = {};
  try {
    data = event && event.data ? event.data.json() : {};
  } catch (err) {
    void err;
    data = {};
  }

  const title = data && data.title ? String(data.title) : "ViaRah";
  const body =
    data && data.body ? String(data.body) : "You have a new notification.";
  const url = data && data.url ? String(data.url) : "/";

  event.waitUntil(
    self.registration.showNotification(title, { body: body, data: { url: url } })
  );
});

self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  const url =
    event.notification && event.notification.data && event.notification.data.url
      ? event.notification.data.url
      : "/";
  event.waitUntil(clients.openWindow(url));
});
