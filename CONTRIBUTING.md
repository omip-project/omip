# CONTRIBUTING.md

# Contributing to OMIP

Thank you for contributing to the Open Mission Intelligence Platform (OMIP).

## Development Workflow

1. Fork the repository.
2. Create a feature branch.

```bash
git checkout -b feature/short-description
```

3. Implement and test your changes.
4. Commit using descriptive commit messages.
5. Push your branch.
6. Open a Pull Request.

## Branch Naming

- feature/<name>
- fix/<name>
- docs/<name>
- refactor/<name>

## Commit Message Convention

Examples:

```text
Foundation: complete Docker runtime environment
Foundation: fix MQTT compatibility with Paho 2.x
Core: add Vehicle aggregate
Mission: implement mission lifecycle
Docs: update Quick Start Guide
```

## Coding Standards

- Python 3.12+
- Black formatting
- Type hints encouraged
- Small, focused commits
- Keep public APIs documented

## Pull Request Checklist

- [ ] Builds successfully
- [ ] Tests pass
- [ ] Documentation updated
- [ ] No secrets or .env committed
- [ ] Docker deployment verified
- [ ] Quick Start still works

## Reporting Issues

Please include:

- OMIP version
- Operating system
- Python version
- Docker version
- Steps to reproduce
- Logs/screenshots if applicable
