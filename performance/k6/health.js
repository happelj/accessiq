import { check, sleep } from "k6";
import http from "k6/http";
import { BASE_URL, expectStatus, scenarioOptions } from "./lib/config.js";

export const options = scenarioOptions({
  http_req_failed: ["rate<0.01"],
  http_req_duration: ["p(95)<500", "p(99)<1000"],
});

export default function () {
  expectStatus(http.get(`${BASE_URL}/health`), [200], "health");
  expectStatus(http.get(`${BASE_URL}/version`), [200], "version");

  const metrics = http.get(`${BASE_URL}/metrics`);
  expectStatus(metrics, [200], "metrics");
  check(metrics, {
    "metrics include request counter": (response) =>
      response.body.includes("accessiq_http_requests_total"),
  });
  sleep(1);
}
