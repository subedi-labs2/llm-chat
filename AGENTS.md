# Agent guidelines

- Prefer small, readable changes and existing project patterns. Keep API, presentation, and configuration concerns separate.
- Backend code belongs in `api/src`; use typed async endpoints, Pydantic models at system boundaries, and settings from the environment. Add pytest coverage for behavior changes.
- Frontend code belongs in `web/src`; use strict TypeScript, functional components, hooks, and shadcn/ui primitives. Keep HTTP access in `src/lib` and test user-visible behavior when test tooling is introduced.
- Keep product-safety integrations behind clear API boundaries: recall data clients live in `api/src/recalls`, the chat agents (Pydantic AI by default, LangChain via `AGENT_BACKEND=langchain`) and chat endpoint live in `api/src/chat`, and the voice input relay to the self-hosted speaches server lives in `api/src/transcribe`; keep both agents behaviorally equivalent. Recall facts must come from tool results, not model memory. Speech-to-text exists for voice input; audio goes only to the self-hosted speaches server. Do not add a database, authentication, additional AI services, or new state management without a concrete requirement.
- Manage Python dependencies with `uv` and JavaScript dependencies with npm. Commit both lockfiles and justify every new runtime dependency.
- Helm charts live in `charts/api`, `charts/web`, and `charts/stt`. A chart's `version` in `Chart.yaml` must be bumped whenever its templates or values change (the Chart Version Bump workflow pushes a patch bump to same-repo PRs automatically); api and web image tags and digests are pinned by the release bot, while the stt chart pins an upstream speaches image by hand.
- Use Conventional Commit PR titles (`feat:`, `fix:`, `docs:`, `chore:`…); release-please uses them to version `api` and `web`. Don't edit versions or changelogs by hand.
- Before handing off, run the affected lint, format, type, test, and build checks. Update documentation when commands or architecture change.
