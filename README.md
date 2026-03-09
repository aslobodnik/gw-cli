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

```bash
gw mail inbox                          # latest emails
gw mail inbox --unread --days 3        # unread from last 3 days
gw mail search "from:boss" --all       # search across all mail
gw mail read <id>                      # read a message
gw mail send to@x.com "Subj" "Body"   # send (agent asks before sending)
gw mail reply <id> "Reply body"        # reply
gw mail star/archive/trash <id>        # organize

gw cal today                           # today's events
gw cal week                            # this week
gw cal add "Meeting" "tomorrow 2pm"    # create event
gw cal add "Lunch" "fri noon" -l "123 Main St" -i friend@gmail.com --meet
gw cal invites                         # pending invitations
gw cal accept/decline <id>             # respond to invite

gw drive ls                            # list files
gw drive ls "quarterly report"         # search
gw drive upload file.pdf               # upload
gw drive download <id>                 # download
gw drive share <id> user@x.com         # share

gw doc create/read/append              # Google Docs
gw sheet create/read/write             # Google Sheets
gw slides create/read/add              # Google Slides

gw -a other@gmail.com mail inbox       # switch accounts
gw auth list                           # show linked accounts
```

## License

MIT
