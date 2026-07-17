import { lazy, Suspense } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { LoadingSpinner } from "./components/LoadingSpinner";
import { AuthProvider } from "./contexts/AuthContext";
import { AppLayout } from "./layouts/AppLayout";
import { ProtectedRoute } from "./layouts/ProtectedRoute";

const AccessPage = lazy(() =>
  import("./pages/AccessPage").then((module) => ({ default: module.AccessPage })),
);
const AccessReviewsPage = lazy(() =>
  import("./pages/AccessReviewsPage").then((module) => ({
    default: module.AccessReviewsPage,
  })),
);
const AIAssistantPage = lazy(() =>
  import("./pages/AIAssistantPage").then((module) => ({
    default: module.AIAssistantPage,
  })),
);
const ApplicationsPage = lazy(() =>
  import("./pages/ApplicationsPage").then((module) => ({
    default: module.ApplicationsPage,
  })),
);
const AuthorizationGraphPage = lazy(() =>
  import("./pages/AuthorizationGraphPage").then((module) => ({
    default: module.AuthorizationGraphPage,
  })),
);
const ConnectorsPage = lazy(() =>
  import("./pages/ConnectorsPage").then((module) => ({
    default: module.ConnectorsPage,
  })),
);
const DashboardPage = lazy(() =>
  import("./pages/DashboardPage").then((module) => ({
    default: module.DashboardPage,
  })),
);
const GroupsPage = lazy(() =>
  import("./pages/GroupsPage").then((module) => ({ default: module.GroupsPage })),
);
const LoginPage = lazy(() =>
  import("./pages/LoginPage").then((module) => ({ default: module.LoginPage })),
);
const NotFoundPage = lazy(() =>
  import("./pages/NotFoundPage").then((module) => ({
    default: module.NotFoundPage,
  })),
);
const ProvisioningJobsPage = lazy(() =>
  import("./pages/ProvisioningJobsPage").then((module) => ({
    default: module.ProvisioningJobsPage,
  })),
);
const RemediationPage = lazy(() =>
  import("./pages/RemediationPage").then((module) => ({
    default: module.RemediationPage,
  })),
);
const SCIMPage = lazy(() =>
  import("./pages/SCIMPage").then((module) => ({ default: module.SCIMPage })),
);
const SettingsPage = lazy(() =>
  import("./pages/SettingsPage").then((module) => ({
    default: module.SettingsPage,
  })),
);
const UnauthorizedPage = lazy(() =>
  import("./pages/UnauthorizedPage").then((module) => ({
    default: module.UnauthorizedPage,
  })),
);
const UsersPage = lazy(() =>
  import("./pages/UsersPage").then((module) => ({ default: module.UsersPage })),
);

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
            <Suspense fallback={<LoadingSpinner label="Loading page" />}>
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
                    <Route
                      path="/provisioning-jobs"
                      element={<ProvisioningJobsPage />}
                    />
                    <Route path="/access-reviews" element={<AccessReviewsPage />} />
                    <Route path="/remediation" element={<RemediationPage />} />
                    <Route
                      path="/authorization-graph"
                      element={<AuthorizationGraphPage />}
                    />
                    <Route path="/ai-assistant" element={<AIAssistantPage />} />
                    <Route path="/settings" element={<SettingsPage />} />
                  </Route>
                </Route>
                <Route path="*" element={<NotFoundPage />} />
              </Routes>
            </Suspense>
          </BrowserRouter>
        </AuthProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
