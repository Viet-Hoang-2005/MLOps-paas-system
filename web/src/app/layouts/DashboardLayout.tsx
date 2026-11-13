import { useState } from "react";
import { Outlet } from "react-router-dom";
import Header from "./Header";
import Sidebar from "./Sidebar";
import { ModelSelectionProvider } from "@/features/projects/components/ModelSelectionProvider";

export default function DashboardLayout() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  return (
    <ModelSelectionProvider>
      <div className="flex h-screen flex-col bg-background text-color-foreground">
        <Header onOpenNavigation={() => setMobileSidebarOpen(true)} />
        <div className="flex min-h-0 flex-1">
          <Sidebar
            collapsed={sidebarCollapsed}
            mobileOpen={mobileSidebarOpen}
            onToggle={() => setSidebarCollapsed((collapsed) => !collapsed)}
            onCloseMobile={() => setMobileSidebarOpen(false)}
          />
          <main id="main-content" className="min-w-0 flex-1 overflow-y-auto">
            <div className="flex min-h-full flex-col p-4 md:p-6">
              <Outlet />
            </div>
          </main>
        </div>
      </div>
    </ModelSelectionProvider>
  );
}
