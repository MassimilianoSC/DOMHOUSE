import type { CredentialScope } from "@/api/deviceCredentials";
import { CredentialsPanel } from "./CredentialsPanel";

/** The list and, next, the windows of its actions (A3). */
export function CredentialsWorkspace({ apartmentId, scope }: { apartmentId: string; scope: CredentialScope }) {
  return <CredentialsPanel apartmentId={apartmentId} scope={scope} onRequest={() => {}} onRegister={() => {}} />;
}
