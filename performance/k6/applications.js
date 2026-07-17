import { sleep } from "k6";
import http from "k6/http";
import { BASE_URL, expectStatus, parseJson, scenarioOptions } from "./lib/config.js";

export const options = scenarioOptions();

export default function () {
  const applications = http.get(`${BASE_URL}/applications`);
  expectStatus(applications, [200], "list applications");

  const payload = parseJson(applications, []);
  const applicationId = payload.length > 0 ? payload[0].id : 1;

  expectStatus(
    http.get(`${BASE_URL}/applications/${applicationId}/entitlements`),
    [200],
    "list application entitlements",
  );
  sleep(1);
}
