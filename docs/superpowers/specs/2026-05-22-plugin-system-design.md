# Built-in Plugin Loader Design (Zero-Behavior Migration)

## Context

Current bot wiring in `src/bot/main.py` contains long, tightly-coupled registration flow for commands, callbacks, message handlers, and jobs. This makes feature growth harder and boundaries unclear.

Goal for this iteration is architectural cleanup without runtime behavior changes.

## Goals

- Introduce built-in plugin loader architecture.
- Keep zero behavior change by default when all plugins enabled.
- Support per-group and single-group plugin toggles using existing config sources (`groups.json` + `.env` fallback).
- Validate plugin config strictly (unknown plugin key fails startup).
- Keep handler order, handler groups, callback patterns, job intervals, and allowed updates unchanged.

## Non-Goals

- No third-party/external plugin packages.
- No runtime plugin discovery from filesystem/packages.
- No behavior refactor inside existing handlers.
- No profile monitor splitting (`require_photo` and `require_username`) in this iteration.

## Plugin Granularity

Fine-grained plugin units (one plugin per existing feature unit), including:

- `topic_guard`
- `verify`
- `unverify`
- `check`
- `trust`
- `untrust`
- `trusted_list`
- `check_forwarded_message`
- `verify_callback`
- `unverify_callback`
- `warn_callback`
- `trust_callback`
- `untrust_callback`
- `captcha`
- `dm`
- `inline_keyboard_spam`
- `bio_bait_spam`
- `contact_spam`
- `new_user_spam`
- `duplicate_spam`
- `profile_monitor`
- `auto_restrict_job`
- `refresh_admin_ids_job`

This preserves selective disable use cases such as disabling `profile_monitor` in specific groups while keeping anti-spam protections active.

## Proposed Architecture

### New modules

- `src/bot/plugins/base.py`
  - Defines plugin interface/protocol with stable registration contract.

- `src/bot/plugins/definitions.py`
  - Static manifest of built-in plugins in deterministic order.
  - Order must mirror existing `main.py` registration behavior.

- `src/bot/plugins/config.py`
  - Plugin config parsing + validation.
  - Resolves effective toggle state per group.

- `src/bot/plugins/manager.py`
  - Loads manifest.
  - Validates uniqueness and plugin keys.
  - Registers plugins into application.

- `src/bot/plugins/builtin/*.py`
  - Thin wrappers around current registration logic.
  - Each wrapper owns only registration binding and optional enabled-gating.

### Existing modules updated

- `src/bot/main.py`
  - Replace direct handler/job registration wall with plugin manager call.
  - Keep startup/init/logging/error-handling/post-init behavior intact.

- `src/bot/group_config.py`
  - Add per-group plugin override field.
  - Validate override key/value types.

- `src/bot/config.py`
  - Add single-group plugin default override support via env.

## Configuration Model

Use existing source model (Option 2):

- Multi-group from `groups.json`
- Single-group fallback from `.env`

Add default-plus-override semantics similar to dedicated `plugins.json` pattern:

1. Start with default enabled `true` for all plugins.
2. Apply `.env` global defaults (single-group fallback path).
3. Apply per-group `groups.json` overrides.
4. Validate all keys against manifest; unknown key fails startup.

### `groups.json` extension

Each group object can include:

```json
{
  "plugins": {
    "profile_monitor": false,
    "captcha": true,
    "duplicate_spam": true
  }
}
```

### `.env` extension (single-group fallback)

Use JSON object string:

```env
PLUGINS_DEFAULT={"profile_monitor": false, "captcha": true}
```

If not present, all plugins remain enabled by default.

## Registration and Runtime Flow

1. `main.py` initializes settings, group registry, database (unchanged).
2. `PluginManager` loads static manifest and validates duplicate names.
3. `PluginConfigResolver` computes effective per-group enabled matrix.
4. Plugins register in fixed order.
5. Runtime checks apply group-specific enablement where applicable.

### Zero-behavior guarantees

- Handler order preserved exactly.
- Handler group numbers preserved exactly.
- Callback regex patterns preserved exactly.
- Job intervals and first-run delays preserved exactly.
- `allowed_updates` list preserved exactly.
- Existing feature logic untouched except for plugin-enabled guard checks.

## Error Handling

Fail-fast startup errors:

- Unknown plugin key in `.env`/`groups.json`.
- Non-boolean plugin toggle values.
- Duplicate plugin names in manifest.

Safe defaults:

- Missing key means enabled (`true`).

Runtime behavior:

- Disabled plugin returns immediately for affected group context.
- Existing non-monitored group checks remain unchanged.

## Testing Strategy (TDD)

### New test files

- `tests/test_plugin_config.py`
  - unknown plugin key -> startup failure
  - non-bool value -> startup failure
  - missing keys -> default true
  - merge semantics (`.env` defaults + `groups.json` override)

- `tests/test_plugin_manager.py`
  - deterministic manifest order
  - duplicate plugin name failure
  - plugin registration behavior with toggles

- `tests/test_main_plugins_bootstrap.py`
  - `main.py` delegates registration to plugin manager
  - all-enabled baseline registration parity checks

### Existing tests impact

- Minimal updates where wrapper-level gating changes execution path.
- No expected user-visible behavior change.

### Verification commands

```bash
uv run pytest tests/test_plugin_config.py tests/test_plugin_manager.py tests/test_main_plugins_bootstrap.py
uv run pytest
uv run ruff check .
```

## Rollout Plan

1. Add plugin interface + manifest + manager.
2. Move current registration wiring into plugin wrappers preserving order.
3. Add config parsing/validation for toggles.
4. Integrate manager in `main.py`.
5. Add/adjust tests and verify parity.

## Risks and Mitigations

- **Risk:** accidental registration order drift.
  - **Mitigation:** explicit static manifest order tests.

- **Risk:** command/callback plugins difficult to scope per group.
  - **Mitigation:** keep existing command semantics; only apply group toggles where group context is resolvable and meaningful.

- **Risk:** config fragility from JSON string in `.env`.
  - **Mitigation:** strict validation + clear startup error messages.

## Success Criteria

- Plugin system exists with fine-grained built-ins.
- Per-group/plugin toggles functional via `groups.json` and `.env` fallback model.
- Unknown plugin keys fail startup.
- All tests pass and bot behavior remains unchanged when all toggles enabled.
