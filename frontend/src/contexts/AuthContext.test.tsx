import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "./AuthContext";

function LoginHarness() {
  const auth = useAuth();

  return (
    <div>
      <span>{auth.currentUser?.email ?? "anonymous"}</span>
      <button
        type="button"
        onClick={() => auth.login("alice@example.com", "Password123!")}
      >
        Login
      </button>
    </div>
  );
}

describe("AuthProvider", () => {
  afterEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it("stores the token and loads the current user after login", async () => {
    const token = buildJwt({ sub: "3" });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/login")) {
          return jsonResponse({
            access_token: token,
            token_type: "bearer",
            expires_in: 1800,
          });
        }
        if (url.endsWith("/users/3")) {
          return jsonResponse({
            id: 3,
            name: "Alice Johnson",
            email: "alice@example.com",
            department: "Engineering",
            active: true,
            operator_role: "security_admin",
          });
        }
        return jsonResponse({ detail: "not found" }, 404);
      }),
    );

    render(
      <AuthProvider>
        <LoginHarness />
      </AuthProvider>,
    );

    await userEvent.click(screen.getByRole("button", { name: "Login" }));

    await waitFor(() => {
      expect(screen.getByText("alice@example.com")).toBeInTheDocument();
    });
    expect(window.localStorage.getItem("accessiq.auth")).toContain(token);
  });
});

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    }),
  );
}

function buildJwt(payload: Record<string, unknown>) {
  return ["header", window.btoa(JSON.stringify(payload)), "signature"].join(".");
}
