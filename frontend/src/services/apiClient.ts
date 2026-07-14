import { API_BASE_URL } from "../config/env";

type QueryValue = string | number | boolean | null | undefined;

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  query?: Record<string, QueryValue>;
  auth?: boolean;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export class ApiClient {
  private accessTokenProvider: (() => string | null) | null = null;
  private unauthorizedHandler: (() => void) | null = null;

  constructor(private readonly baseUrl = API_BASE_URL) {}

  setAccessTokenProvider(provider: () => string | null): void {
    this.accessTokenProvider = provider;
  }

  setUnauthorizedHandler(handler: () => void): void {
    this.unauthorizedHandler = handler;
  }

  get<T>(path: string, options: RequestOptions = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: "GET" });
  }

  post<T>(path: string, body?: unknown, options: RequestOptions = {}): Promise<T> {
    return this.request<T>(path, { ...options, method: "POST", body });
  }

  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const response = await fetch(this.buildUrl(path, options.query), {
      ...options,
      headers: this.buildHeaders(options),
      body: this.buildBody(options.body),
    });

    if (response.status === 401 && options.auth !== false) {
      this.unauthorizedHandler?.();
    }

    const payload = await this.readPayload(response);
    if (!response.ok) {
      throw new ApiError(this.errorMessage(payload, response), response.status, payload);
    }

    return payload as T;
  }

  private buildUrl(path: string, query?: Record<string, QueryValue>): string {
    const url = new URL(`${this.baseUrl}${path}`);
    Object.entries(query ?? {}).forEach(([key, value]) => {
      if (value !== null && value !== undefined && value !== "") {
        url.searchParams.set(key, String(value));
      }
    });
    return url.toString();
  }

  private buildHeaders(options: RequestOptions): Headers {
    const headers = new Headers(options.headers);
    if (!headers.has("Accept")) {
      headers.set("Accept", "application/json");
    }
    if (options.body !== undefined && !(options.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }

    const token = this.accessTokenProvider?.();
    if (token && options.auth !== false) {
      headers.set("Authorization", `Bearer ${token}`);
    }

    return headers;
  }

  private buildBody(body: unknown): BodyInit | undefined {
    if (body === undefined) {
      return undefined;
    }
    if (body instanceof FormData) {
      return body;
    }
    return JSON.stringify(body);
  }

  private async readPayload(response: Response): Promise<unknown> {
    if (response.status === 204) {
      return null;
    }

    const text = await response.text();
    if (!text) {
      return null;
    }

    const contentType = response.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      return JSON.parse(text);
    }

    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  }

  private errorMessage(payload: unknown, response: Response): string {
    if (isErrorPayload(payload) && typeof payload.detail === "string") {
      return payload.detail;
    }
    return response.statusText || "API request failed";
  }
}

function isErrorPayload(value: unknown): value is { detail: unknown } {
  return typeof value === "object" && value !== null && "detail" in value;
}

export const apiClient = new ApiClient();
