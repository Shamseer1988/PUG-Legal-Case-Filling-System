import { AuthGate } from '@/components/AuthGate';
import { RouteGate } from '@/components/RouteGate';
import { Sidebar } from '@/components/Sidebar';
import { Topbar } from '@/components/Topbar';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate>
      <div className="flex min-h-screen">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar />
          <main className="flex-1 overflow-x-auto px-6 py-6">
            <RouteGate>{children}</RouteGate>
          </main>
        </div>
      </div>
    </AuthGate>
  );
}
