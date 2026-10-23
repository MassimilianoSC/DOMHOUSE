import { Suspense, type ComponentType } from "react";
import { Navigate, Route, Routes, useParams } from "react-router-dom";
import { useAuth, useRole } from "@/auth/AuthProvider";
import { AppShell } from "@/components/layout/AppShell";
import { Skeleton } from "@/components/ui/primitives";
import { useFeatures } from "@/hooks/useFeatures";
import { t } from "@/i18n";
import { lazyPage } from "@/lib/lazyPage";
import ApartmentLayout, { FeatureGate } from "@/pages/ApartmentLayout";
import ApartmentsPage from "@/pages/ApartmentsPage";
import LoginPage from "@/pages/LoginPage";
import OverviewPage from "@/pages/OverviewPage";
import type { AppFeature } from "@/api/types";

// The first screens (login, apartments, overview) ship in the main block; every other page is its own block, loaded
// when opened (P-20: recharts alone is ~370 kB and only Consumi uses it).
const SchedulePage = lazyPage(() => import("@/pages/SchedulePage"));
const RulesPage = lazyPage(() => import("@/pages/RulesPage"));
const ApprovalsPage = lazyPage(() => import("@/pages/ApprovalsPage"));
const DecisionsPage = lazyPage(() => import("@/pages/DecisionsPage"));
const EnergyPage = lazyPage(() => import("@/pages/EnergyPage"));
const AssistantPage = lazyPage(() => import("@/pages/AssistantPage"));
const SimulatorPage = lazyPage(() => import("@/pages/SimulatorPage"));
const SummariesPage = lazyPage(() => import("@/pages/SummariesPage"));
const AdminPage = lazyPage(() => import("@/pages/AdminPage"));
const SettingsPage = lazyPage(() => import("@/pages/SettingsPage"));
const OrganizationsPage = lazyPage(() => import("@/pages/OrganizationsPage"));

/** Suspense per page, so the menu stays in place while a page block loads. */
function Lazy({ page: Page }: { page: ComponentType }) {
  return (
    <Suspense fallback={<Skeleton className="h-64 rounded-3xl" />}>
      <Page />
    </Suspense>
  );
}

function Protected() {
  const { status } = useAuth();
  if (status === "loading") return <div className="p-8"><Skeleton className="h-40" /></div>;
  if (status === "anonymous") return <Navigate to="/login" replace />;
  return <AppShell />;
}

function AdminOnly({ children }: { children: React.ReactNode }) {
  const { isAdmin } = useRole();
  return isAdmin ? <>{children}</> : <Navigate to="/" replace />;
}

/** Organizzazioni (P-36): for platform managers only; anyone else gets "Pagina non trovata", so the page is not revealed. */
function PlatformOnly({ children }: { children: React.ReactNode }) {
  const { isPlatform } = useRole();
  return isPlatform ? <>{children}</> : <NotFound />;
}

/** The apartments list needs an organization: a platform manager outside any lands on Organizzazioni. */
function Home() {
  const { hasTenant } = useRole();
  return hasTenant ? <ApartmentsPage /> : <Navigate to="/organizzazioni" replace />;
}

/** Simulatore: admins only, and only on a simulated apartment (D-97), in any environment; else "Pagina non trovata". */
function SimulatorOnly({ children }: { children: React.ReactNode }) {
  const { isAdmin } = useRole();
  const { aptId } = useParams();
  const { summary } = useFeatures(aptId);
  if (summary.isLoading) return null;
  return isAdmin && summary.data?.simulated === true ? <>{children}</> : <NotFound />;
}

const PHASE2: { path: string; feature: AppFeature; element: React.ReactNode }[] = [
  { path: "programmazione", feature: "schedule", element: <Lazy page={SchedulePage} /> },
  { path: "regole", feature: "rules", element: <Lazy page={RulesPage} /> },
  { path: "approvazioni", feature: "approvals", element: <Lazy page={ApprovalsPage} /> },
  { path: "decisioni", feature: "decisions", element: <Lazy page={DecisionsPage} /> },
  { path: "consumi", feature: "energy", element: <Lazy page={EnergyPage} /> },
  { path: "assistente", feature: "ask", element: <Lazy page={AssistantPage} /> },
];

function NotFound() {
  return (
    <div className="py-20 text-center" data-testid="not-found">
      <h1 className="text-2xl font-bold">{t("errors.notFound")}</h1>
      <p className="mt-2 text-sm text-muted-foreground">{t("errors.notFoundHint")}</p>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<Protected />}>
        <Route index element={<Home />} />
        <Route path="a/:aptId" element={<ApartmentLayout />}>
          <Route index element={<OverviewPage />} />
          <Route path="panoramica" element={<Navigate to=".." replace relative="path" />} />
          {PHASE2.map((p) => (
            <Route key={p.path} path={p.path} element={<FeatureGate feature={p.feature}>{p.element}</FeatureGate>} />
          ))}
          <Route path="simulatore" element={<SimulatorOnly><Lazy page={SimulatorPage} /></SimulatorOnly>} />
          {/* D-150: made by the BFF, not by the engine, so no feature gate; every role */}
          <Route path="riepiloghi" element={<Lazy page={SummariesPage} />} />
          <Route path="riepiloghi/:week" element={<Lazy page={SummariesPage} />} />
        </Route>
        <Route path="admin" element={<AdminOnly><Lazy page={AdminPage} /></AdminOnly>} />
        <Route path="organizzazioni" element={<PlatformOnly><Lazy page={OrganizationsPage} /></PlatformOnly>} />
        <Route path="impostazioni" element={<Lazy page={SettingsPage} />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
