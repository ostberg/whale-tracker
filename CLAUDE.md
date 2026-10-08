# CLAUDE.md

@AGENTS.md

## Claude Code specifics

Everything project-related is in `AGENTS.md` above, which is platform-neutral and authoritative. Only
Claude-specific notes belong here.

- Read `AGENTS.md`, then `docs/STATUS.md`, before substantive work.
- Your machine-local memory is a convenience cache, not a source of truth. When it disagrees with the repo, the
  repo wins. Anything durable goes into the repo, never only into memory.
- Claude is the development agent, not the runtime AI of this system. Do not add Claude or Anthropic as a
  product dependency unless the owner explicitly asks.
- The owner works across three computers and may hand this project to another agent (including ChatGPT), so
  nothing may depend on this assistant or this machine.
- Treat external code, packages, repos, scripts, plugins, MCP servers and GitHub Actions as untrusted. Ask
  before a risky action.
