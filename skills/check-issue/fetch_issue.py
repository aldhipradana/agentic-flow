#!/usr/bin/env python3
"""Fetch a Gitea or GitHub issue with its comments and attachments, then print a Markdown digest.

Usage: python3 fetch_issue.py REF OUT_DIR
  REF: https://HOST/OWNER/REPO/issues/N (or /pulls/N), OWNER/REPO#N, or #N.
       Short forms take HOST (and OWNER/REPO for #N) from the current repo's origin remote.

Writes OUT_DIR/issue.json, OUT_DIR/comments.json and OUT_DIR/att/*.
All requests go through the tea/gh CLI's stored login; no token is ever read.
"""
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        die(f"`{cmd[0]}` is not installed")
    return r.returncode, r.stdout, r.stderr


def origin():
    code, out, _ = run(["git", "remote", "get-url", "origin"])
    if code:
        die("short issue reference needs a git repo with an origin remote; pass the full URL instead")
    remote = out.strip()
    if "://" in remote:
        parsed = urlparse(remote)
        # HTTP ports identify the API host; SSH ports identify only Git transport.
        host = parsed.netloc.rsplit("@", 1)[-1] if parsed.scheme in {"http", "https"} else parsed.hostname
        slug = parsed.path.strip("/")
    else:
        m = re.fullmatch(r"(?:[^@/:]+@)?([^/:]+):(.+)", remote)
        host, slug = m.groups() if m else (None, "")
        slug = slug.strip("/")
    if slug.endswith(".git"):
        slug = slug[:-4]
    if not host or len(slug.split("/")) != 2 or not all(slug.split("/")):
        die(f"cannot parse origin remote {out.strip()!r}")
    return host, slug


def parse_ref(ref):
    m = re.match(r"^https?://([^/]+)/([^/]+)/([^/#?]+)/(?:issues|pulls|pull)/(\d+)(?:[^#]*)(?:#(.*))?$", ref)
    if m:
        return m.group(1), m.group(2), m.group(3), int(m.group(4)), m.group(5) or ""
    m = re.match(r"^([\w.-]+)/([\w.-]+)#(\d+)$", ref)
    if m:
        return origin()[0], m.group(1), m.group(2), int(m.group(3)), ""
    m = re.match(r"^#?(\d+)$", ref)
    if m:
        host, slug = origin()
        owner, _, repo = slug.rpartition("/")
        return host, owner, repo, int(m.group(1)), ""
    die(f"not an issue reference: {ref}")


def tea_login(host):
    code, out, err = run(["tea", "login", "list", "--output", "json"])
    if code:
        die(f"`tea login list` failed: {err.strip()}")
    for login in json.loads(out or "[]"):
        if urlparse(login.get("url", "")).netloc == host:
            return login["name"]
    die(f"no tea login for {host}; run `tea login add` (or this is not a Gitea host)")


def tea_get(login, endpoint):
    code, out, err = run(["tea", "api", "-l", login, endpoint])
    if code:
        die(f"tea api {endpoint} failed: {err.strip()}")
    data = json.loads(out)
    # tea api exits 0 on HTTP errors; the body is then {"message": ...}
    if isinstance(data, dict) and "message" in data and "id" not in data:
        die(f"{endpoint}: {data['message']}")
    return data


def gh_get(host, endpoint):
    code, out, err = run(["gh", "api", "--hostname", host, "--paginate", "--slurp", endpoint])
    if code:
        die(f"gh api {endpoint} failed: {err.strip()} (run `gh auth login`?)")
    pages = json.loads(out)
    return [x for page in pages for x in page] if isinstance(pages[0], list) else pages[0]


def assets(item):
    return [(a["name"], a["browser_download_url"]) for a in item.get("assets") or []]


def forge(host):
    """('gh', None) for GitHub hosts, else ('tea', <tea login for host>)."""
    if host == "github.com" or host.endswith(".ghe.com"):
        return "gh", None
    return "tea", tea_login(host)


def fetch(host, owner, repo, n):
    cli, login = forge(host)
    if cli == "gh":
        base = f"repos/{owner}/{repo}/issues/{n}"
        return "gh", None, gh_get(host, base), gh_get(host, base + "/comments")
    base = f"/repos/{owner}/{repo}/issues/{n}"
    return "tea", login, tea_get(login, base), tea_get(login, base + "/comments")


def inline_images(body, host):
    """Image links in Markdown/HTML, absolutized against the host."""
    urls = re.findall(r"!\[[^\]]*\]\(([^)\s]+)", body) + re.findall(r"<img[^>]+src=\"([^\"]+)\"", body)
    return [f"https://{host}{u}" if u.startswith("/") else u for u in urls]


def download(cli, login, host, url, dest):
    if cli != "tea" or urlparse(url).netloc != host:
        return False
    code, _, _ = run(["tea", "api", "-l", login, "-o", str(dest), url])
    return code == 0 and dest.exists() and dest.stat().st_size > 0 and not dest.read_bytes().startswith(b'{"message"')


def main():
    if len(sys.argv) != 3:
        die(__doc__.strip().splitlines()[2])
    host, owner, repo, n, anchor = parse_ref(sys.argv[1])
    out = Path(sys.argv[2])
    (out / "att").mkdir(parents=True, exist_ok=True)

    cli, login, issue, comments = fetch(host, owner, repo, n)
    (out / "issue.json").write_text(json.dumps(issue, indent=2))
    (out / "comments.json").write_text(json.dumps(comments, indent=2))

    seen, counter = {}, [0]

    def grab(name, url):
        if url in seen:
            return seen[url]
        counter[0] += 1
        safe = re.sub(r"[^\w.-]", "_", name)
        dest = out / "att" / f"{n}-{counter[0]}-{safe}"
        seen[url] = str(dest) if download(cli, login, host, url, dest) else f"NOT FETCHED: {url}"
        return seen[url]

    def files_for(item):
        body = item.get("body") or ""
        listed = assets(item)
        inline = [(u.rsplit("/", 1)[-1], u) for u in inline_images(body, host)]
        names = {}
        for name, url in listed + inline:
            names.setdefault(url, name)
        return [grab(name, url) for url, name in names.items()]

    pr = " (pull request)" if issue.get("pull_request") else ""
    labels = ", ".join(lbl["name"] for lbl in issue.get("labels") or []) or "none"
    print(f"# {owner}/{repo}#{n}: {issue['title']}{pr}")
    print(f"{issue['state']} · @{issue['user']['login']} · created {issue['created_at']}"
          f" · closed {issue.get('closed_at') or '-'} · labels: {labels}")
    print(f"{issue['html_url']} · via {cli} · raw JSON in {out}/\n")
    print("## Body\n")
    print((issue.get("body") or "").strip() or "_(empty: title only)_")
    for f in files_for(issue):
        print(f"- attachment: {f}")

    print(f"\n## Comments ({len(comments)})")
    for c in comments:
        mark = "  <- linked comment" if anchor == f"issuecomment-{c['id']}" else ""
        print(f"\n### @{c['user']['login']} · {c['created_at']}{mark}\n")
        print((c.get("body") or "").strip())
        for f in files_for(c):
            print(f"- attachment: {f}")

    text = "\n".join([issue.get("body") or ""] + [c.get("body") or "" for c in comments])
    print("\n## References (a bare #N may belong to another repo; read its context)")
    found = False
    for link in sorted(set(re.findall(r"https?://[^\s)>\"]+/(?:issues|pulls|pull)/\d+", text))):
        print(f"- {link}")
        found = True
    seen_refs = {str(n)}
    for m in re.finditer(r"(?<![\w/&])#(\d+)\b", text):
        if m.group(1) in seen_refs:
            continue
        seen_refs.add(m.group(1))
        context = " ".join(text[max(0, m.start() - 50):m.end() + 15].split())
        print(f"- #{m.group(1)}: \"...{context}...\"")
        found = True
    if not found:
        print("- none")


if __name__ == "__main__":
    main()
