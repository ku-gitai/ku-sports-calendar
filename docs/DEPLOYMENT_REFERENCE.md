# Deployment Reference

This file records the intended end state so the repository is understandable without the original ChatGPT conversation. Actual setup should be performed interactively, one small step at a time, after the owner has a personal GitHub account.

Target deployment:

`KU Athletics -> Python updater -> docs/ku-football.ics -> personal GitHub repository -> GitHub Pages HTTPS -> iPhone Subscribed Calendar`

Required GitHub-side configuration, when the owner is ready:

1. Create a personal repository and place this repository's files on `main`.
2. Keep the repository default `GITHUB_TOKEN` permission read-only. The prepared workflows grant `contents: write` only to their isolated commit jobs; do not create or store a personal access token.
3. Require GitHub Actions to be pinned to full-length commit SHAs, then configure GitHub Pages to deploy from `main` / `/docs`.
4. Verify the public `.ics` URL loads over HTTPS.
5. Add that URL on iPhone as a **Subscribed Calendar**, then perform a controlled update test.

Do not use employer/business GitHub, domains, hosting, servers, accounts, or other work infrastructure.
