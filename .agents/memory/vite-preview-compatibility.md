---
name: Vite preview compatibility
description: Replit preview compatibility details for the Vite version used by this project.
---

Vite 5.4's configuration typings do not include `server.allowedHosts`, even though newer Vite guidance commonly uses that option. The preview works with the dev server bound to `0.0.0.0`; keep the project on a compatible Vite configuration unless the Vite version is intentionally upgraded.

**Why:** The initial Phase 1 build failed at TypeScript validation when `allowedHosts` was added to the Vite 5.4 config.

**How to apply:** When changing the frontend dev-server configuration, validate against the installed Vite version before adding newer config properties.