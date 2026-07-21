# Contributing to OMIP

OMIP is currently establishing its open-source Foundation. Contributions should
remain focused, testable and consistent with the project architecture.

## Development workflow

1. Create or select an Issue.
2. Create a branch from `develop`.
3. Make one focused change.
4. Add or update tests.
5. Update documentation when behaviour changes.
6. Open a Pull Request.
7. Merge only after required checks pass.

## Branch names

```text
feature/<short-description>
fix/<short-description>
docs/<short-description>
research/<short-description>
release/<version>
```

Examples:

```text
feature/python-sdk
fix/mission-selection
docs/docker-quick-start
research/cause-field-prototype
```

## Commit messages

Use concise imperative messages:

```text
Add vehicle profile validation
Fix mission export pagination
Document local MQTT deployment
```

Avoid vague messages such as:

```text
update
changes
fix stuff
```

## Pull Requests

A Pull Request should explain:

- what changed;
- why it changed;
- how it was tested;
- whether APIs or schemas changed;
- whether screenshots are relevant;
- any remaining limitations.

## Testing

Run the test suite before opening a Pull Request:

```powershell
.\scripts\run_tests.cmd
```

## Research code

Experimental research code should be clearly labelled and must not weaken
stable platform contracts. Research functions must not be presented as
certified safety or production control systems.
