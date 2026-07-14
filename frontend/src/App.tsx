import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { AuthProvider } from "./contexts/AuthContext";
import { AppLayout } from "./layouts/AppLayout";
import { ProtectedRoute } from "./layouts/ProtectedRoute";
import { AccessPage } from "./pages/AccessPage";
import { AccessReviewsPage } from "./pages/AccessReviewsPage";
import { AIAssistantPage } from "./pages/AIAssistantPage";
import { ApplicationsPage } from "./pages/ApplicationsPage";
import { AuthorizationGraphPage } from "./pages/AuthorizationGraphPage";
import { ConnectorsPage } from "./pages/ConnectorsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { GroupsPage } from "./pages/GroupsPage";
import { LoginPage } from "./pages/LoginPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { ProvisioningJobsPage } from "./pages/ProvisioningJobsPage";
import { RemediationPage } from "./pages/RemediationPage";
import { SCIMPage } from "./pages/SCIMPage";
import { SettingsPage } from "./pages/SettingsPage";
import { UnauthorizedPage } from "./pages/UnauthorizedPage";
import { UsersPage } from "./pages/UsersPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

export function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/unauthorized" element={<UnauthorizedPage />} />
              <Route element={<ProtectedRoute />}>
                <Route element={<AppLayout />}>
                  <Route index element={<Navigate to="/dashboard" replace />} />
                  <Route path="/dashboard" element={<DashboardPage />} />
                  <Route path="/users" element={<UsersPage />} />
                  <Route path="/applications" element={<ApplicationsPage />} />
                  <Route path="/groups" element={<GroupsPage />} />
                  <Route path="/access" element={<AccessPage />} />
                  <Route path="/scim" element={<SCIMPage />} />
                  <Route path="/connectors" element={<ConnectorsPage />} />
                  <Route path="/provisioning-jobs" element={<ProvisioningJobsPage />} />
                  <Route path="/access-reviews" element={<AccessReviewsPage />} />
                  <Route path="/remediation" element={<RemediationPage />} />
                  <Route path="/authorization-graph" element={<AuthorizationGraphPage />} />
                  <Route path="/ai-assistant" element={<AIAssistantPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                </Route>
              </Route>
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
