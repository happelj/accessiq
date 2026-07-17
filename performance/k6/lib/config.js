import { check } from "k6";

export const BASE_URL = (__ENV.ACCESSIQ_BASE_URL || "http://localhost:8000").replace(
  /\/$/,
  "",
);

export const TEST_EMAIL = __ENV.ACCESSIQ_TEST_EMAIL || "alice@example.com";
export const TEST_PASSWORD = __ENV.ACCESSIQ_TEST_PASSWORD || "Password123!";

export const DEFAULT_THRESHOLDS = {
  http_req_failed: ["rate<0.01"],
  http_req_duration: ["p(95)<750", "p(99)<1500"],
};

export function scenarioOptions(thresholds = DEFAULT_THRESHOLDS) {
  return {
    scenarios: {
      steady: {
        executor: "constant-vus",
        vus: Number(__ENV.K6_VUS || 1),
        duration: __ENV.K6_DURATION || "30s",
      },
    },
    thresholds,
  };
}

export function jsonHeaders(token) {
  const headers = {
    Accept: "application/json",
    "Content-Type": "application/json",
  };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  return headers;
}

export function scimHeaders(token) {
  return {
    ...jsonHeaders(token),
    Accept: "application/scim+json",
    "Content-Type": "application/scim+json",
  };
}

export function authHeaders(token) {
  return {
    Accept: "application/json",
    Authorization: `Bearer ${token}`,
  };
}

export function expectStatus(response, allowedStatuses, label) {
  return check(response, {
    [`${label} status`]: (result) => allowedStatuses.includes(result.status),
  });
}

export function parseJson(response, fallback = {}) {
  try {
    return response.json();
  } catch {
    return fallback;
  }
}
