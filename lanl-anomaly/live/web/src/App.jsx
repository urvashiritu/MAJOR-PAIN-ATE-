import { useState } from "react";
import { AnimatePresence } from "framer-motion";
import Sidebar from "./components/layout/Sidebar";
import TopNavbar from "./components/layout/TopNavbar";
import DashboardPage from "./pages/DashboardPage";
import AlertsPage from "./pages/AlertsPage";
import UsersPage from "./pages/UsersPage";
import SettingsPage from "./pages/SettingsPage";
import InvestigationDrawer from "./components/investigation/InvestigationDrawer";

export default function App() {
  const [activePage, setActivePage] = useState("dashboard");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);
  const [investigateId, setInvestigateId] = useState(null);

  const pages = {
    dashboard: <DashboardPage onInvestigate={setInvestigateId} />,
    alerts: <AlertsPage onInvestigate={setInvestigateId} />,
    users: <UsersPage />,
    settings: <SettingsPage />,
  };

  return (
    <div className="min-h-screen bg-paper">
      <div className="relative z-10 bg-grid">
        <Sidebar
          activePage={activePage}
          setActivePage={setActivePage}
          collapsed={sidebarCollapsed}
          setCollapsed={setSidebarCollapsed}
        />
        <div
          className="transition-all duration-300"
          style={{ marginLeft: sidebarCollapsed ? 72 : 256 }}
        >
          <TopNavbar
            activePage={activePage}
            onNavigate={setActivePage}
            onInvestigate={setInvestigateId}
          />
          <main className="p-5 pt-3 max-w-[1440px] mx-auto">
            <AnimatePresence mode="wait">
              {pages[activePage]}
            </AnimatePresence>
          </main>
        </div>
        {investigateId && (
          <InvestigationDrawer
            eventId={investigateId}
            onClose={() => setInvestigateId(null)}
          />
        )}
      </div>
    </div>
  );
}
