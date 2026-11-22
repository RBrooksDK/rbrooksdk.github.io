# How course progress gets onto the main site

The main site rebuilds itself **every night at 23:00** (GitHub Actions,
`.github/workflows/ci.yml`). During the build, `hooks/catalog.py`:

1. reads `data/catalog.yml` (all courses, books and resources shown on the site),
2. fetches `course.yml` from each course repository and merges it in,
3. finds any *other* public repo under RBrooksDK that has a `course.yml`
   and adds it automatically,
4. works out for each course whether it is upcoming, running or completed,
   how many sessions are done and what comes next.

Nothing needs to be committed for the nightly update.

## A new course (e.g. spring 2027)

1. Create the course repo as usual.
2. Copy `templates/course.yml` into the root of the repo and fill in the
   session dates once.
3. Push. The course appears on the main site the next night as
   "Starts … · week …", shows its progress while it runs, and moves to
   "Earlier editions" by itself after the last session.

No change to the main site is needed. If you want it on the site straight
away, open the main repo's **Actions → Build and deploy → Run workflow**.

## When a session moves or is cancelled

Change its date in `course.yml`, or set `current: N` to state how many
sessions are done.

## The autumn 2026 courses

STA1_26, SMP1_26 and MSE1_26 have no session dates, so their progress is set
by hand in `data/catalog.yml` (`current:`). They switch to "Completed" by
themselves after `ends: 2026-12-18`.

## Older courses, books and resources

These are listed directly in `data/catalog.yml`. Add a line there to show
something that has no `course.yml`. Set `hidden: true` to remove an entry
without deleting it.

## Local preview

```
pip install -r requirements.txt
mkdocs serve                  # fetches course.yml files
RB_OFFLINE=1 mkdocs serve     # no network, uses data/catalog.yml only
RB_TODAY=2027-03-01 mkdocs serve   # see the site as on another date
```
