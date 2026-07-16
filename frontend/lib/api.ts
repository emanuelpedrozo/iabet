export const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';
const SERVER_API = process.env.API_INTERNAL_URL || API;

export const TOKEN_KEY = 'iabet_token';

export type Team = {
  id: number;
  name: string;
  short_name: string;
  crest_url?: string | null;
  elo: number;
  attack_strength: number;
  defense_strength: number;
};

export type Match = {
  id: number;
  kickoff: string;
  venue?: string;
  status: string;
  competition: string;
  home_team: Team;
  away_team: Team;
  favorite: string | null;
  probabilities: { home: number; draw: number; away: number } | null;
  best_value?: {
    market: string;
    selection: string;
    odd: number;
    edge: number;
    strength: string;
  } | null;
};

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('iabet-auth'));
  }
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('iabet-auth'));
  }
}

export async function apiFetch(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  if (!headers.has('Content-Type') && init.body) {
    headers.set('Content-Type', 'application/json');
  }
  const token = getToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(`${API}${path}`, { ...init, headers });
  return response;
}

export async function getMatches(): Promise<Match[]> {
  const r = await fetch(`${SERVER_API}/matches`, { cache: 'no-store' });
  if (!r.ok) throw new Error('API indisponível');
  return r.json();
}

export async function getAnalysis(id: string) {
  const r = await fetch(`${SERVER_API}/matches/${id}`, { cache: 'no-store' });
  if (!r.ok) throw new Error('Análise indisponível');
  return r.json();
}
