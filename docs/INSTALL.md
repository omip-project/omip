# OMIP Installation Guide

## Supported Platforms

- Windows 11
- Ubuntu 22.04+

## Install

1. Install Git.
2. Install Docker Desktop.
3. Install Python 3.12+.
4. Clone the repository.
5. Copy `.env.example` to `.env`.
6. Run:

```bash
docker compose up -d --build
```

## Health Check

```text
GET /api/v1/health
GET /api/v1/acquisition/status
```
