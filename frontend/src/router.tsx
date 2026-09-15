import { createRootRoute, createRoute, createRouter, Outlet } from '@tanstack/react-router'
import { AppShell } from './components/AppShell'
import { DashboardPage } from './features/dashboard/DashboardPage'
import { CompBuilderPage } from './features/comps/CompBuilderPage'
import { CompsPage } from './features/comps/CompsPage'
import { FitDetailPage } from './features/fits/FitDetailPage'
import { FitsPage } from './features/fits/FitsPage'
import { CompScratchpad } from './features/scratchpad/CompScratchpad'
import { ScrimPage } from './features/scrims/ScrimPage'
import { ScrimsPage } from './features/scrims/ScrimsPage'
import { PilotsPage } from './features/team/PilotsPage'
import { AuditPage } from './features/team/AuditPage'
import { TeamPage } from './features/team/TeamPage'

const rootRoute = createRootRoute({
  component: () => (
    <AppShell>
      <Outlet />
    </AppShell>
  ),
})

const routes = [
  createRoute({ getParentRoute: () => rootRoute, path: '/', component: DashboardPage }),
  createRoute({ getParentRoute: () => rootRoute, path: '/scratchpad', component: CompScratchpad }),
  createRoute({ getParentRoute: () => rootRoute, path: '/comps', component: CompsPage }),
  createRoute({ getParentRoute: () => rootRoute, path: '/comps/$compId', component: CompBuilderPage }),
  createRoute({ getParentRoute: () => rootRoute, path: '/fits', component: FitsPage }),
  createRoute({ getParentRoute: () => rootRoute, path: '/fits/$fitId', component: FitDetailPage }),
  createRoute({ getParentRoute: () => rootRoute, path: '/scrims', component: ScrimsPage }),
  createRoute({ getParentRoute: () => rootRoute, path: '/scrims/$scrimId', component: ScrimPage }),
  createRoute({ getParentRoute: () => rootRoute, path: '/team', component: TeamPage }),
  createRoute({ getParentRoute: () => rootRoute, path: '/team/pilots', component: PilotsPage }),
  createRoute({ getParentRoute: () => rootRoute, path: '/team/audit', component: AuditPage }),
]

export const router = createRouter({ routeTree: rootRoute.addChildren(routes) })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
