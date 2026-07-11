# Security Policy

## Reporting A Vulnerability

Please report suspected vulnerabilities privately by emailing security@benchflow.ai.
Include the affected service, commit or version, reproduction steps, impact, and
any logs that do not contain credentials.

Do not open public issues for vulnerabilities involving credential exposure,
authorization bypass, container escape, or access to private task payloads.

## Scope

Security reports are in scope for:

- mock service APIs under `packages/environments/mock-*`
- local launcher and devhub control paths
- task image payload isolation under `/var/lib/task`
- Docker base image build scripts and runtime defaults
- fixture capture scripts that handle live provider credentials

Reports about downstream benchmark scoring policy are usually out of scope for
this repo unless they expose an env0 runtime vulnerability.

## Credential Hygiene

Do not commit OAuth tokens, API keys, real account exports, provider credential
files, or private customer data. Fixture captures must be reviewed and sanitized
before publication.

## Synthetic Security Fixtures

Some agent-safety tasks intentionally contain sensitive-looking values. These
must be unmistakably synthetic, use reserved/example identities where possible,
and authorize only localhost mock services.

The fixed RSA key at
`packages/environments/mock-auth/mock_auth/seed/keys/env-0-auth-key-001.pem`
is an intentional deterministic fixture. It signs fake JWTs for fake localhost
users and protects no external resource; the file carries the same warning in
its header.
