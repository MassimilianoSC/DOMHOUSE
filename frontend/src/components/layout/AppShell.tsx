import { useEffect, useState } from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { NavLink, Outlet, useLocation, useMatch } from "react-router-dom";
import { Download, LogOut, Menu, X } from "lucide-react";
import { toast } from "sonner";
import { useAuth, useRole } from "@/auth/AuthProvider";
import { isIos, useInstallPrompt } from "@/hooks/useInstallPrompt";
import { Button } from "@/components/ui/button";
import { useFeatures } from "@/hooks/useFeatures";
import { AdminSupportNotice, SupportBar, useOrgContextKey } from "@/components/support/SupportBanners";
import { usePushBridge } from "@/hooks/usePushBridge";
import { t } from "@/i18n";
import { cn, env } from "@/lib/utils";
import { EnvBanner } from "./EnvBanner";
import { apartmentNav, globalNav, type NavItem } from "./navItems";

function useNav() {
  const match = useMatch("/a/:aptId/*");
  const aptId = match?.params.aptId;
  const { isAdmin, isPlatform, hasTenant } = useRole();
  const { has, summary, denied } = useFeatures(aptId);
  // Simulatore: admins only, on a simulated apartment, in any environment (D-97).
  const simulator = isAdmin && summary.data?.simulated === true;
  const apt = aptId && !denied ? apartmentNav(aptId, simulator).filter((i) => !i.feature || has(i.feature)) : [];
  return { aptId, apt, global: globalNav(isAdmin, { platform: isPlatform, tenant: hasTenant }), aptName: summary.data?.name };
}

const linkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "flex min-h-[44px] items-center gap-3 rounded-xl px-3 text-sm font-semibold transition-colors focus-ring [&_svg]:size-[18px]",
    isActive ? "bg-primary/10 text-primary" : "text-muted-foreground hover:bg-secondary hover:text-foreground",
  );

function Links({ items, prefix, onNavigate }: { items: NavItem[]; prefix: string; onNavigate?: () => void }) {
  return (
    <>
      {items.map((i) => (
        <NavLink key={i.to} to={i.to} end={i.end} className={linkClass} onClick={onNavigate} data-testid={`${prefix}-nav-${i.key}`}>
          {i.icon} {t(`nav.${i.key}`)}
        </NavLink>
      ))}
    </>
  );
}

/** Install entry at the bottom of the sidebar: native prompt where the browser offers it (Chrome/Edge),
 *  written instructions otherwise; hidden once the app runs installed. */
function SidebarInstall({ prefix }: { prefix: string }) {
  const { canInstall, installed, install } = useInstallPrompt();
  if (installed) return null;
  const onClick = () => {
    if (canInstall) void install();
    else toast.info(t("settings.install"), { description: t(isIos() ? "settings.installIos" : "settings.installDesktop"), duration: 12000 });
  };
  return (
    <Button variant="outline" className="mb-3 w-full justify-start" onClick={onClick} data-testid={`${prefix}-install-btn`}>
      <Download /> {t("settings.install")}
    </Button>
  );
}

/**
 * Menu content (D-103), the same for the fixed sidebar of the computer and the side menu of the phone: logo, every
 * page (general and, inside an apartment, the apartment's, with the usual visibility rules), install, the person
 * with all their roles (D-82) and «Esci». onNavigate closes the phone menu after a choice.
 */
function MenuContent({ prefix, onNavigate }: { prefix: "sidebar" | "drawer"; onNavigate?: () => void }) {
  const { apt, global, aptName } = useNav();
  const { me, logout } = useAuth();
  return (
    <>
      <div className="mb-6 flex items-center gap-2 px-2" data-testid={prefix === "drawer" ? "mobile-menu-logo" : undefined}>
        <img src="/favicon.svg" alt="" className="h-8 w-8" />
        <span className="font-heading text-base font-extrabold leading-tight">{env.appName}</span>
      </div>
      <nav className="space-y-1" data-testid={`${prefix}-global`}>
        <Links items={global.slice(0, 1)} prefix={prefix} onNavigate={onNavigate} />
      </nav>
      {apt.length > 0 && (
        <nav className="mt-5 space-y-1 border-t pt-4" aria-label={t("nav.apartmentMenu")} data-testid={`${prefix}-apartment`}>
          <div className="truncate px-3 pb-1 text-[13px] font-medium text-muted-foreground">{aptName}</div>
          <Links items={apt} prefix={prefix} onNavigate={onNavigate} />
        </nav>
      )}
      <nav className="mt-5 space-y-1 border-t pt-4">
        <Links items={global.slice(1)} prefix={prefix} onNavigate={onNavigate} />
      </nav>
      <div className="mt-auto pt-4" />
      <SidebarInstall prefix={prefix} />
      <div className="rounded-2xl bg-secondary/70 p-3">
        {/* D-170: the name chosen in Settings, with the email under it; without one, the email alone */}
        {me?.user.display_name?.trim() ? (
          <>
            <div className="truncate text-sm font-bold" data-testid={`${prefix}-user-name`}>{me.user.display_name.trim()}</div>
            <div className="truncate text-xs text-muted-foreground" data-testid={`${prefix}-user-email`}>{me.user.email}</div>
          </>
        ) : (
          <div className="truncate text-sm font-bold" data-testid={`${prefix}-user-email`}>{me?.user.email}</div>
        )}
        <div className="text-xs text-muted-foreground" data-testid={`${prefix}-user-role`}>
          {me?.role ? t(`roles.${me.role}`) : me?.user.platform_manager ? t("roles.platform") : ""}
          {me?.tenant ? ` · ${me.tenant.name}` : ""}
          {me?.tenant?.suspended ? ` (${t("platform.suspendedBadge").toLowerCase()})` : ""}
        </div>
        {/* D-82: every role of the person; a platform manager inside an organization sees both */}
        {me?.role && me.user.platform_manager && <div className="text-xs text-muted-foreground" data-testid={`${prefix}-user-platform`}>{t("roles.platform")}</div>}
        <Button
          variant="ghost"
          size="sm"
          className="mt-2 -ml-2"
          onClick={() => {
            onNavigate?.();
            void logout();
          }}
          data-testid={`${prefix}-logout-btn`}
        >
          <LogOut /> {t("nav.logout")}
        </Button>
      </div>
    </>
  );
}

/** Computer: the fixed sidebar. */
function Sidebar() {
  return (
    <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col overflow-y-auto border-r bg-card/80 p-4 backdrop-blur md:flex" aria-label={t("nav.mainMenu")}>
      <MenuContent prefix="sidebar" />
    </aside>
  );
}

/**
 * Phone (D-103): no bottom bar; a three-line button opens the same menu from the left. The dialog keeps the focus
 * inside while open and gives it back to the button; Esc, a tap outside, «Chiudi il menu» or a chosen page close it.
 * Scrolling is locked without a jump (the scrollbar's room is kept).
 */
function MobileMenu() {
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  useEffect(() => setOpen(false), [pathname]); // any change of page closes it, whatever caused it
  return (
    <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
      <header className="pt-safe sticky top-0 z-40 border-b bg-card/85 backdrop-blur-xl md:hidden">
        <div className="flex h-14 items-center gap-2 px-2">
          <DialogPrimitive.Trigger asChild>
            <Button variant="ghost" size="icon" aria-label={t("nav.openMenu")} data-testid="mobile-menu-btn">
              <Menu />
            </Button>
          </DialogPrimitive.Trigger>
          <img src="/favicon.svg" alt="" className="h-7 w-7" />
          <span className="font-heading text-base font-extrabold leading-tight">{env.appName}</span>
        </div>
        {/* P-67: inside the sticky header, so it stays in sight while scrolling, below the notch */}
        <EnvBanner testId="env-banner-mobile" />
      </header>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-foreground/30 backdrop-blur-sm data-[state=open]:animate-in data-[state=open]:fade-in-0 md:hidden" />
        <DialogPrimitive.Content
          aria-describedby={undefined}
          className="pt-safe pb-safe pl-safe fixed inset-y-0 left-0 z-50 flex w-72 max-w-[85vw] flex-col overflow-y-auto border-r bg-card px-4 pb-4 shadow-xl data-[state=open]:animate-in data-[state=open]:slide-in-from-left md:hidden"
          data-testid="mobile-menu"
        >
          <DialogPrimitive.Title className="sr-only">{t("nav.mainMenu")}</DialogPrimitive.Title>
          <div className="flex justify-end pt-2">
            <DialogPrimitive.Close className="rounded-full p-2 opacity-70 hover:opacity-100 focus-ring" aria-label={t("nav.closeMenu")}>
              <X className="h-5 w-5" />
            </DialogPrimitive.Close>
          </div>
          <MenuContent prefix="drawer" onNavigate={() => setOpen(false)} />
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

export function AppShell() {
  usePushBridge();
  const orgKey = useOrgContextKey();
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        {/* P-67: the computer's band, on top of the content and sticky; the phone has its own in the header */}
        <EnvBanner className="sticky top-0 z-30 hidden md:flex" testId="env-banner" />
        <MobileMenu />
        <main className="main-safe min-w-0 flex-1 px-4 pt-5 sm:px-6 lg:px-10 lg:pt-8">
          <SupportBar />
          <AdminSupportNotice />
          <Outlet key={orgKey} />
        </main>
      </div>
    </div>
  );
}
