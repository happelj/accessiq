# AccessIQ SCIM Implementation

AccessIQ implements a focused SCIM 2.0 surface for enterprise identity provider integration. The implementation is isolated under `app/scim` and delegates durable mutations to reusable services under `app/services`.

## Supported Endpoints

| Endpoint | Status |
| --- | --- |
| `GET /scim/v2/ServiceProviderConfig` | Implemented |
| `GET /scim/v2/ResourceTypes` | Implemented |
| `GET /scim/v2/Schemas` | Implemented |
| `GET /scim/v2/Users` | Implemented |
| `GET /scim/v2/Users/{id}` | Implemented |
| `POST /scim/v2/Users` | Implemented |
| `PUT /scim/v2/Users/{id}` | Implemented |
| `PATCH /scim/v2/Users/{id}` | Implemented |
| `GET /scim/v2/Groups` | Implemented |
| `GET /scim/v2/Groups/{id}` | Implemented |
| `POST /scim/v2/Groups` | Implemented |
| `PUT /scim/v2/Groups/{id}` | Implemented |
| `PATCH /scim/v2/Groups/{id}` | Implemented |

`DELETE /Users` and `DELETE /Groups` are not implemented. User deactivation is represented by `active=false`.

## Authentication And Authorization

SCIM endpoints reuse AccessIQ JWT authentication and API RBAC.

Allowed roles:

- `security_admin`
- `iam_admin`

Unauthorized and forbidden SCIM requests return SCIM-shaped `401` and `403` responses with `application/scim+json`.

## User Resources

Core SCIM User attributes:

- `id`
- `userName`
- `name.formatted`
- `displayName`
- `active`
- `emails`
- `meta.resourceType`
- `meta.location`

`userName` maps to AccessIQ `User.email`. `displayName` maps to `User.name`. `active` maps to the soft-active flag.

## Enterprise User Extension

AccessIQ supports the RFC 7643 Enterprise User Extension:

```text
urn:ietf:params:scim:schemas:extension:enterprise:2.0:User
```

Enterprise data is stored in `EnterpriseUserProfile`, not in a JSON blob.

Supported attributes:

- `employeeNumber`
- `department`
- `division`
- `organization`
- `costCenter`
- `manager`

Example:

```json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User",
    "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"
  ],
  "userName": "casey@example.com",
  "displayName": "Casey Morgan",
  "active": true,
  "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User": {
    "employeeNumber": "E-1001",
    "department": "Engineering",
    "division": "Platform",
    "organization": "AccessIQ",
    "costCenter": "ENG-001",
    "manager": {
      "value": "6"
    }
  }
}
```

Manager responses include:

```json
{
  "value": "6",
  "$ref": "http://localhost:8000/scim/v2/Users/6",
  "displayName": "Maya Patel"
}
```

Validation:

- managers must reference existing users
- users cannot manage themselves
- manager cycles are rejected
- `employeeNumber` is unique when present
- invalid enterprise payloads return SCIM `400`
- duplicate employee numbers return SCIM `409` with `scimType: uniqueness`

## User Provisioning

`POST /Users` creates a user and optional enterprise profile.

`PUT /Users/{id}` replaces mutable core attributes and replaces Enterprise User Extension attributes. If the Enterprise User extension is omitted from a PUT request, existing enterprise profile fields are cleared.

`PATCH /Users/{id}` supports `add`, `replace`, and `remove` for:

- `userName`
- `displayName`
- `active`
- `employeeNumber`
- `department`
- `division`
- `organization`
- `costCenter`
- `manager`

Enterprise PATCH paths can be simple:

```json
{
  "op": "replace",
  "path": "department",
  "value": "Finance"
}
```

Or schema-qualified:

```json
{
  "op": "replace",
  "path": "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User:department",
  "value": "Finance"
}
```

## Group Resources

Groups are stored in normalized `Group` and `GroupMember` tables.

Supported attributes:

- `id`
- `displayName`
- `members`
- `meta.resourceType`
- `meta.location`
- `meta.lastModified`

Members reference existing AccessIQ users by SCIM User id.

## Group Provisioning

`POST /Groups` creates a group.

`PUT /Groups/{id}` replaces displayName and the membership set.

`PATCH /Groups/{id}` supports:

- `displayName`
- `members`
- `members[value eq "123"]`

Duplicate group names return SCIM `409` with `scimType: uniqueness`.

## Filtering

User filters:

- `userName eq "alice@example.com"`
- `id eq "123"`
- `displayName co "Alice"`
- `active eq true`
- `active eq false`

Group filters:

- `displayName eq "Admins"`
- `id eq "123"`
- `displayName co "Admin"`

Unsupported or malformed filters return SCIM `400` with `scimType: invalidFilter`.

## Sorting

User sort fields:

- `id`
- `userName`
- `displayName`

Group sort fields:

- `id`
- `displayName`

Supported sort orders:

- `ascending`
- `descending`

Unsupported sort fields return SCIM `400` with `scimType: invalidPath`.

## Pagination

SCIM list endpoints support:

- `startIndex`: 1-based start index, default `1`
- `count`: max resources returned, default `100`

Out-of-range pages return an empty `Resources` array and preserve the requested `startIndex`.

## Projection

SCIM list and resource endpoints support:

- `attributes`
- `excludedAttributes`

Required identity fields `schemas` and `id` are preserved.

## Audit And Transactions

SCIM provisioning writes audit events in the same transaction as database changes. Audit failures roll back provisioning changes.

Audit entitlements:

- `SCIM User Lifecycle`
- `SCIM Enterprise User Extension`
- `SCIM Group Lifecycle`

## Domain Events

Successful commits publish in-process domain events for future integration points. Events are not delivered asynchronously yet.

Enterprise events include:

- `EnterpriseProfileCreated`
- `EnterpriseProfileUpdated`
- `ManagerChanged`
- `DepartmentChanged`
- `OrganizationChanged`
- `CostCenterChanged`
- `DivisionChanged`
- `EmployeeNumberChanged`

## Roadmap

Planned future work:

- connector framework and downstream app delivery
- access reviews and remediation
- dedicated SCIM bearer token management
- AI explanations using deterministic audit and policy context
- optional SCIM DELETE support
