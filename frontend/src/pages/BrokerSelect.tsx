import { BookOpen, ExternalLink, Eye, EyeOff, Info, Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useAuthStore } from '@/stores/authStore'

// All supported brokers with their display names and auth types
const allBrokers = [
  { id: 'fivepaisa', name: '5 Paisa', authType: 'totp' },
  { id: 'fivepaisaxts', name: '5 Paisa (XTS)', authType: 'totp' },
  { id: 'aliceblue', name: 'Alice Blue', authType: 'totp' },
  { id: 'angel', name: 'Angel One', authType: 'totp' },
  { id: 'compositedge', name: 'CompositEdge', authType: 'oauth' },
  { id: 'dhan', name: 'Dhan', authType: 'oauth' },
  { id: 'deltaexchange', name: 'Delta Exchange', authType: 'totp' },
  { id: 'indmoney', name: 'IndMoney', authType: 'totp' },
  { id: 'dhan_sandbox', name: 'Dhan (Sandbox)', authType: 'totp' },
  { id: 'definedge', name: 'Definedge', authType: 'totp' },
  { id: 'firstock', name: 'Firstock', authType: 'totp' },
  { id: 'flattrade', name: 'Flattrade', authType: 'oauth' },
  { id: 'motilal', name: 'Motilal Oswal', authType: 'totp' },
  { id: 'fyers', name: 'Fyers', authType: 'oauth' },
  { id: 'groww', name: 'Groww', authType: 'totp' },
  { id: 'ibulls', name: 'Ibulls', authType: 'totp' },
  { id: 'iifl', name: 'IIFL', authType: 'totp' },
  { id: 'jainamxts', name: 'JainamXts', authType: 'totp' },
  { id: 'kotak', name: 'Kotak Securities', authType: 'totp' },
  { id: 'mstock', name: 'mStock by Mirae Asset', authType: 'totp' },
  { id: 'nubra', name: 'Nubra', authType: 'totp' },
  { id: 'paytm', name: 'Paytm Money', authType: 'oauth' },
  { id: 'pocketful', name: 'Pocketful', authType: 'oauth' },
  { id: 'rmoney', name: 'RMoney', authType: 'oauth' },
  { id: 'samco', name: 'Samco', authType: 'totp' },
  { id: 'shoonya', name: 'Shoonya', authType: 'totp' },
  { id: 'tradejini', name: 'Tradejini', authType: 'totp' },
  { id: 'upstox', name: 'Upstox', authType: 'oauth' },
  { id: 'wisdom', name: 'Wisdom Capital', authType: 'totp' },
  { id: 'zebu', name: 'Zebu', authType: 'totp' },
  { id: 'zerodha', name: 'Zerodha', authType: 'oauth' },
] as const

interface CredentialFormData {
  api_key: string
  api_secret: string
  client_id: string
  redirect_url: string
}

interface ValidationErrors {
  api_key?: string
  api_secret?: string
}

// Helper function to get Flattrade API key
function getFlattradeApiKey(fullKey: string): string {
  if (!fullKey) return ''
  const parts = fullKey.split(':::')
  return parts.length > 1 ? parts[1] : fullKey
}

// Generate random state for OAuth
function generateRandomState(): string {
  const length = 16
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
  let result = ''
  for (let i = 0; i < length; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length))
  }
  return result
}

// Get broker login URL based on broker type
function getBrokerLoginUrl(broker: string, apiKey: string, redirectUrl: string): string {
  switch (broker) {
    case 'fivepaisa':
    case 'fivepaisaxts':
    case 'aliceblue':
    case 'angel':
    case 'mstock':
    case 'indmoney':
    case 'deltaexchange':
    case 'jainamxts':
    case 'dhan_sandbox':
    case 'definedge':
    case 'firstock':
    case 'samco':
    case 'motilal':
    case 'nubra':
    case 'groww':
    case 'ibulls':
    case 'iifl':
    case 'kotak':
    case 'rmoney':
    case 'shoonya':
    case 'tradejini':
    case 'wisdom':
    case 'zebu':
      return `/${broker}/callback`

    case 'dhan':
      return '/dhan/initiate-oauth'

    case 'compositedge':
      return `https://xts.compositedge.com/interactive/thirdparty?appKey=${apiKey}&returnURL=${redirectUrl}`

    case 'flattrade': {
      const flattradeApiKey = getFlattradeApiKey(apiKey)
      return `https://auth.flattrade.in/?app_key=${flattradeApiKey}`
    }

    case 'fyers':
      return `https://api-t1.fyers.in/api/v3/generate-authcode?client_id=${apiKey}&redirect_uri=${redirectUrl}&response_type=code&state=2e9b44629ebb28226224d09db3ffb47c`

    case 'upstox':
      return `https://api.upstox.com/v2/login/authorization/dialog?response_type=code&client_id=${apiKey}&redirect_uri=${redirectUrl}`

    case 'zerodha':
      return `https://kite.trade/connect/login?api_key=${apiKey}`

    case 'paytm':
      return `https://login.paytmmoney.com/merchant-login?apiKey=${apiKey}&state={default}`

    case 'pocketful': {
      const state = generateRandomState()
      localStorage.setItem('pocketful_oauth_state', state)
      const scope = 'orders holdings'
      return `https://trade.pocketful.in/oauth2/auth?client_id=${apiKey}&redirect_uri=${redirectUrl}&response_type=code&scope=${encodeURIComponent(scope)}&state=${encodeURIComponent(state)}`
    }

    default:
      return ''
  }
}

export default function BrokerSelect() {
  const { user, connectBroker } = useAuthStore()
  const [selectedBroker, setSelectedBroker] = useState<string>('')
  const [isFetchingCredentials, setIsFetchingCredentials] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [validationErrors, setValidationErrors] = useState<ValidationErrors>({})
  const [showSecret, setShowSecret] = useState(false)
  const [credentials, setCredentials] = useState<CredentialFormData>({
    api_key: '',
    api_secret: '',
    client_id: '',
    redirect_url: '',
  })

  // Fetch saved credentials when broker is selected
  useEffect(() => {
    if (!selectedBroker) {
      setCredentials({ api_key: '', api_secret: '', client_id: '', redirect_url: '' })
      setValidationErrors({})
      setError(null)
      return
    }

    const fetchCredentials = async () => {
      setIsFetchingCredentials(true)
      setError(null)
      setValidationErrors({})
      try {
        const response = await fetch(`/api/broker-credentials/${selectedBroker}`, {
          credentials: 'include',
        })
        const data = await response.json()

        if (data.status === 'success' && data.data) {
          setCredentials({
            api_key: data.data.api_key || '',
            api_secret: data.data.api_secret || '',
            client_id: data.data.client_id || '',
            redirect_url: data.data.redirect_url || '',
          })
        } else {
          setCredentials({ api_key: '', api_secret: '', client_id: '', redirect_url: '' })
        }
      } catch {
        setCredentials({ api_key: '', api_secret: '', client_id: '', redirect_url: '' })
      } finally {
        setIsFetchingCredentials(false)
      }
    }

    fetchCredentials()
  }, [selectedBroker])

  const validateForm = (): boolean => {
    const errors: ValidationErrors = {}

    if (!credentials.api_key.trim()) {
      errors.api_key = 'API Key is required'
    }
    if (!credentials.api_secret.trim()) {
      errors.api_secret = 'API Secret is required'
    }

    setValidationErrors(errors)
    return Object.keys(errors).length === 0
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!selectedBroker) {
      setError('Please select a broker')
      return
    }

    if (!validateForm()) {
      return
    }

    setIsSubmitting(true)
    setError(null)

    try {
      // Step 1: Save credentials via POST
      const saveResponse = await fetch(`/api/broker-credentials/${selectedBroker}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          api_key: credentials.api_key,
          api_secret: credentials.api_secret,
          client_id: credentials.client_id,
          redirect_url: credentials.redirect_url,
        }),
      })
      const saveData = await saveResponse.json()

      if (saveData.status !== 'success') {
        setError(saveData.message || 'Failed to save credentials')
        setIsSubmitting(false)
        return
      }

      // Step 2: Trigger broker connect via /broker-session/connect
      const connectResult = await connectBroker(selectedBroker)

      if (connectResult.success && connectResult.redirectUrl) {
        // Redirect to broker auth flow URL returned by connect
        setTimeout(() => {
          window.location.href = connectResult.redirectUrl!
        }, 100)
      } else if (connectResult.success) {
        // Fallback: use broker login URL generation logic
        const loginUrl = getBrokerLoginUrl(
          selectedBroker,
          credentials.api_key,
          credentials.redirect_url
        )
        if (loginUrl) {
          setTimeout(() => {
            window.location.href = loginUrl
          }, 100)
        } else {
          setError('Unable to determine broker login URL')
          setIsSubmitting(false)
        }
      } else {
        setError(connectResult.message || 'Failed to connect to broker')
        setIsSubmitting(false)
      }
    } catch {
      setError('An unexpected error occurred')
      setIsSubmitting(false)
    }
  }

  const handleBrokerChange = (value: string) => {
    setSelectedBroker(value)
    setShowSecret(false)
  }

  return (
    <div className="min-h-screen flex items-center justify-center py-8 px-4">
      <div className="container max-w-6xl">
        <div className="flex flex-col lg:flex-row items-center justify-between gap-8 lg:gap-16">
          {/* Right side broker form - Shown first on mobile */}
          <Card className="w-full max-w-md shadow-xl order-1 lg:order-2">
            <CardHeader className="text-center">
              <div className="flex justify-center mb-4">
                <img src="/logo.png" alt="OpenAlgo" className="h-20 w-20" />
              </div>
              <CardTitle className="text-2xl">Connect Your Trading Account</CardTitle>
              <CardDescription>
                Welcome, <span className="font-medium">{user?.username}</span>!
              </CardDescription>
            </CardHeader>
            <CardContent>
              {error && (
                <Alert variant="destructive" className="mb-4">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}

              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="broker-select" className="block text-center">
                    Select Your Broker
                  </Label>
                  <Select
                    value={selectedBroker}
                    onValueChange={handleBrokerChange}
                    disabled={isSubmitting}
                  >
                    <SelectTrigger id="broker-select" className="w-full">
                      <SelectValue placeholder="Select a Broker" />
                    </SelectTrigger>
                    <SelectContent>
                      {allBrokers.map((broker) => (
                        <SelectItem key={broker.id} value={broker.id}>
                          {broker.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {selectedBroker && (
                  <>
                    {isFetchingCredentials ? (
                      <div className="flex items-center justify-center py-4">
                        <Loader2 className="h-5 w-5 animate-spin mr-2" />
                        <span className="text-sm text-muted-foreground">
                          Loading credentials...
                        </span>
                      </div>
                    ) : (
                      <div className="space-y-3">
                        <div className="space-y-1">
                          <Label htmlFor="api-key">
                            API Key <span className="text-destructive">*</span>
                          </Label>
                          <Input
                            id="api-key"
                            type="text"
                            placeholder="Enter API Key"
                            value={credentials.api_key}
                            onChange={(e) => {
                              setCredentials({ ...credentials, api_key: e.target.value })
                              if (validationErrors.api_key) {
                                setValidationErrors({ ...validationErrors, api_key: undefined })
                              }
                            }}
                            disabled={isSubmitting}
                          />
                          {validationErrors.api_key && (
                            <p className="text-xs text-destructive">
                              {validationErrors.api_key}
                            </p>
                          )}
                        </div>

                        <div className="space-y-1">
                          <Label htmlFor="api-secret">
                            API Secret <span className="text-destructive">*</span>
                          </Label>
                          <div className="relative">
                            <Input
                              id="api-secret"
                              type={showSecret ? 'text' : 'password'}
                              placeholder="Enter API Secret"
                              value={credentials.api_secret}
                              onChange={(e) => {
                                setCredentials({ ...credentials, api_secret: e.target.value })
                                if (validationErrors.api_secret) {
                                  setValidationErrors({
                                    ...validationErrors,
                                    api_secret: undefined,
                                  })
                                }
                              }}
                              disabled={isSubmitting}
                            />
                            <button
                              type="button"
                              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                              onClick={() => setShowSecret(!showSecret)}
                              tabIndex={-1}
                            >
                              {showSecret ? (
                                <EyeOff className="h-4 w-4" />
                              ) : (
                                <Eye className="h-4 w-4" />
                              )}
                            </button>
                          </div>
                          {validationErrors.api_secret && (
                            <p className="text-xs text-destructive">
                              {validationErrors.api_secret}
                            </p>
                          )}
                        </div>

                        <div className="space-y-1">
                          <Label htmlFor="client-id">Client ID</Label>
                          <Input
                            id="client-id"
                            type="text"
                            placeholder="Enter Client ID (optional)"
                            value={credentials.client_id}
                            onChange={(e) =>
                              setCredentials({ ...credentials, client_id: e.target.value })
                            }
                            disabled={isSubmitting}
                          />
                        </div>

                        <div className="space-y-1">
                          <Label htmlFor="redirect-url">Redirect URL</Label>
                          <Input
                            id="redirect-url"
                            type="text"
                            placeholder="Enter Redirect URL (optional)"
                            value={credentials.redirect_url}
                            onChange={(e) =>
                              setCredentials({ ...credentials, redirect_url: e.target.value })
                            }
                            disabled={isSubmitting}
                          />
                        </div>
                      </div>
                    )}

                    {(selectedBroker === 'zerodha' || selectedBroker === 'dhan') && (
                      <Alert className="border-amber-500/50 bg-amber-500/10">
                        <Info className="h-4 w-4 text-amber-500" />
                        <AlertDescription className="text-amber-200">
                          {selectedBroker === 'zerodha'
                            ? 'Zerodha requires an active Kite Connect data subscription for market data access.'
                            : 'Dhan requires an active Data API subscription for market data access.'}
                        </AlertDescription>
                      </Alert>
                    )}

                    <Button
                      type="submit"
                      className="w-full"
                      disabled={!selectedBroker || isSubmitting || isFetchingCredentials}
                    >
                      {isSubmitting ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          Connecting...
                        </>
                      ) : (
                        <>
                          <ExternalLink className="mr-2 h-4 w-4" />
                          Save &amp; Connect
                        </>
                      )}
                    </Button>
                  </>
                )}
              </form>
            </CardContent>
          </Card>

          {/* Left side content - Shown second on mobile */}
          <div className="flex-1 max-w-xl text-center lg:text-left order-2 lg:order-1">
            <h1 className="text-4xl lg:text-5xl font-bold mb-6">
              Connect Your <span className="text-primary">Broker</span>
            </h1>
            <p className="text-lg lg:text-xl mb-8 text-muted-foreground">
              Link your trading account to start executing trades through OpenAlgo's algorithmic
              trading platform.
            </p>

            <Alert className="mb-6">
              <BookOpen className="h-4 w-4" />
              <AlertTitle>Need Help?</AlertTitle>
              <AlertDescription>
                Check our documentation for broker setup guides.
              </AlertDescription>
            </Alert>

            <div className="flex justify-center lg:justify-start gap-4">
              <Button variant="outline" asChild>
                <a href="https://docs.openalgo.in" target="_blank" rel="noopener noreferrer">
                  <BookOpen className="mr-2 h-4 w-4" />
                  Documentation
                </a>
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
