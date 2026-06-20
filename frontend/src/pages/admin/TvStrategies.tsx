import { ArrowLeft, Pencil, Plus, Trash2, Tv } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { webClient } from '@/api/client'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { showToast } from '@/utils/toast'

interface TvStrategy {
  name: string
  enabled: boolean
  active_days: string[]
  lot_size: number
  strike_selection: string
  product: string
  exchange: string
}

interface ApiResponse<T = void> {
  status: string
  message?: string
  data?: T
}

export default function TvStrategies() {
  const [strategies, setStrategies] = useState<TvStrategy[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [deleteStrategy, setDeleteStrategy] = useState<TvStrategy | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const navigate = useNavigate()

  const fetchStrategies = async () => {
    try {
      const response = await webClient.get<ApiResponse<TvStrategy[]>>(
        '/admin/api/tv-strategies'
      )
      setStrategies(response.data.data || [])
    } catch {
      showToast.error('Failed to load strategies', 'admin')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchStrategies()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleDelete = async () => {
    if (!deleteStrategy) return

    setIsDeleting(true)
    try {
      const response = await webClient.delete<ApiResponse>(
        `/admin/api/tv-strategies/${encodeURIComponent(deleteStrategy.name)}`
      )

      if (response.data.status === 'success') {
        showToast.success(response.data.message || 'Strategy deleted', 'admin')
        setDeleteStrategy(null)
        fetchStrategies()
      } else {
        showToast.error(response.data.message || 'Failed to delete strategy', 'admin')
      }
    } catch (error: unknown) {
      const err = error as { response?: { data?: { message?: string } } }
      showToast.error(err.response?.data?.message || 'Failed to delete strategy', 'admin')
    } finally {
      setIsDeleting(false)
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    )
  }

  return (
    <div className="py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Link to="/admin" className="text-muted-foreground hover:text-foreground">
              <ArrowLeft className="h-4 w-4" />
            </Link>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Tv className="h-6 w-6" />
              TradingView Strategies
            </h1>
          </div>
          <p className="text-muted-foreground">
            Manage per-strategy configurations for TradingView alert-based trading
          </p>
        </div>
        <Button onClick={() => navigate('/admin/tv-strategies/new')}>
          <Plus className="h-4 w-4 mr-2" />
          New Strategy
        </Button>
      </div>

      {/* Table */}
      <Card>
        <CardHeader>
          <CardTitle>Strategies</CardTitle>
          <CardDescription>
            {strategies.length} {strategies.length === 1 ? 'strategy' : 'strategies'} configured
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="border rounded-md">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Enabled</TableHead>
                  <TableHead>Active Days</TableHead>
                  <TableHead>Lot Size</TableHead>
                  <TableHead>Product</TableHead>
                  <TableHead>Exchange</TableHead>
                  <TableHead className="w-[80px]">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {strategies.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center text-muted-foreground py-8">
                      No strategies configured. Click "New Strategy" to create one.
                    </TableCell>
                  </TableRow>
                ) : (
                  strategies.map((strategy) => (
                    <TableRow key={strategy.name}>
                      <TableCell className="font-medium">
                        <Link
                          to={`/admin/tv-strategies/${encodeURIComponent(strategy.name)}`}
                          className="text-primary hover:underline"
                        >
                          {strategy.name}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={strategy.enabled ? 'default' : 'secondary'}
                          className={
                            strategy.enabled
                              ? 'bg-green-600 text-white hover:bg-green-700'
                              : ''
                          }
                        >
                          {strategy.enabled ? 'Enabled' : 'Disabled'}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <span className="text-sm text-muted-foreground">
                          {strategy.active_days.join(', ')}
                        </span>
                      </TableCell>
                      <TableCell>{strategy.lot_size}</TableCell>
                      <TableCell>{strategy.product}</TableCell>
                      <TableCell>{strategy.exchange}</TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-8 w-8"
                            onClick={(e) => {
                              e.stopPropagation()
                              navigate(`/admin/tv-strategies/${encodeURIComponent(strategy.name)}`)
                            }}
                            title="Edit strategy"
                            aria-label={`Edit strategy ${strategy.name}`}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-8 w-8 text-destructive hover:text-destructive"
                            onClick={(e) => {
                              e.stopPropagation()
                              setDeleteStrategy(strategy)
                            }}
                            title="Delete strategy"
                            aria-label={`Delete strategy ${strategy.name}`}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={!!deleteStrategy} onOpenChange={() => setDeleteStrategy(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Strategy?</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete the strategy "{deleteStrategy?.name}"? This action
              cannot be undone. Any TradingView alerts referencing this strategy will stop working.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} disabled={isDeleting}>
              {isDeleting ? 'Deleting...' : 'Delete'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
