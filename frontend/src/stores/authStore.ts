import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface User {
  username: string
  broker: string | null
  isLoggedIn: boolean
  loginTime: string | null
}

interface AuthStore {
  user: User | null
  apiKey: string | null
  isAuthenticated: boolean
  isBrokerConnected: boolean
  availableBrokers: string[]

  setUser: (user: User) => void
  setApiKey: (apiKey: string | null) => void
  setAvailableBrokers: (brokers: string[]) => void
  login: (username: string, broker: string | null) => void
  logout: () => void
  connectBroker: (broker: string) => Promise<{ success: boolean; redirectUrl?: string; message?: string }>
  disconnectBroker: () => Promise<{ success: boolean; message?: string }>
  checkSession: () => boolean
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set, get) => ({
      user: null,
      apiKey: null,
      isAuthenticated: false,
      isBrokerConnected: false,
      availableBrokers: [],

      setUser: (user) => set({
        user,
        isAuthenticated: !!user.username,
        isBrokerConnected: user.isLoggedIn,
      }),

      setApiKey: (apiKey) => set({ apiKey }),

      setAvailableBrokers: (brokers) => set({ availableBrokers: brokers }),

      login: (username, broker) => {
        const user: User = {
          username,
          broker,
          isLoggedIn: !!broker,
          loginTime: new Date().toISOString(),
        }
        set({
          user,
          isAuthenticated: true,
          isBrokerConnected: !!broker,
        })
      },

      logout: () => {
        set({
          user: null,
          isAuthenticated: false,
          isBrokerConnected: false,
          apiKey: null,
          availableBrokers: [],
        })
      },

      connectBroker: async (broker: string) => {
        try {
          const response = await fetch('/broker-session/connect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ broker }),
          })
          const data = await response.json()
          if (data.status === 'success') {
            return {
              success: true,
              redirectUrl: data.data?.redirect_url,
              message: data.message,
            }
          }
          return { success: false, message: data.message }
        } catch (error) {
          return { success: false, message: 'Failed to connect to broker' }
        }
      },

      disconnectBroker: async () => {
        try {
          const response = await fetch('/broker-session/disconnect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
          })
          const data = await response.json()
          if (data.status === 'success') {
            const { user } = get()
            if (user) {
              set({
                user: { ...user, broker: null, isLoggedIn: false },
                isBrokerConnected: false,
              })
            }
            return { success: true, message: data.message }
          }
          return { success: false, message: data.message }
        } catch (error) {
          return { success: false, message: 'Failed to disconnect broker' }
        }
      },

      checkSession: () => {
        const { user } = get()
        if (!user || !user.loginTime) return false

        // Skip session expiry for crypto brokers (24/7 markets)
        const cryptoBrokers = ['deltaexchange']
        if (user.broker && cryptoBrokers.includes(user.broker)) {
          return true
        }

        // Session expiry check (3 AM IST daily)
        const now = new Date()
        const loginTime = new Date(user.loginTime)

        // Convert to IST properly: UTC + 5.5 hours
        // First get UTC time, then add IST offset
        const istOffsetMs = 5.5 * 60 * 60 * 1000
        const localOffsetMs = now.getTimezoneOffset() * 60 * 1000

        // Convert current time to IST
        const nowUTC = now.getTime() + localOffsetMs
        const nowIST = new Date(nowUTC + istOffsetMs)

        // Convert login time to IST
        const loginUTC = loginTime.getTime() + localOffsetMs
        const loginIST = new Date(loginUTC + istOffsetMs)

        // Create today's 3 AM IST expiry time
        const todayExpiry = new Date(nowIST)
        todayExpiry.setHours(3, 0, 0, 0)

        // If current time is after 3 AM IST today and login was before 3 AM IST today
        if (nowIST > todayExpiry && loginIST < todayExpiry) {
          get().logout()
          return false
        }

        return true
      },
    }),
    {
      name: 'openalgo-auth',
    }
  )
)
