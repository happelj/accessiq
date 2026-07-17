import { sleep } from "k6";
import http from "k6/http";
import { BASE_URL, authHeaders, expectStatus, scenarioOptions } from "./lib/config.js";
import { requireToken } from "./lib/auth.js";

export const options = scenarioOptions();

export function setup() {
  return { token: requireToken() };
}

export default function (data) {
  const params = { headers: authHeaders(data.token) };

  expectStatus(
    http.get(`${BASE_URL}/provisioning/jobs?count=25`, params),
    [200],
    "list provisioning jobs",
  );
  expectStatus(
    http.get(`${BASE_URL}/provisioning/history?count=25`, params),
    [200],
    "list provisioning history",
  );
  expectStatus(
    http.get(`${BASE_URL}/remediation/jobs?count=25`, params),
    [200],
    "list remediation jobs",
  );
  sleep(1);
}
