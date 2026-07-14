import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AuthProvider } from "../contexts/AuthContext";
import { ProtectedRoute } from "./ProtectedRoute";

describe("ProtectedRoute", () => {
  it("redirects anonymous users to the login route", async () => {
    window.localStorage.clear();

    render(
      <AuthProvider>
        <MemoryRouter initialEntries={["/secure"]}>
          <Routes>
            <Route element={<ProtectedRoute />}>
              <Route path="/secure" element={<div>secure content</div>} />
            </Route>
            <Route path="/login" element={<div>login route</div>} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>,
    );

    expect(await screen.findByText("login route")).toBeInTheDocument();
  });
});
