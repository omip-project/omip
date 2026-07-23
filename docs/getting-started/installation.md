# Installation

## Python environment

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install backend dependencies using the requirements file provided by the project.

## Documentation environment

```powershell
pip install -r requirements-docs.txt
```

Preview the documentation:

```powershell
mkdocs serve
```

Open:

```text
http://127.0.0.1:8000
```

!!! note
    If the OMIP backend is already using port 8000, run the documentation site
    on another port:

    ```powershell
    mkdocs serve -a 127.0.0.1:8001
    ```
