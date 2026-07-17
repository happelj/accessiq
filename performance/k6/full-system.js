import { group, sleep } from "k6";
import http from "k6/http";
import {
  BASE_URL,
  authHeaders,
  expectStatus,
  jsonHeaders,
  parseJson,
  scenarioOptions,
  scimHeaders,
} from "./lib/config.js";
import { requireToken } from "./lib/auth.js";

export const options = scenarioOptions({
  http_req_failed: ["rate<0.02"],
  http_req_duration: ["p(95)<1500", "p(99)<3000"],
});

export function setup() {
  return { token: requireToken() };
}

export default function (data) {
  const authParams = { headers: authHeaders(data.token) };
  const jsonParams = { headers: jsonHeaders(data.token) };
  const scimParams = { headers: scimHeaders(data.token) };

  group("public health and catalog", () => {
    expectStatus(http.get(`${BASE_URL}/health`), [200], "health");
    expectStatus(http.get(`${BASE_URL}/version`), [200], "version");
    expectStatus(http.get(`${BASE_URL}/metrics`), [200], "metrics");
    expectStatus(http.get(`${BASE_URL}/users`), [200], "users");
    expectStatus(http.get(`${BASE_URL}/applications`), [200], "applications");
    expectStatus(
      http.get(`${BASE_URL}/applications/1/entitlements`),
      [200],
      "application entitlements",
    );
  });

  group("scim reads", () => {
    expectStatus(
      http.get(`${BASE_URL}/scim/v2/ServiceProviderConfig`, scimParams),
      [200],
      "scim service provider config",
    );
    expectStatus(
      http.get(`${BASE_URL}/scim/v2/Users?startIndex=1&count=10`, scimParams),
      [200],
      "scim users",
    );
    expectStatus(
      http.get(`${BASE_URL}/scim/v2/Groups?startIndex=1&count=10`, scimParams),
      [200],
      "scim groups",
    );
  });

  group("graph and governance reads", () => {
    expectStatus(http.get(`${BASE_URL}/graph/users/1`, authParams), [200], "graph user");
    expectStatus(
      http.get(`${BASE_URL}/graph/users/1/evidence`, authParams),
      [200],
      "graph evidence",
    );
    expectStatus(
      http.get(`${BASE_URL}/access-reviews/campaigns?count=25`, authParams),
      [200],
      "access reviews",
    );
    expectStatus(
      http.get(`${BASE_URL}/provisioning/jobs?count=25`, authParams),
      [200],
      "provisioning jobs",
    );
  });

  group("mock ai explanation", () => {
    const body = JSON.stringify({
      question: "Explain user 1 access.",
      user_id: 1,
      application_id: 1,
      provider: "mock",
      max_tokens: 800,
    });
    const response = http.post(`${BASE_URL}/ai/explain`, body, jsonParams);
    expectStatus(response, [200], "ai explain");
    parseJson(response);
  });

  sleep(1);
}
