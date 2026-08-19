import { useState, useCallback, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import Sidebar from './components/layout/Sidebar'
import TopNavbar from './components/layout/TopNavbar'
import HighRiskBanner from './components/dashboard/HighRiskBanner'
import KpiRow from './components/dashboard/KpiRow'
import ChartGrid from './components/dashboard/ChartGrid'
import AlertFeed from './components/alerts/AlertFeed'
import WorldMap from './components/dashboard/WorldMap'
import LoginTable from './components/tables/LoginTable'
import InvestigationDrawer from './components/investigation/InvestigationDrawer'
import useDashboardData from './hooks/useDashboardData'
import AlertsPage from './pages/AlertsPage'
import UsersPage from './pages/UsersPage'
import DatasetPage from './pages/DatasetPage'

export default function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [activePage, setActivePage] = useState('dashboard')
  const [investigationOpen, setInvestigationOpen] = useState(false)
  const [selectedAlert, setSelectedAlert] = useState(null)
  const { data, loading, error } = useDashboardData()

  const handleAlertClick = useCallback((alert) => {
    setSelectedAlert(alert)
    setInvestigationOpen(true)
  }, [])

  const handleInvestigate = useCallback((alert) => {
    setSelectedAlert(alert)
    setInvestigationOpen(true)
  }, [])

  const dashboard = data || {
    kpis: { totalEvents: 0, anomalies: 0, highRiskUsers: 0, usersMonitored: 0,
            totalEventsChange: 0, anomaliesChange: 0, highRiskChange: 0 },
    anomalyTrend: [], riskDistribution: [], userActivity: [],
    topReasons: [], recentLogins: [], alerts: [], scatterData: [],
  }

  const alerts = dashboard.alerts || []
  const topAlert = useMemo(() => {
    const active = [...alerts].filter(a => a.status !== 'dismissed')
    const order = { critical: 0, high: 1, medium: 2, low: 3 }
    return active.sort((a, b) => (order[a.severity] ?? 9) - (order[b.severity] ?? 9))[0] || null
  }, [alerts])

  const newAlerts = alerts.filter(a => a.status === 'new').length
  const spark = useMemo(() => (dashboard.anomalyTrend || []).map(p => ({ value: p.anomalies })), [dashboard.anomalyTrend])

  const pages = {
    dashboard: (
      <motion.main key="dashboard" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.3 }} className="p-5 pt-3">
        <div className="max-w-[1440px] mx-auto">
          <HighRiskBanner alert={topAlert} onInvestigate={handleInvestigate} />
          <KpiRow
            totalEvents={dashboard.kpis.totalEvents}
            anomalies={dashboard.kpis.anomalies}
            highRiskUsers={dashboard.kpis.highRiskUsers}
            usersMonitored={dashboard.kpis.usersMonitored}
            eventsChange={dashboard.kpis.totalEventsChange}
            anomalyChange={dashboard.kpis.anomaliesChange}
            spark={spark}
          />
          <div className="mb-5"><WorldMap /></div>
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-5 mb-5">
            <div className="xl:col-span-2">
              <ChartGrid
                anomalyTrend={dashboard.anomalyTrend}
                riskDistribution={dashboard.riskDistribution}
                userActivity={dashboard.userActivity}
                topReasons={dashboard.topReasons}
                alerts={alerts}
                onInvestigate={handleInvestigate}
              />
            </div>
            <div className="space-y-5">
              <AlertFeed alerts={alerts} onAlertClick={handleAlertClick} />
            </div>
          </div>
          <LoginTable logins={dashboard.recentLogins} onRowClick={handleAlertClick} />
        </div>
      </motion.main>
    ),
    alerts: <AlertsPage key="alerts" />,
    users: <UsersPage key="users" />,
    dataset: <DatasetPage key="dataset" />,
  }

  return (
    <div className="min-h-screen bg-paper">
      <div className="relative z-10 min-h-screen bg-grid">
        <Sidebar
          collapsed={sidebarCollapsed}
          setCollapsed={setSidebarCollapsed}
          activePage={activePage}
          setActivePage={setActivePage}
          newAlerts={newAlerts}
        />

        <div
          className="transition-all duration-300 min-h-screen"
          style={{ marginLeft: sidebarCollapsed ? 72 : 256 }}
        >
          <TopNavbar onNavigate={setActivePage} />

          {error && (
            <div className="mx-5 mt-3 px-4 py-2 rounded-sm bg-critical/10 text-critical text-sm border border-red-500/20">
              Backend offline: {error}
            </div>
          )}

          <AnimatePresence mode="wait">
            {pages[activePage]}
          </AnimatePresence>
        </div>

        <InvestigationDrawer
          isOpen={investigationOpen}
          onClose={() => setInvestigationOpen(false)}
          alert={selectedAlert}
        />
      </div>
    </div>
  )
}
