from datetime import timedelta

from django.utils import timezone


def parse_date_range(request, default="this_month"):
    today = timezone.localdate()
    preset = (request.GET.get("range") or default).strip()
    start_raw = request.GET.get("start")
    end_raw = request.GET.get("end")
    start = end = None
    if preset == "today":
        start = end = today
    elif preset == "yesterday":
        start = end = today - timedelta(days=1)
    elif preset == "this_week":
        start = today - timedelta(days=today.weekday())
        end = today
    elif preset == "this_month":
        start = today.replace(day=1)
        end = today
    elif preset == "previous_month":
        first = today.replace(day=1)
        end = first - timedelta(days=1)
        start = end.replace(day=1)
    elif preset == "custom" or start_raw or end_raw:
        preset = "custom"
        start = _parse(start_raw) or today.replace(day=1)
        end = _parse(end_raw) or today
    else:
        start = today.replace(day=1)
        end = today
        preset = "this_month"
    if start and end and start > end:
        start, end = end, start
    return start, end, preset


def _parse(value):
    if not value:
        return None
    try:
        from datetime import date

        return date.fromisoformat(value)
    except ValueError:
        return None
