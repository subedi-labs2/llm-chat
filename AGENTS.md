# Agent guidelines

- Prefer small, readable changes and existing project patterns. Keep API, presentation, and configuration concerns separate.
- Backend code belongs in `api/src`; use typed async endpoints, Pydantic models at system boundaries, and settings from the environment. Add pytest coverage for behavior changes.
- Frontend code belongs in `web/src`; use strict TypeScript, functional components, hooks, and shadcn/ui primitives. Keep HTTP access in `src/lib` and test user-visible behavior when test tooling is introduced.
- Keep product-safety integrations behind clear API boundaries: recall data clients live in `api/src/recalls`, and the Pydantic AI agent and chat endpoint live in `api/src/chat`. Recall facts must come from tool results, not model memory. Do not add a database, authentication, additional AI services, or new state management without a concrete requirement.
- Manage Python dependencies with `uv` and JavaScript dependencies with npm. Commit both lockfiles and justify every new runtime dependency.
- Before handing off, run the affected lint, format, type, test, and build checks. Update documentation when commands or architecture change.
