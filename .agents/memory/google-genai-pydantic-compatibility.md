---
name: Google GenAI and Pydantic compatibility
description: Version constraint when installing the Google GenAI SDK without changing the application's Pydantic runtime.
---

Keep the existing Pydantic 2.9.2 pin unless a Pydantic upgrade is explicitly approved. Google GenAI 2.27.0 requires Pydantic 2.12.5 or newer, so it cannot resolve with the current pin. Select a compatible SDK release instead of forcing an install or changing Pydantic during an environment-only setup.

**Why:** The user requested that the Phase 6 application architecture remain unchanged, and upgrading a core validation dependency is broader than installing the runtime SDK.

**How to apply:** When updating Google GenAI, resolve its version against the current Pydantic constraint first. If a newer SDK requires a Pydantic upgrade, evaluate that separately and get approval before changing the pin.