import { createRootRoute, createRoute, createRouter, Link, Outlet } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { CompScratchpad } from './features/scratchpad/CompScratchpad'

function Shell() {
  return (
    <div className="flex h-full flex-col">
      <header className="flex h-10 items-center gap-4 border-b border-line bg-panel px-3">
        <span className="font-semibold">AT Tool</span>
        <nav className="flex gap-3 text-muted">
          <Link to="/" className="hover:text-fg [&.active]:text-fg">
            Home
          </Link>
          <Link to="/scratchpad" className="hover:text-fg [&.active]:text-fg">
            Comp scratchpad
          </Link>
        </nav>
      </header>
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
      return (await resp.json()) as { status: string; version: string; database: string; sde_build: number | null }
    },
  })
  return (
    <div className="text-muted">
      <p>Scaffold is running.</p>
      <p className="mono mt-2">
        backend: {health.isLoading ? '…' : health.data ? `${health.data.status} (${health.data.version}), SDE build ${health.data.sde_build ?? 'none'}` : 'unreachable'}
      </p>
    </div>
  )
}

const rootRoute = createRootRoute({ component: Shell })
const homeRoute = createRoute({ getParentRoute: () => rootRoute, path: '/', component: Home })
const scratchpadRoute = createRoute({ getParentRoute: () => rootRoute, path: '/scratchpad', component: CompScratchpad })

export const router = createRouter({ routeTree: rootRoute.addChildren([homeRoute, scratchpadRoute]) })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
