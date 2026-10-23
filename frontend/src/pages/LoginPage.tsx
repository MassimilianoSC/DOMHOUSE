import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { KeyRound, UserRound } from "lucide-react";
import { toast } from "sonner";
import { bffFetch } from "@/api/bff";
import type { DevUser } from "@/api/types";
import { authErrorMessage, useAuth } from "@/auth/AuthProvider";
import { firebaseConfigured } from "@/auth/firebase";
import { showLoginError } from "@/lib/loginErrors";
import { Button } from "@/components/ui/button";
import { Card, Input, Label, Skeleton } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { env } from "@/lib/utils";

function DevLogin() {
  const { devLogin } = useAuth();
  const users = useQuery({ queryKey: ["dev-users"], queryFn: () => bffFetch<DevUser[]>("/app/dev/users") });
  return (
    <div className="space-y-3" data-testid="dev-login">
      <div className="flex items-center gap-2 text-sm font-bold">
        <KeyRound className="h-4 w-4 text-primary" /> {t("login.devTitle")}
      </div>
      <p className="text-xs text-muted-foreground">{t("login.devHint")}</p>
      {users.isLoading && <Skeleton className="h-14" />}
      {users.data?.map((u) => (
        <button
          key={u.email}
          type="button"
          onClick={() => void devLogin(u.email)}
          data-testid={`dev-login-${u.email}`}
          className="flex w-full items-center gap-3 rounded-lg border bg-card px-4 py-3 text-left transition-[background-color,transform] hover:bg-secondary active:scale-[0.99] focus-ring"
        >
          <span className="rounded-full bg-primary/10 p-2 text-primary">
            <UserRound className="h-4 w-4" />
          </span>
          <span className="min-w-[4.5rem] flex-1">
            <span className="block truncate text-sm font-bold">{u.display_name}</span>
            <span className="block truncate text-xs text-muted-foreground">{u.email}</span>
          </span>
          <span className="rounded-full bg-secondary px-2.5 py-1 text-center text-xs font-bold">{u.role ? t(`roles.${u.role}`) : t("roles.platform")}</span>
        </button>
      ))}
    </div>
  );
}

function ForgotPassword({ initialEmail, onBack }: { initialEmail: string; onBack: () => void }) {
  const { resetPassword } = useAuth();
  const [email, setEmail] = useState(initialEmail);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await resetPassword(email.trim());
      setSent(true);
    } catch (err) {
      // Unknown addresses get the same answer as known ones: the page must not reveal who has an account.
      if ((err as { code?: string })?.code === "auth/user-not-found") setSent(true);
      else toast.error(authErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit} className="space-y-4" data-testid="forgot-password-form">
      <p className="text-sm text-muted-foreground">{sent ? t("login.resetSent", { email }) : t("login.resetHint")}</p>
      {!sent && (
        <div className="space-y-1.5">
          <Label htmlFor="reset-email">{t("login.email")}</Label>
          <Input id="reset-email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} data-testid="reset-email-input" />
        </div>
      )}
      {!sent && <Button type="submit" className="w-full" disabled={busy} data-testid="reset-submit-btn">{t("login.resetSubmit")}</Button>}
      <Button type="button" variant="ghost" className="w-full" onClick={onBack} data-testid="reset-back-btn">{t("login.backToLogin")}</Button>
    </form>
  );
}

function FirebaseLogin() {
  const { emailLogin, googleLogin } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [forgot, setForgot] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await emailLogin(email, password);
    } catch (err) {
      showLoginError(err, "email"); // D-156: the sentence and «Codice: auth/…»
    } finally {
      setBusy(false);
    }
  };
  if (!firebaseConfigured) return <p className="text-sm text-muted-foreground" data-testid="firebase-not-configured">{t("login.notConfigured")}</p>;
  if (forgot) return <ForgotPassword initialEmail={email} onBack={() => setForgot(false)} />;
  return (
    <form onSubmit={submit} className="space-y-4" data-testid="firebase-login-form">
      <div className="space-y-1.5">
        <Label htmlFor="login-email">{t("login.email")}</Label>
        <Input id="login-email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} data-testid="login-email-input" />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="login-password">{t("login.password")}</Label>
        <Input id="login-password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} data-testid="login-password-input" />
        <button type="button" className="text-xs font-semibold text-primary hover:underline focus-ring" onClick={() => setForgot(true)} data-testid="login-forgot-btn">
          {t("login.forgot")}
        </button>
      </div>
      <Button type="submit" className="w-full" disabled={busy} data-testid="login-submit-btn">{t("login.submit")}</Button>
      <div className="text-center text-xs text-muted-foreground">{t("login.or")}</div>
      <Button type="button" variant="outline" className="w-full" onClick={() => googleLogin().catch((err) => showLoginError(err, "google"))} data-testid="login-google-btn">
        {t("login.google")}
      </Button>
    </form>
  );
}

export default function LoginPage() {
  const { status } = useAuth();
  if (status === "authenticated") return <Navigate to="/" replace />;
  return (
    <div className="grid min-h-screen grid-cols-1 lg:grid-cols-[1.1fr_1fr]">
      <section className="relative hidden flex-col justify-between overflow-hidden bg-foreground p-12 text-background lg:flex">
        {/* a solid panel with what the app is for, 36 px (design lot 2); the name sits with the mark above the card */}
        <img src="/favicon.svg" alt="" className="relative h-12 w-12" />
        <p className="relative max-w-md text-4xl font-bold leading-tight" data-testid="login-tagline">{t("app.tagline")}</p>
      </section>
      <section className="flex flex-col items-center justify-center gap-6 p-5">
        {/* the mark and the name above the card at every width (design review c.14, lot 2) */}
        <div className="flex items-center gap-3" data-testid="login-brand">
          <img src="/favicon.svg" alt="" className="h-10 w-10" />
          <span className="font-heading text-2xl font-extrabold">{env.appName}</span>
        </div>
        <Card className="w-full max-w-md p-5 sm:p-8">
          <h1 className="text-2xl font-bold">{t("login.title")}</h1>
          <p className="mb-6 mt-1 text-sm text-muted-foreground">{t("login.subtitle")}</p>
          {env.authMode === "dev" ? <DevLogin /> : <FirebaseLogin />}
        </Card>
      </section>
    </div>
  );
}
