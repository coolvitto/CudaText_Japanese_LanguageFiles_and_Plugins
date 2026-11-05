# -*- coding: utf-8 -*-
"""Cuda Cool Grep - core logic (no CudaText API used here, so it can be unit-tested)."""

import os
import re
import fnmatch
import unicodedata
from datetime import datetime

# ---------------------------------------------------------------- encodings

ENC_IDS = ['auto', 'utf8', 'utf8bom', 'cp932', 'eucjp', 'utf16le', 'utf16be', 'iso2022jp']
ENC_CODECS = {
    'utf8': 'utf-8',
    'utf8bom': 'utf-8',
    'cp932': 'cp932',
    'eucjp': 'euc_jp',
    'utf16le': 'utf-16-le',
    'utf16be': 'utf-16-be',
    'iso2022jp': 'iso2022_jp',
}
# candidates for auto detection (id, enabled)
DEFAULT_ORDER = [('utf8', True), ('iso2022jp', True), ('cp932', True), ('eucjp', True)]

BOMS = [
    (b'\xff\xfe\x00\x00', 'utf-32-le'),
    (b'\x00\x00\xfe\xff', 'utf-32-be'),
    (b'\xef\xbb\xbf', 'utf-8'),
    (b'\xff\xfe', 'utf-16-le'),
    (b'\xfe\xff', 'utf-16-be'),
]

MAX_FILE_SIZE = 300 * 1024 * 1024
MAX_BINARY_SIZE = 128 * 1024 * 1024


class FileText(object):
    def __init__(self, text, codec, bom=b'', binary=False, lossy=False):
        self.text = text
        self.codec = codec
        self.bom = bom
        self.binary = binary
        self.lossy = lossy
        self.raw = None     # raw bytes, kept only for binary files

    def encode(self, new_text):
        return self.bom + new_text.encode(self.codec)


def order_to_str(order):
    return ','.join((i if on else '-' + i) for i, on in order)


def order_from_str(s):
    res = []
    seen = set()
    for item in (s or '').split(','):
        item = item.strip()
        if not item:
            continue
        on = not item.startswith('-')
        i = item.lstrip('-')
        if i in ENC_CODECS and i not in seen and i in [x for x, _ in DEFAULT_ORDER]:
            res.append((i, on))
            seen.add(i)
    for i, on in DEFAULT_ORDER:
        if i not in seen:
            res.append((i, on))
    return res


def _jp_score(t):
    s = 0
    for ch in t:
        o = ord(ch)
        if 0x3040 <= o <= 0x30FF or 0x4E00 <= o <= 0x9FFF or 0x3000 <= o <= 0x303F or 0xFF01 <= o <= 0xFF5E:
            s += 1
        elif 0xFF61 <= o <= 0xFF9F:
            s -= 2
        elif o < 0x20 and ch not in '\t\r\n':
            s -= 3
        elif 0x80 <= o < 0x3000 or 0xE000 <= o <= 0xF8FF:
            s -= 1
    return s


def _guess_utf16(head):
    n = len(head)
    if n < 2:
        return None
    odd = head[1::2].count(0)
    even = head[0::2].count(0)
    if odd > n // 4 and even * 4 < odd:
        return 'utf-16-le'
    if even > n // 4 and odd * 4 < even:
        return 'utf-16-be'
    return None


def decode_raw(raw, enc_id='auto', order=None, utf16_ok=False, binary_ok=False):
    """Returns FileText, or None when the file has to be skipped (binary)."""
    if order is None:
        order = DEFAULT_ORDER
    head = raw[:8192]

    # BOM always wins in auto mode
    bom_found = b''
    bom_codec = None
    for b, c in BOMS:
        if raw.startswith(b):
            bom_found, bom_codec = b, c
            break

    if enc_id != 'auto':
        codec = ENC_CODECS.get(enc_id, 'utf-8')
        bom = b''
        body = raw
        if enc_id in ('utf8', 'utf8bom') and raw.startswith(b'\xef\xbb\xbf'):
            bom, body = b'\xef\xbb\xbf', raw[3:]
        if enc_id == 'utf16le' and raw.startswith(b'\xff\xfe'):
            bom, body = b'\xff\xfe', raw[2:]
        if enc_id == 'utf16be' and raw.startswith(b'\xfe\xff'):
            bom, body = b'\xfe\xff', raw[2:]
        if enc_id not in ('utf16le', 'utf16be') and b'\x00' in head:
            if not binary_ok:
                return None
            return FileText(raw.decode('latin-1'), 'latin-1', b'', True)
        try:
            return FileText(body.decode(codec), codec, bom)
        except UnicodeDecodeError:
            return FileText(body.decode(codec, 'replace'), codec, bom, False, True)

    if bom_codec:
        body = raw[len(bom_found):]
        try:
            return FileText(body.decode(bom_codec), bom_codec, bom_found)
        except UnicodeDecodeError:
            return FileText(body.decode(bom_codec, 'replace'), bom_codec, bom_found, False, True)

    if b'\x00' in head:
        if utf16_ok:
            c = _guess_utf16(head)
            if c:
                try:
                    return FileText(raw.decode(c), c, b'')
                except UnicodeDecodeError:
                    return FileText(raw.decode(c, 'replace'), c, b'', False, True)
        if not binary_ok:
            return None
        return FileText(raw.decode('latin-1'), 'latin-1', b'', True)

    if not raw:
        return FileText('', 'utf-8')

    enabled = [i for i, on in order if on]

    if (b'\x1b$' in raw or b'\x1b(' in raw) and 'iso2022jp' in enabled:
        try:
            return FileText(raw.decode('iso2022_jp'), 'iso2022_jp')
        except UnicodeDecodeError:
            pass

    try:
        return FileText(raw.decode('ascii'), 'utf-8')
    except UnicodeDecodeError:
        pass

    ok = []
    for i in enabled:
        codec = ENC_CODECS[i]
        try:
            t = raw.decode(codec)
        except UnicodeDecodeError:
            continue
        if i == 'utf8':
            return FileText(t, 'utf-8')
        ok.append((i, codec, t))
    if ok:
        best = max(ok, key=lambda x: _jp_score(x[2]))
        # max() returns the first of equal scores, i.e. the one earliest in the order
        return FileText(best[2], best[1])

    codec = ENC_CODECS[enabled[0]] if enabled else 'utf-8'
    return FileText(raw.decode(codec, 'replace'), codec, b'', False, True)


def read_file(path, enc_id='auto', order=None, utf16_ok=False, binary_ok=False):
    try:
        if os.path.getsize(path) > MAX_FILE_SIZE:
            return None
        with open(path, 'rb') as f:
            raw = f.read()
    except OSError:
        return None
    ft = decode_raw(raw, enc_id, order, utf16_ok, binary_ok)
    if ft is not None and ft.binary:
        if len(raw) > MAX_BINARY_SIZE:
            return None
        ft.raw = raw
    return ft


def write_file(path, ft, new_text, backup=False):
    import shutil
    data = ft.encode(new_text)
    if backup:
        shutil.copy2(path, path + '.bak')
    tmp = path + '.cgtmp'
    try:
        with open(tmp, 'wb') as f:
            f.write(data)
        try:
            shutil.copymode(path, tmp)
        except OSError:
            pass
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


# ---------------------------------------------------------------- text helpers

_EOL = re.compile(r'(\r\n|\r|\n)')


def split_lines(text):
    parts = _EOL.split(text)
    return parts[0::2], parts[1::2]


_MARKS = '\u3099\u309a\uff9e\uff9f'


def fz_line(s):
    """Normalize for fuzzy search. Returns (normalized, index_map or None).
    index_map[i] = (start, end) of the original text for normalized char i."""
    if s.isascii():
        return s.lower(), None
    out = []
    idx = []
    i = 0
    n = len(s)
    while i < n:
        j = i + 1
        while j < n and s[j] in _MARKS:
            j += 1
        t = unicodedata.normalize('NFKC', s[i:j]).lower()
        for ch in t:
            o = ord(ch)
            if 0x30A1 <= o <= 0x30F6:
                ch = chr(o - 0x60)
            out.append(ch)
            idx.append((i, j))
        i = j
    return ''.join(out), idx


def _fz_pattern(q, regex):
    if not regex:
        return fz_line(q)[0]
    res = []
    i = 0
    n = len(q)
    while i < n:
        c = q[i]
        if c == '\\' and i + 1 < n:
            res.append(q[i:i + 2])
            i += 2
            continue
        res.append(fz_line(c)[0])
        i += 1
    return ''.join(res)


class Matcher(object):
    def __init__(self, query, case=False, word=False, regex=False, fuzzy=False):
        self.query = query
        self.regex = regex
        self.fuzzy = fuzzy
        pat = _fz_pattern(query, regex) if fuzzy else query
        if not regex:
            pat = re.escape(pat)
        if word:
            pat = r'(?<!\w)(?:' + pat + r')(?!\w)'
        flags = 0
        if fuzzy or not case:
            flags |= re.IGNORECASE
        self.rx = re.compile(pat, flags)

    def has_match(self, line):
        if self.fuzzy:
            line = fz_line(line)[0]
        return self.rx.search(line) is not None

    def iter_matches(self, line):
        """yield (start, end, match, idx_map) in coordinates of the original line"""
        if self.fuzzy:
            nl, idx = fz_line(line)
        else:
            nl, idx = line, None
        for m in self.rx.finditer(nl):
            a, b = m.span()
            if idx is None:
                yield a, b, m, None
            else:
                sa = idx[a][0] if a < len(idx) else len(line)
                sb = idx[b - 1][1] if b > a else sa
                yield sa, sb, m, idx

    def spans(self, line, limit=1000):
        res = []
        for a, b, m, idx in self.iter_matches(line):
            if b > a:
                res.append((a, b))
                if len(res) >= limit:
                    break
        return res

    @staticmethod
    def _group(m, n, line, idx):
        try:
            a, b = m.span(n)
        except IndexError:
            return ''
        if a < 0:
            return ''
        if idx is None:
            return line[a:b]
        sa = idx[a][0] if a < len(idx) else len(line)
        sb = idx[b - 1][1] if b > a else sa
        return line[sa:sb]

    def expand(self, tpl, m, line, idx):
        out = []
        i = 0
        n = len(tpl)
        while i < n:
            c = tpl[i]
            if c == '\\' and i + 1 < n:
                d = tpl[i + 1]
                if d.isdigit() and d.isascii():
                    out.append(self._group(m, int(d), line, idx))
                    i += 2
                    continue
                if d == 'n':
                    out.append('\n')
                    i += 2
                    continue
                if d == 't':
                    out.append('\t')
                    i += 2
                    continue
                if d == '\\':
                    out.append('\\')
                    i += 2
                    continue
                if d == 'g' and i + 2 < n and tpl[i + 2] == '<':
                    j = tpl.find('>', i + 3)
                    if j > 0:
                        name = tpl[i + 3:j]
                        key = int(name) if name.isdigit() else name
                        out.append(self._group(m, key, line, idx))
                        i = j + 1
                        continue
            out.append(c)
            i += 1
        return ''.join(out)

    def replace_line(self, line, repl):
        """returns (new_line, count)"""
        out = []
        last = 0
        cnt = 0
        for sa, sb, m, idx in self.iter_matches(line):
            out.append(line[last:sa])
            out.append(self.expand(repl, m, line, idx) if self.regex else repl)
            last = sb
            cnt += 1
        if not cnt:
            return line, 0
        out.append(line[last:])
        return ''.join(out), cnt



# ---------------------------------------------------------------- grep / replace on text

def grep_text(ft, matcher, invert=False, limit=0):
    """returns list of (y, line, spans)"""
    lines, seps = split_lines(ft.text)
    hits = []
    for y, line in enumerate(lines):
        if invert and not line and seps and y == len(lines) - 1:
            continue
        if invert:
            if not matcher.has_match(line):
                hits.append((y, line, []))
        else:
            sp = matcher.spans(line)
            if sp or matcher.has_match(line):
                hits.append((y, line, sp))
        if limit and len(hits) >= limit:
            break
    return hits


_CHUNK = re.compile('[^\\x00-\\x08\\x0a-\\x1f\\x7f\\udc80-\\udcff\\ufffd]+')


def grep_binary(raw, matcher, utf16=False, limit=200):
    """Search strings inside a binary file. The bytes are viewed as Latin-1 (ASCII),
    and, depending on the query, also as Shift_JIS, UTF-8 and (if utf16) UTF-16LE.
    returns list of (byte_offset, view_label, snippet, spans_in_snippet)"""
    views = [('ASCII', 'latin-1', 0)]
    if matcher.regex or matcher.fuzzy or not matcher.query.isascii():
        views.append(('Shift_JIS', 'cp932', 0))
        views.append(('UTF-8', 'utf-8', 0))
    if utf16:
        views.append(('UTF-16LE', 'utf-16-le', 0))
        views.append(('UTF-16LE', 'utf-16-le', 1))
    hits = []
    seen = set()
    for label, codec, align in views:
        if codec == 'utf-16-le':
            body = raw[align:]
            body = body[:len(body) - (len(body) % 2)]
            text = body.decode(codec, 'replace')
        elif codec == 'latin-1':
            text = raw.decode(codec)
        else:
            text = raw.decode(codec, 'surrogateescape')
        for m in _CHUNK.finditer(text):
            chunk = m.group()
            if not matcher.has_match(chunk):
                continue
            spans = matcher.spans(chunk)
            s0 = spans[0][0] if spans else 0
            start = max(0, s0 - 40)
            end = min(len(chunk), s0 + 160)
            snippet = chunk[start:end]
            sp = [(a - start, b - start) for a, b in spans if a >= start and b <= end]
            idx = m.start() + s0
            if codec == 'latin-1':
                off = idx
            elif codec == 'utf-16-le':
                off = align + 2 * idx
            else:
                off = len(text[:idx].encode(codec, 'surrogateescape'))
            if off in seen:
                continue
            seen.add(off)
            hits.append((off, label, snippet, sp))
            if len(hits) >= limit:
                return hits
    hits.sort(key=lambda h: h[0])
    return hits


class Plan(object):
    def __init__(self):
        self.new_text = None
        self.changes = []   # (y, old, new, count)
        self.total = 0


def plan_replace(ft, matcher, repl):
    lines, seps = split_lines(ft.text)
    plan = Plan()
    new_lines = []
    for y, line in enumerate(lines):
        new, cnt = matcher.replace_line(line, repl)
        if cnt:
            if '\n' in new:
                eol = seps[y] if y < len(seps) else (seps[0] if seps else '\n')
                new = new.replace('\n', eol)
            if new != line:
                plan.changes.append((y, line, new, cnt))
            plan.total += cnt
        new_lines.append(new)
    if plan.changes:
        out = []
        for i, l in enumerate(new_lines):
            out.append(l)
            if i < len(seps):
                out.append(seps[i])
        plan.new_text = ''.join(out)
    return plan


# ---------------------------------------------------------------- file walking

def split_patterns(s):
    res = []
    for p in re.split(r'[;|]', s or ''):
        p = p.strip().strip('"')
        if p:
            res.append(p)
    return res


def _match_any(name, pats):
    n = name.lower()
    for p in pats:
        if fnmatch.fnmatchcase(n, p.lower()):
            return True
    return False


def _is_hidden(entry):
    if entry.name.startswith('.'):
        return True
    if os.name == 'nt':
        try:
            return bool(entry.stat().st_file_attributes & 2)
        except (OSError, AttributeError):
            return False
    return False


def parse_date(s):
    s = (s or '').strip()
    if not s:
        return None
    for f in ('%Y-%m-%d', '%Y/%m/%d', '%Y-%m-%d %H:%M', '%Y/%m/%d %H:%M'):
        try:
            return datetime.strptime(s, f).timestamp()
        except ValueError:
            pass
    raise ValueError(s)


class WalkOptions(object):
    def __init__(self):
        self.include = []
        self.exclude_files = []
        self.exclude_dirs = []
        self.subdirs = True
        self.max_depth = None
        self.hidden = False
        self.size_min = None   # bytes
        self.size_max = None
        self.date_from = None  # timestamps
        self.date_to = None


def walk_files(root, wo):
    if os.path.isfile(root):
        yield root
        return
    inc = [p for p in wo.include if p not in ('*.*', '*')]
    all_files = (not inc)

    def _walk(path, depth):
        try:
            entries = sorted(os.scandir(path), key=lambda e: e.name.lower())
        except OSError:
            return
        dirs = []
        for e in entries:
            try:
                is_dir = e.is_dir(follow_symlinks=False)
                is_file = (not is_dir) and e.is_file()
            except OSError:
                continue
            if not wo.hidden and _is_hidden(e):
                continue
            if is_dir:
                dirs.append(e)
                continue
            if not is_file:
                continue
            if not all_files and not _match_any(e.name, inc):
                continue
            if wo.exclude_files and _match_any(e.name, wo.exclude_files):
                continue
            if wo.size_min is not None or wo.size_max is not None or wo.date_from is not None or wo.date_to is not None:
                try:
                    st = e.stat()
                except OSError:
                    continue
                if wo.size_min is not None and st.st_size < wo.size_min:
                    continue
                if wo.size_max is not None and st.st_size > wo.size_max:
                    continue
                if wo.date_from is not None and st.st_mtime < wo.date_from:
                    continue
                if wo.date_to is not None and st.st_mtime > wo.date_to:
                    continue
            yield e.path
        if wo.subdirs and (wo.max_depth is None or depth < wo.max_depth):
            for d in dirs:
                if wo.exclude_dirs and _match_any(d.name, wo.exclude_dirs):
                    continue
                for p in _walk(d.path, depth + 1):
                    yield p

    for p in _walk(root, 0):
        yield p
