// Telegram Web App SDK - using window.Telegram.WebApp directly
let telegramWebApp = null

export function initTelegramWebApp() {
  try {
    // Check if running in Telegram Web App
    if (window.Telegram && window.Telegram.WebApp) {
      window.Telegram.WebApp.ready()
      telegramWebApp = window.Telegram.WebApp
      return true
    } else {
      console.warn('Not running in Telegram Web App environment')
      // Create a mock for local development
      telegramWebApp = {
        ready: () => {},
        close: () => {},
        expand: () => {},
        MainButton: {
          setText: () => {},
          show: () => {},
          hide: () => {}
        }
      }
      return false
    }
  } catch (error) {
    console.error('Telegram Web App initialization failed:', error)
    return false
  }
}

export function getTelegramWebApp() {
  return telegramWebApp || (window.Telegram && window.Telegram.WebApp) || null
}

export function getInitData() {
  if (window.Telegram && window.Telegram.WebApp) {
    // initData is a string, not an object
    return window.Telegram.WebApp.initData || null
  }
  return null
}

export function getInitDataRaw() {
  if (window.Telegram && window.Telegram.WebApp) {
    return window.Telegram.WebApp.initDataUnsafe || {}
  }
  return {}
}

// Request phone number from Telegram Web App
// Note: This uses the MainButton to request phone number
export function requestPhoneNumber() {
  return new Promise((resolve, reject) => {
    if (window.Telegram && window.Telegram.WebApp) {
      const webApp = window.Telegram.WebApp
      
      // Set up MainButton to request phone number
      webApp.MainButton.setText('Share Phone Number')
      webApp.MainButton.show()
      
      // Handle phone number request
      const handlePhoneRequest = () => {
        if (webApp.initDataUnsafe && webApp.initDataUnsafe.user && webApp.initDataUnsafe.user.phone_number) {
          webApp.MainButton.hide()
          webApp.offEvent('mainButtonClicked', handlePhoneRequest)
          resolve(webApp.initDataUnsafe.user.phone_number)
        } else {
          // Request phone number access
          webApp.openTelegramLink('https://t.me/share/phone')
          // Note: After user shares phone, initData will be updated
          // We'll need to check periodically or use a different approach
          reject(new Error('Phone number not available. Please share your phone number through the bot.'))
        }
      }
      
      webApp.onEvent('mainButtonClicked', handlePhoneRequest)
      
      // Check if phone number is already available
      if (webApp.initDataUnsafe && webApp.initDataUnsafe.user && webApp.initDataUnsafe.user.phone_number) {
        webApp.MainButton.hide()
        resolve(webApp.initDataUnsafe.user.phone_number)
      }
    } else {
      reject(new Error('Telegram Web App not available'))
    }
  })
}

