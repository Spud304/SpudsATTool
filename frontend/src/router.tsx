import { createRootRoute, createRoute, createRouter, Outlet } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'

function Shell() {
  return (
    <div className="flex h-full flex-col">
      <header className="flex h-10 items-center border-b border-line bg-panel px-3 font-semibold">AT Tool</header>
      <main className="min-h-0 flex-1 overflow-auto p-4">
        <Outlet />
      </main>
    </div>
  )
}

function Home() {
  const health = useQuery({
    queryKey: ['health'],
    queryFn: async () => {
      const resp = await fetch('/api/health')
      if (!resp.ok) throw new Error(`health ${resp.status}`)
      return (await resp.json()) as { status: string; version: string; database: string }
    },
  })
  return (
    <div className="text-muted">
      <p>Scaffold is running.</p>
      <p className="mono mt-2">
        backend: {health.isLoading ? '…' : health.data ? `${health.data.status} (${health.data.version})` : 'unreachable'}
      </p>
    </div>
  )
}

const rootRoute = createRootRoute({ component: Shell })
const homeRoute = createRoute({ getParentRoute: () => rootRoute, path: '/', component: Home })

export const router = createRouter({ routeTree: rootRoute.addChildren([homeRoute]) })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
