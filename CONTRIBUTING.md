## Adding a New Service

1. Create `src/gw_cli/services/<name>.py` with a client class
   - Constructor takes API service + optional account
   - Methods return formatted strings
   - Import `resolve_id` from `..utils` if using Drive file IDs

2. Add `get_<name>_service()` to `auth.py`

3. Add Click subgroup to `cli.py`:
   ```python
   @main.group()
   @click.pass_context
   def <name>(ctx):
       """Description."""
       pass
   ```

4. Add service-specific config defaults to `config.py` if needed

5. Update `~/.claude/skills/gw/SKILL.md` with new commands
