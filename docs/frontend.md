# Frontend Architecture

Milestone 13A adds a React admin portal under `frontend/`. The portal is a Vite, React, and TypeScript application that consumes the existing FastAPI backend without duplicating backend business logic.

## Stack

- React functional components
- TypeScript with strict compiler settings
- Vite for local development and production builds
- React Router for authenticated routes
- TanStack Query for server state, caching, and loading/error states
- Browser `localStorage` for the current development JWT session

## Routing

The app uses a protected route shell:

```text
/login
  -> public login form

ProtectedRoute
  -> AppLayout
     -> /dashboard
     -> /users
     -> /applications
     -> /groups
     -> /access
     -> /scim
     -> /connectors
     -> /provisioning-jobs
     -> /access-reviews
     -> /remediation
     -> /authorization-graph
     -> /ai-assistant
     -> /settings
```

`/unauthorized` and the catch-all 404 page are available as error destinations.

## Authentication

`AuthProvider` owns login, logout, session restore, and the token refresh placeholder. Login calls the backend `POST /login` endpoint, stores the returned JWT and expiration in `localStorage`, decodes the JWT `sub` claim, and loads the current user through `GET /users/{id}`.

The backend does not currently expose a refresh-token endpoint, so `refreshAccessToken()` intentionally returns `false`. The API client is already structured to support a refresh endpoint later without changing page components.

## API Layer

Page components do not call `fetch()` directly. Backend access is centralized in:

- `frontend/src/services/apiClient.ts`: base URL, headers, JSON handling, bearer token injection, typed API errors, and unauthorized handling.
- `frontend/src/services/accessiq.ts`: endpoint-specific functions for users, applications, SCIM groups, connectors, provisioning jobs, access reviews, remediation, authorization graph, and AI explanations.
- `frontend/src/types/api.ts`: TypeScript response models aligned to the FastAPI schemas.

The API base URL is configured through `VITE_API_BASE_URL`, defaulting to `http://localhost:8000`.

## Component Organization

Reusable UI is under `frontend/src/components/`:

- `Card`
- `DataTable`
- `Badge`
- `StatusChip`
- `LoadingSpinner`
- `EmptyState`
- `ErrorPanel`
- `SearchBox`
- `Pagination`
- `StatCard`
- `PageHeader`
- `ErrorBoundary`

Layouts live under `frontend/src/layouts/`, context under `frontend/src/contexts/`, and API/config/format helpers under `frontend/src/services/`, `frontend/src/config/`, and `frontend/src/utils/`.

## Backend Integration

The portal calls existing endpoints where practical:

- Dashboard: health, users, groups, applications, connectors, provisioning jobs, campaigns, AI providers
- Users: `GET /users`
- Applications: `GET /applications`, `GET /applications/{id}/entitlements`
- Groups: `GET /scim/v2/Groups`
- Access: `GET /users/{id}/access`
- SCIM: metadata endpoints
- Connectors: connector list and health
- Provisioning Jobs: jobs and history
- Access Reviews: campaigns
- Remediation: remediation jobs
- Authorization Graph: cache status and JSON export
- AI Assistant: `GET /ai/providers`, `POST /ai/explain`

Some pages are read-only foundations because backend write workflows already exist as APIs but have not yet been designed as full UI workflows.

## Docker

`docker-compose.yml` includes a `frontend` service using `node:22-alpine`. It runs Vite on port `5173` and sets `VITE_API_BASE_URL=http://localhost:8000` by default.

The API service also accepts:

- `CORS_ALLOWED_ORIGINS`
- `CORS_ALLOW_CREDENTIALS`

The default CORS origins include the Vite dev server.

## Testing

Frontend tests use Vitest, Testing Library, and jsdom. Current coverage validates:

- API client bearer token injection, JSON serialization, and typed error handling
- Authentication login/session behavior
- Protected-route redirect behavior
- Reusable table rendering and empty states

## Future Roadmap

- Add create/edit workflows for users, campaigns, delegations, access grants, and remediation actions.
- Add token refresh once the backend exposes a refresh endpoint.
- Generate API types from OpenAPI when the backend schema stabilizes.
- Add role-aware navigation and per-route authorization screens.
- Add graph visualization once the graph export UX is designed.
- Add streaming AI responses if backend provider support is added.
