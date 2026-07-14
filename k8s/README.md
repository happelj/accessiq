# Kubernetes Manifests

Helm is the primary Kubernetes deployment mechanism for AccessIQ.

Use:

```bash
helm template accessiq helm/accessiq -f helm/accessiq/values-dev.yaml
```

to render raw manifests when you need to inspect or pipe them to Kubernetes tooling.

This directory is reserved for future hand-authored Kubernetes examples that cannot be represented cleanly in Helm values. Do not duplicate the Helm chart here.

