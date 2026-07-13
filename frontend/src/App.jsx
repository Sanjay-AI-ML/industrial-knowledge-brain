import { useEffect, useState } from "react";
import {
  LayoutDashboard,
  MessageSquare,
  Workflow,
  Wrench,
  ClipboardCheck,
} from "lucide-react";
import Dashboard from "./pages/Dashboard.jsx";
import CopilotChat from "./pages/CopilotChat.jsx";
import PIDViewer from "./pages/PIDViewer.jsx";
import MaintenanceRCA from "./pages/MaintenanceRCA.jsx";
import ComplianceTracker from "./pages/ComplianceTracker.jsx";
import useTheme from "./hooks/useTheme.js";
import useHealth from "./hooks/useHealth.js";
import Sidebar from "./components/layout/Sidebar.jsx";
import MobileNav from "./components/layout/MobileNav.jsx";
import TopBar from "./components/layout/TopBar.jsx";
import ShortcutsPanel from "./components/layout/ShortcutsPanel.jsx";
import PageTransition from "./components/ui/PageTransition.jsx";

const PAGES = {
  home: { label: "Dashboard", shortLabel: "Home", icon: LayoutDashboard, component: Dashboard },
  copilot: { label: "Knowledge Copilot", shortLabel: "Copilot", icon: MessageSquare, component: CopilotChat },
  pid: { label: "P&ID Viewer", shortLabel: "P&ID", icon: Workflow, component: PIDViewer },
  maintenance: { label: "Maintenance & RCA", shortLabel: "RCA", icon: Wrench, component: MaintenanceRCA },
  compliance: { label: "Compliance Tracker", shortLabel: "Compliance", icon: ClipboardCheck, component: ComplianceTracker },
};

const PAGE_KEYS = Object.keys(PAGES);
const SIDEBAR_KEY = "ikb-sidebar-collapsed";

export default function App() {
  const [currentPage, setCurrentPage] = useState("home");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => window.localStorage.getItem(SIDEBAR_KEY) === "true"
  );
  const [showShortcuts, setShowShortcuts] = useState(false);
  const { isDark, toggleTheme } = useTheme();
  const health = useHealth();

  useEffect(() => {
    window.localStorage.setItem(SIDEBAR_KEY, String(sidebarCollapsed));
  }, [sidebarCollapsed]);

  // Keyboard shortcuts: 1-5 switch tabs, "d" toggles dark mode, "?" shows shortcuts.
  useEffect(() => {
    function onKeyDown(e) {
      const tag = e.target.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || e.metaKey || e.ctrlKey) return;

      if (e.key >= "1" && e.key <= String(PAGE_KEYS.length)) {
        setCurrentPage(PAGE_KEYS[Number(e.key) - 1]);
      } else if (e.key.toLowerCase() === "d") {
        toggleTheme();
      } else if (e.key === "?") {
        setShowShortcuts((v) => !v);
      } else if (e.key === "Escape") {
        setShowShortcuts(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [toggleTheme]);

  const PageComponent = PAGES[currentPage].component;

  return (
    <div className="min-h-screen flex bg-slate-100 transition-colors">
      <Sidebar
        pages={PAGES}
        currentPage={currentPage}
        onNavigate={setCurrentPage}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed((c) => !c)}
      />

      <div className="flex-1 flex flex-col min-w-0 min-h-screen pb-16 md:pb-0">
        <TopBar
          isDark={isDark}
          toggleTheme={toggleTheme}
          health={health}
          showShortcuts={showShortcuts}
          onToggleShortcuts={() => setShowShortcuts((v) => !v)}
        />

        <PageTransition pageKey={currentPage}>
          <PageComponent onNavigate={setCurrentPage} />
        </PageTransition>
      </div>

      <MobileNav pages={PAGES} currentPage={currentPage} onNavigate={setCurrentPage} />

      {showShortcuts && (
        <ShortcutsPanel pages={PAGES} onClose={() => setShowShortcuts(false)} />
      )}
    </div>
  );
}
