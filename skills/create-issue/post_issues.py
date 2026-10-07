#!/usr/bin/env python3
"""Post issue drafts to Gitea (via tea) or GitHub (via gh).

Usage: python3 post_issues.py DRAFTS_DIR [--dry] [--force]

DRAFTS_DIR holds one Markdown file per action, posted in file-name order:

    ---
    key: be
    repo: HOST/OWNER/REPO
    title: Issue title
    comment: N
    update: N
    ---
    Markdown body

  key      optional; other drafts write {{be}} to link to this issue
  repo     HOST/OWNER/REPO or https://HOST/OWNER/REPO (OWNER/REPO takes HOST from the git origin)
  title    required to create; on update, replaces the title
  comment  comment on issue N instead of creating one
  update   replace issue N's body (and its title, when given)

--dry checks every draft and prints the plan without writing anything.
Progress is kept in DRAFTS_DIR/.posted.json, so a rerun skips what was already posted.
All requests go through the tea/gh CLI's stored login; no token is ever read.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "check-issue"))
try:
    from fetch_issue import die, forge, origin, run
except ImportError:
    print("ERROR: needs the check-issue skill beside this one (check-issue/fetch_issue.py with forge())",
          file=sys.stderr)
    sys.exit(1)

FIELDS = {"key", "repo", "title", "comment", "update"}
PLACEHOLDER = re.compile(r"\{\{\s*([\w.-]+)\s*\}\}")
QUALIFIED_REF = re.compile(r"(?<![\w/.-])([\w.-]+)/([\w.-]+)#(\d+)\b")
BARE_REF = re.compile(r"(?<![\w/&])#(\d+)\b")
HANDMADE_PLACEHOLDER = re.compile(r"(?<![\w/&])#[A-Z][A-Z_]{2,}\b")
LOCAL_PATH = re.compile(r"(?<![\w.])(?:/Users/|/home/|/private/(?:tmp|var)/|/tmp/|/var/folders/|[A-Za-z]:\\Users\\)")
ATTRIBUTION = re.compile(
    r"noreply@anthropic\.com|(?:co-authored-by|generated|drafted|written|created)\W+(?:with|by)?\W*"
    r"[^\n]{0,40}?\b(?:claude|anthropic|codex|openai|chatgpt|gpt-?\d*|copilot|an? ai|ai agent)\b",
    re.I)
CODE = re.compile(r"```.*?```|`[^`\n]*`", re.S)
FORWARD = "(link follows)"


class Draft:
    def __init__(self, path):
        self.file = path.name
        text = path.read_text()
        m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
        if not m:
            die(f"{self.file}: no front matter; start the file with --- ... ---")
        meta = {}
        for line in m.group(1).splitlines():
            if not line.strip():
                continue
            name, sep, value = line.partition(":")
            name, value = name.strip(), value.strip()
            if not sep or name not in FIELDS:
                die(f"{self.file}: unknown front-matter line {line!r}; allowed: {', '.join(sorted(FIELDS))}")
            if len(value) > 1 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            meta[name] = value
        self.body = m.group(2).strip() + "\n"
        self.key = meta.get("key") or None
        self.title = meta.get("title") or None
        if "repo" not in meta:
            die(f"{self.file}: repo is required")
        self.host, self.owner, self.repo = parse_repo(meta["repo"], self.file)
        if "comment" in meta and "update" in meta:
            die(f"{self.file}: use comment or update, not both")
        self.action = "comment" if "comment" in meta else "update" if "update" in meta else "create"
        self.number = None
        if self.action != "create":
            raw = meta[self.action].lstrip("#")
            if not raw.isdigit():
                die(f"{self.file}: {self.action} needs an issue number, got {meta[self.action]!r}")
            self.number = int(raw)
        if self.action == "create" and not self.title:
            die(f"{self.file}: title is required to create an issue")
        if self.action == "comment" and self.title:
            die(f"{self.file}: a comment has no title")
        if not self.body.strip():
            die(f"{self.file}: the body is empty")

    @property
    def slug(self):
        return f"{self.owner}/{self.repo}"

    @property
    def identity(self):
        return {"host": self.host, "repo": self.slug.lower(),
                "action": self.action, "number": self.number}

    def same_repo(self, other):
        return (self.host, self.slug.lower()) == (other.host, other.slug.lower())


def parse_repo(value, file):
    parts = re.sub(r"^https?://", "", value).removesuffix(".git").strip("/").split("/")
    if len(parts) == 3:
        return parts[0].lower(), parts[1], parts[2]
    if len(parts) == 2:
        return origin()[0].lower(), parts[0], parts[1]
    die(f"{file}: repo must be HOST/OWNER/REPO, got {value!r}")


def norm(text):
    return (text or "").replace("\r\n", "\n").strip()


def digest(text):
    return hashlib.sha256(norm(text).encode()).hexdigest()


class Forges:
    """The CLI and login per host, and the API calls made through them."""

    def __init__(self):
        self.by_host = {}
        self.info = {}

    def get(self, host):
        if host not in self.by_host:
            self.by_host[host] = forge(host)
        return self.by_host[host]

    def label(self, host):
        cli, login = self.get(host)
        return f"{cli} ({login})" if login else cli

    def api(self, host, method, endpoint, payload=None):
        """(True, data) or (False, error message)."""
        cli, login = self.get(host)
        tmp = None
        try:
            if payload is not None:
                fd, tmp = tempfile.mkstemp(suffix=".json")
                with os.fdopen(fd, "w") as f:
                    json.dump(payload, f)
            if cli == "tea":
                cmd = ["tea", "api", "-l", login, "-X", method] + (["-d", "@" + tmp] if tmp else []) + [endpoint]
            else:
                cmd = ["gh", "api", "--hostname", host, "-X", method] + (["--input", tmp] if tmp else []) \
                      + [endpoint.lstrip("/")]
            code, out, err = run(cmd)
        finally:
            if tmp:
                os.unlink(tmp)
        try:
            data = json.loads(out) if out.strip() else None
        except json.JSONDecodeError:
            data = None
        # tea api exits 0 on HTTP errors; the body is then {"message": ...}
        if code or data is None or (isinstance(data, dict) and "message" in data and "id" not in data):
            message = data.get("message") if isinstance(data, dict) else None
            return False, message or (err or out).strip() or f"exit {code}"
        return True, data

    def issue(self, host, slug, n):
        """'"title" (state)' for an existing issue or PR, else None."""
        k = (host, slug.lower(), n)
        if k not in self.info:
            ok, data = self.api(host, "GET", f"/repos/{slug}/issues/{n}")
            self.info[k] = f"\"{data['title']}\" ({data['state']})" if ok else None
        return self.info[k]


def ref(src, dst, n):
    if src.same_repo(dst):
        return f"#{n}"
    if src.host == dst.host:
        return f"{dst.slug}#{n}"
    return f"https://{dst.host}/{dst.slug}/issues/{n}"


def render(d, by_key, numbers):
    """The body with every {{key}} replaced; links to issues not yet created read FORWARD."""
    def sub(m):
        target = by_key[m.group(1)]
        n = target.number or numbers.get(target.file)
        return ref(d, target, n) if n else FORWARD
    return PLACEHOLDER.sub(sub, d.body)


def resume_errors(drafts, state):
    """Reject progress that cannot be tied to the current draft's target."""
    if not isinstance(state, dict):
        return [".posted.json must contain progress entries keyed by draft filename"]
    errors = []
    for d in drafts:
        if d.file not in state:
            continue
        entry = state[d.file]
        if not isinstance(entry, dict) or not isinstance(entry.get("identity"), dict):
            errors.append(f"{d.file}: progress has no saved target identity; keep .posted.json "
                          "and reconcile its saved URLs with the drafts before retrying")
        elif (entry["identity"] != d.identity or entry.get("action") != d.action
              or (d.number is not None and entry.get("number") != d.number)):
            errors.append(f"{d.file}: target differs from saved progress; keep .posted.json "
                          "and reconcile its saved URLs with the drafts before retrying")
    return errors


def check(drafts, forges, state):
    """Print the plan; return (errors, warnings)."""
    errors, warnings = resume_errors(drafts, state), []
    if errors:
        return errors, warnings
    by_key = {}
    for d in drafts:
        if d.key:
            if d.key in by_key:
                errors.append(f"{d.file}: key {d.key!r} is also used by {by_key[d.key].file}")
            by_key[d.key] = d
    width = max(len(d.file) for d in drafts)
    print(f"Plan ({len(drafts)} draft(s)):")
    for i, d in enumerate(drafts):
        target = f"{d.slug}#{d.number}" if d.number else d.slug
        print(f"\n{d.file:<{width}}  {d.action:<7}  {d.host}/{target}  via {forges.label(d.host)}")
        if d.title:
            print(f"{'':<{width}}  title    {d.title}")
        if d.file in state:
            print(f"{'':<{width}}  already posted: {state[d.file]['url']}")
        if d.number:
            info = forges.issue(d.host, d.slug, d.number)
            if info:
                print(f"{'':<{width}}  target   {info}")
            else:
                errors.append(f"{d.file}: {d.host}/{d.slug}#{d.number} not found")
        text = (d.title or "") + "\n" + d.body
        for m in PLACEHOLDER.finditer(d.body):
            target = by_key.get(m.group(1))
            if not target:
                errors.append(f"{d.file}: {{{{{m.group(1)}}}}} matches no draft key")
            elif target.number:
                print(f"{'':<{width}}  {m.group(0)} -> {ref(d, target, target.number)} "
                      f"{forges.issue(target.host, target.slug, target.number) or ''}")
            else:
                later = drafts.index(target) > i
                print(f"{'':<{width}}  {m.group(0)} -> new issue in {target.slug} ({target.file})"
                      + (", filled in after it is posted" if later else ""))
        prose = CODE.sub("", d.body)
        refs = [(o, r, int(n)) for o, r, n in QUALIFIED_REF.findall(prose)]
        refs += [(d.owner, d.repo, int(n)) for n in BARE_REF.findall(prose)]
        for owner, repo, n in dict.fromkeys(refs):
            shown = f"#{n}" if f"{owner}/{repo}".lower() == d.slug.lower() else f"{owner}/{repo}#{n}"
            info = forges.issue(d.host, f"{owner}/{repo}", n)
            if info:
                print(f"{'':<{width}}  {shown} -> {owner}/{repo}#{n} {info}")
            else:
                warnings.append(f"{d.file}: {shown} -> {owner}/{repo}#{n}, which does not exist")
        for m in HANDMADE_PLACEHOLDER.finditer(prose):
            warnings.append(f"{d.file}: {m.group(0)} looks like a placeholder; write {{{{key}}}} instead")
        for m in LOCAL_PATH.finditer(text):
            path = re.match(r"[^\s`)\]>\"']+", text[m.start():]).group(0).rstrip(".,;:")
            warnings.append(f"{d.file}: local path, unreadable for others: {path}")
        for m in ATTRIBUTION.finditer(text):
            warnings.append(f"{d.file}: attribution line: {m.group(0)[:80]!r}")
    return errors, warnings


def load_state(path):
    return json.loads(path.read_text()) if path.exists() else {}


def save_state(path, state):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(path)


def post(drafts, forges, state, state_path):
    errors = resume_errors(drafts, state)
    if errors:
        die("\n".join(errors))
    by_key = {d.key: d for d in drafts if d.key}
    numbers = {f: s["number"] for f, s in state.items() if s["action"] == "create"}

    for d in drafts:
        if d.file in state:
            continue
        body = render(d, by_key, numbers)
        if d.action == "create":
            ok, data = forges.api(d.host, "POST", f"/repos/{d.slug}/issues", {"title": d.title, "body": body})
        elif d.action == "comment":
            ok, data = forges.api(d.host, "POST", f"/repos/{d.slug}/issues/{d.number}/comments", {"body": body})
        else:
            payload = {"body": body} | ({"title": d.title} if d.title else {})
            ok, data = forges.api(d.host, "PATCH", f"/repos/{d.slug}/issues/{d.number}", payload)
        if not ok:
            die(f"{d.file}: {d.action} failed: {data}. Earlier drafts are posted; fix this one and rerun.")
        entry = {"identity": d.identity, "action": d.action, "url": data["html_url"], "sent": digest(body),
                 "number": data["number"] if d.action != "comment" else d.number}
        if d.action == "comment":
            entry["comment_id"] = data["id"]
        state[d.file] = entry
        save_state(state_path, state)
        if d.action == "create":
            numbers[d.file] = entry["number"]
        print(f"{d.action:<7}  {entry['url']}")

    # Fill in links to issues created later, then read every body back.
    problems = []
    for d in drafts:
        entry = state[d.file]
        endpoint = (f"/repos/{d.slug}/issues/comments/{entry['comment_id']}" if d.action == "comment"
                    else f"/repos/{d.slug}/issues/{entry['number']}")
        final = render(d, by_key, numbers)
        ok, data = forges.api(d.host, "GET", endpoint)
        if not ok:
            problems.append(f"{d.file}: cannot read back {entry['url']}: {data}")
            continue
        if norm(data.get("body")) == norm(final):
            continue
        if digest(data.get("body")) != entry["sent"]:
            problems.append(f"{d.file}: {entry['url']} differs from the draft and was changed after posting; left as is")
            continue
        ok, data = forges.api(d.host, "PATCH", endpoint, {"body": final})
        if ok and norm(data.get("body")) == norm(final):
            entry["sent"] = digest(final)
            save_state(state_path, state)
            print(f"linked   {entry['url']}")
        else:
            problems.append(f"{d.file}: filling in links on {entry['url']} failed: {data if not ok else 'body differs'}")

    print("\nPosted:")
    for d in drafts:
        entry = state[d.file]
        what = {"create": "new", "comment": "comment", "update": "updated"}[d.action]
        print(f"- {entry['url']}  {what}  {d.title or ''}".rstrip())
    if problems:
        print("\nProblems:\n" + "\n".join(f"- {p}" for p in problems))
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("drafts_dir", type=Path)
    ap.add_argument("--dry", action="store_true", help="check and print the plan; post nothing")
    ap.add_argument("--force", action="store_true", help="post despite warnings the user has accepted")
    args = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)  # keep the plan and stderr errors in order when piped

    files = sorted(p for p in args.drafts_dir.glob("*.md") if not p.name.startswith("."))
    if not files:
        die(f"no *.md drafts in {args.drafts_dir}")
    drafts = [Draft(p) for p in files]
    forges = Forges()
    state_path = args.drafts_dir / ".posted.json"
    state = load_state(state_path)

    errors, warnings = check(drafts, forges, state)
    if warnings:
        print("\nWarnings:\n" + "\n".join(f"- {w}" for w in warnings))
    if errors:
        print("\nErrors:\n" + "\n".join(f"- {e}" for e in errors))
        sys.exit(1)
    if args.dry:
        print("\nDry run: nothing posted.")
        return
    if warnings and not args.force:
        print("\nNothing posted: fix the warnings, or pass --force once the user accepts them.")
        sys.exit(1)
    print()
    post(drafts, forges, state, state_path)


if __name__ == "__main__":
    main()
