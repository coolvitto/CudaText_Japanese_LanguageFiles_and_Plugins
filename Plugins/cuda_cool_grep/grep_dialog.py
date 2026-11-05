# -*- coding: utf-8 -*-
"""Cuda Cool Grep - dialog (grep / grep and replace in one window, like Hidemaru)."""

import os
import json
import configparser
from cudatext import *
from cudax_lib import get_translation
from . import grep_core as core
from .grep_runner import Options

_ = get_translation(__file__)

CFG_FILE = os.path.join(app_path(APP_DIR_SETTINGS), 'cuda_cool_grep.ini')
HIST_MAX = 20
DEPTH_ITEMS = 10

W = 484
BTN_X = 392
BTN_W = 84


def enc_label(i):
    return {
        'auto': _('Auto detect'),
        'utf8': 'UTF-8',
        'utf8bom': 'UTF-8 (BOM)',
        'cp932': 'Shift_JIS (CP932)',
        'eucjp': 'EUC-JP',
        'utf16le': 'UTF-16 LE',
        'utf16be': 'UTF-16 BE',
        'iso2022jp': 'ISO-2022-JP',
    }[i]


# ------------------------------------------------------------------ settings

class Settings(object):
    def __init__(self):
        self.cp = configparser.ConfigParser(interpolation=None)
        try:
            self.cp.read(CFG_FILE, encoding='utf-8')
        except Exception:
            pass
        for s in ('state', 'history'):
            if not self.cp.has_section(s):
                self.cp.add_section(s)

    def get(self, key, default=''):
        return self.cp.get('state', key, fallback=default)

    def get_bool(self, key, default=False):
        v = self.cp.get('state', key, fallback=None)
        if v is None:
            return default
        return v == '1'

    def get_int(self, key, default=0):
        try:
            return int(self.cp.get('state', key, fallback=default))
        except ValueError:
            return default

    def set(self, key, value):
        if isinstance(value, bool):
            value = '1' if value else '0'
        self.cp.set('state', key, str(value))

    def get_hist(self, key):
        try:
            v = json.loads(self.cp.get('history', key, fallback='[]'))
            return [s for s in v if isinstance(s, str)]
        except ValueError:
            return []

    def push_hist(self, key, value):
        if not value:
            return
        h = [x for x in self.get_hist(key) if x != value]
        h.insert(0, value)
        self.cp.set('history', key, json.dumps(h[:HIST_MAX], ensure_ascii=True))

    def save(self):
        try:
            with open(CFG_FILE, 'w', encoding='utf-8') as f:
                self.cp.write(f)
        except OSError:
            pass


# ------------------------------------------------------------------ helper dialogs

def _simple_dialog(caption, w, h):
    hd = dlg_proc(0, DLG_CREATE)
    dlg_proc(hd, DLG_PROP_SET, prop={'cap': caption, 'w': w, 'h': h, 'border': DBORDER_DIALOG, 'keypreview': True})
    return hd


def _add(hd, typ, name, **props):
    n = dlg_proc(hd, DLG_CTL_ADD, typ)
    props['name'] = name
    dlg_proc(hd, DLG_CTL_PROP_SET, index=n, prop=props)
    return n


def _val(hd, name):
    return dlg_proc(hd, DLG_CTL_PROP_GET, name=name)['val']


def extra_dialog(cfg):
    """dialog of extra conditions. returns new cfg dict or None"""
    hd = _simple_dialog(_('Extra conditions'), 420, 232)
    res = {'cfg': None}
    rows = [
        ('ex_dirs', _('Exclude folders:'), 12),
        ('ex_files', _('Exclude files:'), 44),
        ('size_min', _('Min size (KB):'), 76),
        ('size_max', _('Max size (KB):'), 108),
        ('date_from', _('Modified from (YYYY-MM-DD):'), 140),
        ('date_to', _('Modified to (YYYY-MM-DD):'), 172),
    ]
    for key, cap, y in rows:
        _add(hd, 'label', 'l_' + key, x=12, y=y + 4, w=190, cap=cap)
        _add(hd, 'edit', key, x=206, y=y, w=200, val=cfg.get(key, ''))

    def ok(id_dlg, id_ctl, data='', info=''):
        new = {}
        for key, _c, _y in rows:
            new[key] = _val(hd, key).strip()
        try:
            for k in ('size_min', 'size_max'):
                if new[k]:
                    float(new[k])
            core.parse_date(new['date_from'])
            core.parse_date(new['date_to'])
        except ValueError:
            msg_box(_('Invalid value in the extra conditions.'), MB_OK + MB_ICONWARNING)
            return
        res['cfg'] = new
        dlg_proc(hd, DLG_HIDE)

    def cancel(id_dlg, id_ctl, data='', info=''):
        dlg_proc(hd, DLG_HIDE)

    def keydown(id_dlg, id_ctl, data='', info=''):
        if id_ctl == 27:
            dlg_proc(hd, DLG_HIDE)
            return False

    dlg_proc(hd, DLG_PROP_SET, prop={'on_key_down': keydown})
    _add(hd, 'button', 'ok', x=206, y=200, w=96, cap=_('OK'), ex0=True, on_change=ok)
    _add(hd, 'button', 'cancel', x=310, y=200, w=96, cap=_('Cancel'), on_change=cancel)
    dlg_proc(hd, DLG_SHOW_MODAL)
    dlg_proc(hd, DLG_FREE)
    return res['cfg']


def enc_order_dialog(order):
    """dialog to set order of auto detect. returns new order or None"""
    hd = _simple_dialog(_('Auto detect order'), 360, 276)
    st = {'order': [list(x) for x in order], 'result': None}

    def fill(sel=0):
        items = ['[{}] {}'.format('x' if on else ' ', enc_label(i)) for i, on in st['order']]
        dlg_proc(hd, DLG_CTL_PROP_SET, name='list', prop={'items': '\t'.join(items), 'val': sel})

    def cur():
        try:
            return int(_val(hd, 'list'))
        except (ValueError, TypeError):
            return -1

    def toggle(id_dlg, id_ctl, data='', info=''):
        i = cur()
        if 0 <= i < len(st['order']):
            st['order'][i][1] = not st['order'][i][1]
            fill(i)

    def move(d):
        i = cur()
        j = i + d
        if 0 <= i < len(st['order']) and 0 <= j < len(st['order']):
            st['order'][i], st['order'][j] = st['order'][j], st['order'][i]
            fill(j)

    def ok(id_dlg, id_ctl, data='', info=''):
        if not any(on for _i, on in st['order']):
            msg_box(_('Select at least one encoding.'), MB_OK + MB_ICONWARNING)
            return
        st['result'] = [(i, on) for i, on in st['order']]
        dlg_proc(hd, DLG_HIDE)

    def cancel(id_dlg, id_ctl, data='', info=''):
        dlg_proc(hd, DLG_HIDE)

    def keydown(id_dlg, id_ctl, data='', info=''):
        if id_ctl == 27:
            dlg_proc(hd, DLG_HIDE)
            return False

    dlg_proc(hd, DLG_PROP_SET, prop={'on_key_down': keydown})
    _add(hd, 'label', 'hint', x=12, y=8, w=336, cap=_('Encodings tried in this order when "Auto detect" is selected:'))
    _add(hd, 'listbox', 'list', x=12, y=32, w=230, h=190, on_click_dbl=toggle)
    _add(hd, 'button', 'toggle', x=252, y=32, w=96, cap=_('Toggle(&T)'), on_change=toggle)
    _add(hd, 'button', 'up', x=252, y=64, w=96, cap=_('Move up(&U)'), on_change=lambda a, b, data='', info='': move(-1))
    _add(hd, 'button', 'down', x=252, y=96, w=96, cap=_('Move down(&D)'), on_change=lambda a, b, data='', info='': move(1))
    _add(hd, 'button', 'ok', x=148, y=238, w=96, cap=_('OK'), ex0=True, on_change=ok)
    _add(hd, 'button', 'cancel', x=252, y=238, w=96, cap=_('Cancel'), on_change=cancel)
    fill(0)
    dlg_proc(hd, DLG_SHOW_MODAL)
    dlg_proc(hd, DLG_FREE)
    return st['result']


# ------------------------------------------------------------------ main dialog

class GrepDialog(object):
    def __init__(self):
        self.st = Settings()
        self.replace_mode = (self.st.get('mode', 'grep') == 'replace')
        self.extra_cfg = {
            'ex_dirs': self.st.get('extra_ex_dirs', '.git;.svn;.hg;node_modules'),
            'ex_files': self.st.get('extra_ex_files', ''),
            'size_min': self.st.get('extra_size_min', ''),
            'size_max': self.st.get('extra_size_max', ''),
            'date_from': self.st.get('extra_date_from', ''),
            'date_to': self.st.get('extra_date_to', ''),
        }
        self.enc_order = core.order_from_str(self.st.get('enc_order', ''))
        self.result = None      # Options when OK was pressed
        self.h = None

    # ---- control helpers
    def add(self, typ, name, **props):
        return _add(self.h, typ, name, **props)

    def setp(self, name, **props):
        dlg_proc(self.h, DLG_CTL_PROP_SET, name=name, prop=props)

    def val(self, name):
        return _val(self.h, name)

    def checked(self, name):
        return str(self.val(name)).strip().lower() in ('1', 'true')

    def popup(self, btn, labels, on_pick):
        """drop-down menu just below the given button; on_pick(index) is called on selection"""
        d = dlg_proc(self.h, DLG_CTL_PROP_GET, name=btn)
        nx, ny = dlg_proc(self.h, DLG_COORD_LOCAL_TO_SCREEN, index=d['x'], index2=d['y'] + d['h'])
        hm = menu_proc(0, MENU_CREATE)
        for i, label in enumerate(labels):
            menu_proc(hm, MENU_ADD, command=(lambda i=i: on_pick(i)), caption=label)
        menu_proc(hm, MENU_SHOW, command='%d,%d' % (nx, ny))

    # ---- build
    def build(self):
        st = self.st
        h = self.h = dlg_proc(0, DLG_CREATE)
        dlg_proc(h, DLG_PROP_SET, prop={
            'cap': _('Grep'), 'w': W, 'h': 400, 'border': DBORDER_DIALOG,
            'keypreview': True, 'on_key_down': self.on_key,
        })

        def row(label, name, items, val, btn):
            self.add('label', 'l_' + name, x=12, y=0, w=104, cap=label)
            self.add('combo', name, x=118, y=0, w=232, items='\t'.join(items), val=val)
            self.add('button', 'b_' + name, x=354, y=0, w=24, cap=btn, on_change=getattr(self, 'on_btn_' + name))

        row(_('Search for:'), 'search', st.get_hist('search'), st.get('search'), '>')
        row(_('Replace with:'), 'replace', st.get_hist('replace'), st.get('replace'), '>')
        row(_('File mask:'), 'files', st.get_hist('files'), st.get('files', '*.*'), '>')
        row(_('Wildcard:'), 'wildcard', st.get_hist('wildcard'), st.get('wildcard'), '>')
        row(_('Search folder:'), 'folder', st.get_hist('folder'), self.initial_folder(), '...')
        self.setp('wildcard', hint=_('File name patterns to exclude (separate with ;). A pattern ending with \\ or / excludes folders.'))
        self.setp('files', hint=_('File name patterns (separate with ;), e.g. *.txt;*.py'))

        def chk(name, cap, key, default=False, w=200, cb=None):
            props = dict(x=0, y=0, w=w, cap=cap, val=st.get_bool(key, default))
            if cb:
                # check boxes: handle both events, the handler is idempotent
                props['on_change'] = cb
                props['on_click'] = cb
            self.add('check', name, **props)

        chk('case', _('Case sensitive'), 'case')
        chk('word', _('Whole word'), 'word')
        chk('regex', _('Regular expression'), 'regex')
        chk('fuzzy', _('Fuzzy search'), 'fuzzy')
        chk('extra', _('Extra conditions'), 'extra', w=110, cb=self.on_extra_state)
        self.add('button', 'extra_set', x=0, y=0, w=84, cap=_('Se&ttings...'), on_change=self.on_extra_set)
        chk('hidden', _('Include hidden files and folders'), 'hidden', w=250)
        # grep only
        chk('highlight', _('Highlight search string'), 'highlight', True, w=250)
        chk('invert', _('Show non-matching lines'), 'invert', w=250)
        chk('binary', _('Search binary files'), 'binary', w=250)
        chk('utf16', _('Also decode UTF-16LE 2-byte data'), 'utf16', w=250)
        # replace only
        chk('backup', _('Create backup'), 'backup', w=250)
        chk('confirm', _('Confirm before saving'), 'confirm', w=250)
        chk('open_editor', _('Replace in open tabs (do not save)'), 'open_editor', w=250)

        self.add('bevel', 'sep', x=12, y=0, w=W - 24, h=2)

        chk('subdirs', _('Search subfolders'), 'subdirs', True, w=200, cb=self.on_depth_state)
        chk('depth_on', _('Depth:'), 'depth_on', False, w=70, cb=self.on_depth_state)
        depth_items = [_('All')] + [str(i) for i in range(1, DEPTH_ITEMS + 1)]
        self.add('combo_ro', 'depth', x=0, y=0, w=120, items='\t'.join(depth_items), val=st.get_int('depth_idx', 0))

        self.add('label', 'l_enc', x=0, y=0, w=200, cap=_('Encoding'))
        enc_items = [enc_label(i) for i in core.ENC_IDS]
        self.add('combo_ro', 'enc', x=0, y=0, w=204, items='\t'.join(enc_items), val=st.get_int('enc_idx', 0))
        self.add('button', 'b_enc', x=0, y=0, w=26, cap='...', on_change=self.on_btn_enc)

        self.add('label', 'l_fmt', x=0, y=0, w=200, cap=_('Output format'))
        self.add('combo_ro', 'fmt', x=0, y=0, w=200,
                 items='\t'.join([_('Standard'), _('File names only'), _('File names and counts')]),
                 val=st.get_int('out_fmt', 0))
        self.add('label', 'l_dest', x=0, y=0, w=200, cap=_('Output to'))
        self.add('combo_ro', 'dest', x=0, y=0, w=236,
                 items='\t'.join([_('Auto'), _('Output panel'), _('New tab')]),
                 val=st.get_int('out_dest', 0))

        # buttons (right column)
        self.add('button', 'ok', x=BTN_X, y=12, w=BTN_W, h=26, cap=_('OK'), ex0=True, on_change=self.on_ok)
        self.add('button', 'ok_menu', x=BTN_X + BTN_W - 22, y=12, w=22, h=26, cap='v', on_change=self.on_ok_menu)
        self.add('button', 'cancel', x=BTN_X, y=44, w=BTN_W, h=26, cap=_('Cancel'), on_change=self.on_cancel)
        self.add('button', 'help', x=BTN_X, y=76, w=BTN_W, h=26, cap=_('Help'), on_change=self.on_help)
        self.add('button', 'switch', x=BTN_X, y=112, w=BTN_W, h=26, cap='', on_change=self.on_switch)

        self.on_depth_state()
        self.layout()

    def initial_folder(self):
        try:
            fn = ed.get_filename()
            if fn and os.path.isfile(fn):
                return os.path.dirname(fn)
        except Exception:
            pass
        return self.st.get('folder', '')

    # ---- layout (positions depend on the mode)
    def layout(self):
        rep = self.replace_mode
        P = self.setp
        y = 14
        rows = [('search', True), ('replace', rep), ('files', True), ('wildcard', True), ('folder', True)]
        for name, vis in rows:
            P('l_' + name, vis=vis, y=y + 4)
            P(name, vis=vis, y=y)
            P('b_' + name, vis=vis, y=y - 1, h=26)
            if vis:
                y += 30
        y0 = y + 8      # top of the check box block
        pitch = 24
        L, R = 14, 224

        def put(name, x, row, **kw):
            P(name, x=x, y=y0 + row * pitch, vis=True, **kw)

        def hide(*names):
            for n in names:
                P(n, vis=False)

        put('case', L, 0)
        put('word', L, 1)
        put('regex', L, 2)
        put('fuzzy', L, 3)
        if not rep:
            put('extra', L, 4)
            P('extra_set', x=L + 112, y=y0 + 4 * pitch - 2, vis=True)
            put('highlight', R, 0)
            put('invert', R, 1)
            put('binary', R, 2)
            put('utf16', R, 3)
            put('hidden', R, 4)
            hide('backup', 'confirm', 'open_editor')
        else:
            put('open_editor', L, 4)
            put('backup', R, 0)
            put('confirm', R, 1)
            put('hidden', R, 2)
            put('extra', R, 3)
            P('extra_set', x=R + 112, y=y0 + 3 * pitch - 2, vis=True)
            hide('highlight', 'invert', 'binary', 'utf16')
        P('extra_set', en=self.checked('extra'))

        ys = y0 + 5 * pitch + 6
        P('sep', y=ys)
        y1 = ys + 12
        P('subdirs', x=L, y=y1)
        P('depth_on', x=L, y=y1 + 28)
        P('depth', x=L + 76, y=y1 + 26)
        P('l_enc', x=R, y=y1 + 4)
        P('enc', x=R, y=y1 + 26)
        P('b_enc', x=R + 208, y=y1 + 25, h=26)
        P('l_fmt', x=L, y=y1 + 64)
        P('fmt', x=L, y=y1 + 86)
        P('l_dest', x=R, y=y1 + 64)
        P('dest', x=R, y=y1 + 86)
        height = y1 + 86 + 44

        # buttons
        if rep:
            P('ok', cap=_('Replace'), w=BTN_W - 24)
            P('ok_menu', vis=True)
            P('switch', cap=_('S&earch <<'))
            dlg_proc(self.h, DLG_PROP_SET, prop={'cap': _('Grep and Replace'), 'h': height})
        else:
            P('ok', cap=_('OK'), w=BTN_W)
            P('ok_menu', vis=False)
            P('switch', cap=_('Re&place >>'))
            dlg_proc(self.h, DLG_PROP_SET, prop={'cap': _('Grep'), 'h': height})

    # ---- events
    def on_key(self, id_dlg, id_ctl, data='', info=''):
        if id_ctl == 27:   # Esc
            self.on_cancel()
            return False

    def on_cancel(self, id_dlg=0, id_ctl=0, data='', info=''):
        self.result = None
        dlg_proc(self.h, DLG_HIDE)

    def on_switch(self, id_dlg=0, id_ctl=0, data='', info=''):
        self.replace_mode = not self.replace_mode
        self.layout()

    def on_depth_state(self, id_dlg=0, id_ctl=0, data='', info=''):
        sub = self.checked('subdirs')
        on = self.checked('depth_on')
        self.setp('depth_on', en=sub)
        self.setp('depth', en=(sub and on))

    def on_extra_state(self, id_dlg=0, id_ctl=0, data='', info=''):
        self.setp('extra_set', en=self.checked('extra'))

    def on_extra_set(self, id_dlg=0, id_ctl=0, data='', info=''):
        cfg = extra_dialog(self.extra_cfg)
        if cfg is not None:
            self.extra_cfg = cfg
            self.setp('extra', val=True)
            self.setp('extra_set', en=True)

    def on_btn_enc(self, id_dlg=0, id_ctl=0, data='', info=''):
        order = enc_order_dialog(self.enc_order)
        if order is not None:
            self.enc_order = order

    def on_help(self, id_dlg=0, id_ctl=0, data='', info=''):
        msg_box(_(
            'Cuda Cool Grep\n\n'
            'File mask: patterns separated with ;  e.g. *.txt;*.py\n'
            'Wildcard: patterns of files (or folders, ending with \\) to exclude.\n'
            'Regular expression: matches inside one line. In the replacement text use \\0 (whole match), \\1 to \\9 (groups), \\t and \\n.\n'
            'Fuzzy search: ignores case, full/half width and hiragana/katakana differences.\n'
            'Press Esc while searching to stop.\n'
            'Double-click a result line to jump to the file.'), MB_OK + MB_ICONINFO)

    def _append(self, name, text):
        cur = self.val(name)
        self.setp(name, val=cur + text)

    def _items_menu(self, btn, items, on_pick):
        self.popup(btn, ['{}    {}'.format(a, b) if a else b for a, b in items], on_pick)

    def on_btn_search(self, id_dlg=0, id_ctl=0, data='', info=''):
        items = [
            ('.', _('Any character')), ('.*', _('Any string')), ('^', _('Beginning of line')),
            ('$', _('End of line')), ('\\s', _('White space')), ('\\d', _('Digit')),
            ('\\w', _('Word character')), ('\\t', _('Tab')), ('[]', _('Character class')),
            ('()', _('Group')), ('|', _('Or')), ('\\\\', _('Backslash')),
        ]
        self._items_menu('b_search', items, lambda i: self._append('search', items[i][0]))

    def on_btn_replace(self, id_dlg=0, id_ctl=0, data='', info=''):
        items = [
            ('\\0', _('Whole match')), ('\\1', _('Group 1')), ('\\2', _('Group 2')),
            ('\\3', _('Group 3')), ('\\t', _('Tab')), ('\\n', _('Line break')), ('\\\\', _('Backslash')),
        ]
        self._items_menu('b_replace', items, lambda i: self._append('replace', items[i][0]))

    def on_btn_files(self, id_dlg=0, id_ctl=0, data='', info=''):
        items = [
            ('*.*', _('All files')), ('*.txt', _('Text files')), ('*.txt;*.md;*.log', _('Text, Markdown, log')),
            ('*.py;*.pyw', _('Python')), ('*.c;*.cpp;*.cc;*.h;*.hpp', _('C / C++')),
            ('*.html;*.htm;*.css;*.js', _('Web files')), ('*.pas;*.dpr;*.dfm;*.inc', _('Pascal / Delphi')),
            ('*.po;*.pot;*.ts;*.json;*.ini', _('Translation files')),
        ]
        try:
            fn = ed.get_filename()
            if fn and os.path.splitext(fn)[1]:
                items.append(('*' + os.path.splitext(fn)[1], _('Extension of the current file')))
        except Exception:
            pass
        self._items_menu('b_files', items, lambda i: self.setp('files', val=items[i][0]))

    def on_btn_wildcard(self, id_dlg=0, id_ctl=0, data='', info=''):
        items = [
            ('*.exe;*.dll;*.obj;*.o;*.so', _('Binaries')), ('*.bak;*.tmp;*.old', _('Backup and temporary files')),
            ('*.zip;*.7z;*.rar;*.gz;*.tar', _('Archives')), ('*.png;*.jpg;*.jpeg;*.gif;*.bmp;*.ico', _('Images')),
            ('*.min.js;*.min.css', _('Minified files')), ('.git\\;node_modules\\', _('Folders: .git, node_modules')),
            ('', _('Clear')),
        ]

        def pick(i):
            if not items[i][0]:
                self.setp('wildcard', val='')
                return
            cur = self.val('wildcard').strip()
            self.setp('wildcard', val=(cur + ';' + items[i][0]) if cur else items[i][0])

        self._items_menu('b_wildcard', items, pick)

    def on_btn_folder(self, id_dlg=0, id_ctl=0, data='', info=''):
        d = dlg_dir(self.val('folder'), _('Search folder'))
        if d:
            self.setp('folder', val=d)

    def on_ok_menu(self, id_dlg=0, id_ctl=0, data='', info=''):
        self.popup('ok_menu', [_('Replace'), _('Preview only (do not replace)')],
                   lambda i: self.finish(preview=(i == 1)))

    def on_ok(self, id_dlg=0, id_ctl=0, data='', info=''):
        self.finish(preview=False)

    # ---- collect values
    def finish(self, preview=False):
        o = Options()
        o.mode = 'replace' if self.replace_mode else 'grep'
        o.preview = preview and self.replace_mode
        o.search = self.val('search')
        o.replace = self.val('replace')
        o.files = self.val('files').strip() or '*.*'
        o.wildcard = self.val('wildcard').strip()
        o.folder = self.val('folder').strip().strip('"')
        for k in ('case', 'word', 'regex', 'fuzzy', 'extra', 'hidden', 'highlight', 'invert',
                  'binary', 'utf16', 'backup', 'confirm', 'open_editor', 'subdirs'):
            setattr(o, k, self.checked(k))
        o.extra_cfg = dict(self.extra_cfg)
        depth_idx = int(self.val('depth') or 0)
        o.depth = depth_idx if (o.subdirs and self.checked('depth_on') and depth_idx > 0) else None
        if not o.subdirs:
            o.depth = 0
        enc_idx = int(self.val('enc') or 0)
        o.enc = core.ENC_IDS[enc_idx] if 0 <= enc_idx < len(core.ENC_IDS) else 'auto'
        o.enc_order = self.enc_order
        o.out_fmt = int(self.val('fmt') or 0)
        o.out_dest = int(self.val('dest') or 0)
        if not self.replace_mode:
            o.out_fmt = o.out_fmt
        self.save(o, depth_idx, enc_idx)
        self.result = o
        dlg_proc(self.h, DLG_HIDE)

    def save(self, o, depth_idx, enc_idx):
        st = self.st
        st.set('mode', o.mode)
        for k in ('case', 'word', 'regex', 'fuzzy', 'extra', 'hidden', 'highlight', 'invert',
                  'binary', 'utf16', 'backup', 'confirm', 'open_editor', 'subdirs'):
            st.set(k, getattr(o, k))
        st.set('depth_on', self.checked('depth_on'))
        st.set('depth_idx', depth_idx)
        st.set('enc_idx', enc_idx)
        st.set('out_fmt', o.out_fmt)
        st.set('out_dest', o.out_dest)
        st.set('search', o.search)
        st.set('replace', o.replace)
        st.set('files', o.files)
        st.set('wildcard', o.wildcard)
        st.set('folder', o.folder)
        st.set('enc_order', core.order_to_str(self.enc_order))
        for k, v in self.extra_cfg.items():
            st.set('extra_' + k, v)
        st.push_hist('search', o.search)
        if self.replace_mode:
            st.push_hist('replace', o.replace)
        st.push_hist('files', o.files)
        st.push_hist('wildcard', o.wildcard)
        st.push_hist('folder', o.folder)
        st.save()

    # ---- show
    def show(self):
        self.build()
        self.setp('search', act=True)
        dlg_proc(self.h, DLG_CTL_FOCUS, name='search')
        dlg_proc(self.h, DLG_SHOW_MODAL)
        dlg_proc(self.h, DLG_FREE)
        return self.result
