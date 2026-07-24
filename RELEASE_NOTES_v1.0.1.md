# OMIP Foundation v1.0.1

## Overview

OMIP Foundation v1.0.1 is a maintenance release that improves the first public Foundation release.

This version primarily enhances Docker deployment reliability and Windows compatibility.

---

## Highlights

### Docker

- Default host port changed from **8000** to **18080**
- Improved Windows / WSL / Hyper-V compatibility

### Documentation

Updated:

- README
- QUICK_START
- TROUBLESHOOTING

---

## Fixed

- Docker port conflict on Windows
- Deployment documentation improvements

---

## Upgrade

Existing users can simply:

```bash
git pull
docker compose down
docker compose up -d --build