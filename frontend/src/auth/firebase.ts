import type { FirebaseApp } from "firebase/app";

const config = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
};

export const firebaseConfigured = Boolean(config.apiKey) && !config.apiKey.startsWith("your-");

/** Loaded on demand like firebase/auth and firebase/messaging, so the SDK stays out of the main block (P-20). */
export async function firebaseApp(): Promise<FirebaseApp> {
  const { getApps, initializeApp } = await import("firebase/app");
  return getApps()[0] ?? initializeApp(config);
}

/** Firebase Auth instance with Italian set for the emails Firebase sends from the browser (password reset,
 *  email verification, email change) and for its action pages. */
export async function firebaseAuth() {
  const [{ getAuth }, app] = await Promise.all([import("firebase/auth"), firebaseApp()]);
  const auth = getAuth(app);
  auth.languageCode = "it";
  return auth;
}

/** Where Firebase's action pages send the user back after a reset / verification. */
export const continueUrl = () => ({ url: `${window.location.origin}/login` });
