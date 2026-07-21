# Security Policy

OMIP is currently an early research and community preview.

## Reporting a vulnerability

Do not disclose suspected security vulnerabilities in a public GitHub Issue.

Until a dedicated project security address is established, repository owners
should configure GitHub Private Vulnerability Reporting under:

```text
Repository Settings → Security → Code security and analysis
```

Reports should include:

- affected component and version;
- reproduction steps;
- potential impact;
- suggested mitigation, when available.

## Current security boundary

The local development configuration may use permissive CORS, anonymous MQTT,
development servers and local SQLite storage. These defaults are not suitable
for direct public Internet exposure.

Public deployment requires, at minimum:

- HTTPS and WSS;
- authenticated MQTT over TLS;
- topic-level MQTT ACLs;
- protected API access;
- secrets outside source control;
- restricted CORS;
- backup and recovery procedures;
- dependency and container scanning.
