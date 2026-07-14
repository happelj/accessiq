interface JwtPayload {
  sub?: string;
  exp?: number;
}

export function readUserIdFromJwt(token: string): number | null {
  const payload = readJwtPayload(token);
  if (!payload?.sub) {
    return null;
  }

  const userId = Number(payload.sub);
  return Number.isFinite(userId) ? userId : null;
}

export function readJwtPayload(token: string): JwtPayload | null {
  const [, payload] = token.split(".");
  if (!payload) {
    return null;
  }

  try {
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(
      normalized.length + ((4 - (normalized.length % 4)) % 4),
      "=",
    );
    return JSON.parse(window.atob(padded)) as JwtPayload;
  } catch {
    return null;
  }
}
