import { BarChart3, Bot, Building2, CalendarClock, ClipboardCheck, FlaskConical, History, LayoutDashboard, Network, Settings, Shield, SlidersHorizontal } from "lucide-react";
import type { ReactNode } from "react";
import type { AppFeature } from "@/api/types";

export interface NavItem {
  to: string;
  key: string;
  icon: ReactNode;
  feature?: AppFeature;
  end?: boolean;
}

export function apartmentNav(aptId: string, simulator = false): NavItem[] {
  const base = `/a/${aptId}`;
  const items: NavItem[] = [
    { to: base, key: "overview", icon: <LayoutDashboard />, end: true },
    { to: `${base}/approvazioni`, key: "approvals", icon: <ClipboardCheck />, feature: "approvals" },
    { to: `${base}/decisioni`, key: "decisions", icon: <History />, feature: "decisions" },
    { to: `${base}/consumi`, key: "energy", icon: <BarChart3 />, feature: "energy" },
    { to: `${base}/programmazione`, key: "schedule", icon: <CalendarClock />, feature: "schedule" },
    { to: `${base}/regole`, key: "rules", icon: <SlidersHorizontal />, feature: "rules" },
    { to: `${base}/assistente`, key: "assistant", icon: <Bot />, feature: "ask" },
  ];
  if (simulator) items.push({ to: `${base}/simulatore`, key: "simulator", icon: <FlaskConical /> });
  return items;
}

/** Global menu: Appartamenti and Amministrazione need an organization; Organizzazioni only for platform managers (P-36). */
export function globalNav(isAdmin: boolean, opts: { platform?: boolean; tenant?: boolean } = {}): NavItem[] {
  const tenant = opts.tenant ?? true;
  const items: NavItem[] = [];
  if (tenant) items.push({ to: "/", key: "apartments", icon: <Building2 />, end: true });
  if (tenant && isAdmin) items.push({ to: "/admin", key: "admin", icon: <Shield /> });
  if (opts.platform) items.push({ to: "/organizzazioni", key: "organizations", icon: <Network /> });
  items.push({ to: "/impostazioni", key: "settings", icon: <Settings /> });
  return items;
}
