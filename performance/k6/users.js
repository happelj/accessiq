import { sleep } from "k6";
import http from "k6/http";
import { BASE_URL, expectStatus, parseJson, scenarioOptions } from "./lib/config.js";

export const options = scenarioOptions();

export default function () {
  const users = http.get(`${BASE_URL}/users`);
  expectStatus(users, [200], "list users");

  const payload = parseJson(users, []);
  const userId = payload.length > 0 ? payload[0].id : 1;

  expectStatus(http.get(`${BASE_URL}/users/${userId}`), [200], "get user");
  expectStatus(
    http.get(`${BASE_URL}/users/${userId}/access`),
    [200],
    "list user access",
  );
  sleep(1);
}
