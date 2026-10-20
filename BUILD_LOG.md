# Build log

This mirror starts at the open-core split, so its git history is short. This
log records how the backend got here, from the private repository's history.
Dates are commits to `main`.

## 2025: the app
- **2025-03 to 2025-12**: FastAPI + SQLAlchemy social backend: posts, likes, reposts, quotes, drafts, follows, JWT auth.

## 2026: features
- **2026-03-28**: Laugh reactions, a configurable ranking feed, user settings, email verification, the first test suite.
- **2026-09-23**: The skins' backends (Chronicle, Amble, blog, widgets, trends), the admin console and content generators; posts split into a package; per-domain tests. Same day: widget execution locked down, blog HTML sanitized, Chronicle paging capped.

## 2026-09 to 2026-10: the DevOps roadmap
- **09-24**: Containerized: multi-service compose stack (Postgres + API + frontend) and DB bootstrap.
- **09-30**: GitHub Actions CI (lint, test, build); cross-repo end-to-end tests (full stack in compose, real browser).
- **10-01**: ruff (format + rule families added one at a time), mypy with a ratchet (262 type errors fixed), pre-commit in CI, Bandit, TruffleHog on commit, push and weekly, Dependabot. Replaced an unmaintained JWT library with a small module on PyJWT 2; migrated to pydantic 2 / FastAPI 0.142 / Starlette 1.7.
- **10-02**: Test suite 4x faster (parallel workers, bcrypt cost in tests), 95% coverage floor.
- **10-03**: Dependencies moved to `pyproject.toml` + `uv.lock` (uv).
- **10-05**: `/health` and `/health/live`; a code-quality pass against [CODE_QUALITY_RULES.md](CODE_QUALITY_RULES.md): response schemas on every endpoint, mirrored test files, no function over 50 lines.
- **10-07**: Multi-stage image, 811 MB to 617 MB compressed.
- **10-15**: AWS deployment as Terraform (ECS Fargate, ALB, Neon-or-RDS), planned but not applied; secrets audit and an SSM loader; GitHub OIDC deploy role (no stored AWS keys); Caddy with automatic TLS in front of the stack.
- **10-16**: Observability: Prometheus metrics, Loki logs, a Grafana dashboard and alert email, drilled on the real stack; tflint + Checkov; every Terraform stack's state in S3 with native locking.
- **10-18**: Continuous delivery: images published to ECR by commit SHA and deployed health-gated, with rollback.
- **10-19**: Feature flags (OpenFeature + flagd); SonarQube Cloud with a quality gate, then its findings cleared.
- **10-20**: Self-hosted SonarQube for comparison; a jscpd duplicate-code ratchet and deduplication down to 0.3%; free SAST/SCA (Semgrep, pip-audit, Grype; distroless frontend image); an on-demand AI code reviewer.
- **10-20**: The open-core split: the private parts moved behind one seam (`app/plugins.py`), a public baseline edition, and this mirror exported from an allowlist with leak and secret checks.
