const storageKey = "accessiq.auth";

export interface StoredAuth {
  accessToken: string;
  expiresAt: number;
}

export const authStorage = {
  get(): StoredAuth | null {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) {
      return null;
    }

    try {
      return JSON.parse(raw) as StoredAuth;
    } catch {
      window.localStorage.removeItem(storageKey);
      return null;
    }
  },

  set(value: StoredAuth): void {
    window.localStorage.setItem(storageKey, JSON.stringify(value));
  },

  clear(): void {
    window.localStorage.removeItem(storageKey);
  },
};
