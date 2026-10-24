self.addEventListener('install', () => {
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim())
})

self.addEventListener('push', (event) => {
  let data = {}
  try {
    data = event.data ? JSON.parse(event.data.text()) : {}
  } catch (e) {
    /* ignore malformed payloads */
  }
  const title = data.title || 'Car Lottery Admin'
  const options = {
    body: data.body || '',
    tag: data.tag || 'admin-notify',
    renotify: true,
    data: { url: data.url || '/admin-dashboard' },
  }
  event.waitUntil(self.registration.showNotification(title, options))
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const target = new URL(
    (event.notification.data && event.notification.data.url) || '/admin-dashboard',
    self.registration.scope,
  ).href
  event.waitUntil(
    (async () => {
      const wins = await self.clients.matchAll({ type: 'window' })
      for (const win of wins) {
        if (new URL(win.url).origin === new URL(target).origin) {
          await win.navigate(target)
          return win.focus()
        }
      }
      return self.clients.openWindow(target)
    })(),
  )
})

// Browser push keys rotate: re-subscribe and re-register with the backend.
self.addEventListener('pushsubscriptionchange', (event) => {
  event.waitUntil(
    (async () => {
      try {
        const publicKey = await (await fetch('/api/admin-dashboard/push/vapid-key/')).json()
        const sub = await self.registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(publicKey.public_key),
        })
        const { endpoint, keys } = sub.toJSON()
        await fetch('/api/admin-dashboard/push/subscribe/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ endpoint, keys }),
        })
      } catch (e) {
        /* best-effort only */
      }
    })(),
  )
})

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(base64)
  const output = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i++) {
    output[i] = raw.charCodeAt(i)
  }
  return output
}