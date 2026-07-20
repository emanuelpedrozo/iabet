'use client';

import { useCallback, useSyncExternalStore } from 'react';
import { TOKEN_KEY, TOKEN_ROLE_KEY, clearToken, getToken, getTokenRole } from '@/lib/api';

const AUTH_EVENT = 'iabet-auth';

function subscribe(onStoreChange: () => void) {
  if (typeof window === 'undefined') return () => undefined;
  const onStorage = (e: StorageEvent) => {
    if (e.key === TOKEN_KEY || e.key === TOKEN_ROLE_KEY || e.key === null) onStoreChange();
  };
  window.addEventListener('storage', onStorage);
  window.addEventListener(AUTH_EVENT, onStoreChange);
  return () => {
    window.removeEventListener('storage', onStorage);
    window.removeEventListener(AUTH_EVENT, onStoreChange);
  };
}

function getSnapshot() {
  return `${Boolean(getToken())}:${getTokenRole() || ''}`;
}

function getServerSnapshot() {
  return 'false:';
}

export function notifyAuthChange() {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(AUTH_EVENT));
  }
}

export function useAuth() {
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const [logged, role = ''] = snapshot.split(':');
  const loggedIn = logged === 'true';

  const logout = useCallback(() => {
    clearToken();
    notifyAuthChange();
    window.location.href = '/';
  }, []);

  return { loggedIn, role, isAdmin: role === 'admin', logout };
}
