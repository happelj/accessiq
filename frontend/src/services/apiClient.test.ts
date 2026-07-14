import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClient, ApiError } from "./apiClient";

describe("ApiClient", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("adds bearer authentication and serializes JSON bodies", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const client = new ApiClient("http://api.test");
    client.setAccessTokenProvider(() => "token-123");

    await client.post("/example", { name: "Alice" });

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const headers = new Headers(init?.headers);
    expect(url).toBe("http://api.test/example");
    expect(headers.get("Authorization")).toBe("Bearer token-123");
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(init?.body).toBe(JSON.stringify({ name: "Alice" }));
  });

  it("throws a typed error for failed API responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ detail: "Invalid credentials" }), {
          status: 401,
          statusText: "Unauthorized",
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    const client = new ApiClient("http://api.test");

    await expect(client.get("/secure")).rejects.toMatchObject({
      status: 401,
      message: "Invalid credentials",
    });
  });
});
