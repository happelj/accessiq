import { sleep } from "k6";
import http from "k6/http";
import { BASE_URL, authHeaders, expectStatus, scenarioOptions } from "./lib/config.js";
import { requireToken } from "./lib/auth.js";

export const options = scenarioOptions({
  http_req_failed: ["rate<0.01"],
  http_req_duration: ["p(95)<1200", "p(99)<2500"],
});

export function setup() {
  return { token: requireToken() };
}

export default function (data) {
  const params = { headers: authHeaders(data.token) };

  expectStatus(http.get(`${BASE_URL}/graph/cache/status`, params), [200], "graph cache");
  expectStatus(http.get(`${BASE_URL}/graph/users/1`, params), [200], "graph user");
  expectStatus(
    http.get(`${BASE_URL}/graph/users/1/access`, params),
    [200],
    "graph user access",
  );
  expectStatus(
    http.get(`${BASE_URL}/graph/users/1/evidence`, params),
    [200],
    "graph user evidence",
  );
  expectStatus(
    http.get(`${BASE_URL}/graph/applications/1`, params),
    [200],
    "graph application",
  );
  expectStatus(
    http.get(
      `${BASE_URL}/graph/path?source_type=User&source_id=1&target_type=Application&target_id=1`,
      params,
    ),
    [200],
    "graph path",
  );
  sleep(1);
}
