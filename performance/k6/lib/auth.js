import { check, fail } from "k6";
import http from "k6/http";
import { BASE_URL, TEST_EMAIL, TEST_PASSWORD, jsonHeaders, parseJson } from "./config.js";

export function login(email = TEST_EMAIL, password = TEST_PASSWORD) {
  const response = http.post(
    `${BASE_URL}/login`,
    JSON.stringify({ email, password }),
    { headers: jsonHeaders() },
  );
  const payload = parseJson(response);

  check(response, {
    "login returned 200": (result) => result.status === 200,
    "login returned bearer token": () => typeof payload.access_token === "string",
  });

  return payload.access_token || "";
}

export function requireToken() {
  const token = login();

  if (!token) {
    fail("Login failed; cannot continue authenticated performance scenario.");
  }

  return token;
}
