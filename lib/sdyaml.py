"""A deliberately small YAML subset reader/writer.

strip-down's data files are meant to be hand-edited and committed, so YAML is
the right format. But the plugin must run with no installed dependencies, and
PyYAML is not in the standard library. So: if PyYAML is present we read with
it, and otherwise we read with the parser below, which supports exactly the
subset strip-down writes.

Supported
  - a mapping at the top level, nested by 2-space indentation
  - block sequences ("- x") of scalars and of mappings
  - scalars: plain, 'single-quoted', "double-quoted", int, float,
    true/false/yes/no, null/~/empty
  - inline empty collections: [] and {}
  - inline flow sequences of scalars: [a, b, c]
  - "#" comments, outside of quotes

Not supported (and reported with a line number rather than mis-parsed)
  - anchors, aliases, tags, documents (---), multi-line scalars (| and >),
    nested flow collections, complex keys

Writing always emits the canonical form above, so a file round-trips through
this module even if it was written by PyYAML.
"""

import re

__all__ = ["load", "loads", "dump", "dumps", "YamlError"]


class YamlError(ValueError):
    """Raised with a 1-based line number when a file leaves the subset."""

    def __init__(self, message, line=None):
        self.line = line
        if line is not None:
            message = "line %d: %s" % (line, message)
        super(YamlError, self).__init__(message)


_UNSUPPORTED = (
    ("---", "multiple YAML documents are not supported"),
    ("...", "document end markers are not supported"),
)

_FLOAT_RE = re.compile(r"^-?(\d+\.\d*|\.\d+|\d+[eE][-+]?\d+|\d+\.\d+[eE][-+]?\d+)$")
_INT_RE = re.compile(r"^-?\d+$")


def _strip_comment(raw):
    """Remove a trailing # comment, respecting quotes."""
    out = []
    quote = None
    i = 0
    while i < len(raw):
        ch = raw[i]
        if quote:
            out.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < len(raw):
                out.append(raw[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
            out.append(ch)
        elif ch == "#" and (not out or out[-1] in " \t"):
            break
        else:
            out.append(ch)
        i += 1
    return "".join(out).rstrip()


def _scalar(text, line):
    text = text.strip()
    if text == "" or text in ("~", "null", "Null", "NULL"):
        return None
    if text == "[]":
        return []
    if text == "{}":
        return {}
    if text[0] == "'" and text[-1] == "'" and len(text) >= 2:
        return text[1:-1].replace("''", "'")
    if text[0] == '"' and text[-1] == '"' and len(text) >= 2:
        body = text[1:-1]
        for a, b in (("\\n", "\n"), ("\\t", "\t"), ('\\"', '"'), ("\\\\", "\\")):
            body = body.replace(a, b)
        return body
    if text[0] == "[":
        if not text.endswith("]"):
            raise YamlError("unterminated flow sequence", line)
        inner = text[1:-1].strip()
        if not inner:
            return []
        if "[" in inner or "{" in inner:
            raise YamlError("nested flow collections are not supported", line)
        return [_scalar(p, line) for p in _split_flow(inner)]
    if text[0] in "{&*!|>":
        raise YamlError("unsupported YAML syntax %r" % text[0], line)
    low = text.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if _INT_RE.match(text):
        return int(text)
    if _FLOAT_RE.match(text):
        return float(text)
    return text


def _split_flow(inner):
    parts = []
    buf = []
    quote = None
    for ch in inner:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
            buf.append(ch)
        elif ch == ",":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip() != ""]


def _split_key(text, line):
    """Split 'key: value' at the first unquoted colon-space (or trailing colon)."""
    quote = None
    for i, ch in enumerate(text):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == ":":
            rest = text[i + 1:]
            if rest == "" or rest[0] in " \t":
                return _scalar(text[:i], line), rest.strip()
    return None, None


class _Line(object):
    __slots__ = ("indent", "text", "no")

    def __init__(self, indent, text, no):
        self.indent = indent
        self.text = text
        self.no = no


def loads(text):
    """Parse the supported subset and return a dict (or {} for an empty file)."""
    lines = []
    for no, raw in enumerate(text.splitlines(), 1):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise YamlError("tab in indentation; use spaces", no)
        for marker, why in _UNSUPPORTED:
            if raw.strip() == marker:
                raise YamlError(why, no)
        body = _strip_comment(raw)
        if body.strip() == "":
            continue
        lines.append(_Line(len(body) - len(body.lstrip(" ")), body.strip(), no))
    if not lines:
        return {}
    value, idx = _parse_block(lines, 0, lines[0].indent)
    if idx != len(lines):
        raise YamlError("unexpected indentation", lines[idx].no)
    return value


def _parse_block(lines, idx, indent):
    if lines[idx].text.startswith("- "):
        return _parse_seq(lines, idx, indent)
    if lines[idx].text == "-":
        return _parse_seq(lines, idx, indent)
    return _parse_map(lines, idx, indent)


def _parse_map(lines, idx, indent):
    out = {}
    while idx < len(lines):
        ln = lines[idx]
        if ln.indent < indent:
            break
        if ln.indent > indent:
            raise YamlError("unexpected indentation in mapping", ln.no)
        if ln.text.startswith("- "):
            raise YamlError("sequence item where a mapping key was expected", ln.no)
        key, rest = _split_key(ln.text, ln.no)
        if key is None:
            raise YamlError("expected 'key: value', got %r" % ln.text, ln.no)
        idx += 1
        if rest != "":
            out[key] = _scalar(rest, ln.no)
            continue
        if idx < len(lines) and lines[idx].indent > indent:
            out[key], idx = _parse_block(lines, idx, lines[idx].indent)
        elif (
            idx < len(lines)
            and lines[idx].indent == indent
            and lines[idx].text.startswith("-")
        ):
            # a sequence written at the same indentation as its key
            out[key], idx = _parse_seq(lines, idx, indent)
        else:
            out[key] = None
    return out, idx


def _parse_seq(lines, idx, indent):
    out = []
    while idx < len(lines):
        ln = lines[idx]
        if ln.indent < indent:
            break
        if ln.indent > indent:
            raise YamlError("unexpected indentation in sequence", ln.no)
        if not ln.text.startswith("-"):
            break
        item = ln.text[1:].strip()
        idx += 1
        if item == "":
            if idx < len(lines) and lines[idx].indent > indent:
                value, idx = _parse_block(lines, idx, lines[idx].indent)
                out.append(value)
            else:
                out.append(None)
            continue
        key, rest = _split_key(item, ln.no)
        if key is None:
            out.append(_scalar(item, ln.no))
            continue
        # "- key: value" opens an inline mapping; its siblings are indented to
        # the column the key started at.
        child_indent = ln.indent + 2
        entry = {key: _scalar(rest, ln.no) if rest != "" else None}
        if rest == "" and idx < len(lines) and lines[idx].indent > child_indent:
            entry[key], idx = _parse_block(lines, idx, lines[idx].indent)
        while idx < len(lines) and lines[idx].indent == child_indent and not lines[
            idx
        ].text.startswith("- "):
            sub = lines[idx]
            k2, r2 = _split_key(sub.text, sub.no)
            if k2 is None:
                raise YamlError("expected 'key: value', got %r" % sub.text, sub.no)
            idx += 1
            if r2 != "":
                entry[k2] = _scalar(r2, sub.no)
            elif idx < len(lines) and lines[idx].indent > child_indent:
                entry[k2], idx = _parse_block(lines, idx, lines[idx].indent)
            elif (
                idx < len(lines)
                and lines[idx].indent == child_indent
                and lines[idx].text.startswith("-")
            ):
                entry[k2], idx = _parse_seq(lines, idx, child_indent)
            else:
                entry[k2] = None
        out.append(entry)
    return out, idx


def load(path):
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    try:
        import yaml  # noqa: F401  (optional, only used when already installed)
    except ImportError:
        return loads(text)
    else:
        data = yaml.safe_load(text)
        return {} if data is None else data


_PLAIN_SAFE = re.compile(r"^[A-Za-z_][A-Za-z0-9_./@+-]*$")
_RESERVED = {
    "true", "false", "yes", "no", "on", "off", "null", "none", "~",
    "y", "n",
}


def _emit_scalar(value):
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return repr(value)
    text = str(value)
    if text == "":
        return "''"
    if text.lower() in _RESERVED or not _PLAIN_SAFE.match(text) or text != text.strip():
        return "'" + text.replace("'", "''") + "'"
    if _INT_RE.match(text) or _FLOAT_RE.match(text):
        return "'" + text + "'"
    return text


def _emit(value, indent, out):
    pad = " " * indent
    if isinstance(value, dict):
        if not value:
            out.append("{}")
            return
        for key, val in value.items():
            head = "%s%s:" % (pad, _emit_scalar(key))
            if isinstance(val, dict):
                if val:
                    out.append(head)
                    _emit(val, indent + 2, out)
                else:
                    out.append(head + " {}")
            elif isinstance(val, (list, tuple)):
                if val:
                    out.append(head)
                    _emit(list(val), indent + 2, out)
                else:
                    out.append(head + " []")
            else:
                out.append("%s %s" % (head, _emit_scalar(val)))
    elif isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, dict):
                if not item:
                    out.append("%s- {}" % pad)
                    continue
                keys = list(item.keys())
                first = True
                for key in keys:
                    val = item[key]
                    prefix = "%s- " % pad if first else "%s  " % pad
                    first = False
                    head = "%s%s:" % (prefix, _emit_scalar(key))
                    if isinstance(val, dict):
                        if val:
                            out.append(head)
                            _emit(val, indent + 4, out)
                        else:
                            out.append(head + " {}")
                    elif isinstance(val, (list, tuple)):
                        if val:
                            out.append(head)
                            _emit(list(val), indent + 4, out)
                        else:
                            out.append(head + " []")
                    else:
                        out.append("%s %s" % (head, _emit_scalar(val)))
            elif isinstance(item, (list, tuple)):
                raise YamlError("nested sequences are not supported by the writer")
            else:
                out.append("%s- %s" % (pad, _emit_scalar(item)))
    else:
        out.append(pad + _emit_scalar(value))


def dumps(data):
    out = []
    _emit(data, 0, out)
    return "\n".join(out) + "\n"


def dump(data, path):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(dumps(data))
