# CI/CD Quality Gates

Milestone 13B adds continuous integration for AccessIQ. The pipeline validates backend quality, frontend quality, test suites, dependency security, and Docker image builds on every pull request and every push to `main`.

This milestone does not deploy infrastructure, publish container images, or require cloud credentials.

## Workflow Architecture

The workflow lives at `.github/workflows/ci.yml` and runs four jobs:

1. `backend-quality`: Python dependency install, Ruff linting, Black format check, MyPy type checking, and the full backend pytest suite against PostgreSQL.
2. `frontend-quality`: Node dependency install, ESLint, Prettier format check, TypeScript validation, Vitest, and Vite production build.
3. `docker-build`: backend Docker image build and frontend Docker image build. Images are local to the CI runner and are not pushed.
4. `kubernetes-quality`: Helm linting, dev/prod manifest rendering, and kubectl client-side dry-run validation against a disposable kind cluster.
5. `dependency-security`: Python dependency audit through `pip-audit` and JavaScript dependency audit through `npm audit`.

The workflow triggers on:

- `pull_request`
- `push` to `main`

The workflow uses read-only repository permissions and does not require secrets for normal execution.

## Pipeline Stages

The effective quality gate is:

```text
Checkout
  -> Set up Python and Node
  -> Install backend dependencies
  -> Install frontend dependencies
  -> Lint
  -> Format check
  -> Type checking
  -> Backend tests
  -> Frontend tests
  -> Frontend production build
  -> Docker build validation
  -> Kubernetes manifest validation
  -> Dependency security scan
  -> Success
```

Backend tests run with a PostgreSQL service container to match local Docker development more closely than SQLite.

## Local Developer Workflow

Backend quality:

```bash
python -m pip install -r requirements-dev.txt
ruff check app tests
black --check app tests
mypy
pytest -vv
bash scripts/python-dependency-audit.sh
```

Frontend quality:

```bash
cd frontend
npm ci
npm run lint
npm run format:check
npm run typecheck
npm test
npm run build
npm audit --audit-level=moderate
```

Docker validation:

```bash
docker build -t accessiq-api:ci .
docker build -t accessiq-frontend:ci frontend
```

Kubernetes validation:

```bash
helm lint helm/accessiq
helm template accessiq helm/accessiq -f helm/accessiq/values-dev.yaml
helm template accessiq helm/accessiq -f helm/accessiq/values-dev.yaml | kubectl apply --dry-run=client -f -
```

## Tooling

Python tools are configured in `pyproject.toml`:

- Ruff for focused linting
- Black for Python formatting
- MyPy for pragmatic application type checking
- pip-audit for dependency vulnerability scanning

Frontend tools are configured under `frontend/`:

- ESLint flat config in `frontend/eslint.config.js`
- Prettier config in `frontend/.prettierrc.json`
- TypeScript config in `frontend/tsconfig.json`
- npm scripts in `frontend/package.json`

## Security Scanning

`scripts/python-dependency-audit.sh` runs `pip-audit` in strict mode with bounded retries for transient PyPI connectivity failures. Known Python dependency vulnerabilities still fail the workflow. `npm audit --audit-level=moderate` fails the workflow for moderate, high, or critical JavaScript dependency findings.

When a scan fails:

1. Read the advisory and affected package.
2. Prefer a direct package upgrade when possible.
3. If the vulnerable package is transitive, update the parent dependency or regenerate the lockfile.
4. Avoid bypassing the scan unless there is a documented false positive and a follow-up issue.

## Artifacts

The backend job uploads the pytest JUnit report as `backend-pytest-report`. The workflow does not upload frontend build output or Docker layers because this milestone validates quality only and does not publish release artifacts.

## Branch Protection Recommendations

For `main`, enable branch protection with:

- Require pull request before merging
- Require status checks to pass before merging
- Require the CI workflow jobs: backend quality, frontend quality, Docker build validation, Kubernetes and Helm validation, and dependency security
- Require branches to be up to date before merging
- Restrict force pushes

## Troubleshooting

- Ruff failures usually mean lint errors need to be fixed. Run `ruff check app tests --fix` only when the change is mechanical and review the diff.
- Black failures mean formatting differs. Run `black app tests`.
- MyPy failures usually indicate missing or inconsistent annotations in application code.
- Frontend lint failures should be fixed in source rather than suppressed unless the rule is not appropriate for AccessIQ.
- Docker build failures often come from missing files in `.dockerignore`, dependency install failures, or frontend build-time environment assumptions.
- Security scan failures should be handled by upgrading dependencies or documenting an unavoidable temporary exception.

## Future Deployment Roadmap

Future milestones can add:

- Container image publishing to a registry
- Release tagging
- Staging deployment
- Kubernetes manifests or Helm charts
- AWS infrastructure deployment
- Environment-specific smoke tests

Those deployment stages should build on this quality gate rather than replacing it.
