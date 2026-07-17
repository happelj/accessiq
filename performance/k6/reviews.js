import { sleep } from "k6";
import http from "k6/http";
import { BASE_URL, authHeaders, expectStatus, parseJson, scenarioOptions } from "./lib/config.js";
import { requireToken } from "./lib/auth.js";

export const options = scenarioOptions();

export function setup() {
  return { token: requireToken() };
}

export default function (data) {
  const params = { headers: authHeaders(data.token) };
  const campaigns = http.get(`${BASE_URL}/access-reviews/campaigns?count=25`, params);
  expectStatus(campaigns, [200], "list access review campaigns");

  const payload = parseJson(campaigns, []);
  if (payload.length > 0) {
    const campaignId = payload[0].id;
    expectStatus(
      http.get(`${BASE_URL}/access-reviews/campaigns/${campaignId}`, params),
      [200],
      "get access review campaign",
    );
    expectStatus(
      http.get(`${BASE_URL}/access-reviews/campaigns/${campaignId}/summary`, params),
      [200],
      "summarize access review campaign",
    );
    expectStatus(
      http.get(`${BASE_URL}/access-reviews/campaigns/${campaignId}/items?count=25`, params),
      [200],
      "list access review items",
    );
  }

  sleep(1);
}
