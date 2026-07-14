import type {
  AccessAssignment,
  AIExplainPayload,
  AIExplanationResponse,
  AIProvidersResponse,
  Application,
  Campaign,
  Connector,
  ConnectorHealth,
  Entitlement,
  GraphCacheStatus,
  GraphExport,
  HealthResponse,
  ProvisioningHistory,
  ProvisioningJob,
  RemediationJob,
  ScimGroup,
  ScimListResponse,
  TokenResponse,
  User,
} from "../types/api";
import { apiClient } from "./apiClient";
import { authStorage } from "./storage";

apiClient.setAccessTokenProvider(() => authStorage.get()?.accessToken ?? null);
apiClient.setUnauthorizedHandler(() => {
  authStorage.clear();
  window.dispatchEvent(new Event("accessiq:unauthorized"));
});

export const accessIqApi = {
  login(email: string, password: string): Promise<TokenResponse> {
    return apiClient.post<TokenResponse>(
      "/login",
      { email, password },
      { auth: false },
    );
  },

  getHealth(): Promise<HealthResponse> {
    return apiClient.get<HealthResponse>("/health", { auth: false });
  },

  listUsers(): Promise<User[]> {
    return apiClient.get<User[]>("/users", { auth: false });
  },

  getUser(userId: number): Promise<User> {
    return apiClient.get<User>(`/users/${userId}`, { auth: false });
  },

  listApplications(): Promise<Application[]> {
    return apiClient.get<Application[]>("/applications", { auth: false });
  },

  listEntitlements(applicationId: number): Promise<Entitlement[]> {
    return apiClient.get<Entitlement[]>(`/applications/${applicationId}/entitlements`, {
      auth: false,
    });
  },

  listUserAccess(userId: number): Promise<AccessAssignment[]> {
    return apiClient.get<AccessAssignment[]>(`/users/${userId}/access`, {
      auth: false,
    });
  },

  listConnectors(): Promise<Connector[]> {
    return apiClient.get<Connector[]>("/connectors");
  },

  getConnectorHealth(name: string): Promise<ConnectorHealth> {
    return apiClient.get<ConnectorHealth>(`/connectors/${name}/health`);
  },

  listProvisioningJobs(count = 25): Promise<ProvisioningJob[]> {
    return apiClient.get<ProvisioningJob[]>("/provisioning/jobs", {
      query: { count },
    });
  },

  listProvisioningHistory(count = 25): Promise<ProvisioningHistory[]> {
    return apiClient.get<ProvisioningHistory[]>("/provisioning/history", {
      query: { count },
    });
  },

  listCampaigns(count = 25): Promise<Campaign[]> {
    return apiClient.get<Campaign[]>("/access-reviews/campaigns", {
      query: { count },
    });
  },

  listRemediationJobs(count = 25): Promise<RemediationJob[]> {
    return apiClient.get<RemediationJob[]>("/remediation/jobs", {
      query: { count },
    });
  },

  listScimGroups(count = 50): Promise<ScimListResponse<ScimGroup>> {
    return apiClient.get<ScimListResponse<ScimGroup>>("/scim/v2/Groups", {
      query: { count },
    });
  },

  getScimServiceProviderConfig(): Promise<Record<string, unknown>> {
    return apiClient.get<Record<string, unknown>>("/scim/v2/ServiceProviderConfig");
  },

  getScimResourceTypes(): Promise<Record<string, unknown>> {
    return apiClient.get<Record<string, unknown>>("/scim/v2/ResourceTypes");
  },

  getScimSchemas(): Promise<Record<string, unknown>> {
    return apiClient.get<Record<string, unknown>>("/scim/v2/Schemas");
  },

  getGraphCacheStatus(): Promise<GraphCacheStatus> {
    return apiClient.get<GraphCacheStatus>("/graph/cache/status");
  },

  getGraphExport(): Promise<GraphExport> {
    return apiClient.get<GraphExport>("/graph/export", {
      query: { format: "json" },
    });
  },

  listAiProviders(): Promise<AIProvidersResponse> {
    return apiClient.get<AIProvidersResponse>("/ai/providers");
  },

  explain(payload: AIExplainPayload): Promise<AIExplanationResponse> {
    return apiClient.post<AIExplanationResponse>("/ai/explain", payload);
  },
};
