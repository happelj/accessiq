import { sleep } from "k6";
import http from "k6/http";
import { BASE_URL, expectStatus, jsonHeaders, scenarioOptions } from "./lib/config.js";
import { requireToken } from "./lib/auth.js";

export const options = scenarioOptions({
  http_req_failed: ["rate<0.01"],
  http_req_duration: ["p(95)<1500", "p(99)<3000"],
});

export function setup() {
  return { token: requireToken() };
}

export default function (data) {
  const params = { headers: jsonHeaders(data.token) };
  const body = JSON.stringify({
    question: "Why does user 1 have access to Salesforce?",
    user_id: 1,
    application_id: 1,
    provider: "mock",
    max_tokens: 800,
  });

  expectStatus(http.get(`${BASE_URL}/ai/providers`, params), [200], "ai providers");
  expectStatus(
    http.post(`${BASE_URL}/ai/context`, body, params),
    [200],
    "ai context",
  );
  expectStatus(
    http.post(`${BASE_URL}/ai/explain`, body, params),
    [200],
    "ai explain",
  );
  sleep(1);
}
