export const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';
const SERVER_API = process.env.API_INTERNAL_URL || API;

export const TOKEN_KEY = 'iabet_token';
export const TOKEN_ROLE_KEY = 'iabet_role';

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
  round_number?: number | null;
  kickoff: string;
  venue?: string;
  status: string;
  competition: string;
  home_team: Team;
  away_team: Team;
  favorite: string | null;
  probabilities: { home: number; draw: number; away: number } | null;
  model_pick?: {
    market: string;
    selection: 'home' | 'draw' | 'away';
    odd: number | null;
    estimated_probability: number;
    fair_odd: number | null;
    has_value: boolean;
    price_status: string;
  } | null;
  best_value?: {
    market: string;
    selection: string;
    line?: number | null;
    odd: number;
    edge: number;
    strength: string;
    recommended?: boolean;
    risk_profile?: string;
  } | null;
};

export type RoundMatches = {
  round: number;
  competition_id: number;
  competition: string;
  season: string;
  matches: Match[];
};

export type StandingRow = {
  position: number;
  team: Team;
  played: number;
  wins: number;
  draws: number;
  losses: number;
  goals_for: number;
  goals_against: number;
  goal_difference: number;
  points: number;
};

export type Standings = {
  competition_id: number;
  competition: string;
  season: string;
  source: string;
  updated_at: string;
  table: StandingRow[];
};

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getTokenRole(): string | null {
  if (typeof window === 'undefined') return null;
  const stored = localStorage.getItem(TOKEN_ROLE_KEY);
  if (stored) return stored;
  const token = getToken();
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    return typeof payload.role === 'string' ? payload.role : null;
  } catch {
    return null;
  }
}

export function setToken(token: string, role?: string) {
  localStorage.setItem(TOKEN_KEY, token);
  if (role) localStorage.setItem(TOKEN_ROLE_KEY, role);
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('iabet-auth'));
  }
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(TOKEN_ROLE_KEY);
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

export async function getStandings(): Promise<Standings> {
  const r = await fetch(`${SERVER_API}/matches/standings`, { cache: 'no-store' });
  if (!r.ok) throw new Error('Classificação indisponível');
  return r.json();
}

export async function getNextRound(): Promise<RoundMatches> {
  const r = await fetch(`${SERVER_API}/matches/rounds/next`, { cache: 'no-store' });
  if (!r.ok) throw new Error('Próxima rodada indisponível');
  return r.json();
}

export async function getAnalysis(id: string) {
  const r = await fetch(`${SERVER_API}/matches/${id}`, { cache: 'no-store' });
  if (!r.ok) throw new Error('Análise indisponível');
  return r.json();
}
