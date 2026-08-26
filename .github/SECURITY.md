# Security Policy

## Supported version

Security fixes are applied to the latest commit on `main`. Older commits and
local modifications are not maintained as separate supported releases.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting feature from the
repository **Security** tab. Do not open a public issue for an unpatched
vulnerability and do not include API keys, tokens, personal data, database
files, or uploaded user content in a report.

Include the affected component, reproduction steps, impact, and any suggested
mitigation. The maintainer will acknowledge the report and coordinate a fix
and disclosure timeline through the private advisory.

## Secrets and local data

Use `backend/.env.example` as the configuration template. Real `.env` files,
`backend/fiona.db`, `backend/uploads/`, backups, logs, and
`desktop/fiona.config.json` must remain local and must never be committed.
