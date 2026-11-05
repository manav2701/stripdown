"""Shared helpers: repo file listing, glob matching, inventory load/validate."""

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sdyaml  # noqa: E402

SCHEMA_VERSION = 1
STATE_DIR = ".stripdown"
INVENTORY_PATH = os.path.join(STATE_DIR, "inventory.yml")
CONFIG_PATH = os.path.join(STATE_DIR, "config.yml")

GATE_KEYS = ("contractual", "regulated", "public_api")
GATE_VALUES = ("yes", "no", "unknown")
STATUSES = ("active", "deprecated", "sunset-planned")
MODES = ("pre-users", "has-users")

# Directories never worth scanning even when they are tracked in git.
SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "vendor", "dist", "build", "out",
    "target", "__pycache__", ".next", ".nuxt", ".svelte-kit", ".venv", "venv",
    "env", ".tox", ".mypy_cache", ".pytest_cache", ".gradle", ".idea",
    ".terraform", "coverage", ".cache", "bower_components", "Pods",
    ".stripdown",
}

BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg", ".pdf", ".zip",
    ".gz", ".tgz", ".bz2", ".xz", ".7z", ".jar", ".war", ".class", ".so",
    ".dylib", ".dll", ".exe", ".bin", ".wasm", ".woff", ".woff2", ".ttf",
    ".eot", ".otf", ".mp3", ".mp4", ".mov", ".avi", ".webm", ".ogg", ".wav",
    ".db", ".sqlite", ".sqlite3", ".pyc", ".pyo", ".o", ".a", ".lock",
}

TEST_HINTS = (
    "test", "tests", "spec", "specs", "__tests__", "e2e", "cypress",
    "playwright", "fixtures", "factories",
)


def die(message, code=2):
    sys.stderr.write("strip-down: %s\n" % message)
    raise SystemExit(code)


def run(args, cwd=None, check=True):
    """Run a command and return stdout, or None when it fails and check=False."""
    try:
        proc = subprocess.run(
            args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True,
        )
    except (OSError, ValueError) as exc:
        if check:
            die("could not run %s: %s" % (" ".join(args), exc))
        return None
    if proc.returncode != 0:
        if check:
            die("%s failed: %s" % (" ".join(args[:2]), proc.stderr.strip()))
        return None
    return proc.stdout


def resolve_root(path, explicit):
    """Use the path the caller gave when they named one, else the git toplevel.

    Without this, pointing a script at a subdirectory of a repo would silently
    widen the scan to the whole repo.
    """
    if explicit:
        return os.path.abspath(path)
    return repo_root(path)


def repo_root(start="."):
    out = run(["git", "rev-parse", "--show-toplevel"], cwd=start, check=False)
    if out:
        return out.strip()
    return os.path.abspath(start)


def is_git_repo(root):
    out = run(["git", "rev-parse", "--is-inside-work-tree"], cwd=root, check=False)
    return bool(out) and out.strip() == "true"


def _skip(path):
    parts = path.split("/")
    return any(part in SKIP_DIRS for part in parts[:-1]) or parts[0] in SKIP_DIRS


def list_files(root):
    """Repo-relative paths of tracked files, falling back to a walk."""
    out = run(["git", "ls-files", "-z", "--cached", "--others",
               "--exclude-standard"],
              cwd=root, check=False)
    if out is not None:
        files = [p for p in out.split("\0") if p]
    else:
        files = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in filenames:
                full = os.path.join(dirpath, name)
                files.append(os.path.relpath(full, root).replace(os.sep, "/"))
    return sorted(p for p in files if not _skip(p))


def is_texty(path):
    return os.path.splitext(path)[1].lower() not in BINARY_EXT


def is_test_path(path):
    low = path.lower()
    name = low.rsplit("/", 1)[-1]
    if any("/%s/" % h in "/" + low for h in TEST_HINTS):
        return True
    return (
        name.startswith("test_")
        or "_test." in name
        or ".test." in name
        or ".spec." in name
        or "_spec." in name
    )


def read_text(path, limit=400000):
    try:
        with open(path, "rb") as fh:
            blob = fh.read(limit + 1)
    except OSError:
        return None
    if b"\0" in blob[:4096]:
        return None
    truncated = len(blob) > limit
    return blob[:limit].decode("utf-8", "replace"), truncated


def glob_to_re(pattern):
    """Translate a path glob (with ** support) to an anchored regex."""
    out = []
    i = 0
    n = len(pattern)
    while i < n:
        if pattern.startswith("**/", i):
            out.append("(?:[^/]+/)*")
            i += 3
        elif pattern.startswith("/**", i) and i + 3 == n:
            out.append("(?:/.*)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        elif pattern[i] == "[":
            close = pattern.find("]", i)
            if close == -1:
                out.append(re.escape("["))
                i += 1
            else:
                out.append(pattern[i:close + 1])
                i = close + 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


class Matcher(object):
    """Maps repo files to feature ids.

    A path with no wildcard also matches everything beneath it, so "app/billing"
    behaves like "app/billing/**". When several features match one file, the one
    whose pattern has the longest literal prefix wins; ties and genuine overlaps
    are recorded so the report can show them rather than hide them.
    """

    def __init__(self, features):
        self.rules = []
        for feat in features:
            for pattern in feat.get("paths") or []:
                pattern = str(pattern).strip().lstrip("./")
                if not pattern:
                    continue
                literal = re.split(r"[*?\[]", pattern)[0]
                self.rules.append((
                    feat["id"], pattern, glob_to_re(pattern),
                    "*" not in pattern and "?" not in pattern and "[" not in pattern,
                    len(literal),
                ))
        self.overlaps = {}

    def match(self, path):
        hits = []
        for fid, pattern, rx, is_literal, weight in self.rules:
            if rx.match(path) or (
                is_literal and (path == pattern or path.startswith(pattern + "/"))
            ):
                hits.append((weight, fid))
        if not hits:
            return None
        hits.sort(key=lambda h: (-h[0], h[1]))
        best = hits[0][1]
        distinct = sorted({fid for _, fid in hits})
        if len(distinct) > 1:
            self.overlaps.setdefault(path, distinct)
        return best

    def assign(self, paths):
        mapping = {}
        for path in paths:
            fid = self.match(path)
            if fid:
                mapping.setdefault(fid, []).append(path)
        return mapping


def blank_feature(fid, name):
    return {
        "id": fid,
        "name": name,
        "status": "active",
        "paths": [],
        "events": [],
        "owner": "",
        "tags": [],
        "gates": {"contractual": "unknown", "regulated": "unknown",
                  "public_api": "unknown"},
        "notes": "",
    }


_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def validate(data, strict=False):
    """Return (errors, warnings) for an inventory mapping."""
    errors = []
    warnings = []
    if not isinstance(data, dict):
        return (["inventory root must be a mapping"], [])
    version = data.get("version")
    if version != SCHEMA_VERSION:
        warnings.append(
            "version is %r, expected %d" % (version, SCHEMA_VERSION))
    mode = data.get("mode")
    if mode is not None and mode not in MODES:
        errors.append("mode must be one of %s, got %r" % ("/".join(MODES), mode))
    features = data.get("features")
    if features is None:
        errors.append("no 'features' key")
        return errors, warnings
    if not isinstance(features, list):
        errors.append("'features' must be a list")
        return errors, warnings
    seen = set()
    for idx, feat in enumerate(features):
        where = "features[%d]" % idx
        if not isinstance(feat, dict):
            errors.append("%s is not a mapping" % where)
            continue
        fid = feat.get("id")
        if not fid or not isinstance(fid, str):
            errors.append("%s has no id" % where)
            continue
        where = "feature %r" % fid
        if not _ID_RE.match(fid):
            errors.append("%s: id must be lowercase a-z0-9, - or _" % where)
        if fid in seen:
            errors.append("%s: duplicate id" % where)
        seen.add(fid)
        if not feat.get("name"):
            warnings.append("%s: no human name" % where)
        status = feat.get("status", "active")
        if status not in STATUSES:
            errors.append("%s: status must be one of %s" % (where, "/".join(STATUSES)))
        paths = feat.get("paths")
        if not paths:
            errors.append("%s: no paths; cost and usage cannot be attributed" % where)
        elif not isinstance(paths, list):
            errors.append("%s: paths must be a list" % where)
        events = feat.get("events")
        if events is None:
            warnings.append("%s: no events key (will be read as a blind spot)" % where)
        elif not isinstance(events, list):
            errors.append("%s: events must be a list" % where)
        elif not events:
            warnings.append("%s: no events mapped — blind spot" % where)
        gates = feat.get("gates") or {}
        if not isinstance(gates, dict):
            errors.append("%s: gates must be a mapping" % where)
        else:
            for key in GATE_KEYS:
                val = gates.get(key, "unknown")
                if isinstance(val, bool):
                    continue
                if str(val) not in GATE_VALUES:
                    errors.append(
                        "%s: gates.%s must be yes/no/unknown, got %r"
                        % (where, key, val))
            if strict:
                for key in GATE_KEYS:
                    if str(gates.get(key, "unknown")) == "unknown":
                        warnings.append("%s: gates.%s is unanswered" % (where, key))
    return errors, warnings


def gate_value(gates, key):
    """Normalise a gate to 'yes'/'no'/'unknown'.

    A hand-written unquoted ``no`` parses as the boolean False, so gates are
    normalised on read rather than trusting the literal. strip-down's own
    writer always quotes these, but humans edit this file.
    """
    raw = (gates or {}).get(key, "unknown")
    if raw is True:
        return "yes"
    if raw is False:
        return "no"
    text = str(raw).strip().lower()
    return text if text in GATE_VALUES else "unknown"


def load_inventory(root, required=True):
    path = os.path.join(root, INVENTORY_PATH)
    if not os.path.exists(path):
        if required:
            die("no %s — run /strip-down:inventory first" % INVENTORY_PATH)
        return None
    try:
        data = sdyaml.load(path)
    except sdyaml.YamlError as exc:
        die("%s: %s" % (INVENTORY_PATH, exc))
    errors, _ = validate(data)
    if errors:
        die("%s is not valid:\n  - %s" % (INVENTORY_PATH, "\n  - ".join(errors)))
    return data


def save_inventory(root, data):
    os.makedirs(os.path.join(root, STATE_DIR), exist_ok=True)
    sdyaml.dump(data, os.path.join(root, INVENTORY_PATH))


def load_config(root):
    path = os.path.join(root, CONFIG_PATH)
    if not os.path.exists(path):
        return {}
    try:
        return sdyaml.load(path) or {}
    except sdyaml.YamlError as exc:
        die("%s: %s" % (CONFIG_PATH, exc))


def emit(data, as_json, writer=None):
    writer = writer or sys.stdout
    if as_json:
        json.dump(data, writer, indent=2, sort_keys=False)
        writer.write("\n")
    else:
        writer.write(sdyaml.dumps(data))


def pct(numerator, denominator):
    if not denominator:
        return None
    return round(100.0 * numerator / denominator, 1)
