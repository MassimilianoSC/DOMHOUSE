import { roleOf, useRole } from "@/auth/AuthProvider";

/**
 * One place that turns the role into what a person may do (activation by the client, §7.4 of o2's estimate): the
 * pages ask for a function, never for a role, so a new role (the «Installatore», postponed) is added here only.
 */
export type Permission =
  /** «Stato dei dispositivi» of an apartment: diagnosis while a kit is installed (step 17, owner of the app). */
  | "devices.status"
  /** «Credenziali dei dispositivi» (A3): the passwords of the Shelly on the broker; whoever answers for them, the admin.
   *  A platform manager in an assistance access has an operator's rights, so not this (server proposal §8.1). */
  | "devices.credentials";

export function can(r: ReturnType<typeof roleOf>, p: Permission): boolean {
  switch (p) {
    case "devices.status":
    case "devices.credentials":
      return r.isAdmin;
  }
}

export function useCan(p: Permission): boolean {
  return can(useRole(), p);
}
