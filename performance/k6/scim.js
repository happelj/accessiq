import { sleep } from "k6";
import http from "k6/http";
import {
  BASE_URL,
  expectStatus,
  parseJson,
  scenarioOptions,
  scimHeaders,
} from "./lib/config.js";
import { requireToken } from "./lib/auth.js";

export const options = scenarioOptions({
  http_req_failed: ["rate<0.01"],
  http_req_duration: ["p(95)<1000", "p(99)<2000"],
});

export function setup() {
  return { token: requireToken() };
}

export default function (data) {
  const params = { headers: scimHeaders(data.token) };

  expectStatus(
    http.get(`${BASE_URL}/scim/v2/ServiceProviderConfig`, params),
    [200],
    "scim service provider config",
  );
  expectStatus(
    http.get(`${BASE_URL}/scim/v2/ResourceTypes`, params),
    [200],
    "scim resource types",
  );
  expectStatus(
    http.get(`${BASE_URL}/scim/v2/Schemas`, params),
    [200],
    "scim schemas",
  );

  const users = http.get(
    `${BASE_URL}/scim/v2/Users?startIndex=1&count=10&sortBy=id&sortOrder=ascending`,
    params,
  );
  expectStatus(users, [200], "scim list users");

  const userPayload = parseJson(users, { Resources: [] });
  const userId = userPayload.Resources.length > 0 ? userPayload.Resources[0].id : "1";

  expectStatus(
    http.get(`${BASE_URL}/scim/v2/Users/${userId}?attributes=userName,displayName`, params),
    [200],
    "scim get user",
  );

  expectStatus(
    http.get(`${BASE_URL}/scim/v2/Groups?startIndex=1&count=10`, params),
    [200],
    "scim list groups",
  );
  sleep(1);
}
