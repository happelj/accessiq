import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { accessIqApi } from "../services/accessiq";
import { authStorage, type StoredAuth } from "../services/storage";
import type { User } from "../types/api";
import { readUserIdFromJwt } from "../utils/auth";

interface AuthContextValue {
  currentUser: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshAccessToken: () => Promise<boolean>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [storedAuth, setStoredAuth] = useState<StoredAuth | null>(() => authStorage.get());
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const logout = useCallback(() => {
    authStorage.clear();
    setStoredAuth(null);
    setCurrentUser(null);
  }, []);

  const loadCurrentUser = useCallback(
    async (token: string) => {
      const userId = readUserIdFromJwt(token);
      if (!userId) {
        logout();
        return;
      }

      const user = await accessIqApi.getUser(userId);
      setCurrentUser(user);
    },
    [logout],
  );

  useEffect(() => {
    let active = true;

    async function restoreSession() {
      const existing = authStorage.get();
      if (!existing || existing.expiresAt <= Date.now()) {
        logout();
        if (active) {
          setIsLoading(false);
        }
        return;
      }

      setStoredAuth(existing);
      try {
        await loadCurrentUser(existing.accessToken);
      } catch {
        logout();
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    }

    restoreSession();
    return () => {
      active = false;
    };
  }, [loadCurrentUser, logout]);

  useEffect(() => {
    window.addEventListener("accessiq:unauthorized", logout);
    return () => window.removeEventListener("accessiq:unauthorized", logout);
  }, [logout]);

  const login = useCallback(
    async (email: string, password: string) => {
      const token = await accessIqApi.login(email, password);
      const nextAuth = {
        accessToken: token.access_token,
        expiresAt: Date.now() + token.expires_in * 1000,
      };
      authStorage.set(nextAuth);
      setStoredAuth(nextAuth);
      await loadCurrentUser(nextAuth.accessToken);
    },
    [loadCurrentUser],
  );

  const refreshAccessToken = useCallback(async () => {
    return false;
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      currentUser,
      token: storedAuth?.accessToken ?? null,
      isAuthenticated: Boolean(storedAuth && storedAuth.expiresAt > Date.now()),
      isLoading,
      login,
      logout,
      refreshAccessToken,
    }),
    [currentUser, isLoading, login, logout, refreshAccessToken, storedAuth],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return value;
}
