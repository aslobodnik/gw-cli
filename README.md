# gw

Unified CLI for Google Workspace. One command for Gmail, Calendar, Drive, Docs, Sheets, and Slides.

## Quick start for AI agents

If you use [Claude Code](https://docs.anthropic.com/en/docs/claude-code), drop the skill file and go:

```bash
# Install
git clone https://github.com/aslobodnik/gw-cli.git
cd gw-cli && python3 -m venv .venv && .venv/bin/pip install -e .

# Add to PATH (the gw wrapper activates the venv automatically)
echo 'export PATH="'"$(pwd)"':$PATH"' >> ~/.zshrc && source ~/.zshrc

# Auth (one-time, opens browser -- see GOOGLE_SETUP.md first)
gw auth add you@gmail.com

# Install the Claude Code skill
cp gw.skill ~/.claude/skills/

# Add routing rules to your CLAUDE.md
cat >> ~/.claude/CLAUDE.md << 'EOF'
# ROUTING RULES
- Calendar, schedule, events, meetings → invoke `/gw` skill
- Email, inbox, messages → invoke `/gw` skill
- Google Drive, files, folders → invoke `/gw` skill
- Google Docs, Sheets, Slides → invoke `/gw` skill
EOF
```

That's it. Say "check my email" or "what's my schedule" and your agent handles the rest.

For other AI assistants, the skill file is a zip archive containing a `SKILL.md` reference and workflow guides -- unzip and feed to your agent however it consumes instructions.

---

## The rest of the README (for humans)

### Prerequisites

- Python 3.10+
- Git

On a fresh Mac, both may require Xcode Command Line Tools (`xcode-select --install`).

### Install

```bash
git clone https://github.com/aslobodnik/gw-cli.git
cd gw-cli
python3 -m venv .venv
.venv/bin/pip install -e .
```

Add `gw` to your PATH so you can run it from anywhere (the wrapper script activates the venv automatically):

```bash
# Add to your ~/.zshrc or ~/.bashrc
export PATH="$HOME/path/to/gw-cli:$PATH"
```

### Google OAuth credentials

You need a Google Cloud project with OAuth 2.0 credentials. See **[GOOGLE_SETUP.md](GOOGLE_SETUP.md)** for the full walkthrough. Cumbersome the first time, straightforward after.

Once you have your credentials, download the `client_secrets.json` from Google Cloud Console and place it in `~/.google_workspace_mcp/credentials/` or the project root.

```bash
gw auth add you@gmail.com
```

Opens a browser for OAuth consent. Subsequent accounts reuse the same OAuth app.

### Config (optional)

```bash
mkdir -p ~/.config/gw-cli
cp config.example.yaml ~/.config/gw-cli/config.yaml
```

```yaml
# ~/.config/gw-cli/config.yaml
default_account: you@gmail.com

aliases:
  work: you@company.com
  personal: you@gmail.com

calendar_aliases:
  work: you@company.com
  personal: you@gmail.com

timezone: America/New_York
```

Without a config, pass `-a` on every command.

### Usage

#### Authentication

```bash
gw auth add you@gmail.com              # add account (opens browser)
gw auth list                           # show linked accounts
gw auth remove you@gmail.com           # remove account
gw -a work mail inbox                  # use account alias
```

#### Gmail

```bash
gw mail inbox                          # latest 10 emails
gw mail inbox --unread --days 3        # unread from last 3 days
gw mail inbox --limit 25               # more results
gw mail search "from:boss" --all       # search across all mail
gw mail search "invoice" -A            # search all accounts
gw mail read <id>                      # read a message
gw mail read <id> --brief              # cleaned-up summary (strips tracking URLs)
gw mail read <id> --peek               # read without marking as read
gw mail read <id1> <id2> <id3>         # read multiple messages
gw mail send to@x.com "Subj" "Body"   # send
gw mail reply <id> "Reply body"        # reply
gw mail download <id>                  # download attachments
gw mail download <id> -d ~/Downloads   # download to specific folder
gw mail star/unstar <id>               # star management
gw mail archive <id>                   # remove from inbox
gw mail trash <id>                     # move to trash
gw mail mark-read <id>                 # mark as read
gw mail mark-unread <id>              # mark as unread
gw mail spam <id>                      # report as spam
gw mail spam <id> --block              # report spam + block sender
gw mail block <id>                     # block sender (auto-deletes future mail)
gw mail labels                         # list custom labels
gw mail label <id> "Work"             # add label to message
gw mail unlabel <id> "Work"           # remove label
gw mail accounts                       # list accounts & aliases
```

Mail config subcommands:

```bash
gw mail config set timezone US/Pacific
gw mail config get default_account
gw mail config alias work you@company.com
```

#### Calendar

```bash
gw cal today                           # today's events (all calendars)
gw cal tomorrow                        # tomorrow's events
gw cal week                            # next 7 days
gw cal next                            # single upcoming event with countdown
gw cal add "Meeting" "tomorrow 2pm"    # create event
gw cal add "Lunch" "fri noon" -l "123 Main St" -i friend@gmail.com --meet
gw cal add "Standup" "Mon 9am" -i a@x.com -i b@x.com
gw cal delete <id>                     # delete event
gw cal invites                         # pending invitations
gw cal accept <id>                     # accept invite
gw cal decline <id>                    # decline invite
gw cal calendars                       # list accessible calendars
gw cal --tz Asia/Kolkata today         # override timezone
```

Time parsing supports natural language: `today 2pm`, `tomorrow 10:30am`, `Thu noon`, `next Monday`, `Feb 12 10:30am`, `2026-02-12 10:30am`. Add a range with a dash: `tomorrow 10:30am-1:30pm`.

#### Drive

```bash
gw drive ls                            # list recent files
gw drive ls "quarterly report"         # search
gw drive ls -l 50                      # more results
gw drive info <id>                     # detailed metadata & sharing info
gw drive upload file.pdf               # upload
gw drive upload file.pdf -f <folder>   # upload to folder
gw drive download <id>                 # download
gw drive download <id> -o ~/out.pdf    # download to path
gw drive mkdir "Project Files"         # create folder
gw drive mkdir "Sub" -p <parent_id>    # nested folder
gw drive trash <id>                    # move to trash
gw drive untrash <id>                  # restore from trash
gw drive share <id> user@x.com         # share (reader by default)
gw drive share <id> user@x.com -r writer  # share with write access
gw drive unshare <id> user@x.com       # revoke access
```

#### Docs, Sheets, Slides

```bash
gw doc create "Meeting Notes"          # create Google Doc
gw doc read <id>                       # read as plain text
gw doc append <id> "New paragraph"     # append text

gw sheet create "Budget"               # create Google Sheet
gw sheet read <id>                     # read default sheet
gw sheet read <id> "Sheet1!A1:C10"     # read specific range
gw sheet write <id> "A1:B2" '[["a","b"],["c","d"]]'  # write cells

gw slides create "Q1 Review"           # create presentation
gw slides read <id>                    # read all slide text
gw slides add <id> "Slide Title" "Body text"  # add slide
```

### Short IDs

All commands accept short IDs (last 8-12 characters of the full ID). IDs from recent list/search results are cached for fast resolution.

## License

MIT
