import { sleep } from "k6";
import http from "k6/http";
import { BASE_URL, expectStatus, scenarioOptions } from "./lib/config.js";
import { login } from "./lib/auth.js";

export const options = scenarioOptions({
  http_req_failed: ["rate<0.01"],
  http_req_duration: ["p(95)<1000", "p(99)<2000"],
});

export default function () {
  login();
  expectStatus(http.get(`${BASE_URL}/health`), [200], "health after login");
  sleep(1);
}
