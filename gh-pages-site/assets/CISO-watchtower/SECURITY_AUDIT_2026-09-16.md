# CISO Watchtower Security Audit

Date: 2026-09-16

## Executive summary

The application builds and its 35 tests pass, but it should not be considered production-hardened. The main risks are integrity compromise of the news pipeline, untrusted CI/CD automation with powerful credentials, and non-reproducible artifacts. Two directly used runtime dependencies have known vulnerabilities: Flask 3.1.1 and aiohttp 3.12.15.

The highest-risk end-to-end paths are:

1. Any GitHub user able to comment on a pull request can trigger the `/forge` workflow. The workflow has repository write permission and passes a long-lived GCP service-account key to a tag-pinned third-party action. There is no actor or author-association check.
2. Merely setting `HTTPS_PROXY` disables all certificate and hostname verification for processor traffic. A network or proxy-path attacker can alter feeds, which are persisted in BigQuery and rendered as trusted security intelligence.
3. Feed-controlled URLs are fetched server-side without destination validation and later assigned to browser `href` and image properties without a scheme allowlist. Feed or source-registry compromise can therefore become SSRF, internal-service discovery, phishing, client tracking, or active `javascript:` links.

## Scope and limitations

Reviewed:

- Both Dockerfiles and Docker build contexts
- Python and Node dependency declarations and resolved container packages
- Six workflows under `.github/workflows`
- Flask web application, browser code, asynchronous feed processor, and tests
- Local builds and a local runtime deployment
- The Cloud Run URL published in the README

Not available in this workspace:

- Terraform, Helm, Cloud Run service definitions, IAM policies, VPC/egress policy, BigQuery ACLs, scheduler configuration, or organization policies
- Access to GCP, JFrog, GitHub repository settings, action source code, or the custom `cloud` runner
- Existing remote image manifests, SBOMs, attestations, signatures, and registry scan results

The repository therefore does not provide enough IaC to verify least privilege, ingress authentication, service-account separation, metadata protection, egress controls, or production resource limits. The published Cloud Run URL returned HTTP 404 for `/`, `/api/items`, and `/api/categories` at audit time, so the production revision could not be compared to the local artifact.

## Findings

### F-01: Forge revision can be triggered without an authorization check - Critical

Evidence: `.github/workflows/forge-revise.yml:1-22`

The `issue_comment` event runs when a comment starts with `/forge`. It does not constrain `github.actor`, `author_association`, repository membership, or a trusted team. The job receives `contents: write`, `pull-requests: write`, `GITHUB_TOKEN`, and `GCP_SERVICE_ACCOUNT_JSON` through `ccfc/ops-factory/actions/forge@v1`.

Attack path: untrusted comment -> privileged AI/action invocation -> prompt or action abuse -> repository modification, pull-request manipulation, credential exposure, or GCP access.

Remediation:

- Require `MEMBER`, `OWNER`, or `COLLABORATOR` author association and an explicit environment approval.
- Remove GCP credentials where not strictly needed and replace service-account JSON with GitHub OIDC/Workload Identity Federation.
- Pin the action to a reviewed full commit SHA.
- Give each mode a dedicated, minimal service account and token permission set.

### F-02: TLS verification is disabled whenever HTTPS_PROXY exists - High

Evidence: `news_processor/news_processor.py:25-35`, `.env.example:5-7`

The built image was tested with `HTTPS_PROXY` set and returned `check_hostname=False` and `verify_mode == CERT_NONE`. `NO_PROXY=metadata.google.internal` does not repair TLS integrity for external feeds.

Attack path: proxy-path interception -> modified RSS/Atom response -> poisoned titles, summaries, links, and image URLs -> persistent misinformation or malicious links in the dashboard.

Remediation: install the corporate root CA in the image and keep `CERT_REQUIRED` plus hostname verification enabled. Fail closed if the trust chain cannot be established.

### F-03: Unrestricted server-side URL fetching and redirects - High

Evidence: `news_processor/news_processor.py:225-240`, `news_processor/image_utils.py:14-27`

Source URIs from BigQuery and article links from external feeds are fetched without a scheme, host, resolved-IP, or redirect-target allowlist. The client also honors proxy environment variables. An attacker controlling a feed can make the processor request an article URL on an internal address; a principal with write access to the source table can directly target internal endpoints and return parseable content.

Attack path: malicious feed or BigQuery write -> URL to loopback, RFC1918, link-local, metadata, or internal DNS -> processor request -> internal discovery or content propagated through parsed feed/image metadata.

Remediation: allow only HTTPS, resolve and reject non-public IP ranges on every redirect, restrict ports, cap response size, disable automatic decompression where appropriate, and enforce Cloud Run egress/firewall policy. Protect the source table with a separate narrow writer role.

### F-04: Known exploitable dependency vulnerabilities - High

Evidence: `webapp/requirements.txt:1`, `news_processor/requirements.txt:1`

`pip-audit` found:

| Component | Installed | Finding | Minimum remediation observed |
|---|---:|---|---:|
| Flask | 3.1.1 | PYSEC-2026-2151 | 3.1.3 |
| aiohttp | 3.12.15 | 64 advisory records reported; relevant client risks include response decompression bombs, malformed-response DoS, redirect credential handling, and TLS/SNI validation defects | 3.14.3 |

Trivy 0.67.2 independently identified two High findings in aiohttp:

- CVE-2025-69223: `auto_decompress` zip bomb; fixed in 3.13.3
- CVE-2026-69244: malformed HTTP response DoS; fixed in 3.14.3

These are reachable because the processor consumes attacker-influenced HTTP responses and enables automatic decompression by default.

Remediation: update Flask to at least 3.1.3 and aiohttp to at least 3.14.3, run tests, rebuild, and rescan the resulting images.

### F-05: CI actions and deployment artifacts are not immutably pinned - High

Evidence: all workflow `uses:` entries; both CI/CD workflows; both Dockerfiles

Actions use mutable major tags such as `@v1`, `@v2`, and `@v4`. Base images use mutable tags. Deployments select a mutable image tag rather than a digest. There is no signature, SBOM, provenance attestation, admission policy, or post-push scan.

The build also marks PyPI hosts as trusted, weakening TLS verification during package installation. The Tailwind stage does not copy `package.json` or `package-lock.json`; it runs an unconstrained `npm install`. Although the repository declares `^4.1.18`, the audited build resolved Tailwind and its CLI to 4.3.3.

Attack path: compromised action/tag, registry account, package release, DNS/proxy path, or mutable tag -> altered image -> automatic Cloud Run deployment with no integrity gate.

Remediation: SHA-pin actions and digest-pin base/deployed images, remove `--trusted-host`, build with lockfiles (`npm ci`, Python hashes), generate CycloneDX/SPDX SBOMs and SLSA provenance, sign with keyless cosign, and verify signatures before deployment.

### F-06: Pull requests execute builds on a credentialed custom runner - High

Evidence: `.github/workflows/pr-build-test.yml:1-67`

Pull-request code, including Dockerfiles and package install scripts, is built on the custom `cloud` runner. The build action receives Artifactory credentials. No fork policy, ephemeral-runner guarantee, environment approval, or runner isolation is visible. The workflow called "Build Test" does not execute the 35 application tests.

Attack path: malicious PR -> attacker-controlled build instructions on shared runner -> runner/cache/network abuse and potential theft of credentials available to the action or persistent workspace.

Remediation: use ephemeral isolated runners for untrusted builds, never expose secrets to forked or unapproved PR jobs, split uncredentialed build/test from approved publish, and add explicit pytest and security gates.

### F-07: Feed-controlled links lack a browser URL-scheme allowlist - High

Evidence: `webapp/static/js/script.js:544-566`, `webapp/static/js/script.js:640-660`, `webapp/static/js/script.js:813-846`

Text is generally assigned safely with `textContent`, but feed-controlled `item.link` is assigned directly to anchor `href`. Values such as `javascript:` or deceptive non-HTTP schemes are not rejected. Image URLs are also loaded directly, enabling third-party tracking of every dashboard client. The absence of Content Security Policy increases impact.

Attack path: feed poisoning -> stored malicious link -> dashboard user click -> phishing or script-capable navigation in the application origin, depending on browser behavior.

Remediation: accept only `https:` URLs using a shared parser/validator before persistence and again before DOM assignment. Proxy approved images through a controlled fetch/cache layer or disable arbitrary images. Add a restrictive CSP.

### F-08: Public endpoints have no application-layer access or abuse controls - Medium

Evidence: `webapp/app.py:71-145`

The dashboard and APIs have no authentication, authorization, application rate limiting, or explicit cache policy. `/api/items` may include the `internal` source category. Repeated cache-miss traffic can generate BigQuery work. Whether public access is intended and whether Cloud Armor/IAP protects the service cannot be determined from the repository.

Remediation: classify the data, require IAP or Cloud Run IAM if internal, enforce rate/quota controls at the edge, use a dedicated read-only BigQuery service account, and set explicit cache headers.

### F-09: Internal exception details are returned to clients - Medium

Evidence: `webapp/app.py:103-112`, `webapp/app.py:134-143`

The local deployment returned the complete Google authentication exception from `/api/items`. Production errors can disclose project, dataset, query, credential, or upstream details.

Remediation: return a stable generic error and correlation ID; keep full details only in access-controlled logs.

### F-10: Browser hardening headers are absent - Medium

The local response only contained Gunicorn's basic headers. It lacked Content-Security-Policy, frame protection, `X-Content-Type-Options`, Referrer-Policy, Permissions-Policy, and an application HSTS policy. The page permits Google Fonts and favicons, which must be reflected in a deliberate CSP or self-hosted.

Remediation: apply headers in Flask or, preferably, at the trusted edge and add regression tests.

### F-11: Deployment configuration is incomplete and preserves unknown state - Medium

Evidence: `.github/workflows/webapp-ci-cd.yml:52-63`, `.github/workflows/news-processor-ci-cd.yml:52-63`

The workflows only update image, region, and project. They do not declare ingress, authentication, runtime service account, egress connector, environment variables, secret mounts, resource limits, concurrency, timeout, scaling, Binary Authorization, or deletion protection. The news job must already exist, so its security posture is entirely external to version control.

Remediation: manage Cloud Run, scheduler, BigQuery, IAM, network, secrets, and policies as reviewed IaC. Detect drift in CI.

### F-12: Dataset creation grants the processor excessive control - Medium

Evidence: `news_processor/news_processor.py:61-108`

At runtime the processor creates datasets and tables and seeds source configuration. Its identity therefore needs broader BigQuery permissions than normal ingestion requires. Compromise of the SSRF-facing processor has a larger blast radius.

Remediation: provision schema through IaC/migrations and run the processor with only dataset-level read/update/insert permissions required for normal operation.

## Verified component inventory

| Artifact | Verified runtime/build components |
|---|---|
| Webapp image `sha256:91632a6...` | Debian 12.15, Python 3.11.16, Flask 3.1.1, Gunicorn 23.0.0, google-cloud-bigquery 3.38.0, cachetools 5.5.2 |
| Processor image `sha256:1e28b9d...` | Debian 12.15, Python 3.11.16, aiohttp 3.12.15, Beautiful Soup 4.13.4, feedparser 6.0.12, google-cloud-bigquery 3.38.0 |
| Tailwind stage `sha256:9dc4fde...` | Node 20.20.2, npm 10.8.2, Tailwind CSS/CLI 4.3.3 |

Both runtime images execute as UID/GID 10001. Trivy reported no fixable High/Critical Debian findings and no High/Critical Python findings in the webapp image using its vulnerability database. `npm audit` reported zero findings for the resolved Tailwind stage. These clean results do not offset the Flask advisory found by `pip-audit` or the integrity gaps in the build process.

## Validation record

- `docker build --pull` succeeded for both production Dockerfiles.
- Local Gunicorn deployment returned HTTP 200 for `/` on port 18080.
- Unauthenticated `/api/items` reached application logic and returned a detailed credential error because the audit container intentionally had no GCP credentials.
- TLS verification disablement was reproduced inside the processor image.
- `pytest -q`: 35 passed.
- `npm audit`: 0 vulnerabilities in the resolved Tailwind stage.
- Trivy 0.67.2 image scan: two High aiohttp findings; no fixable High/Critical OS findings.
- Trivy repository scan: no committed secret or Dockerfile misconfiguration finding at Medium or above. GitHub Actions were not recognized as configuration targets by this scan.
- Bandit findings included dynamic SQL construction. The table and dataset identifiers come from environment variables; validate them against strict GCP identifier patterns, but this is a post-deployment configuration injection risk rather than a direct public SQL injection.
- Bandit's MD5 warning is not treated as a security finding here because the hash is used for deduplication, not authentication or integrity.

## Prioritized remediation plan

Within 24 hours:

1. Disable or authorization-gate Forge workflows; rotate the GCP JSON key and migrate to OIDC.
2. Restore TLS verification by installing the corporate CA.
3. Upgrade aiohttp to 3.14.3 or newer and Flask to 3.1.3 or newer.
4. Restrict source and article URLs to validated HTTPS destinations and block internal/link-local ranges after every resolution and redirect.

Within one sprint:

1. Move deployment resources and IAM into IaC with separate least-privilege runtime and deploy identities.
2. Split untrusted PR tests from credentialed publication and use ephemeral runners.
3. Add tests, SAST, dependency audit, image scan, secret scan, SBOM, provenance, signing, and digest verification as required CI gates.
4. Add URL scheme validation, generic API errors, security headers, and explicit edge authentication/rate limits.
5. Pin all actions, base images, Python transitive dependencies, and Node dependencies immutably.