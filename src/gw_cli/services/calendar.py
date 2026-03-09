"""Google Calendar API client."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..config import get_calendar_aliases, get_timezone


def _get_tz(override: str | None = None) -> ZoneInfo:
    return ZoneInfo(override) if override else ZoneInfo(get_timezone())


def now(tz_override: str | None = None) -> datetime:
    """Current time in local timezone."""
    return datetime.now(_get_tz(tz_override))


def to_rfc3339(dt: datetime) -> str:
    """Convert datetime to RFC3339 string."""
    return dt.isoformat()


def _parse_time_part(s: str) -> tuple[int, int]:
    """Parse a single time like '10:30am', '2pm', '14:00' into (hour, minute)."""
    import re

    s = s.strip().lower().rstrip(".")
    # 12-hour: 10:30am, 2pm, 1030am
    m = re.match(r"(\d{1,2}):?(\d{2})?\s*(am|pm)", s)
    if m:
        h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        if ap == "pm" and h != 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        return h, mi
    # 24-hour: 14:00, 9:30
    m = re.match(r"(\d{1,2}):(\d{2})", s)
    if m:
        return int(m.group(1)), int(m.group(2))
    # bare number: "9", "14"
    m = re.match(r"(\d{1,2})", s)
    if m:
        return int(m.group(1)), 0
    raise ValueError(f"Cannot parse time: {s}")


def _resolve_day(day_str: str, base: datetime) -> datetime:
    """Resolve a day reference to a date. Always picks a future date for day names."""
    import re
    from dateutil import parser as dateutil_parser

    day_str = day_str.strip().lower()
    midnight = base.replace(hour=0, minute=0, second=0, microsecond=0)

    if not day_str or day_str == "today":
        return midnight
    if day_str == "tomorrow":
        return midnight + timedelta(days=1)

    # Day name: mon, tue, wed, thu, fri, sat, sun (or full names)
    day_names = {
        "mon": 0, "monday": 0, "tue": 1, "tuesday": 1, "wed": 2, "wednesday": 2,
        "thu": 3, "thursday": 3, "fri": 4, "friday": 4, "sat": 5, "saturday": 5,
        "sun": 6, "sunday": 6,
    }
    if day_str in day_names:
        target = day_names[day_str]
        current = base.weekday()
        delta = (target - current) % 7
        if delta == 0:
            delta = 7  # next week if same day
        return midnight + timedelta(days=delta)

    # Explicit date: "Feb 12", "2026-02-12", "02/12", etc.
    try:
        parsed = dateutil_parser.parse(day_str, fuzzy=True, default=base)
        result = parsed.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=base.tzinfo)
        # If parsed date is in the past (and no year was explicit), bump to next year
        if result < midnight and not re.search(r"\d{4}", day_str):
            result = result.replace(year=result.year + 1)
        return result
    except Exception:
        return midnight


def parse_time(time_str: str) -> tuple[datetime, datetime]:
    """Parse natural language time to start/end datetimes.

    Supported formats:
      "today 2pm", "tomorrow 10:30am-1:30pm", "Thu 10:30am-1:30pm",
      "Feb 12 10:30am", "2026-02-12 10:30am-1:30pm", "noon", "morning"
    """
    import re

    tz = _get_tz()
    time_str = time_str.strip()
    base = now()
    duration = timedelta(hours=1)

    # Split into day portion and time portion
    # Try to find a time-like pattern (digits with am/pm or colon)
    time_pattern = re.search(
        r"("
        r"\d{1,2}:?\d{0,2}\s*(?:am|pm)\s*-\s*\d{1,2}:?\d{0,2}\s*(?:am|pm)"  # 2pm-4pm
        r"|\d{1,2}:?\d{0,2}\s*-\s*\d{1,2}:?\d{0,2}\s*(?:am|pm)"              # 2-4pm
        r"|\d{1,2}:?\d{0,2}\s*(?:am|pm)"                                       # 2pm
        r"|\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}"                                  # 14:00-16:00
        r"|\d{1,2}:\d{2}"                                                       # 14:00
        r")",
        time_str,
        re.IGNORECASE,
    )

    if time_pattern:
        day_part = time_str[: time_pattern.start()].strip()
        time_part = time_pattern.group(0).strip()
    else:
        # Check for keyword times (longest first to avoid "noon" matching "afternoon")
        lower = time_str.lower()
        keywords = {"afternoon": (14, 0), "morning": (9, 0), "evening": (18, 0), "noon": (12, 0)}
        found_keyword = None
        day_part = lower
        for kw, (h, m) in keywords.items():
            if kw in lower:
                found_keyword = (h, m)
                day_part = lower.replace(kw, "").strip()
                break

        if found_keyword:
            day = _resolve_day(day_part, base)
            start = day.replace(hour=found_keyword[0], minute=found_keyword[1])
            return start, start + duration

        # No time found at all — default to 9am
        day = _resolve_day(time_str, base)
        start = day.replace(hour=9)
        return start, start + duration

    day = _resolve_day(day_part, base) if day_part else base.replace(hour=0, minute=0, second=0, microsecond=0)

    # Parse time range (e.g. "10:30am-1:30pm") or single time
    if "-" in time_part:
        parts = time_part.split("-", 1)
        # Propagate trailing am/pm to start time when missing (e.g. "2-4pm")
        start_raw, end_raw = parts[0].strip(), parts[1].strip()
        if not re.search(r"(?:am|pm)", start_raw, re.IGNORECASE):
            suffix = re.search(r"(am|pm)", end_raw, re.IGNORECASE)
            if suffix:
                start_raw = start_raw + suffix.group(1)
        start_h, start_m = _parse_time_part(start_raw)
        end_h, end_m = _parse_time_part(end_raw)
        start = day.replace(hour=start_h, minute=start_m)
        end = day.replace(hour=end_h, minute=end_m)
        if end <= start:
            end += timedelta(days=1)
        return start, end
    else:
        start_h, start_m = _parse_time_part(time_part)
        start = day.replace(hour=start_h, minute=start_m)
        return start, start + duration


def format_time(start: str, end: str | None = None, tz_override: str | None = None) -> str:
    """Format event time for display."""
    from dateutil import parser as dateutil_parser

    tz = _get_tz(tz_override)
    start_dt = dateutil_parser.parse(start)

    if "T" not in start:
        return "all day"

    start_dt = start_dt.astimezone(tz)
    hour = start_dt.hour
    minute = start_dt.minute

    if minute == 0:
        start_str = f"{hour % 12 or 12}{'am' if hour < 12 else 'pm'}"
    else:
        start_str = f"{hour % 12 or 12}:{minute:02d}{'am' if hour < 12 else 'pm'}"

    if end and "T" in end:
        end_dt = dateutil_parser.parse(end).astimezone(tz)
        end_hour = end_dt.hour
        end_minute = end_dt.minute
        if end_minute == 0:
            end_str = f"{end_hour % 12 or 12}{'am' if end_hour < 12 else 'pm'}"
        else:
            end_str = f"{end_hour % 12 or 12}:{end_minute:02d}{'am' if end_hour < 12 else 'pm'}"
        return f"{start_str}-{end_str}"

    return start_str


def format_date(dt_str: str) -> str:
    """Format date for display: Mon 28."""
    from dateutil import parser as dateutil_parser

    dt = dateutil_parser.parse(dt_str)
    return dt.strftime("%a %-d")


def get_location_short(event: dict) -> str:
    """Get shortened location or Meet indicator."""
    location = event.get("location", "")
    hangout = event.get("hangoutLink", "")

    if hangout:
        return "(Meet)"
    if location:
        parts = location.split(",")
        return parts[0][:20]
    return ""


class CalendarClient:
    """Google Calendar API wrapper."""

    def __init__(self, service, account: str, tz_override: str | None = None):
        self.service = service
        self.account = account
        self.tz_override = tz_override
        self._event_cache: dict[str, tuple[str, str]] = {}
        self._calendars: list[str] | None = None

    def _get_calendar_id(self, alias: str | None) -> str:
        """Resolve calendar alias to ID."""
        if not alias:
            return self.account
        aliases = get_calendar_aliases()
        return aliases.get(alias, alias)

    def _get_all_calendars(self) -> list[str]:
        """Get all accessible calendar IDs (cached)."""
        if self._calendars is not None:
            return self._calendars

        result = self.service.calendarList().list().execute()
        self._calendars = []
        for cal in result.get("items", []):
            cal_id = cal.get("id", "")
            if "holiday@group" in cal_id:
                continue
            self._calendars.append(cal_id)

        aliases = get_calendar_aliases()
        for cal_id in aliases.values():
            if cal_id not in self._calendars:
                self._calendars.append(cal_id)

        return self._calendars

    def _cache_event(self, event: dict, calendar_id: str) -> str:
        """Cache event and return short ID."""
        full_id = event.get("id", "")
        short_id = full_id[-8:]
        self._event_cache[short_id] = (full_id, calendar_id)
        return short_id

    def _resolve_event_id(self, short_id: str, calendar_id: str | None = None) -> tuple[str, str]:
        """Resolve short ID to full ID and calendar."""
        if short_id in self._event_cache:
            cached_full, cached_cal = self._event_cache[short_id]
            return cached_full, calendar_id or cached_cal

        # Search specific calendar or all calendars
        search_cals = [self._get_calendar_id(calendar_id)] if calendar_id else self._get_all_calendars()
        for cal_id in search_cals:
            try:
                events = self.list_events(calendar_id=cal_id, max_results=100)
                for e in events:
                    if e.get("id", "").endswith(short_id):
                        return e["id"], cal_id
            except Exception:
                continue  # skip inaccessible calendars, try next

        return short_id, calendar_id or self.account

    def list_events(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        calendar_id: str | None = None,
        max_results: int = 50,
    ) -> list[dict]:
        """List events in time range."""
        cal_id = self._get_calendar_id(calendar_id)
        start = start or now()
        end = end or (start + timedelta(days=7))

        result = self.service.events().list(
            calendarId=cal_id,
            timeMin=to_rfc3339(start),
            timeMax=to_rfc3339(end),
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        return result.get("items", [])

    def list_all_calendars(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict]:
        """List events from all calendars."""
        all_events = []
        for cal_id in self._get_all_calendars():
            try:
                events = self.list_events(start=start, end=end, calendar_id=cal_id)
                for e in events:
                    e["_calendar"] = cal_id
                    self._cache_event(e, cal_id)
                all_events.extend(events)
            except Exception:
                pass

        def sort_key(e):
            start = e.get("start", {})
            return start.get("dateTime", start.get("date", ""))

        return sorted(all_events, key=sort_key)

    def format_day(self, events: list[dict], show_date: bool = False) -> str:
        """Format events for a single day."""
        if not events:
            return "No events"

        lines = []
        if self.tz_override:
            lines.append(f"[Times shown in {self.tz_override}]")
        if show_date:
            first_start = events[0].get("start", {})
            date_str = first_start.get("dateTime", first_start.get("date", ""))
            lines.append(format_date(date_str))

        lines.append("| ID | Time | Event | Where |")
        lines.append("|----|------|-------|-------|")

        for e in events:
            start = e.get("start", {})
            end = e.get("end", {})
            start_str = start.get("dateTime", start.get("date", ""))
            end_str = end.get("dateTime", end.get("date", ""))

            short_id = e.get("id", "")[-8:]
            time = format_time(start_str, end_str, tz_override=self.tz_override)
            title = e.get("summary", "(no title)")[:25]
            where = get_location_short(e)

            lines.append(f"| {short_id} | {time} | {title} | {where} |")

        return "\n".join(lines)

    def format_week(self, events: list[dict]) -> str:
        """Format events for week view."""
        if not events:
            return "No events this week"

        lines = []
        if self.tz_override:
            lines.append(f"[Times shown in {self.tz_override}]")
        lines.append("| ID | Day | Time | Event | Where |")
        lines.append("|----|-----|------|-------|-------|")

        for e in events:
            start = e.get("start", {})
            end = e.get("end", {})
            start_str = start.get("dateTime", start.get("date", ""))
            end_str = end.get("dateTime", end.get("date", ""))

            short_id = e.get("id", "")[-8:]
            day = format_date(start_str)
            time = format_time(start_str, end_str, tz_override=self.tz_override)
            title = e.get("summary", "(no title)")[:22]
            where = get_location_short(e)

            lines.append(f"| {short_id} | {day} | {time} | {title} | {where} |")

        return "\n".join(lines)

    def today(self) -> str:
        """Get today's events."""
        start = now().replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        events = self.list_all_calendars(start=start, end=end)
        return self.format_day(events, show_date=True)

    def tomorrow(self) -> str:
        """Get tomorrow's events."""
        start = (now() + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        events = self.list_all_calendars(start=start, end=end)
        return self.format_day(events, show_date=True)

    def week(self) -> str:
        """Get next 7 days of events."""
        start = now().replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7)
        events = self.list_all_calendars(start=start, end=end)
        return self.format_week(events)

    def next_event(self) -> str:
        """Get next upcoming event."""
        from dateutil import parser as dateutil_parser

        events = self.list_all_calendars(start=now(), end=now() + timedelta(days=7))
        if not events:
            return "No upcoming events"

        e = events[0]
        start = e.get("start", {})
        start_str = start.get("dateTime", start.get("date", ""))
        title = e.get("summary", "(no title)")
        where = get_location_short(e)

        start_dt = dateutil_parser.parse(start_str)
        if "T" in start_str:
            start_dt = start_dt.astimezone(_get_tz(self.tz_override))
            diff = start_dt - now()
            mins = int(diff.total_seconds() / 60)
            if mins < 60:
                time_until = f"in {mins}min"
            else:
                hours = mins // 60
                time_until = f"in {hours}h"
            time_str = format_time(start_str, tz_override=self.tz_override)
            result = f"{title} {time_until} ({time_str})"
        else:
            result = f"{title} ({format_date(start_str)})"

        if where:
            result += f" @ {where}"

        if self.tz_override:
            result = f"[{self.tz_override}] {result}"

        return result

    def add_event(
        self,
        title: str,
        time_str: str,
        calendar_id: str | None = None,
        add_meet: bool = False,
        location: str | None = None,
        attendees: list[str] | None = None,
    ) -> str:
        """Add a new event."""
        cal_id = self._get_calendar_id(calendar_id)
        start, end = parse_time(time_str)
        tz_name = get_timezone()

        body = {
            "summary": title,
            "start": {"dateTime": to_rfc3339(start), "timeZone": tz_name},
            "end": {"dateTime": to_rfc3339(end), "timeZone": tz_name},
        }

        if location:
            body["location"] = location

        if attendees:
            body["attendees"] = [{"email": e} for e in attendees]

        if add_meet:
            body["conferenceData"] = {
                "createRequest": {"requestId": f"meet-{start.timestamp()}"}
            }

        self.service.events().insert(
            calendarId=cal_id,
            body=body,
            conferenceDataVersion=1 if add_meet else 0,
            sendUpdates="all" if attendees else "none",
        ).execute()

        time_display = format_time(to_rfc3339(start), to_rfc3339(end))
        date_display = format_date(to_rfc3339(start))
        aliases = get_calendar_aliases()
        cal_short = [k for k, v in aliases.items() if v == cal_id]
        cal_label = f" ({cal_short[0]})" if cal_short else ""

        return f"Created: {title}, {date_display} {time_display}{cal_label}"

    def delete_event(self, event_id: str, calendar_id: str | None = None) -> str:
        """Delete an event."""
        full_id, cal_id = self._resolve_event_id(event_id, calendar_id)

        event = self.service.events().get(calendarId=cal_id, eventId=full_id).execute()
        title = event.get("summary", "(no title)")

        self.service.events().delete(calendarId=cal_id, eventId=full_id).execute()

        return f"Deleted: {title}"

    def pending_invites(self) -> str:
        """List pending invites (events needing response)."""
        events = self.list_all_calendars(start=now(), end=now() + timedelta(days=30))

        pending = []
        for e in events:
            attendees = e.get("attendees", [])
            for a in attendees:
                if a.get("email") == self.account and a.get("responseStatus") == "needsAction":
                    organizer = e.get("organizer", {}).get("displayName") or e.get("organizer", {}).get("email", "")
                    pending.append({
                        "id": e.get("id"),
                        "title": e.get("summary", "(no title)"),
                        "start": e.get("start", {}),
                        "organizer": organizer,
                    })

        if not pending:
            return "No pending invites"

        lines = ["| ID | Event | When | From |", "|----|-------|------|------|"]
        for p in pending:
            start = p["start"]
            start_str = start.get("dateTime", start.get("date", ""))
            when = f"{format_date(start_str)} {format_time(start_str, tz_override=self.tz_override)}"
            short_id = p["id"][-8:]
            lines.append(f"| {short_id} | {p['title'][:18]} | {when} | {p['organizer'][:12]} |")

        return "\n".join(lines)

    def respond_invite(self, event_id: str, response: str, calendar_id: str | None = None) -> str:
        """Accept or decline an invite."""
        full_id, cal_id = self._resolve_event_id(event_id, calendar_id)

        event = self.service.events().get(calendarId=cal_id, eventId=full_id).execute()
        title = event.get("summary", "(no title)")
        attendees = event.get("attendees", [])

        for a in attendees:
            if a.get("email") == self.account:
                a["responseStatus"] = response

        self.service.events().patch(
            calendarId=cal_id,
            eventId=full_id,
            body={"attendees": attendees},
        ).execute()

        action = "Accepted" if response == "accepted" else "Declined"
        return f"{action}: {title}"
