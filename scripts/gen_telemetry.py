#!/usr/bin/env python3
"""Generate self-hosted neon telemetry SVGs from the GitHub GraphQL API.

Outputs (written to ../assets):
  telemetry.svg  - stat tiles (commits, merged PRs, issues, stars, repos, followers)
  languages.svg  - top languages by code size across public, non-fork repos
  activity.svg   - 52-week contribution heatmap

Env:
  GH_TOKEN       - token for api.github.com (the Actions GITHUB_TOKEN is enough)
  PROFILE_LOGIN  - GitHub login (default: Sana-oss)
Run with --placeholder (or without GH_TOKEN) to write "sync pending" images.
"""
import datetime
import html
import json
import os
import sys
import urllib.request

LOGIN = os.environ.get("PROFILE_LOGIN", "Sana-oss")
TOKEN = os.environ.get("GH_TOKEN")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")

BG, PANEL, MUTED, TEXT = "#0a0e17", "#111a2a", "#8A9BB5", "#E6F1FF"
CYAN, MAGENTA, GREEN, AMBER = "#00F2FF", "#FF2BD6", "#00FF41", "#FFB000"
FONT = "'Courier New', ui-monospace, Menlo, Consolas, monospace"

QUERY = """
query($login:String!){
  user(login:$login){
    followers{totalCount}
    pullRequests(states:MERGED){totalCount}
    issues{totalCount}
    repositories(ownerAffiliation:OWNER,isFork:false,privacy:PUBLIC,first:100){
      totalCount
      nodes{
        stargazerCount
        languages(first:10,orderBy:{field:SIZE,direction:DESC}){edges{size node{name}}}
      }
    }
    contributionsCollection{
      totalCommitContributions
      contributionCalendar{
        totalContributions
        weeks{contributionDays{contributionCount}}
      }
    }
  }
}
"""


def fetch():
    body = json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": "bearer " + TOKEN,
            "Content-Type": "application/json",
            "User-Agent": "profile-telemetry",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    if payload.get("errors"):
        raise SystemExit("GraphQL error: %s" % payload["errors"])
    return payload["data"]["user"]


def esc(s):
    return html.escape(str(s), quote=True)


def wrap(w, h, title, desc, body):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" '
        'role="img" aria-labelledby="t d">\n'
        '  <title id="t">%s</title>\n  <desc id="d">%s</desc>\n'
        '  <rect width="%d" height="%d" rx="10" fill="%s"/>\n'
        '  <rect x=".5" y=".5" width="%d" height="%d" rx="10" fill="none" stroke="#1d2a3d"/>\n'
        "%s</svg>\n"
    ) % (w, h, w, h, esc(title), esc(desc), w, h, BG, w - 1, h - 1, body)


def stamp(ok):
    if ok:
        return datetime.datetime.now(datetime.timezone.utc).strftime("SYNCED %Y-%m-%d UTC")
    return "SYNC PENDING - FIRST RUN OF THE TELEMETRY ACTION UPDATES THIS"


def telemetry_svg(u):
    if u:
        cc = u["contributionsCollection"]
        stars = sum(n["stargazerCount"] for n in u["repositories"]["nodes"])
        vals = [
            (cc["totalCommitContributions"], "COMMITS / YR", CYAN),
            (u["pullRequests"]["totalCount"], "PRS MERGED", MAGENTA),
            (u["issues"]["totalCount"], "ISSUES", GREEN),
            (stars, "STARS", AMBER),
            (u["repositories"]["totalCount"], "PUBLIC REPOS", CYAN),
            (u["followers"]["totalCount"], "FOLLOWERS", MAGENTA),
        ]
    else:
        labels = [("COMMITS / YR", CYAN), ("PRS MERGED", MAGENTA), ("ISSUES", GREEN),
                  ("STARS", AMBER), ("PUBLIC REPOS", CYAN), ("FOLLOWERS", MAGENTA)]
        vals = [("--", l, c) for l, c in labels]
    parts = ['  <g font-family="%s">\n' % FONT,
             '    <text x="30" y="34" font-size="14" letter-spacing="3" fill="%s">// LIVE TELEMETRY</text>\n' % MUTED]
    for i, (v, label, color) in enumerate(vals):
        x = 30 + i * 142
        parts.append(
            '    <rect x="%d" y="52" width="130" height="86" rx="6" fill="%s"/>\n'
            '    <rect x="%d" y="52" width="130" height="3" fill="%s"/>\n'
            '    <text x="%d" y="100" font-size="30" font-weight="700" text-anchor="middle" fill="%s">%s</text>\n'
            '    <text x="%d" y="124" font-size="11" letter-spacing="1" text-anchor="middle" fill="%s">%s</text>\n'
            % (x, PANEL, x, color, x + 65, TEXT, esc(v), x + 65, MUTED, esc(label))
        )
    parts.append('    <text x="30" y="166" font-size="11" letter-spacing="1" fill="%s">%s</text>\n' % (MUTED, esc(stamp(bool(u)))))
    parts.append("  </g>\n")
    desc = "Stat tiles for %s: commits in the last year, merged pull requests, issues, stars, public repos, followers." % LOGIN
    return wrap(900, 180, "Live telemetry", desc, "".join(parts))


def languages_svg(u):
    palette = [CYAN, MAGENTA, GREEN, AMBER, MUTED]
    rows = []
    if u:
        totals = {}
        for repo in u["repositories"]["nodes"]:
            for e in repo["languages"]["edges"]:
                totals[e["node"]["name"]] = totals.get(e["node"]["name"], 0) + e["size"]
        all_bytes = sum(totals.values()) or 1
        top = sorted(totals.items(), key=lambda kv: -kv[1])[:5]
        rows = [(n, 100.0 * b / all_bytes) for n, b in top]
    h = 56 + max(len(rows), 1) * 34 + 28
    parts = ['  <g font-family="%s" font-size="14" letter-spacing="2">\n' % FONT,
             '    <text x="30" y="34" font-size="14" letter-spacing="3" fill="%s">// TOP LANGUAGES</text>\n' % MUTED]
    if not rows:
        parts.append('    <text x="30" y="80" fill="%s">SYNC PENDING</text>\n' % MUTED)
    for i, (name, pct) in enumerate(rows):
        y = 56 + i * 34
        c = palette[i % len(palette)]
        parts.append(
            '    <text x="30" y="%d" fill="%s">%s</text>\n'
            '    <rect x="210" y="%d" width="480" height="18" fill="%s"/>\n'
            '    <rect x="210" y="%d" width="%.1f" height="18" fill="%s"/>\n'
            '    <text x="710" y="%d" fill="%s">%.1f%%</text>\n'
            % (y + 14, TEXT, esc(name.upper()), y, PANEL, y, 480 * pct / 100.0, c, y + 14, c, pct)
        )
    parts.append('    <text x="30" y="%d" font-size="11" letter-spacing="1" fill="%s">%s</text>\n' % (h - 12, MUTED, esc(stamp(bool(u)))))
    parts.append("  </g>\n")
    desc = "Top programming languages by code size in public repositories of %s." % LOGIN
    return wrap(900, h, "Top languages", desc, "".join(parts))


def activity_svg(u):
    cell, gap, x0, y0 = 11, 3, 79, 56
    weeks = []
    total = None
    if u:
        cal = u["contributionsCollection"]["contributionCalendar"]
        weeks = [[d["contributionCount"] for d in w["contributionDays"]] for w in cal["weeks"]]
        total = cal["totalContributions"]
    mx = max([c for w in weeks for c in w] + [1])
    ramp = ["#0f1c2e", "#0e3a40", "#0a7f8a", "#00c6d4", CYAN]

    def level(c):
        if c <= 0:
            return 0
        return min(4, 1 + int(3.999 * c / mx))

    parts = ['  <g font-family="%s">\n' % FONT,
             '    <text x="30" y="34" font-size="14" letter-spacing="3" fill="%s">// CONTRIBUTION ACTIVITY</text>\n' % MUTED]
    if not weeks:
        weeks = [[0] * 7 for _ in range(52)]
    for wi, w in enumerate(weeks):
        for di, c in enumerate(w):
            parts.append('    <rect x="%d" y="%d" width="%d" height="%d" rx="2" fill="%s"/>\n'
                         % (x0 + wi * (cell + gap), y0 + di * (cell + gap), cell, cell, ramp[level(c)]))
    label = "%d CONTRIBUTIONS IN THE LAST YEAR  |  %s" % (total, stamp(True)) if total is not None else stamp(False)
    parts.append('    <text x="30" y="%d" font-size="11" letter-spacing="1" fill="%s">%s</text>\n' % (y0 + 7 * (cell + gap) + 18, MUTED, esc(label)))
    parts.append("  </g>\n")
    desc = "Heatmap of daily contributions by %s over the last year." % LOGIN
    return wrap(900, y0 + 7 * (cell + gap) + 34, "Contribution activity", desc, "".join(parts))


def main():
    placeholder = "--placeholder" in sys.argv or not TOKEN
    u = None if placeholder else fetch()
    os.makedirs(OUT, exist_ok=True)
    for name, fn in (("telemetry.svg", telemetry_svg), ("languages.svg", languages_svg), ("activity.svg", activity_svg)):
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            f.write(fn(u))
    print("wrote 3 SVGs (%s)" % ("placeholder" if placeholder else "live data"))


if __name__ == "__main__":
    main()
