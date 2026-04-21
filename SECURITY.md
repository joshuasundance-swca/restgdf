# Security Policy

## Supported Versions

Only the latest minor release line of `restgdf` receives security updates.

| Version | Supported          |
| ------- | ------------------ |
| 2.x     | :white_check_mark: |
| 1.x     | :x:                |
| < 1.0   | :x:                |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues,
discussions, or pull requests.**

Report vulnerabilities privately via GitHub's
[private vulnerability reporting](https://github.com/joshuasundance-swca/restgdf/security/advisories/new)
feature.

You should receive an initial acknowledgement within **72 hours**. If the
issue is confirmed, we will work with you on a coordinated disclosure and
release a patch as quickly as is practical.

## Supply-chain integrity

`restgdf` releases are published to PyPI via
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (OIDC — no
long-lived API tokens) and every release artifact is signed with
[Sigstore](https://www.sigstore.dev/). The `.sigstore` bundles are attached to
the corresponding
[GitHub release](https://github.com/joshuasundance-swca/restgdf/releases) and
can be verified with the
[`sigstore` CLI](https://pypi.org/project/sigstore/):

```bash
python -m pip install sigstore
python -m sigstore verify identity \
  --cert-identity "https://github.com/joshuasundance-swca/restgdf/.github/workflows/publish_on_pypi.yml@refs/tags/<TAG>" \
  --cert-oidc-issuer "https://token.actions.githubusercontent.com" \
  <file>
```
