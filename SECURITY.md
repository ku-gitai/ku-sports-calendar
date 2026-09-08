# Security

This repository is designed to require **no personal API keys, passwords, personal access tokens, SSH keys, or other long-lived credentials**.

## Credential rules

- Do not commit `.env` files, private keys, tokens, passwords, cookies, browser exports, or cloud/service-account credentials.
- Do not add a personal GitHub access token to the repository or workflow files. The workflows use GitHub's short-lived, repository-scoped `GITHUB_TOKEN` automatically.
- Keep the repository's default workflow token permission read-only. The prepared workflows elevate only the isolated commit job to `contents: write`.
- GitHub Actions dependencies are pinned to full commit SHAs. Update those pins deliberately; Dependabot is configured to propose updates.
- Runtime Python dependencies are version-pinned. Do not change them to unbounded ranges in the scheduled workflow without review.

If a real credential is ever committed, deleting the file in a later commit is not sufficient. Revoke/rotate the credential immediately and remove it from Git history before continuing to use the repository.
