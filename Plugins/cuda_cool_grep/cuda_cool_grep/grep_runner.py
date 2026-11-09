# -*- coding: utf-8 -*-
"""Cuda Cool Grep - runs grep / replace and shows results (uses CudaText API)."""

import os
import re
import time
from cudatext import *
from cudax_lib import get_translation
from . import grep_core as core

_ = get_translation(__file__)

TAG_RESULT = 'cool_grep_result'   # PROP_TAG of the result tab
ATTR_TAG = 4371021                # tag of the highlight attributes
HL_FONT = 0x000000
HL_BG = 0x80FFFF                  # yellow (BGR)
MAX_LINES = 50000
MAX_MARKS = 20000

# output line -> (path, line_index, column, length)
RESULTS = {}
LAST = {'matcher': None, 'highlight': False}

_RX_LINE = re.compile(r'^(.+?)\((\d+)\): ')


class Options(object):
    """plain container, filled by the dialog"""
    def __init__(self):
        self.mode = 'grep'          # 'grep' / 'replace'
        self.preview = False
        self.search = ''
        self.replace = ''
        self.files = '*.*'
        self.wildcard = ''
        self.folder = ''
        self.case = False
        self.word = False
        self.regex = False
        self.fuzzy = False
        self.extra = False
        self.extra_cfg = {}
        self.hidden = False
        self.highlight = True
        self.invert = False
        self.binary = False
        self.utf16 = False
        self.backup = False
        self.confirm = False
        self.open_editor = False
        self.subdirs = True
        self.depth = None           # None = all
        self.enc = 'auto'
        self.enc_order = core.DEFAULT_ORDER
        self.out_fmt = 0            # 0 standard, 1 file names, 2 names+counts
        self.out_dest = 0           # 0 auto, 1 output panel, 2 new tab


# ------------------------------------------------------------------ helpers

def _walk_options(o):
    wo = core.WalkOptions()
    wo.include = core.split_patterns(o.files) or ['*.*']
    exc = core.split_patterns(o.wildcard)
    wo.exclude_files = [p for p in exc if p[-1] not in '/\\']
    wo.exclude_dirs = [p.rstrip('/\\') for p in exc if p[-1] in '/\\']
    wo.subdirs = o.subdirs
    wo.max_depth = o.depth
    wo.hidden = o.hidden
    if o.extra:
        c = o.extra_cfg
        wo.exclude_dirs += core.split_patterns(c.get('ex_dirs', ''))
        wo.exclude_files += core.split_patterns(c.get('ex_files', ''))
        try:
            v = c.get('size_min', '').strip()
            wo.size_min = int(float(v) * 1024) if v else None
            v = c.get('size_max', '').strip()
            wo.size_max = int(float(v) * 1024) if v else None
            wo.date_from = core.parse_date(c.get('date_from', ''))
            wo.date_to = core.parse_date(c.get('date_to', ''))
            if wo.date_to is not None and len(c.get('date_to', '').strip()) <= 10:
                wo.date_to += 86400 - 1
        except ValueError:
            raise ValueError(_('Invalid value in the extra conditions.'))
    return wo


_RX_CTRL = re.compile(r'[\x00-\x08\x0a-\x1f\x7f-\x9f\ud800-\udfff\ue000-\uf8ff\ufdd0-\ufdef\ufff0-\uffff\U00010000-\U0010ffff]')


def _clean(text, limit=2000):
    # one-to-one replacement, so positions of matches stay valid
    text = _RX_CTRL.sub(' ', text)
    if len(text) > limit:
        text = text[:limit] + '...'
    return text


def clear_highlights():
    try:
        for h in ed_handles():
            Editor(h).attr(MARKERS_DELETE_BY_TAG, tag=ATTR_TAG)
    except Exception:
        pass


def apply_highlight(e):
    m = LAST.get('matcher')
    if not m or not LAST.get('highlight'):
        return
    xs, ys, ls = [], [], []
    n = min(e.get_line_count(), 300000)
    for y in range(n):
        line = e.get_text_line(y)
        for a, b in m.spans(line):
            xs.append(a)
            ys.append(y)
            ls.append(b - a)
        if len(xs) >= MAX_MARKS:
            break
    e.attr(MARKERS_DELETE_BY_TAG, tag=ATTR_TAG)
    if xs:
        e.attr(MARKERS_ADD, tag=ATTR_TAG, x=xs, y=ys, len=ls, color_font=HL_FONT, color_bg=HL_BG)


def _open_editors():
    res = {}
    for h in ed_handles():
        e = Editor(h)
        fn = e.get_filename()
        if fn:
            res[os.path.normcase(os.path.abspath(fn))] = e
    return res


class _Progress(object):
    """status bar message with a rotating mark, so that the user can see that the search is alive"""
    FRAMES = '|/-*'

    def __init__(self):
        self.last = 0.0
        self.i = 0
        self.text = ''
        app_proc(PROC_SET_ESCAPE, '0')

    def tick(self, text=None):
        if text is not None:
            self.text = text
        now = time.time()
        if now - self.last > 0.12:
            self.last = now
            self.i = (self.i + 1) % len(self.FRAMES)
            # the mark is at the end: the width of the marks differs in a proportional font, and the text before it must not move
            msg_status(self.text + '  ' + self.FRAMES[self.i], True)

    def cancelled(self):
        if app_proc(PROC_GET_ESCAPE, ''):
            app_proc(PROC_SET_ESCAPE, '0')
            return True
        return False

    def poll(self):
        """called from inside the long running searching functions"""
        self.tick()
        if self.cancelled():
            raise core.Cancelled()


class _Sink(object):
    """collects output lines; writes to the Output panel at once, or to a new tab at the end"""
    def __init__(self, to_tab):
        self.to_tab = to_tab
        self.lines = []
        self.marks = []    # (line_index, start, end)
        self.count = 0
        if not to_tab:
            app_log(LOG_CLEAR, '', panel=LOG_PANEL_OUTPUT)
            # our own double-click handler (on_output_nav) is used instead of the default navigation
            app_log(LOG_SET_REGEX, r'^\x01cool_grep_no_match\x01$', panel=LOG_PANEL_OUTPUT)
            app_log(LOG_SET_NAME_ID, '1', panel=LOG_PANEL_OUTPUT)
            app_log(LOG_SET_LINE_ID, '2', panel=LOG_PANEL_OUTPUT)
            try:
                app_proc(PROC_BOTTOMPANEL_ACTIVATE, 'Output')
            except Exception:
                pass

    def add(self, line, marks=None):
        if self.to_tab:
            idx = len(self.lines)
            self.lines.append(line)
            for a, b in (marks or []):
                self.marks.append((idx, a, b))
        else:
            app_log(LOG_ADD, line, panel=LOG_PANEL_OUTPUT)

    def finish(self):
        if not self.to_tab:
            return
        file_open('')
        e = ed
        try:
            # the tab is UTF-8 (just in case)
            e.set_prop(PROP_ENC, 'UTF-8')
        except Exception:
            pass
        # ed.insert() decodes the text as UTF-8 directly; set_text_all() falls back to the ANSI code page
        # when it finds anything that looks invalid, which garbles the whole text
        e.set_text_all('')
        e.insert(0, 0, '\n'.join(self.lines) + '\n')
        e.set_prop(PROP_TAG, TAG_RESULT)
        try:
            e.set_prop(PROP_TAB_TITLE, 'Cool Grep')
        except Exception:
            pass
        e.set_prop(PROP_MODIFIED, False)
        e.set_caret(0, 0)
        if self.marks:
            m = self.marks[:MAX_MARKS]
            e.attr(MARKERS_DELETE_BY_TAG, tag=ATTR_TAG)
            e.attr(MARKERS_ADD, tag=ATTR_TAG,
                   x=[a for _i, a, _b in m], y=[i for i, _a, _b in m], len=[b - a for _i, a, b in m],
                   color_font=HL_FONT, color_bg=HL_BG)


def _fmt_line(path, y, text):
    return '{}({}): {}'.format(path, y + 1, text)


def _register(line, path, y=0, x=0, ln=0):
    if len(RESULTS) < 200000:
        RESULTS[line] = (path, y, x, ln)


def _check_common(o):
    """returns Matcher or None (error already shown)"""
    if not o.search:
        msg_box(_('Enter a search string.'), MB_OK + MB_ICONWARNING)
        return None
    if not o.folder or not os.path.exists(o.folder):
        msg_box(_('Folder not found: {}').format(o.folder), MB_OK + MB_ICONWARNING)
        return None
    try:
        return core.Matcher(o.search, o.case, o.word, o.regex, o.fuzzy)
    except re.error as ex:
        msg_box(_('Invalid regular expression: {}').format(ex), MB_OK + MB_ICONERROR)
        return None


# ------------------------------------------------------------------ grep

def run_grep(o):
    matcher = _check_common(o)
    if matcher is None:
        return
    try:
        wo = _walk_options(o)
    except ValueError as ex:
        msg_box(str(ex), MB_OK + MB_ICONWARNING)
        return

    clear_highlights()
    RESULTS.clear()
    LAST['matcher'] = matcher
    LAST['highlight'] = bool(o.highlight and not o.invert)

    sink = _Sink(o.out_dest == 2)
    sink.add(_('[Cool Grep] "{q}"  folder: {f}  files: {m}').format(q=o.search, f=o.folder, m=o.files))
    prog = _Progress()
    searched = hit_files = hit_lines = 0
    truncated = cancelled = False

    for path in core.walk_files(o.folder, wo):
        searched += 1
        if prog.cancelled():
            cancelled = True
            break
        prog.tick(_('Cool Grep: {n} files searched, {m} lines found - {f} (Esc to cancel)').format(
            n=searched, m=hit_lines, f=os.path.basename(path)))
        ft = core.read_file(path, o.enc, o.enc_order, o.utf16, o.binary)
        if ft is None:
            continue
        path = os.path.normpath(path)
        entries = []   # (head, text, spans, nav)
        try:
            if ft.binary:
                if o.invert:
                    continue
                ft_raw, ft.raw = ft.raw, None
                for off, label, snippet, sp in core.grep_binary(ft_raw, matcher, o.utf16, progress=prog.poll):
                    entries.append(('{}(0x{:08X} {}): '.format(path, off, label), _clean(snippet), sp, (path, 0, 0, 0)))
            else:
                for y, line, spans in core.grep_text(ft, matcher, o.invert, progress=prog.poll):
                    a = spans[0][0] if spans else 0
                    ln = (spans[0][1] - spans[0][0]) if spans else 0
                    entries.append((_fmt_line(path, y, ''), _clean(line), spans, (path, y, a, ln)))
        except re.error:
            entries = []
        except core.Cancelled:
            cancelled = True
            break
        if not entries:
            continue
        hit_files += 1
        hit_lines += len(entries)
        if o.out_fmt == 0:
            for head, text, spans, nav in entries:
                out = head + text
                _register(out, *nav)
                sink.add(out, [(len(head) + s, len(head) + e) for s, e in spans if e <= len(text)] if o.highlight else None)
                sink.count += 1
        elif o.out_fmt == 1:
            _register(path, path)
            sink.add(path)
            sink.count += 1
        else:
            out = '{} ({})'.format(path, len(entries))
            _register(out, path)
            sink.add(out)
            sink.count += 1
        if sink.count >= MAX_LINES:
            truncated = True
            break

    footer = _('[Cool Grep] {n} lines found in {m} files ({k} files searched)').format(n=hit_lines, m=hit_files, k=searched)
    if cancelled:
        footer += ' ' + _('(interrupted)')
    if truncated:
        footer += ' ' + _('(stopped: too many results)')
    sink.add(footer)
    sink.finish()
    msg_status(footer)


# ------------------------------------------------------------------ replace

def _confirm_text(path, plan):
    sample = []
    for y, old, new, cnt in plan.changes[:3]:
        sample.append('{}: {}  ->  {}'.format(y + 1, _clean(old.strip(), 60), _clean(new.strip(), 60)))
    return _('{p}\n\n{n} places in {l} lines.\n\n{s}\n\nReplace in this file?').format(
        p=path, n=plan.total, l=len(plan.changes), s='\n'.join(sample))


def run_replace(o):
    matcher = _check_common(o)
    if matcher is None:
        return
    try:
        wo = _walk_options(o)
    except ValueError as ex:
        msg_box(str(ex), MB_OK + MB_ICONWARNING)
        return

    clear_highlights()
    RESULTS.clear()
    LAST['matcher'] = None
    LAST['highlight'] = False

    editors = _open_editors()
    sink = _Sink(o.out_dest == 2)
    sink.add(_('[Cool Grep] replace "{q}" -> "{r}"  folder: {f}  files: {m}').format(q=o.search, r=o.replace, f=o.folder, m=o.files))
    prog = _Progress()
    searched = done_files = done_lines = done_places = 0
    cancelled = truncated = False
    errors = []

    def emit(path, changes):
        for y, old, new, cnt in changes:
            if o.preview:
                text = '{}  =>  {}'.format(_clean(old.strip(), 150), _clean(new.strip(), 150))
            else:
                text = _clean(new)
            out = _fmt_line(path, y, text)
            _register(out, path, y)
            sink.add(out)
            sink.count += 1

    for path in core.walk_files(o.folder, wo):
        searched += 1
        if prog.cancelled():
            cancelled = True
            break
        prog.tick(_('Cool Grep: {n} files searched, {m} places replaced (Esc to cancel)').format(n=searched, m=done_places))
        npath = os.path.normpath(path)
        e = editors.get(os.path.normcase(os.path.abspath(path)))

        if e is not None and (o.open_editor or e.get_prop(PROP_MODIFIED)):
            # replace in the editor text (not saved)
            changes = []
            for y in range(e.get_line_count()):
                line = e.get_text_line(y)
                new, cnt = matcher.replace_line(line, o.replace)
                if cnt and new != line:
                    changes.append((y, line, new, cnt))
            if not changes:
                continue
            if not o.preview:
                for y, line, new, cnt in reversed(changes):
                    e.replace(0, y, len(line), y, new)
            done_files += 1
            done_lines += len(changes)
            done_places += sum(c[3] for c in changes)
            emit(npath, changes)
        else:
            ft = core.read_file(path, o.enc, o.enc_order, False, False)
            if ft is None:
                continue
            if ft.lossy:
                errors.append(_('{}: skipped (cannot decode the file with the selected encoding)').format(npath))
                continue
            plan = core.plan_replace(ft, matcher, o.replace)
            if not plan.changes:
                continue
            if not o.preview:
                if o.confirm:
                    r = msg_box(_confirm_text(npath, plan), MB_YESNOCANCEL + MB_ICONQUESTION)
                    if r == ID_CANCEL:
                        cancelled = True
                        break
                    if r != ID_YES:
                        continue
                try:
                    core.write_file(path, ft, plan.new_text, backup=o.backup)
                except (OSError, UnicodeEncodeError) as ex:
                    errors.append(_('{p}: cannot write ({e})').format(p=npath, e=ex))
                    continue
            done_files += 1
            done_lines += len(plan.changes)
            done_places += plan.total
            emit(npath, plan.changes)
        if sink.count >= MAX_LINES:
            truncated = True
            break

    for s in errors:
        sink.add(s)
    if o.preview:
        footer = _('[Cool Grep] {n} places will be replaced in {l} lines of {m} files (preview, {k} files searched)')
    else:
        footer = _('[Cool Grep] {n} places replaced in {l} lines of {m} files ({k} files searched)')
    footer = footer.format(n=done_places, l=done_lines, m=done_files, k=searched)
    if cancelled:
        footer += ' ' + _('(interrupted)')
    if truncated:
        footer += ' ' + _('(stopped: too many results)')
    sink.add(footer)
    sink.finish()
    msg_status(footer)


# ------------------------------------------------------------------ navigation from results

def lookup(line):
    info = RESULTS.get(line)
    if info:
        return info
    m = _RX_LINE.match(line)
    if m and os.path.isfile(m.group(1)):
        return (m.group(1), int(m.group(2)) - 1, 0, 0)
    return None


def goto(info):
    path, y, x, ln = info
    if not os.path.isfile(path):
        msg_status(_('File not found: {}').format(path))
        return
    file_open(path)
    e = ed
    e.focus()
    y = max(0, min(y, e.get_line_count() - 1))
    if ln > 0:
        e.set_caret(x + ln, y, x, y)
    else:
        e.set_caret(x, y)
    if LAST.get('highlight') and LAST.get('matcher'):
        apply_highlight(e)
    msg_status('{}({})'.format(path, y + 1))
