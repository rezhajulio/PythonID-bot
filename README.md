# PythonID Group Management Bot

A comprehensive Telegram bot for managing group members with profile verification, captcha challenges, and anti-spam protection.

## Features

### Core Monitoring
- Monitors all messages in a configured group
- Checks if users have a public profile picture
- Checks if users have a username set
- Sends warnings to a dedicated topic (thread) for non-compliant users
- **Warning topic protection**: Only admins and the bot can post in the warning topic

### Restriction & Unrestriction
- **Progressive restriction**: Optional mode to restrict users after multiple warnings (message-based)
- **Time-based auto-restriction**: Automatically restricts users after X hours from first warning
- **Scheduled job**: Background scheduler checks and enforces time-based restrictions every 5 minutes
- **DM unrestriction flow**: Restricted users can DM the bot to get unrestricted after completing their profile

### New Member Protection
- **Captcha verification**: New members must verify they're human before joining (optional)
- **Captcha timeout recovery**: Automatically recovers pending verifications after bot restart
- **New user probation**: New members restricted from sending links/forwarded messages for 3 days (configurable)
- **Anti-spam enforcement**: Tracks violations and restricts spammers after threshold

### Admin Tools
- **/verify command**: Whitelist users with hidden profile pictures (DM only)
- **/unverify command**: Remove users from verification whitelist (DM only)
- **Inline verification**: Forward messages to bot for quick verify/unverify buttons
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

## Installation

```bash
# Install dependencies
uv sync

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
```

### Test Coverage

The project maintains comprehensive test coverage:
- **Coverage**: 99% (1,216 statements)
- **Tests**: 404 total
- **Pass Rate**: 100% (404/404 passed)
- **All modules**: 100% coverage including JobQueue scheduler integration, captcha verification, and anti-spam enforcement
  - Services: `bot_info.py` (100%), `scheduler.py` (100%), `user_checker.py` (100%), `telegram_utils.py` (100%), `captcha_recovery.py` (100%)
  - Handlers: `anti_spam.py` (100%), `captcha.py` (100%), `check.py` (100%), `dm.py` (100%), `message.py` (100%), `topic_guard.py` (100%), `verify.py` (100%)
  - Database: `service.py` (100%), `models.py` (100%)
  - Config: `config.py` (100%)
  - Constants: `constants.py` (100%)

All modules are fully unit tested with:
- Mocked async dependencies (telegram bot API calls)
- Edge case handling (errors, empty results, boundary conditions)
- Database initialization and schema validation
- Background job testing (JobQueue integration, job configuration, auto-restriction logic)
- Captcha verification flow (new member handling, callback verification, timeout handling)
- Anti-spam protection (forwarded messages, URL whitelisting, external replies)

## Project Structure

```
PythonID/
├── pyproject.toml
├── .env                  # Your configuration (not committed)
├── .env.example          # Example configuration
├── README.md
├── data/
│   └── bot.db            # SQLite database (auto-created)
├── tests/
│   ├── test_anti_spam.py
│   ├── test_bot_info.py
│   ├── test_captcha.py
│   ├── test_captcha_recovery.py
│   ├── test_config.py
│   ├── test_constants.py
│   ├── test_database.py
│   ├── test_dm_handler.py
│   ├── test_message_handler.py
│   ├── test_photo_verification.py
│   ├── test_scheduler.py     # JobQueue scheduler tests
│   ├── test_telegram_utils.py
│   ├── test_topic_guard.py
│   ├── test_user_checker.py
│   └── test_verify_handler.py
└── src/
    └── bot/
        ├── main.py              # Entry point with JobQueue integration
        ├── config.py            # Pydantic settings
        ├── constants.py         # Shared constants
        ├── handlers/
        │   ├── anti_spam.py     # Anti-spam handler for probation users
        │   ├── captcha.py       # Captcha verification handler
        │   ├── dm.py            # DM unrestriction handler
        │   ├── message.py       # Group message handler
        │   ├── topic_guard.py   # Warning topic protection
        │   └── verify.py        # /verify and /unverify command handlers
        ├── database/
        │   ├── models.py        # SQLModel schemas
        │   └── service.py       # Database operations
        └── services/
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
    Start([Bot Starts]) --> Init[Initialize Database & Config]
    Init --> FetchAdmins[Fetch Group Admin IDs]
    FetchAdmins --> RecoverCaptcha{Captcha<br/>Enabled?}
    RecoverCaptcha -->|Yes| RecoverPending[Recover Pending Captchas]
    RecoverCaptcha -->|No| StartJobs
    RecoverPending --> StartJobs[Start JobQueue Scheduler<br/>5-minute interval]
    StartJobs --> Poll[Poll for Updates]
    
    Poll --> UpdateType{Update Type?}
    
    %% New Member Flow
    UpdateType -->|New Member| CheckCaptchaEnabled{Captcha<br/>Enabled?}
    CheckCaptchaEnabled -->|No| StartProbation[Start Probation Only]
    CheckCaptchaEnabled -->|Yes| RestrictAndChallenge[Restrict & Send Captcha]
    RestrictAndChallenge --> StorePending[(Store Pending Validation)]
    StorePending --> ScheduleTimeout[Schedule Timeout Job]
    ScheduleTimeout --> WaitCaptcha[Wait for Verification]
    
    WaitCaptcha --> CaptchaAnswer{User<br/>Action?}
    CaptchaAnswer -->|Correct Button| CancelTimeout[Cancel Timeout Job]
    CancelTimeout --> UnrestrictMember[Unrestrict Member]
    UnrestrictMember --> StartProbationAfter[Start Probation]
    CaptchaAnswer -->|Wrong User| ShowError[Show Error Message]
    CaptchaAnswer -->|Timeout| KickMember[Keep Restricted]
    KickMember --> UpdateMessage[Update Challenge Message]
    
    %% Anti-Spam Flow (New User Probation)
    UpdateType -->|Group Message| CheckProbation{User On<br/>Probation?}
    CheckProbation -->|No| CheckBot
    CheckProbation -->|Yes| CheckExpired{Probation<br/>Expired?}
    CheckExpired -->|Yes| ClearProbation[(Clear Probation)]
    CheckExpired -->|No| CheckViolation{Forward/Link/<br/>External Reply?}
    
    CheckViolation -->|No| End1([Continue])
    CheckViolation -->|Yes| CheckWhitelisted{URL<br/>Whitelisted?}
    CheckWhitelisted -->|Yes| End1
    CheckWhitelisted -->|No| DeleteSpam[Delete Message]
    DeleteSpam --> IncrementViolation[(Increment Violation)]
    IncrementViolation --> ViolationCount{Violation<br/>Count?}
    
    ViolationCount -->|First| SendSpamWarning[Send Probation Warning]
    ViolationCount -->|< Threshold| End2([Done])
    ViolationCount -->|>= Threshold| RestrictSpammer[Restrict User]
    RestrictSpammer --> SendSpamRestriction[Send Restriction Notice]
    
    %% Group Message Flow - Topic Guard
    CheckBot{From Bot?}
    CheckBot -->|Yes| End3([Ignore])
    CheckBot -->|No| TopicGuard{In Warning<br/>Topic?}
    TopicGuard -->|Yes| IsAdmin{Is Admin<br/>or Bot?}
    IsAdmin -->|No| DeleteMsg[Delete Message]
    IsAdmin -->|Yes| End4([Allow])
    
    %% Group Message Flow - Profile Check
    TopicGuard -->|No| CheckWhitelist{User<br/>Whitelisted?}
    CheckWhitelist -->|Yes| End5([Allow])
    CheckWhitelist -->|No| CheckProfile[Check User Profile:<br/>Photo + Username]
    
    CheckProfile --> ProfileComplete{Profile<br/>Complete?}
    ProfileComplete -->|Yes| End6([Allow])
    ProfileComplete -->|No| CheckMode{Restriction<br/>Mode?}
    
    %% Warning Mode
    CheckMode -->|Warning Only| SendWarning[Send Warning to Topic<br/>Time threshold mentioned]
    SendWarning --> End7([Done])
    
    %% Progressive Restriction Mode
    CheckMode -->|Progressive| CheckCount{Message<br/>Count?}
    CheckCount -->|First Message| SendFirstWarning[Send Warning with<br/>Message & Time Thresholds]
    SendFirstWarning --> IncrementDB[(Store Warning in DB<br/>with timestamp)]
    IncrementDB --> End8([Done])
    
    CheckCount -->|2 to N-1| SilentIncrement[(Silent: Increment Count)]
    SilentIncrement --> End9([Done])
    
    CheckCount -->|>= Threshold| RestrictUser[Apply Restriction<br/>Mute Permissions]
    RestrictUser --> MarkRestricted[(Mark as Restricted<br/>in Database)]
    MarkRestricted --> SendRestrictionMsg[Send Restriction Notice<br/>with DM Link]
    SendRestrictionMsg --> End10([Done])
    
    %% DM Flow
    UpdateType -->|Private Message| CheckInGroup{User in<br/>Group?}
    CheckInGroup -->|No| SendNotInGroup[Send: Not in Group]
    CheckInGroup -->|Yes| CheckPendingCaptcha{Has Pending<br/>Captcha?}
    
    CheckPendingCaptcha -->|Yes| SendCaptchaRedirect[Send: Complete Captcha<br/>in Group First]
    CheckPendingCaptcha -->|No| CheckDMProfile[Check Profile]
    
    CheckDMProfile --> DMProfileComplete{Profile<br/>Complete?}
    DMProfileComplete -->|No| SendMissing[Send: Missing Items]
    DMProfileComplete -->|Yes| CheckBotRestricted{Restricted<br/>by Bot?}
    
    CheckBotRestricted -->|No| SendNoRestriction[Send: No Bot Restriction]
    CheckBotRestricted -->|Yes| CheckCurrentStatus{Currently<br/>Restricted?}
    
    CheckCurrentStatus -->|No| ClearRecord[(Clear Database Record)]
    ClearRecord --> SendAlreadyUnrestricted[Send: Already Unrestricted]
    
    CheckCurrentStatus -->|Yes| UnrestrictUser[Remove Restriction]
    UnrestrictUser --> ClearRecord2[(Clear Database Record)]
    ClearRecord2 --> SendSuccess[Send: Success Message]
    
    %% Scheduler Job (Background)
    StartJobs -.->|Every 5 min| SchedulerJob[Auto-Restriction Job]
    SchedulerJob --> QueryDB[(Query Warnings Past<br/>Time Threshold)]
    QueryDB --> HasExpired{Expired<br/>Warnings?}
    
    HasExpired -->|No| EndJob([Wait Next Cycle])
    HasExpired -->|Yes| CheckKicked{User<br/>Kicked?}
    
    CheckKicked -->|Yes| ClearKicked[(Clear Record)]
    ClearKicked --> NextUser{More<br/>Users?}
    
    CheckKicked -->|No| ApplyTimeRestriction[Apply Restriction<br/>Mute Permissions]
    ApplyTimeRestriction --> MarkTimeRestricted[(Mark as Restricted)]
    MarkTimeRestricted --> SendTimeNotice[Send Time-Based<br/>Restriction Notice]
    SendTimeNotice --> NextUser
    
    NextUser -->|Yes| CheckKicked
    NextUser -->|No| EndJob
    
    %% Command Handlers - Verify/Unverify
    UpdateType -->|/verify Command| CheckAdminVerify{Is Admin?}
    CheckAdminVerify -->|No| DenyVerify[Send: Admin Only]
    CheckAdminVerify -->|Yes| AddWhitelist[(Add User to<br/>Photo Whitelist)]
    AddWhitelist --> UnrestrictVerified[Unrestrict User]
    UnrestrictVerified --> DeleteWarnings[(Delete Warning Records)]
    DeleteWarnings --> CheckWarningsExist{Had<br/>Warnings?}
    CheckWarningsExist -->|Yes| SendClearance[Send Clearance Notification<br/>to Warning Topic]
    CheckWarningsExist -->|No| SendVerifySuccess[Send: User Verified]
    SendClearance --> SendVerifySuccess
    
    UpdateType -->|/unverify Command| CheckAdminUnverify{Is Admin?}
    CheckAdminUnverify -->|No| DenyUnverify[Send: Admin Only]
    CheckAdminUnverify -->|Yes| RemoveWhitelist[(Remove from Whitelist)]
    RemoveWhitelist --> SendUnverifySuccess[Send: User Unverified]
    
    %% Forwarded Message Handler
    UpdateType -->|Forwarded Message<br/>in DM| CheckAdminForward{Is Admin?}
    CheckAdminForward -->|No| DenyForward[Send: Admin Only]
    CheckAdminForward -->|Yes| ExtractUser{Extract<br/>User Info?}
    ExtractUser -->|Success| SendButtons[Send Verify/Unverify Buttons]
    ExtractUser -->|Failed| SendExtractError[Send: Cannot Extract User]
    
    %% Callback Handlers
    UpdateType -->|Verify Button| ProcessVerify[Process Verify Callback]
    ProcessVerify --> AddWhitelist
    UpdateType -->|Unverify Button| ProcessUnverify[Process Unverify Callback]
    ProcessUnverify --> RemoveWhitelist
    
    classDef processNode fill:#1a1a2e,stroke:#16213e,color:#eee
    classDef decisionNode fill:#0f3460,stroke:#16213e,color:#eee
    classDef dataNode fill:#16213e,stroke:#0f3460,color:#eee
    classDef actionNode fill:#533483,stroke:#16213e,color:#eee
    classDef endNode fill:#e94560,stroke:#16213e,color:#eee
    classDef startNode fill:#1a5f7a,stroke:#16213e,color:#eee
    
    class Init,FetchAdmins,RecoverPending,StartJobs,Poll,CheckProfile,CheckDMProfile,RestrictAndChallenge,StorePending,ScheduleTimeout,WaitCaptcha,StartProbation,StartProbationAfter processNode
    class UpdateType,RecoverCaptcha,TopicGuard,IsAdmin,CheckBot,CheckWhitelist,ProfileComplete,CheckMode,CheckCount,CheckInGroup,CheckPendingCaptcha,DMProfileComplete,CheckBotRestricted,CheckCurrentStatus,HasExpired,CheckKicked,NextUser,CheckAdminVerify,CheckAdminUnverify,CaptchaAnswer,CheckCaptchaEnabled,CheckProbation,CheckExpired,CheckViolation,CheckWhitelisted,ViolationCount,CheckWarningsExist,CheckAdminForward,ExtractUser decisionNode
    class IncrementDB,SilentIncrement,MarkRestricted,ClearRecord,ClearRecord2,QueryDB,ClearKicked,MarkTimeRestricted,AddWhitelist,RemoveWhitelist,IncrementViolation,ClearProbation,DeleteWarnings dataNode
    class DeleteMsg,SendWarning,SendFirstWarning,RestrictUser,SendRestrictionMsg,SendNotInGroup,SendCaptchaRedirect,SendMissing,SendNoRestriction,SendAlreadyUnrestricted,UnrestrictUser,SendSuccess,ApplyTimeRestriction,SendTimeNotice,SchedulerJob,SendVerifySuccess,SendUnverifySuccess,DenyVerify,DenyUnverify,UnrestrictMember,KickMember,UpdateMessage,CancelTimeout,ShowError,DeleteSpam,SendSpamWarning,RestrictSpammer,SendSpamRestriction,UnrestrictVerified,SendClearance,DenyForward,SendButtons,SendExtractError,ProcessVerify,ProcessUnverify actionNode
    class End1,End2,End3,End4,End5,End6,End7,End8,End9,End10,EndJob,StartProbation endNode
    class Start startNode
```

## How It Works

### Architecture

The bot is organized into clear modules for maintainability:

- **main.py**: Entry point with python-telegram-bot's JobQueue integration and graceful shutdown
- **handlers/**: Message processing logic
  - `message.py`: Monitors group messages and sends warnings/restrictions
  - `dm.py`: Handles DM unrestriction flow
  - `topic_guard.py`: Protects warning topic from unauthorized messages
  - `captcha.py`: Captcha verification for new members
  - `anti_spam.py`: Anti-spam enforcement for users on probation
  - `verify.py`: /verify and /unverify command handlers
- **services/**: Business logic and utilities
  - `scheduler.py`: JobQueue background job that runs every 5 minutes for time-based auto-restrictions
  - `user_checker.py`: Profile validation (photo + username check)
  - `bot_info.py`: Caches bot metadata to avoid repeated API calls
  - `telegram_utils.py`: Shared telegram utilities (user status checks, etc.)
  - `captcha_recovery.py`: Captcha timeout recovery on bot restart
- **database/**: Data persistence
  - `service.py`: Database operations with SQLite
  - `models.py`: Data models using SQLModel (UserWarning, PhotoVerificationWhitelist, PendingCaptchaValidation, NewUserProbation)
- **config.py**: Environment configuration using Pydantic
- **constants.py**: Centralized message templates and utilities for consistent formatting across handlers

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
- Messages from regular users are automatically deleted

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
| `RESTRICT_FAILED_USERS` | Enable progressive restriction mode | `false` |
| `WARNING_THRESHOLD` | Messages before restriction (message-based) | `3` |
| `WARNING_TIME_THRESHOLD_MINUTES` | Minutes before auto-restriction (time-based) | `180` (3 hours) |
| `CAPTCHA_ENABLED` | Enable captcha verification for new members | `false` |
| `CAPTCHA_TIMEOUT_SECONDS` | Seconds before kicking unverified members | `120` (2 minutes) |
| `NEW_USER_PROBATION_HOURS` | Hours new users can't send links/forwards | `72` (3 days) |
| `NEW_USER_VIOLATION_THRESHOLD` | Spam violations before restriction | `3` |
| `DATABASE_PATH` | SQLite database path | `data/bot.db` |
| `RULES_LINK` | Link to group rules message | `https://t.me/pythonID/290029/321799` |
| `LOGFIRE_ENABLED` | Enable Logfire logging integration | `true` |
| `LOGFIRE_TOKEN` | Logfire API token (optional) | None |
| `LOG_LEVEL` | Logging level (DEBUG/INFO/WARNING/ERROR) | `INFO` |

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
