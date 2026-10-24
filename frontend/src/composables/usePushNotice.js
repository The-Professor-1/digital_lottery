import { reactive } from 'vue'
import { getPushVapidKey, pushSubscribe, pushUnsubscribe } from '../services/api'

export const pushState = reactive({
  supported: false,
  ready: false,
  enabled: false,
})

export function isPushSupported() {
  return (
    typeof window !== 'undefined' &&
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window &&
    window.isSecureContext === true
  )
}

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

/** Detect support, register the service worker and read the current state. */
export async function initPush() {
  if (!isPushSupported()) {
    pushState.supported = false
    return pushState
  }
  pushState.supported = true
  try {
    await navigator.serviceWorker.register('/sw.js')
  } catch (error) {
    return pushState
  }
  try {
    const reg = await navigator.serviceWorker.ready
    const sub = await reg.pushManager.getSubscription()
    pushState.enabled = !!(sub && Notification.permission === 'granted')
  } catch (error) {
    pushState.enabled = false
  }
  pushState.ready = true
  return pushState
}

/** Ask permission, subscribe via the browser push service and persist it. */
export async function enablePush(role) {
  if (!isPushSupported()) return false
  if (Notification.permission === 'denied') return false
  if (Notification.permission !== 'granted') {
    const permission = await Notification.requestPermission()
    if (permission !== 'granted') return false
  }
  const publicKey = await getPushVapidKey()
  if (!publicKey) throw new Error('Push is not configured on the server')
  const reg = await navigator.serviceWorker.ready
  const sub = await reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(publicKey),
  })
  const data = sub.toJSON()
  await pushSubscribe({ endpoint: data.endpoint, keys: data.keys }, { role })
  pushState.enabled = true
  return true
}

/** Unsubscribe from the browser push service and drop the stored endpoint. */
export async function disablePush() {
  if (!isPushSupported()) return
  try {
    const reg = await navigator.serviceWorker.ready
    const sub = await reg.pushManager.getSubscription()
    if (sub) {
      try {
        await pushUnsubscribe(sub.endpoint)
      } catch (error) {
        /* server may be unreachable; still unsubscribe locally */
      }
      await sub.unsubscribe()
    }
  } catch (error) {
    /* ignore */
  }
  pushState.enabled = false
}