/**
 * JWT bearer-token holder for the Dashboard API.
 *
 * The contract uses `Authorization: Bearer <token>` (not the HttpOnly session
 * cookie the provider-portal README assumed). For the hackathon demo we keep the
 * token in `sessionStorage` so a page reload stays signed in; it is cleared on
 * sign-out. sessionStorage (not localStorage) means the token dies with the tab.
 */
const KEY = 'metron.token';

let memory: string | null = null;

export function getToken(): string | null {
  if (memory !== null) return memory;
  try {
    memory = sessionStorage.getItem(KEY);
  } catch {
    memory = null;
  }
  return memory;
}

export function setToken(token: string | null): void {
  memory = token;
  try {
    if (token) sessionStorage.setItem(KEY, token);
    else sessionStorage.removeItem(KEY);
  } catch {
    /* sessionStorage unavailable (private mode / SSR) — memory holder still works */
  }
}

export function clearToken(): void {
  setToken(null);
}
