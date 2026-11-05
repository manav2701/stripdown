"""An approximate inbound-dependency index for the repository.

"What breaks if we remove this?" is a static-analysis question, and it is the
one question an analytics tool can never answer. This builds a cheap, honest
approximation: it collects import/require/include targets from every text file,
normalises them, and can then answer "does anything outside this feature's
paths import anything inside them?".

It is approximate on purpose, and the limits are reported rather than hidden:

  * it resolves module strings by path suffix, not by running the module
    resolver of eight ecosystems, so an alias like "@/lib/x" resolves but an
    exotic webpack alias may not
  * it sees only static imports: a dynamic require, a reflection-based
    container, a Rails autoload or a dependency-injection registry is invisible
  * database tables, queues and HTTP calls are couplings it does not model

So a clean result means "no static import crosses this boundary", which is
weaker than "nothing depends on it". The dependency gate reports it in those
words.
"""

import os
import re

IMPORT_RES = [
    # JS/TS: import ... from 'x'  /  require('x')  /  import('x')
    re.compile(r"""(?:from|require|import)\s*\(?\s*['"]([^'"\n]{2,200})['"]"""),
    # Python: from a.b.c import x  /  import a.b.c
    re.compile(r"""^\s*from\s+([\w.]{2,200})\s+import\b""", re.M),
    re.compile(r"""^\s*import\s+([\w.]{2,200})""", re.M),
    # Go / Java / Kotlin / C# / PHP / Rust
    re.compile(r"""^\s*import\s+["']?([\w./-]{2,200})["']?;?\s*$""", re.M),
    re.compile(r"""^\s*use\s+([\w:]{2,200})""", re.M),
    re.compile(r"""^\s*(?:require|include|require_once|include_once)\s*\(?\s*['"]([^'"\n]{2,200})['"]""", re.M),
    # Ruby
    re.compile(r"""^\s*require(?:_relative)?\s+['"]([^'"\n]{2,200})['"]""", re.M),
]

STRIP_PREFIXES = ("./", "../", "@/", "~/", "@", "~")
CODE_EXT = {
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".py", ".rb", ".php", ".go",
    ".java", ".kt", ".kts", ".scala", ".cs", ".rs", ".ex", ".exs", ".swift",
    ".dart", ".svelte", ".vue", ".astro",
}


def normalise(target):
    """Turn an import string into a comparable slash path."""
    text = target.strip().replace("\\", "/")
    if not text:
        return ""
    # Python and Java dotted paths; leave real relative paths alone.
    if "/" not in text and "." in text and not text.startswith("."):
        text = text.replace(".", "/")
    text = text.replace("::", "/")
    while True:
        for prefix in STRIP_PREFIXES:
            if text.startswith(prefix):
                text = text[len(prefix):]
                break
        else:
            break
    text = text.strip("/")
    base, ext = os.path.splitext(text)
    if ext in CODE_EXT:
        text = base
    if text.endswith("/index"):
        text = text[: -len("/index")]
    return text


def tails(path, min_parts=2):
    """Comparable suffixes of a repo path, longest first.

    Single-component tails are excluded by default: matching on "page" or
    "utils" alone would produce false couplings in any real codebase.
    """
    base, _ = os.path.splitext(path)
    if base.endswith("/index"):
        base = base[: -len("/index")]
    parts = base.split("/")
    out = []
    for start in range(0, len(parts) - min_parts + 1):
        out.append("/".join(parts[start:]))
    if not out and parts:
        out.append(parts[-1])
    return out


class DepIndex(object):
    def __init__(self, root, files, read_text):
        self.root = root
        self.imports = {}      # file -> set of normalised targets
        self.unparsed = 0
        self.code_files = 0
        for path in files:
            if os.path.splitext(path)[1].lower() not in CODE_EXT:
                continue
            self.code_files += 1
            got = read_text(os.path.join(root, path))
            if not got:
                self.unparsed += 1
                continue
            text = got[0]
            found = set()
            for rx in IMPORT_RES:
                for match in rx.finditer(text):
                    norm = normalise(match.group(1))
                    if norm and "/" in norm:
                        found.add(norm)
            self.imports[path] = found

    def inbound(self, feature_files, limit=12):
        """Files outside the feature that statically import something inside it."""
        inside = set(feature_files)
        targets = {}
        for path in inside:
            for tail in tails(path):
                targets.setdefault(tail, path)
        if not targets:
            return [], 0
        hits = []
        for path, found in self.imports.items():
            if path in inside:
                continue
            for target in found:
                for tail, owner in targets.items():
                    if target == tail or target.endswith("/" + tail):
                        hits.append({"from": path, "imports": target,
                                     "resolves_to": owner})
                        break
                else:
                    continue
                break
        hits.sort(key=lambda h: h["from"])
        return hits[:limit], len(hits)
