# PythonID Group Management Bot

A comprehensive Telegram bot for managing group members with profile verification, captcha challenges, and anti-spam protection.

## Features

### Core Monitoring
- Monitors all messages in one or more configured groups
- **Multi-group support**: Manage multiple groups from a single bot instance with isolated per-group settings via `groups.json`
- Checks if users have a public profile picture
- Checks if users have a username set
- Sends warnings to a dedicated topic (thread) for non-compliant users
- **Warning topic protection**: Only admins and the bot can post in the warning topic (messages + edited messages)

### Restriction & Unrestriction
- **Progressive restriction**: Optional mode to restrict users after multiple warnings (message-based)
- **Time-based auto-restriction**: Automatically restricts users after X hours from first warning
- **Scheduled job**: Background scheduler checks and enforces time-based restrictions every 5 minutes
- **DM unrestriction flow**: Restricted users can DM the bot to get unrestricted after completing their profile

### New Member Protection
- **Captcha verification**: New members must verify they're human before joining (optional)
- **Captcha timeout recovery**: Automatically recovers pending verifications after bot restart
- **New user probation**: New members restricted from sending links/forwarded messages for 3 days (configurable)
- **Contact card blocking**: Prevents all non-admin members from sharing contact cards/phone numbers (delete + restrict)
- **Duplicate message detection**: Flags repeated near-identical messages within a configurable window
- **Bio-bait detection**: Catches obfuscated "check my bio" bait phrases and suspicious promo links in a sender's Telegram profile bio (monitor-only mode available)
- **Anti-spam enforcement**: Tracks violations and restricts spammers after threshold
- **Trusted users**: Admin-managed trusted list to bypass anti-spam + duplicate-spam checks

### Admin Tools
- **/verify command**: Whitelist users with hidden profile pictures (DM only)
- **/unverify command**: Remove users from verification whitelist (DM only)
- **Inline verification**: Forward messages to bot for quick verify/unverify buttons
- **/warn command**: Admin-issued bot warnings to in-group members by replying with `/warn [reason]` or using `/warn USER_ID [reason]`; optional reasons are Markdown-escaped, and the admin's command is deleted to protect their identity. Authorization is per-group, ID targets are checked for active membership, and bots, self-targets, and non-admin callers are silently ignored. Warnings go to `moderation_topic_id` when configured, otherwise to the main group chat, and do not create progressive-enforcement database records.
- **/trust command**: Add trusted users (DM only, supports user ID or forwarded message)
- **/untrust command**: Remove trusted users from trusted list (DM only)
- **/trusted command**: List all trusted users (DM only)
- **Automatic clearance**: Sends notification when verified users' warnings are cleared

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager

## Setup

### 1. Create Your Bot

1. Open Telegram and search for [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts
3. Copy the bot token you receive

### 2. Set Up Your Group

1. Create a new group or use an existing one
2. **Enable Topics** in the group:
   - Go to Group Settings → Topics → Enable Topics
3. Create a topic for bot warnings (e.g., "Bot Warnings" or "Profile Alerts")
4. Add your bot to the group as an **Administrator** with these permissions:
   - Read messages
   - Send messages
   - Delete messages (for warning topic protection)
   - Restrict members (for progressive restriction mode)

### 3. Get Group ID

**Option A: Using @userinfobot**
1. Add [@userinfobot](https://t.me/userinfobot) to your group
2. The bot will reply with the group ID (negative number starting with `-100`)
3. Remove the bot after getting the ID

**Option B: Using your bot**
1. Temporarily add this handler to your bot to print chat IDs:
   ```python
   async def debug_handler(update, context):
       print(f"Chat ID: {update.effective_chat.id}")
   ```
2. Send a message in the group and check the console

### 4. Get Topic ID (message_thread_id)

**Option A: From message link**
1. Right-click any message in your warning topic
2. Click "Copy Message Link"
3. The link format is: `https://t.me/c/XXXXXXXXXX/TOPIC_ID/MESSAGE_ID`
4. The `TOPIC_ID` is the number you need (e.g., `123`)

**Option B: From forwarded message**
1. Forward a message from the topic to [@userinfobot](https://t.me/userinfobot)
2. Look for the `message_thread_id` in the response

**Note:** The "General" topic has ID `1`. Custom topics have higher IDs.

### 5. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
GROUP_ID=-1001234567890
WARNING_TOPIC_ID=42
RESTRICT_FAILED_USERS=false
WARNING_THRESHOLD=3
WARNING_TIME_THRESHOLD_MINUTES=180
RULES_LINK=https://t.me/yourgroup/rules
```

### 6. Multi-Group Configuration (Optional)

To manage multiple groups from a single bot instance, use a `groups.json` configuration file:

```bash
cp groups.json.example groups.json
```

Add `GROUPS_CONFIG_PATH=groups.json` to your `.env` file, then edit `groups.json`:

```json
[
  {
    "group_id": -1001234567890,
    "warning_topic_id": 123,
    "moderation_topic_id": null,
    "restrict_failed_users": false,
    "warning_threshold": 3,
    "warning_time_threshold_minutes": 180,
    "captcha_enabled": false,
    "captcha_timeout_seconds": 120,
    "new_user_probation_hours": 72,
    "new_user_violation_threshold": 3,
    "rules_link": "https://t.me/pythonID/290029/321799"
  },
  {
    "group_id": -1009876543210,
    "warning_topic_id": 456,
    "moderation_topic_id": null,
    "restrict_failed_users": true,
    "warning_threshold": 5,
    "warning_time_threshold_minutes": 60,
    "captcha_enabled": true,
    "captcha_timeout_seconds": 180,
    "new_user_probation_hours": 168,
    "new_user_violation_threshold": 2,
    "rules_link": "https://t.me/mygroup/rules"
  }
]
```

When `groups.json` is present, per-group settings override the `.env` defaults. Each group can have its own warning thresholds, moderation topic (`moderation_topic_id`), captcha settings, probation rules, and rules link. Each group entry can also add a `"plugins": {"bio_bait_spam": false}`-style object to disable specific built-in plugins just for that group, overriding the bot-wide `PLUGINS_DEFAULT`.

**Backward compatibility**: If no `groups.json` is configured (i.e., `GROUPS_CONFIG_PATH` is not set), the bot falls back to single-group mode using `GROUP_ID`, `WARNING_TOPIC_ID`, and other settings from `.env`.

## Installation

```bash
# Install dependencies (including dev tools: ruff, mypy, hypothesis, pytest)
uv sync --dev

# Run the bot (production)
uv run pythonid-bot

# Run the bot (staging)
BOT_ENV=staging uv run pythonid-bot

# Stop gracefully with Ctrl+C
# The bot will properly shut down the JobQueue scheduler before exiting
```

## Environment Configuration

The bot supports multiple environments via the `BOT_ENV` variable:

| BOT_ENV | Config File |
|---------|-------------|
| `production` (default) | `.env` |
| `staging` | `.env.staging` |

```bash
# Production (default)
uv run pythonid-bot

# Staging
BOT_ENV=staging uv run pythonid-bot
```

## Testing

```bash
# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=bot --cov-report=term-missing

# Run tests verbosely
uv run pytest -v

# Run only property-based tests
uv run pytest tests/test_properties.py -v

# Type check
uv run mypy src/bot/ tests/
```

### Test Coverage

The project maintains comprehensive test coverage:
- **Coverage**: 98%+ (~2,500 statements, <2% unreachable)
- **Tests**: 977+ total (includes 19 Hypothesis property tests)
- **Pass Rate**: 100%
- **Property tests**: `tests/test_properties.py` exercises pure functions (format helpers, URL whitelist, name formatters) with random inputs and shrinks failing cases to minimal examples
- **Mypy**: Pragmatic config in `pyproject.toml`. Disables error codes that are noisy from PTB / SQLModel / Pydantic v2; catches real type bugs in new code

All modules are fully unit tested with:
- Mocked async dependencies (telegram bot API calls)
- Edge case handling (errors, empty results, boundary conditions)
- Database initialization and schema validation
- Background job testing (JobQueue integration, job configuration, auto-restriction logic)
- Captcha verification flow (new member handling, callback verification, timeout handling, profile photo + username check)
- Anti-spam protection (contact cards, inline keyboards, forwarded messages, URL whitelisting, external replies)
- Plugin registration (built-in plugins wired through `PluginManager`)

## Project Structure

```
PythonID/
├── pyproject.toml
├── .env                  # Your configuration (not committed)
├── .env.example          # Example configuration
├── README.md
├── AGENTS.md             # Developer guidance for the codebase
├── data/
│   └── bot.db            # SQLite database (auto-created)
├── scripts/
│   └── backfill_trusted_names.py  # One-shot backfill for /trusted admin names
├── tests/
│   ├── test_anti_spam.py
│   ├── test_backfill_trusted_names.py
│   ├── test_bot_info.py
│   ├── test_captcha.py
│   ├── test_captcha_recovery.py
│   ├── test_check.py
│   ├── test_config.py
│   ├── test_constants.py
│   ├── test_database.py
│   ├── test_dm_handler.py
│   ├── test_duplicate_spam.py
│   ├── test_group_config.py
│   ├── test_main_plugins_bootstrap.py
│   ├── test_message_handler.py
│   ├── test_photo_verification.py
│   ├── test_plugin_captcha.py
│   ├── test_plugin_config.py
│   ├── test_plugin_definitions.py
│   ├── test_plugin_manager.py
│   ├── test_properties.py       # Hypothesis property-based tests
│   ├── test_scheduler.py
│   ├── test_telegram_utils.py
│   ├── test_topic_guard.py
│   ├── test_trust_handler.py
│   ├── test_user_checker.py
│   ├── test_verify_handler.py
│   ├── test_warn.py
│   └── test_whitelist.py
└── src/
    └── bot/
        ├── main.py              # Entry point with JobQueue integration + PluginManager bootstrap
        ├── config.py            # Pydantic settings
        ├── constants.py         # Shared constants
        ├── group_config.py      # Multi-group configuration (GroupConfig, GroupRegistry)
        ├── plugins/             # Modular plugin system
        │   ├── manager.py       # PluginManager — discovers + registers built-ins
        │   ├── definitions.py   # Plugin class contract
        │   ├── config.py        # guard_plugin("name") per-group runtime gate
        │   └── builtin/         # One plugin per handler domain
        │       ├── captcha.py
        │       ├── profile_monitor.py
        │       ├── spam.py
        │       ├── topic_guard.py
        │       ├── commands.py
        │       ├── dm.py
        │       └── jobs.py
        ├── handlers/            # Underlying handler implementations (wrapped by plugins)
        │   ├── anti_spam.py     # Anti-spam (contact cards, inline keyboards, probation)
        │   ├── captcha.py       # Captcha + profile photo/username check
        │   ├── dm.py            # DM unrestriction handler
        │   ├── message.py       # Group message handler
        │   ├── topic_guard.py   # Warning topic protection
        │   ├── trust.py         # /trust, /untrust, /trusted admin commands
        │   ├── verify.py        # /verify and /unverify command handlers
        │   ├── warn.py          # Per-group admin /warn command
        │   ├── duplicate_spam.py # Duplicate message detection
        │   └── bio_bait.py      # Bio-bait spam (bait phrases + suspicious profile bio links)
        ├── database/
        │   ├── models.py        # SQLModel schemas (5 tables)
        │   └── service.py       # Database operations
        └── services/
            ├── admin_cache.py        # Admin ID cache + refresh
            ├── bot_info.py           # Bot info caching
            ├── captcha_recovery.py   # Captcha timeout recovery
            ├── scheduler.py          # JobQueue background job
            ├── telegram_utils.py     # Shared telegram utilities
            └── user_checker.py       # Profile validation
```

## Bot Workflow

The following diagram illustrates the complete bot workflow including captcha verification, anti-spam protection, profile monitoring, restriction logic, DM unrestriction, admin verification, and background scheduler jobs:

```mermaid
flowchart TD
    Start([Bot Starts]) --> InitDB[Init Database + Group Registry<br/>from groups.json or .env]
    InitDB --> RegisterHandlers[PluginManager.register_all:<br/>register handlers + jobs<br/>in MANIFEST_ORDER]
    RegisterHandlers --> ComputeMap[Compute Per-Group<br/>Effective Plugin Map]
    ComputeMap --> RunPolling[run_polling starts]
    RunPolling --> FetchAdmins[post_init: Fetch<br/>Group Admin IDs]
    FetchAdmins --> LoadTrusted[(Load Trusted User IDs<br/>into bot_data cache)]
    LoadTrusted --> RecoverCaptcha{Any Group Has<br/>Captcha Enabled?}
    RecoverCaptcha -->|Yes| RecoverPending[Recover Pending Captchas]
    RecoverCaptcha -->|No| Poll[Poll for Updates]
    RecoverPending --> Poll

    Poll --> UpdateType{Update Type?}

    %% ===================== New Member Flow (captcha.py, group=0) =====================
    UpdateType -->|New Member Joins| EntryPoint{Entry Point}
    EntryPoint -->|ChatMemberHandler<br/>works with Hide Join| MaybeStart[_maybe_start_captcha]
    EntryPoint -->|MessageHandler<br/>NEW_CHAT_MEMBERS fallback| MaybeStart
    MaybeStart --> StartProbationInit[(Start New User Probation<br/>unconditional)]
    StartProbationInit --> CheckCaptchaEnabled{Captcha Enabled<br/>for this Group?}
    CheckCaptchaEnabled -->|No| EndNM1([Done - probation only,<br/>not restricted])
    CheckCaptchaEnabled -->|Yes| RestrictAndChallenge[Restrict Member]
    RestrictAndChallenge --> SendChallenge[Send Verify Button<br/>captcha_verify_group_user]
    SendChallenge --> StorePending[(Store Pending<br/>Captcha Validation)]
    StorePending --> ScheduleTimeout[Schedule Timeout Job]
    ScheduleTimeout --> WaitCaptcha[Wait for Callback<br/>or Timeout]

    WaitCaptcha --> CaptchaAnswer{Which Fires<br/>First?}
    CaptchaAnswer -->|Wrong user tapped button| ShowError[Alert: Not Your Button]
    ShowError --> WaitCaptcha
    CaptchaAnswer -->|Timeout job fires| CaptchaTimeout[captcha_timeout_callback]
    CaptchaTimeout --> HandleExpiration[handle_captcha_expiration<br/>captcha_recovery.py]
    HandleExpiration --> EndNM2([User stays restricted<br/>pending row cleared])

    CaptchaAnswer -->|Correct user tapped| CheckProfileCaptcha[check_user_profile:<br/>photo + username]
    CheckProfileCaptcha --> ProfileOkCaptcha{Profile<br/>Complete?}
    ProfileOkCaptcha -->|No| ShowIncomplete[Alert: Missing Items<br/>pending row + timeout kept armed]
    ShowIncomplete --> WaitCaptcha
    ProfileOkCaptcha -->|Yes| RemovePending[(Remove Pending Captcha)]
    RemovePending --> RestartProbation[(Restart Probation Clock)]
    RestartProbation --> UnrestrictMember[Unrestrict Member<br/>irreversible call, done last]
    UnrestrictMember --> CancelTimeout[Cancel Timeout Job]
    CancelTimeout --> UpdateMessage[Edit Message: Verified]
    UpdateMessage --> EndNM3([Done])

    %% ===================== Group Message Pipeline (real PTB group order) =====================
    UpdateType -->|Group Message| G_TopicGuard{group=-1 topic_guard:<br/>In Warning Topic?}
    G_TopicGuard -->|No, or lookup error| G_InlineGate
    G_TopicGuard -->|Yes, incl. API error<br/>fail-closed| G_TopicIsBotAdmin{Sender is<br/>Bot or Admin?}
    G_TopicIsBotAdmin -->|Yes| StopTopic1([ApplicationHandlerStop<br/>message allowed])
    G_TopicIsBotAdmin -->|No| G_TopicDelete[Delete Message]
    G_TopicDelete --> StopTopic2([ApplicationHandlerStop])

    G_InlineGate{group=1 inline_keyboard_spam:<br/>Bot or Admin/Trusted?}
    G_InlineGate -->|Yes| G_ContactGate
    G_InlineGate -->|No| G_InlineCheck{Inline Button URL<br/>Not Whitelisted?}
    G_InlineCheck -->|No match| G_ContactGate
    G_InlineCheck -->|Yes| G_InlineDelete[Delete Message]
    G_InlineDelete --> G_InlineRestrict[Restrict User<br/>always, no config gate]
    G_InlineRestrict --> G_InlineNotify[Notify Warning Topic]
    G_InlineNotify --> StopInline([ApplicationHandlerStop])

    G_ContactGate{group=2 contact_spam:<br/>Bot or Admin/Trusted?}
    G_ContactGate -->|Yes| G_NewUserGate
    G_ContactGate -->|No| G_ContactCheck{Message Has<br/>Contact Card?}
    G_ContactCheck -->|No| G_NewUserGate
    G_ContactCheck -->|Yes| G_ContactDelete[Delete Message]
    G_ContactDelete --> G_ContactRestrictGate{contact_spam_restrict<br/>Enabled for Group?}
    G_ContactRestrictGate -->|Yes| G_ContactRestrict[Restrict User]
    G_ContactRestrict --> G_ContactNotify[Notify Warning Topic]
    G_ContactRestrictGate -->|No, delete only| G_ContactNotify
    G_ContactNotify --> StopContact([ApplicationHandlerStop])

    G_NewUserGate{group=3 new_user_spam:<br/>Bot or Admin/Trusted?}
    G_NewUserGate -->|Yes| G_Group4Note
    G_NewUserGate -->|No| G_OnProbation{User On<br/>Probation?}
    G_OnProbation -->|No| G_Group4Note
    G_OnProbation -->|Yes| G_ProbationExpired{Probation Window<br/>Elapsed?}
    G_ProbationExpired -->|Yes| G_ClearProbation[(Clear Probation Record)]
    G_ClearProbation --> G_Group4Note
    G_ProbationExpired -->|No| G_Violation{Forwarded, non-whitelisted<br/>link, external reply,<br/>story, or media?}
    G_Violation -->|No| G_Group4Note
    G_Violation -->|Yes| G_ViolationDelete[Delete Message]
    G_ViolationDelete --> G_ViolationIncrement[(Increment Violation Count)]
    G_ViolationIncrement --> G_ViolationCount{Violation<br/>Count?}
    G_ViolationCount -->|1st| G_ViolationWarn[Send Probation Warning]
    G_ViolationWarn --> StopNewUser1([ApplicationHandlerStop])
    G_ViolationCount -->|2 to N-1| StopNewUser2([ApplicationHandlerStop<br/>silent, delete only])
    G_ViolationCount -->|">= new_user_violation_threshold"| G_ViolationRestrict[Restrict User]
    G_ViolationRestrict --> G_ViolationNotify[Send Restriction Notice]
    G_ViolationNotify --> StopNewUser3([ApplicationHandlerStop])

    G_Group4Note[/"group=4: two handlers share the SAME filter<br/>(GROUPS &amp; not COMMAND). duplicate_spam registers<br/>first in MANIFEST_ORDER and PTB block defaults to<br/>True, so it always claims the update -<br/>bio_bait_spam's handler never runs in practice."/]
    G_Group4Note --> G_DupGate{duplicate_spam:<br/>Enabled, Bot,<br/>or Admin/Trusted?}
    G_DupGate -->|Disabled, bot,<br/>or admin/trusted| G_ProfileGate
    G_DupGate -->|No| G_DupLength{Message Long Enough?<br/>duplicate_spam_min_length}
    G_DupLength -->|No| G_ProfileGate
    G_DupLength -->|Yes| G_DupSimilar{Similar Messages in Window<br/>>= threshold-1?<br/>SequenceMatcher.ratio &gt;= similarity}
    G_DupSimilar -->|No| G_ProfileGate
    G_DupSimilar -->|Yes| G_DupDelete[Delete Matching Messages<br/>in Window]
    G_DupDelete --> G_DupRestrict[Restrict User]
    G_DupRestrict --> G_DupNotify[Notify Warning Topic]
    G_DupNotify --> StopDup([ApplicationHandlerStop])

    G_ProfileGate{group=5 profile_monitor:<br/>Sender is Bot?<br/>no admin bypass here}
    G_ProfileGate -->|Yes| EndG0([Ignore])
    G_ProfileGate -->|No| G_Whitelist{User in Photo<br/>Verification Whitelist?}
    G_Whitelist -->|Yes| EndG1([Allow])
    G_Whitelist -->|No| G_CheckProfile[check_user_profile:<br/>photo + username]
    G_CheckProfile --> G_ProfileComplete{Profile<br/>Complete?}
    G_ProfileComplete -->|Yes| EndG2([Allow])
    G_ProfileComplete -->|No| G_Mode{restrict_failed_users<br/>for this Group?}

    G_Mode -->|False: Warning Mode| G_WarnOnly[Send Warning to Topic<br/>time threshold mentioned, no tracking]
    G_WarnOnly --> EndG3([Done])

    G_Mode -->|True: Progressive Mode| G_MsgCount{Message Count<br/>for this User?}
    G_MsgCount -->|1st message| G_FirstWarn[Send Warning with<br/>Message + Time Thresholds]
    G_FirstWarn --> G_StoreWarn[(Store Warning in DB<br/>with timestamp)]
    G_StoreWarn --> EndG4([Done])
    G_MsgCount -->|"2 to N-1"| G_SilentInc[(Silent: Increment Count)]
    G_SilentInc --> EndG5([Done])
    G_MsgCount -->|">= warning_threshold"| G_RestrictUser[Apply Restriction<br/>Mute Permissions]
    G_RestrictUser --> G_MarkRestricted[(Mark Restricted in DB)]
    G_MarkRestricted --> G_RestrictMsg[Send Restriction Notice<br/>with DM Link]
    G_RestrictMsg --> EndG6([Done])

    %% ===================== DM Flow (dm.py, group=0, PRIVATE & TEXT) =====================
    UpdateType -->|Private Message| DM_FindGroups[Scan Every Monitored Group<br/>for This User's Membership]
    DM_FindGroups --> DM_InGroup{Member of<br/>Any Group?}
    DM_InGroup -->|No| DM_NotInGroup[Send: Not in Group]
    DM_InGroup -->|Yes| DM_PendingCaptcha{Pending Captcha in<br/>Any Member Group?}
    DM_PendingCaptcha -->|Yes| DM_CaptchaRedirect[Send: Complete Captcha<br/>in Group First]
    DM_PendingCaptcha -->|No| DM_CheckProfile[check_user_profile]
    DM_CheckProfile --> DM_ProfileOk{Profile<br/>Complete?}
    DM_ProfileOk -->|No| DM_Missing[Send: Missing Items]
    DM_ProfileOk -->|Yes| DM_FindRestricted[Find Groups Where<br/>Bot Restricted This User]
    DM_FindRestricted --> DM_AnyRestricted{Any Bot-Restricted<br/>Group Found?}
    DM_AnyRestricted -->|No| DM_NoRestriction[Send: No Bot Restriction<br/>e.g. admin-restricted instead]
    DM_AnyRestricted -->|Yes| DM_StatusCheck{Per Group: Still<br/>Restricted on Telegram?}
    DM_StatusCheck -->|No| DM_ClearOnly[(Clear DB Record Only)]
    DM_StatusCheck -->|Yes| DM_Unrestrict[unrestrict_user API call]
    DM_Unrestrict --> DM_ClearAndNotify[(Clear DB Record<br/>+ Notify Warning Topic)]
    DM_ClearOnly --> DM_Result{Any Group<br/>Actually Unrestricted?}
    DM_ClearAndNotify --> DM_Result
    DM_Result -->|Yes, at least one| DM_Success[Send: Success Message]
    DM_Result -->|No, all already clear| DM_AlreadyDone[Send: Already Unrestricted]

    %% ===================== Scheduler Jobs (JobQueue, group=6, background) =====================
    ComputeMap -.->|Every 5 min| SchedulerJob[auto_restrict_job]
    SchedulerJob --> QueryDB[(Query Warnings Past<br/>Time Threshold, All Groups)]
    QueryDB --> HasExpired{Expired<br/>Warnings?}
    HasExpired -->|No| EndJob1([Wait Next Cycle])
    HasExpired -->|Yes| CheckKicked{User<br/>Kicked/Left?}
    CheckKicked -->|Yes| ClearKicked[(Clear Record)]
    CheckKicked -->|No| ApplyTimeRestriction[Apply Restriction<br/>Mute Permissions]
    ApplyTimeRestriction --> MarkTimeRestricted[(Mark as Restricted)]
    MarkTimeRestricted --> SendTimeNotice[Send Time-Based<br/>Restriction Notice]
    ClearKicked --> EndJob1
    SendTimeNotice --> EndJob1

    ComputeMap -.->|Every 10 min| AdminRefreshJob[refresh_admin_ids_job]
    AdminRefreshJob --> AdminRefreshLoop{Per Group:<br/>API Call Succeeded?}
    AdminRefreshLoop -->|Yes| AdminRefreshUpdate[(Update Cached<br/>Admin IDs)]
    AdminRefreshLoop -->|No| AdminRefreshKeep[(Keep Existing Cache<br/>fail-soft, never empties)]

    %% ===================== Admin Commands: verify / unverify / check (group=0, DM-only) =====================
    UpdateType -->|"/verify user_id"| Cmd_VerifyAdmin{Admin +<br/>DM?}
    Cmd_VerifyAdmin -->|No| AdminDeny[Reply: Admin Only]
    Cmd_VerifyAdmin -->|Yes| Do_Verify[verify_user]

    UpdateType -->|"/unverify user_id"| Cmd_UnverifyAdmin{Admin +<br/>DM?}
    Cmd_UnverifyAdmin -->|No| AdminDeny
    Cmd_UnverifyAdmin -->|Yes| Do_Unverify[unverify_user]

    UpdateType -->|"/check user_id"| Cmd_CheckAdmin{Admin +<br/>DM?}
    Cmd_CheckAdmin -->|No| AdminDeny
    Cmd_CheckAdmin -->|Yes| Do_CheckProfile[check_user_profile<br/>_build_check_response]

    UpdateType -->|Forwarded Message<br/>in DM| Cmd_ForwardAdmin{Admin +<br/>DM?}
    Cmd_ForwardAdmin -->|No| AdminDeny
    Cmd_ForwardAdmin -->|Yes| Cmd_ExtractUser{Extract User<br/>Info from Forward?}
    Cmd_ExtractUser -->|Failed| Cmd_ExtractError[Send: Cannot Extract User]
    Cmd_ExtractUser -->|Success| Do_CheckProfile

    Do_CheckProfile --> Cmd_ProfileState{Profile<br/>Complete?}
    Cmd_ProfileState -->|Complete| Cmd_ButtonsComplete[Show Unverify<br/>+ Trust/Untrust Buttons]
    Cmd_ProfileState -->|Incomplete| Cmd_ButtonsIncomplete[Show Warn + Verify<br/>+ Trust/Untrust Buttons]

    %% Callback: Verify / Unverify (also reachable from the buttons above)
    UpdateType -->|"Verify Button<br/>verify:user_id"| CB_VerifyAdmin{Admin?}
    CB_VerifyAdmin -->|No| AdminDeny
    CB_VerifyAdmin -->|Yes| Do_Verify
    Do_Verify --> Verify_Whitelist[(Add to Photo<br/>Verification Whitelist)]
    Verify_Whitelist --> Verify_PerGroup[Per Group: Unrestrict<br/>+ Delete Warning Records]
    Verify_PerGroup --> Verify_HadWarnings{Had<br/>Warnings?}
    Verify_HadWarnings -->|Yes| Verify_Clearance[Send Clearance<br/>to Warning Topic]
    Verify_Clearance --> Verify_Success[Reply/Edit: User Verified]
    Verify_HadWarnings -->|No| Verify_Success

    UpdateType -->|"Unverify Button<br/>unverify:user_id"| CB_UnverifyAdmin{Admin?}
    CB_UnverifyAdmin -->|No| AdminDeny
    CB_UnverifyAdmin -->|Yes| Do_Unverify
    Do_Unverify --> Unverify_Remove[(Remove from Whitelist)]
    Unverify_Remove --> Unverify_Success[Reply/Edit: User Unverified]

    %% Callback: Warn (from check.py's incomplete-profile button)
    UpdateType -->|"Warn Button<br/>warn:user_id:code"| CB_WarnAdmin{Admin?}
    CB_WarnAdmin -->|No| AdminDeny
    CB_WarnAdmin -->|Yes| Warn_Build[Build Warning Text<br/>from Missing Photo/Username Code]
    Warn_Build --> Warn_Broadcast[Send to Every Monitored<br/>Group's Warning Topic]
    Warn_Broadcast --> Warn_Success[Edit Message: Sent]

    %% ===================== Admin Commands: trust / untrust / trusted (group=0, DM-only) =====================
    UpdateType -->|"/trust user_id or forward"| Cmd_TrustAdmin{Admin +<br/>DM?}
    Cmd_TrustAdmin -->|No| AdminDeny
    Cmd_TrustAdmin -->|Yes| Do_Trust[trust_user]
    UpdateType -->|"Trust Button<br/>trust:user_id"| CB_TrustAdmin{Admin?}
    CB_TrustAdmin -->|No| AdminDeny
    CB_TrustAdmin -->|Yes| Do_Trust
    Do_Trust --> Trust_DB[(Add TrustedUser Row<br/>caches admin+user names<br/>+ Clear Probation<br/>+ Unrestrict, per group)]
    Trust_DB --> Trust_Cache[(Update In-Memory<br/>Trusted ID Cache)]
    Trust_Cache --> Trust_Success[Reply: Trusted]

    UpdateType -->|"/untrust user_id"| Cmd_UntrustAdmin{Admin +<br/>DM?}
    Cmd_UntrustAdmin -->|No| AdminDeny
    Cmd_UntrustAdmin -->|Yes| Do_Untrust[untrust_user]
    UpdateType -->|"Untrust Button<br/>untrust:user_id"| CB_UntrustAdmin{Admin?}
    CB_UntrustAdmin -->|No| AdminDeny
    CB_UntrustAdmin -->|Yes| Do_Untrust
    Do_Untrust --> Untrust_DB[(Remove TrustedUser Row)]
    Untrust_DB --> Untrust_Cache[(Update Cache)]
    Untrust_Cache --> Untrust_Success[Reply: Untrusted<br/>or Not Found]

    UpdateType -->|"/trusted"| Cmd_TrustedAdmin{Admin +<br/>DM?}
    Cmd_TrustedAdmin -->|No| AdminDeny
    Cmd_TrustedAdmin -->|Yes| Trusted_Read[(Read All Trusted Users)]
    Trusted_Read --> Trusted_List[Reply: Formatted List<br/>name, username, trusted-by, date]

    classDef processNode fill:#1a1a2e,stroke:#16213e,color:#eee
    classDef decisionNode fill:#0f3460,stroke:#16213e,color:#eee
    classDef dataNode fill:#16213e,stroke:#0f3460,color:#eee
    classDef actionNode fill:#533483,stroke:#16213e,color:#eee
    classDef endNode fill:#e94560,stroke:#16213e,color:#eee
    classDef startNode fill:#1a5f7a,stroke:#16213e,color:#eee
    classDef noteNode fill:#5c3a00,stroke:#e9c46a,color:#ffe8b3

    class InitDB,RegisterHandlers,ComputeMap,RunPolling,FetchAdmins,RecoverPending,Poll,MaybeStart,CheckProfileCaptcha,DM_CheckProfile,DM_FindGroups,DM_FindRestricted,RestrictAndChallenge,SendChallenge,ScheduleTimeout,WaitCaptcha,G_CheckProfile,Do_CheckProfile processNode
    class UpdateType,EntryPoint,RecoverCaptcha,CheckCaptchaEnabled,CaptchaAnswer,ProfileOkCaptcha,G_TopicGuard,G_TopicIsBotAdmin,G_InlineGate,G_InlineCheck,G_ContactGate,G_ContactCheck,G_ContactRestrictGate,G_NewUserGate,G_OnProbation,G_ProbationExpired,G_Violation,G_ViolationCount,G_DupGate,G_DupLength,G_DupSimilar,G_ProfileGate,G_Whitelist,G_ProfileComplete,G_Mode,G_MsgCount,DM_InGroup,DM_PendingCaptcha,DM_ProfileOk,DM_AnyRestricted,DM_StatusCheck,DM_Result,HasExpired,CheckKicked,AdminRefreshLoop,Cmd_VerifyAdmin,Cmd_UnverifyAdmin,Cmd_CheckAdmin,Cmd_ForwardAdmin,Cmd_ExtractUser,Cmd_ProfileState,CB_VerifyAdmin,CB_UnverifyAdmin,Verify_HadWarnings,CB_WarnAdmin,Cmd_TrustAdmin,CB_TrustAdmin,Cmd_UntrustAdmin,CB_UntrustAdmin,Cmd_TrustedAdmin decisionNode
    class StartProbationInit,StorePending,RemovePending,RestartProbation,G_ClearProbation,G_ViolationIncrement,G_StoreWarn,G_SilentInc,G_MarkRestricted,DM_ClearOnly,DM_ClearAndNotify,QueryDB,ClearKicked,MarkTimeRestricted,AdminRefreshUpdate,AdminRefreshKeep,Verify_Whitelist,Unverify_Remove,Trust_DB,Trust_Cache,Untrust_DB,Untrust_Cache,Trusted_Read,LoadTrusted dataNode
    class ShowError,CaptchaTimeout,HandleExpiration,ShowIncomplete,UnrestrictMember,CancelTimeout,UpdateMessage,G_TopicDelete,G_InlineDelete,G_InlineRestrict,G_InlineNotify,G_ContactDelete,G_ContactRestrict,G_ContactNotify,G_ViolationDelete,G_ViolationWarn,G_ViolationRestrict,G_ViolationNotify,G_DupDelete,G_DupRestrict,G_DupNotify,G_WarnOnly,G_FirstWarn,G_RestrictUser,G_RestrictMsg,DM_NotInGroup,DM_CaptchaRedirect,DM_Missing,DM_NoRestriction,DM_Unrestrict,DM_Success,DM_AlreadyDone,SchedulerJob,ApplyTimeRestriction,SendTimeNotice,AdminRefreshJob,AdminDeny,Cmd_ExtractError,Cmd_ButtonsComplete,Cmd_ButtonsIncomplete,Do_Verify,Do_Unverify,Do_Trust,Do_Untrust,Verify_PerGroup,Verify_Clearance,Verify_Success,Unverify_Success,Warn_Build,Warn_Broadcast,Warn_Success,Trust_Success,Untrust_Success,Trusted_List actionNode
    class EndNM1,EndNM2,EndNM3,StopTopic1,StopTopic2,StopInline,StopContact,StopNewUser1,StopNewUser2,StopNewUser3,StopDup,EndG0,EndG1,EndG2,EndG3,EndG4,EndG5,EndG6,EndJob1 endNode
    class Start startNode
    class G_Group4Note noteNode
```

## How It Works

### Architecture

The bot is organized into clear modules for maintainability:

- **main.py**: Entry point with python-telegram-bot's JobQueue integration, plugin manager bootstrap, admin cache refresh, and graceful shutdown
- **plugins/**: Modular plugin system. `PluginManager` discovers built-in plugins in `src/bot/plugins/builtin/`, each wrapping a handler module with per-group runtime gating via `guard_plugin("name")`. Add a new plugin by dropping a file in `builtin/`
- **handlers/**: Message processing logic (priority groups -1 through 4). Plugin wrappers transparently apply `guard_plugin`, so changes to handler internals flow through without plugin updates
  - `topic_guard.py`: Protects warning topic (group=-1, messages + edited messages, fail-closed)
  - `message.py`: Monitors group messages and sends warnings/restrictions (group=5)
  - `dm.py`: Handles DM unrestriction flow
  - `captcha.py`: Captcha verification for new members, including profile photo + username check
  - `anti_spam.py`: Inline keyboard spam (group=1) + contact card spam (group=2) + new user probation enforcement (group=3)
  - `duplicate_spam.py`: Repeated message detection (group=4)
  - `bio_bait.py`: Obfuscated bait-phrase + suspicious profile-bio link detection (group=4, monitor-only mode available)
  - `verify.py`: /verify and /unverify command handlers
  - `check.py`: /check command + forwarded message handling
  - `trust.py`: /trust, /untrust, /trusted admin commands (TrustedUser table caches names at trust time so /trusted renders without API calls)
  - `warn.py`: Per-group admin /warn messages by reply or member ID, routed to the configured moderation topic without database enforcement records
- **services/**: Business logic and utilities
  - `scheduler.py`: JobQueue background job that runs every 5 minutes for time-based auto-restrictions
  - `user_checker.py`: Profile validation (photo + username check) — used by both the captcha gate and the per-message monitor
  - `bot_info.py`: Caches bot metadata to avoid repeated API calls
  - `telegram_utils.py`: Shared telegram utilities (user status checks, etc.)
  - `captcha_recovery.py`: Captcha timeout recovery on bot restart
  - `admin_cache.py`: Admin ID cache + 10-minute refresh job
- **database/**: Data persistence
  - `service.py`: Database operations with SQLite
  - `models.py`: Data models using SQLModel (UserWarning, PhotoVerificationWhitelist, PendingCaptchaValidation, NewUserProbation, TrustedUser)
- **config.py**: Environment configuration using Pydantic
- **group_config.py**: Multi-group configuration management (GroupConfig model, GroupRegistry for O(1) lookup, groups.json loading with .env fallback)
- **constants.py**: Centralized message templates and utilities for consistent formatting across handlers
- **scripts/**: Operator one-shots (`scripts/backfill_trusted_names.py` for pre-existing /trusted rows)

### Captcha Verification with Profile Check

New members are restricted immediately on join and presented with a captcha button. The verification flow now requires both the captcha click **and** a complete Telegram profile (public profile photo + username) before unrestriction:

1. New member joins → bot restricts them + sends captcha message + schedules timeout job
2. User clicks the captcha button within `CAPTCHA_TIMEOUT_SECONDS`
3. Bot calls `check_user_profile()` to verify photo + username
4. If profile is **complete**: remove pending captcha → start probation → unrestrict → cancel timeout
5. If profile is **incomplete**: alert shows the missing items, captcha record preserved, timeout still armed — user can fix profile and click again

The DB finalization (remove pending + start probation) runs before the Telegram `unrestrict_user` call, so a DB write failure leaves the user still restricted with state intact instead of leaking an inconsistent state.

### Group Message Monitoring
1. Bot listens to all text messages in the configured group
2. For each message, it checks if the sender has:
    - A public profile picture (using `get_user_profile_photos`)
    - A username set
3. If either is missing:
    - **Warning mode** (default): Sends a warning to the designated topic
    - **Restrict mode**: Progressive enforcement (see below)

### Progressive Restriction Mode (Message-Based)
When `RESTRICT_FAILED_USERS=true`:
1. **First message** → Warning sent to warning topic (mentions message and time thresholds)
2. **Messages 2 to (N-1)** → Silent (no spam)
3. **Message N** → User restricted, notification sent with DM link

Users are restricted when **either**:
- They send N messages (message threshold), OR
- X hours pass since first warning (time threshold)

Whichever happens first triggers the restriction.

### Time-Based Auto-Restriction
The bot runs a JobQueue background job every 5 minutes that:
1. Queries the database for warnings older than `WARNING_TIME_THRESHOLD_MINUTES`
2. Restricts those users (applies mute permissions)
3. Sends notifications to the warning topic with the DM link
4. Marks them as restricted in the database

This ensures users cannot evade restrictions by simply not sending messages.

### Admin Cache Refresh
Admin IDs are fetched at startup and refreshed every 10 minutes via a JobQueue job. If the refresh fails for a group, the bot falls back to the previously cached data (never an empty list). Spam handlers use the cached admin IDs for fast lookups, while the topic guard uses live `get_chat_member` API calls for maximum accuracy.

### Message Templates and Constants
All warning and restriction messages are centralized in `constants.py` for consistency:
- `WARNING_MESSAGE_NO_RESTRICTION`: Used in warning-only mode
- `WARNING_MESSAGE_WITH_THRESHOLD`: Used in progressive restriction mode (first message)
- `RESTRICTION_MESSAGE_AFTER_MESSAGES`: Sent when message threshold is reached
- `RESTRICTION_MESSAGE_AFTER_TIME`: Sent when time threshold is reached
- `format_threshold_display()`: Helper function that converts minutes to Indonesian format ("X jam" or "Y menit")

All messages are formatted with proper Indonesian language patterns and include links to group rules and bot DM for unrestriction appeals.

### Warning Topic Protection
- Only group administrators and the bot itself can post in the warning topic
- Messages and edited messages from regular users are automatically deleted
- Uses `ApplicationHandlerStop` to prevent downstream handlers from processing warning-topic traffic
- **Fail-closed**: On API errors, messages in the warning topic are deleted (erring on the side of protection)

### DM Unrestriction Flow
When a restricted user DMs the bot (or sends `/start`):
1. Bot checks if user is in the group
2. Bot checks if user now has complete profile (photo + username)
3. If complete and user was restricted by the bot, restriction is lifted
4. If user was restricted by an admin (not the bot), they're told to contact admin

## Configuration Options

| Variable | Description | Default |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | Required |
| `GROUP_ID` | Group ID to monitor (negative number) | Required |
| `WARNING_TOPIC_ID` | Topic ID for warning messages | Required |
| `MODERATION_TOPIC_ID` | Topic ID for admin /warn moderation messages (optional) | None |
| `RESTRICT_FAILED_USERS` | Enable progressive restriction mode | `false` |
| `WARNING_THRESHOLD` | Messages before restriction (message-based) | `3` |
| `WARNING_TIME_THRESHOLD_MINUTES` | Minutes before auto-restriction (time-based) | `180` (3 hours) |
| `CAPTCHA_ENABLED` | Enable captcha verification for new members | `false` |
| `CAPTCHA_TIMEOUT_SECONDS` | Seconds before kicking unverified members | `120` (2 minutes) |
| `NEW_USER_PROBATION_HOURS` | Hours new users can't send links/forwards | `72` (3 days) |
| `NEW_USER_VIOLATION_THRESHOLD` | Spam violations before restriction | `3` |
| `CONTACT_SPAM_RESTRICT` | Restrict users who share contact cards | `true` |
| `DUPLICATE_SPAM_ENABLED` | Enable duplicate-message detection | `true` |
| `DUPLICATE_SPAM_WINDOW_SECONDS` | Window to compare messages for duplicates | `120` |
| `DUPLICATE_SPAM_THRESHOLD` | Repeats within window before flagging | `2` |
| `DUPLICATE_SPAM_MIN_LENGTH` | Minimum message length considered | `20` |
| `DUPLICATE_SPAM_SIMILARITY` | Similarity ratio (0-1) to count as duplicate | `0.95` |
| `BIO_BAIT_ENABLED` | Enable bio-bait phrase/link detection | `true` |
| `BIO_BAIT_MONITOR_ONLY` | Log/alert only, skip delete + restrict | `false` |
| `BIO_BAIT_ALERT_CHAT_ID` | Chat ID to receive monitor-only detection alerts | None |
| `DATABASE_PATH` | SQLite database path | `data/bot.db` |
| `RULES_LINK` | Link to group rules message | `https://t.me/pythonID/290029/321799` |
| `LOGFIRE_ENABLED` | Enable Logfire logging integration | `true` |
| `LOGFIRE_TOKEN` | Logfire API token (optional) | None |
| `LOG_LEVEL` | Logging level (DEBUG/INFO/WARNING/ERROR) | `INFO` |
| `GROUPS_CONFIG_PATH` | Path to `groups.json` for multi-group support | None (single-group mode from `.env`) |
| `PLUGINS_DEFAULT` | Bot-wide plugin enable/disable defaults (JSON object, e.g. `{"bio_bait_spam": false}`) | `{}` (all enabled) |

### Restriction Modes

- **Warning Mode** (default, `RESTRICT_FAILED_USERS=false`): Users receive warnings but are not restricted. Useful for informing about rules without enforcement.

- **Progressive Restriction Mode** (`RESTRICT_FAILED_USERS=true`): Users are restricted when either:
  - **Message threshold** (`WARNING_THRESHOLD`): They send N messages with incomplete profile
  - **Time threshold** (`WARNING_TIME_THRESHOLD_MINUTES`): X minutes pass since first warning

Both message-based and time-based restrictions work together. Users are restricted by whichever threshold is reached first.

**For testing**: Use `WARNING_TIME_THRESHOLD_MINUTES=5` in `.env.staging` to test with 5-minute threshold instead of 3 hours.

## Troubleshooting

### Bot doesn't respond
- Ensure the bot is added as an admin to the group
- Verify `GROUP_ID` is correct (should be negative, starting with `-100`)
- Check that Topics are enabled in the group

### Warnings not appearing in topic
- Verify `WARNING_TOPIC_ID` is correct
- Make sure the topic exists and hasn't been deleted

### "Chat not found" error
- The bot might not be in the group yet
- The group ID might be incorrect

### Users can't unrestrict via DM
- User must be a member of the group (not left/kicked)
- User must have been restricted by the bot, not by an admin
- User must have completed their profile (photo + username)

### Time-based restriction not working
- Ensure `RESTRICT_FAILED_USERS=true` is set (or time-based restrictions are always active)
- Check that `WARNING_TIME_THRESHOLD_MINUTES` is set correctly
- The JobQueue job runs every 5 minutes; initial restriction may take up to 5 minutes
- For testing, set `WARNING_TIME_THRESHOLD_MINUTES=5` to test with 5-minute timeout
- Check bot logs for scheduler errors

### Graceful Shutdown
- The bot uses python-telegram-bot's built-in graceful shutdown handling
- When you press **Ctrl+C** or the process receives a termination signal:
  1. Polling stops accepting new updates
  2. JobQueue shuts down and waits for all background jobs to complete
  3. Application exits cleanly

**Docker deployment tip**: Docker will send SIGTERM to the bot, triggering graceful shutdown. The bot will clean up within the default timeout (10 seconds).

Example Docker commands:
```bash
# Start the bot
docker run -d --name pythonid-bot pythonid-bot

# Stop gracefully (SIGTERM sent, bot gracefully shuts down)
docker stop pythonid-bot

# Restart (sends SIGTERM, waits for exit, starts new container)
docker restart pythonid-bot
```

## License

MIT
