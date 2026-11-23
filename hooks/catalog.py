"""MkDocs hook: builds the course catalogue for rbrooksdk.github.io.

Runs on every build (and therefore every night in CI):

1. reads data/catalog.yml and data/supervision.yml,
2. for each catalogue entry with `repo:` fetches that repo's course.yml
   (if it has one) and merges it on top,
3. if `discover: true`, finds other public repos under the owner that have a
   course.yml and adds them (so a new course needs no change here),
4. computes status (running / upcoming / completed), progress and
   "up next" for every course, using today's date in Copenhagen,
5. exposes the result to the templates as `config.extra.catalog`, and
   writes data/status.json (a small snapshot the nightly job commits when
   progress changes).

Network failures never break the build: the entry from catalog.yml is used.

Environment variables (all optional):
  GITHUB_TOKEN  used for the repo listing in discovery (higher rate limit)
  RB_OFFLINE=1  skip all network calls (fast local builds)
  RB_TODAY      pretend today is this date (YYYY-MM-DD), for testing
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

log = logging.getLogger("mkdocs.hooks.catalog")

TZ = ZoneInfo("Europe/Copenhagen")
AREA_LABELS = {
    "stat": "Statistics & probability",
    "math": "Mathematics",
    "ml": "ML & AI",
    "other": "Other",
}


# ---------------------------------------------------------------- network --

def _get(url: str, token: str | None = None, timeout: float = 8.0) -> bytes | None:
    headers = {"User-Agent": "rbrooksdk-site-build"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
            return r.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        log.debug("fetch failed %s: %s", url, exc)
        return None


def _fetch_course_yml(owner: str, repo: str) -> dict | None:
    raw = _get(f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/course.yml")
    if not raw:
        return None
    try:
        data = yaml.safe_load(raw.decode("utf-8"))
    except yaml.YAMLError as exc:
        log.warning("course.yml in %s is not valid YAML (%s) — ignored", repo, exc)
        return None
    if not isinstance(data, dict):
        log.warning("course.yml in %s is not a mapping — ignored", repo)
        return None
    return data


def _list_repos(owner: str, token: str | None) -> list[str]:
    names: list[str] = []
    for page in range(1, 6):
        raw = _get(
            f"https://api.github.com/users/{owner}/repos?per_page=100&type=owner&page={page}",
            token,
        )
        if not raw:
            break
        batch = json.loads(raw)
        if not batch:
            break
        names += [r["name"] for r in batch if not r.get("fork") and not r.get("archived")]
    return names


# ----------------------------------------------------------------- status --

def _as_date(value):
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _fmt(d: dt.date) -> str:
    return f"{d.day} {d.strftime('%b')} {d.year}"


def _compute(entry: dict, owner: str, today: dt.date) -> dict:
    c = dict(entry)
    repo = c.get("repo")
    c.setdefault("url", f"https://{owner.lower()}.github.io/{repo}/" if repo else "#")
    c.setdefault("code", (repo or "").split("_")[0].upper())
    c.setdefault("title", repo or c["code"])
    c.setdefault("area", "other")
    c.setdefault("lang", "en")
    c.setdefault("glyph", "∑")
    c.setdefault("description", "")
    c["area_label"] = AREA_LABELS.get(c["area"], c["area"])

    sessions = []
    for i, s in enumerate(c.get("sessions") or [], start=1):
        if isinstance(s, str):
            s = {"title": s}
        s = dict(s)
        if False in s:  # YAML 1.1 reads the key `no` as boolean False
            s["no"] = s.pop(False)
        s.setdefault("no", i)
        s["date"] = _as_date(s.get("date"))
        sessions.append(s)
    sessions.sort(key=lambda s: s["no"])
    c["sessions"] = sessions

    total = c.get("total") or len(sessions) or None
    done = c.get("current")
    status = c.get("status")
    dated = [s["date"] for s in sessions if s["date"]]
    # with a manual `current`, a few dated sessions only label "up next"
    use_dates = c.get("current") is None
    starts = _as_date(c.get("starts")) or (min(dated) if dated and use_dates else None)
    ends = _as_date(c.get("ends")) or (max(dated) if dated else None)

    if done is None and dated:
        done = sum(1 for s in sessions if s["date"] and s["date"] <= today)

    if status is None:
        if starts and today < starts:
            status = "upcoming"
        elif ends and today > ends:
            status = "completed"
        elif done is not None or dated:
            status = "running"
        else:
            status = "completed"

    if status == "completed" and total:
        done = total
    if status == "upcoming":
        done = 0

    nxt = None
    if status == "running" and done is not None:
        nxt = next((s for s in sessions if s["no"] == done + 1), None)
        if nxt is None and c.get("next"):
            nxt = {"no": done + 1, "title": c["next"], "date": None}

    c.update(
        status=status,
        total=total,
        done=done or 0,
        pct=round(100 * (done or 0) / total) if total else 0,
        has_progress=status == "running" and bool(total),
        next=(
            {
                "no": nxt["no"],
                "title": nxt["title"],
                "date": _fmt(nxt["date"]) if nxt.get("date") else None,
            }
            if nxt
            else None
        ),
        starts_label=(f"Starts {_fmt(starts)} · week {starts.isocalendar().week}" if starts else None),
        year=int(c.get("year") or (starts.year if starts else today.year)),
        term=c.get("term") or (str(starts.year) if starts else ""),
    )
    # dates are not JSON serialisable; keep templates simple
    c["sessions"] = [
        {"no": s["no"], "title": s["title"], "date": _fmt(s["date"]) if s["date"] else None}
        for s in sessions
    ]
    c.pop("starts", None)
    c.pop("ends", None)
    return c


def _palette(cat: dict) -> list[dict]:
    """Items for the Ctrl K palette (searched client-side)."""
    items: list[dict] = []
    for c in cat["running"]:
        if c["next"]:
            items.append({"kind": c["code"], "label": f"Session {c['next']['no']} · {c['next']['title']}", "hint": "up next", "href": c["url"]})
    for c in cat["all"]:
        hint = {"running": "running now", "upcoming": "coming up"}.get(c["status"], c["term"])
        items.append({"kind": c["code"], "label": c["title"], "hint": hint, "href": c["url"]})
        if c["status"] in ("running", "upcoming"):
            for s in c["sessions"]:
                items.append({"kind": c["code"], "label": f"{s['no']:02d} · {s['title']}", "hint": "session", "href": c["url"], "deep": True})
    items += [
        {"kind": "page", "label": "Home", "hint": "page", "href": "/"},
        {"kind": "page", "label": "All courses by year", "hint": "page", "href": "/courses/"},
        {"kind": "page", "label": "Supervision and project ideas", "hint": "page", "href": "/supervision/"},
        {"kind": "page", "label": "Books and resources", "hint": "page", "href": "/resources/"},
        {"kind": "page", "label": "Blog", "hint": "page", "href": "/blog/"},
    ]
    items += [{"kind": "book", "label": b["title"], "hint": "book", "href": b["url"]} for b in cat["books"]]
    items += [{"kind": "tool", "label": r["title"], "hint": r.get("kind", "resource"), "href": r["url"]} for r in cat["resources"]]
    items += [
        {"kind": "link", "label": "GitHub — RBrooksDK", "hint": "external", "href": "https://github.com/RBrooksDK/"},
        {"kind": "link", "label": "LinkedIn", "hint": "external", "href": "https://www.linkedin.com/in/rbrooks-dk/"},
        {"kind": "mail", "label": "rib@via.dk", "hint": "email", "href": "mailto:rib@via.dk"},
    ]
    return items


# ------------------------------------------------------------------- hook --

def on_config(config, **kwargs):
    root = Path(config.config_file_path).parent
    data_dir = root / "data"
    cat = yaml.safe_load((data_dir / "catalog.yml").read_text(encoding="utf-8")) or {}
    sup = yaml.safe_load((data_dir / "supervision.yml").read_text(encoding="utf-8")) or {}

    owner = cat.get("owner", "RBrooksDK")
    offline = os.environ.get("RB_OFFLINE") == "1"
    token = os.environ.get("GITHUB_TOKEN")
    today = _as_date(os.environ.get("RB_TODAY")) or dt.datetime.now(TZ).date()

    entries = [dict(e) for e in cat.get("courses") or []]
    known = {e["repo"] for e in entries if e.get("repo")}

    if not offline:
        for e in entries:
            if e.get("repo"):
                remote = _fetch_course_yml(owner, e["repo"])
                if remote:
                    e.update(remote)
                    log.info("catalog: merged course.yml from %s", e["repo"])
        if cat.get("discover"):
            for name in _list_repos(owner, token):
                if name in known or name.lower() == f"{owner.lower()}.github.io":
                    continue
                remote = _fetch_course_yml(owner, name)
                if remote:
                    remote.setdefault("repo", name)
                    entries.append(remote)
                    log.info("catalog: discovered %s via course.yml", name)

    courses = [_compute(e, owner, today) for e in entries if not e.get("hidden")]
    running = [c for c in courses if c["status"] == "running"]
    upcoming = sorted(
        (c for c in courses if c["status"] == "upcoming"),
        key=lambda c: c.get("starts_label") or "",
    )
    completed = [c for c in courses if c["status"] == "completed"]
    years = sorted({c["year"] for c in completed}, reverse=True)

    catalog = {
        "today": _fmt(today),
        "running": running,
        "upcoming": upcoming,
        "earlier": [{"year": y, "courses": [c for c in completed if c["year"] == y]} for y in years],
        "all": running + upcoming + completed,
        "areas": [
            {"key": k, "label": v}
            for k, v in AREA_LABELS.items()
            if any(c["area"] == k for c in courses)
        ],
        "resources": cat.get("resources") or [],
        "books": cat.get("books") or [],
        "supervision": sup,
    }
    catalog["palette"] = _palette(catalog)
    config["extra"]["catalog"] = catalog

    snapshot = {
        c.get("repo") or c["code"]: {"status": c["status"], "done": c["done"], "total": c["total"]}
        for c in courses
    }
    (data_dir / "status.json").write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    log.info(
        "catalog: %d running, %d upcoming, %d completed (today %s)",
        len(running), len(upcoming), len(completed), today,
    )
    return config
