# 名称:       メニューの編集 (cuda_ctxmenu_editor)
# 作者:       coolvitto
# バージョン: 0.2.0
# 作成日時:   2026-11-04 05:12
# URL:        https://coolvitto.hateblo.jp
# Context Menu Editor for CudaText  (v0.2.0)
# - 既存メニュー(エディタ右クリック/タブ/メインメニュー)に項目を追加、またはサブメニューを追加する
# - 既存項目の非表示・表示名の変更ができる
import os
import re
import json
import copy
import traceback
from cudatext import *
from cudax_lib import get_translation

_ = get_translation(__file__)


def N_(s):
    """翻訳対象の文字列を示すだけのマーカー(実際の翻訳は _() で行う)"""
    return s


MOD = __name__
CFG_NAME = 'cuda_ctxmenu_editor.json'

TARGETS = [
    ('text', N_('Editor context menu')),
    ('tab', N_('Tab context menu')),
    ('top', N_('Main menu (top level)')),
    ('top-file', N_('Main menu > File')),
    ('top-edit', N_('Main menu > Edit')),
    ('top-sel', N_('Main menu > Selection')),
    ('top-sr', N_('Main menu > Search')),
    ('top-view', N_('Main menu > View')),
    ('top-op', N_('Main menu > Options')),
    ('top-help', N_('Main menu > Help')),
]

COND_LABELS = [
    ('always', N_('Always show')),
    ('sel', N_('Show only when text is selected')),
    ('nosel', N_('Show only when nothing is selected')),
]

MODE_LABELS = [
    ('inline', N_('Add to existing menu')),
    ('submenu', N_('Submenu')),
]

CAT_ALL = N_('(All)')
CAT_PLUGIN = N_('Plugins')
CAT_OTHER = N_('Other')

# コマンドの分類。英語のコマンド名の「分類: 名前」の分類部分(コロンが無ければ名前全体)に対し、
# 上から順に、キーワードで照合する。キーワードが空白を含む場合は部分一致、含まない場合は
# 単語の先頭一致。どれにも一致しなければ「その他」になる。
CATEGORY_RULES = [
    (N_('Clipboard'), ['clipboard', 'copy', 'paste', 'cut']),
    (N_('Deletion'), ['delete', 'erase']),
    (N_('Search'), ['find', 'search', 'replace']),
    (N_('Folding'), ['fold']),
    (N_('Selection'), ['select', 'column']),
    (N_('Cursor movement'), ['caret', 'go to', 'goto', 'jump', 'scroll', 'bookmark', 'marker',
                             'bracket', 'navigat', 'move']),
    (N_('File'), ['file', 'save', 'open', 'new', 'reload', 'recent', 'session', 'project',
                  'encoding', 'line end', 'close', 'print']),
    (N_('Window/Tab'), ['group', 'tab', 'window', 'split', 'dialog']),
    (N_('View'), ['view', 'font', 'zoom', 'toggle', 'show', 'sidebar', 'panel', 'tree', 'ui',
                  'status', 'minimap']),
    (N_('Menu/Macro'), ['menu', 'macro']),
    (N_('Settings'), ['option', 'config', 'setting', 'lexer', 'theme', 'hotkey']),
    (N_('Help'), ['help', 'about']),
    (N_('Insert/Edit'), ['edit', 'indent', 'case', 'comment', 'sort', 'undo', 'redo', 'line',
                         'text', 'insert', 'join', 'trim', 'duplicate', 'code', 'word',
                         'unicode']),
]
CATEGORY_ORDER = [c for c, _k in CATEGORY_RULES] + [CAT_OTHER, CAT_PLUGIN]


# --- config ---

def cfg_path():
    return os.path.join(app_path(APP_DIR_SETTINGS), CFG_NAME)


def load_cfg():
    try:
        with open(cfg_path(), 'r', encoding='utf-8') as f:
            d = json.load(f)
        if isinstance(d, dict) and isinstance(d.get('menus'), list):
            if not isinstance(d.get('overrides'), dict):
                d['overrides'] = {}
            return d
    except Exception:
        pass
    return {'menus': [], 'overrides': {}}


def save_cfg(d):
    with open(cfg_path(), 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def new_menu(title):
    return {'title': title, 'target': 'text', 'mode': 'inline', 'cond': 'always', 'items': []}


def clean_text(s):
    return (s or '').replace('\t', ' ').replace('\r', ' ').replace('\n', ' ').strip()


def item_caption(it):
    return clean_text(it.get('caption') or it.get('name') or '')


def strip_prefix(name):
    for sep in (':', '：'):
        if sep in name:
            rest = name.split(sep, 1)[1].strip()
            if rest:
                return rest
    return name


def category_of(name):
    """英語のコマンド名から分類(英語のmsgid)を返す"""
    key = (name.split(':', 1)[0] if ':' in name else name).lower()
    tokens = re.findall(r'[a-z]+', key)
    for cat, kws in CATEGORY_RULES:
        for kw in kws:
            if ' ' in kw:
                if kw in key:
                    return cat
            elif any(t.startswith(kw) for t in tokens):
                return cat
    return CAT_OTHER


# --- command names (英語->日本語) ---

_names = None


def _flatten_names(d):
    if isinstance(d, dict):
        flat = dict((k, v) for k, v in d.items() if isinstance(k, str) and isinstance(v, str))
        if flat and len(flat) * 2 >= len(d):
            return flat
        for v in d.values():
            if isinstance(v, dict):
                r = _flatten_names(v)
                if r:
                    return r
    return {}


def command_names():
    """command_names_ja.json(英語名->日本語名)を読み込む。無ければ空。UIが日本語のときのみ。"""
    global _names
    if _names is not None:
        return _names
    _names = {}
    try:
        lang = app_proc(PROC_GET_LANG, '') or ''
    except Exception:
        lang = ''
    if not lang.startswith('ja'):
        return _names
    cands = [
        os.path.join(os.path.dirname(__file__), 'command_names_ja.json'),
        os.path.join(app_path(APP_DIR_PY), 'cuda_config_keys_ja', 'command_names_ja.json'),
    ]
    for fn in cands:
        if not os.path.isfile(fn):
            continue
        try:
            with open(fn, 'r', encoding='utf-8-sig') as f:
                d = _flatten_names(json.load(f))
        except Exception:
            continue
        if d:
            _names = d
            _names.update(dict((k.lower(), v) for k, v in d.items()))
            break
    return _names


def tr_name(name):
    n = command_names()
    return n.get(name) or n.get(name.lower()) or name


# --- runtime menu ---

_added = []       # 自分が追加した項目のid(文字列)
_groups = []      # (表示条件, [id, ...])
_applied = {}     # 既存項目に加えた変更: id -> {'cap': 元の表示名, 'vis': 元の表示状態}
_run_table = []   # パラメータ付きプラグインコマンドの実行表
_built = False


def _clear():
    for mid, st in list(_applied.items()):
        try:
            menu_proc(mid, MENU_SET_CAPTION, command=st['cap'])
            menu_proc(mid, MENU_SET_VISIBLE, command=bool(st['vis']))
        except Exception:
            pass
    _applied.clear()
    for i in _added:
        try:
            menu_proc(i, MENU_REMOVE)
        except Exception:
            pass
    del _added[:]
    del _groups[:]
    del _run_table[:]


def _add_item(parent, it):
    t = it.get('t')
    if t == 'sep':
        return menu_proc(parent, MENU_ADD, caption='-')
    cap = item_caption(it) or '?'
    if t == 'cmd':
        return menu_proc(parent, MENU_ADD, command=int(it['cmd']), caption=cap)
    if t == 'plugin':
        mod = it.get('module', '')
        meth = it.get('method', '')
        prm = it.get('params', '')
        if prm:
            _run_table.append('%s,%s,%s' % (mod, meth, prm))
            cb = "module=%s;func=run_plugin_item;info=%d;" % (MOD, len(_run_table) - 1)
        else:
            cb = 'module=%s;cmd=%s;' % (mod, meth)
        return menu_proc(parent, MENU_ADD, command=cb, caption=cap)
    return None


def existing_items(target):
    """target メニューにある、自分が追加したもの以外の項目(元の表示名で)を返す"""
    mine = set(_added)
    res = []
    try:
        lst = menu_proc(target, MENU_ENUM) or []
    except Exception:
        lst = []
    for d in lst:
        mid = str(d.get('id'))
        if mid in mine:
            continue
        st = _applied.get(mid)
        cap = st['cap'] if st else d.get('cap', '')
        vis = st['vis'] if st else d.get('vis', True)
        if not cap or not vis:
            continue
        sep = (cap == '-')
        sub = False
        if not sep:
            try:
                sub = bool(menu_proc(d.get('id'), MENU_ENUM))
            except Exception:
                pass
        res.append({'id': mid, 'cap': cap, 'cmd': str(d.get('command', '')), 'sep': sep, 'sub': sub})
    return res


def rebuild():
    global _built
    _clear()
    cfg = load_cfg()

    # 既存項目の変更(非表示・表示名)
    for target, ovs in (cfg.get('overrides') or {}).items():
        if not ovs:
            continue
        try:
            lst = menu_proc(target, MENU_ENUM) or []
        except Exception:
            continue
        for d in lst:
            mid = str(d.get('id'))
            cap = d.get('cap', '')
            for o in ovs:
                if o.get('orig') == cap and o.get('cmd') == str(d.get('command', '')):
                    _applied[mid] = {'cap': cap, 'vis': d.get('vis', True)}
                    if o.get('caption'):
                        menu_proc(mid, MENU_SET_CAPTION, command=o['caption'])
                    if o.get('hide'):
                        menu_proc(mid, MENU_SET_VISIBLE, command=False)
                    break

    # 追加するメニュー
    sep_done = set()
    for m in cfg.get('menus', []):
        items = m.get('items') or []
        if not items:
            continue
        target = m.get('target', 'text')
        cond = m.get('cond', 'always') if target == 'text' else 'always'
        lead = (target not in sep_done and target != 'top' and items[0].get('t') != 'sep')
        sep_done.add(target)
        ids = []
        if m.get('mode', 'inline') == 'submenu':
            if lead:
                ids.append(menu_proc(target, MENU_ADD, caption='-'))
            sid = menu_proc(target, MENU_ADD, caption=clean_text(m.get('title')) or 'Menu')
            ids.append(sid)
            for it in items:
                _add_item(sid, it)
        else:
            if lead:
                ids.append(menu_proc(target, MENU_ADD, caption='-'))
            for it in items:
                ids.append(_add_item(target, it))
        ids = [i for i in ids if i]
        _added.extend(ids)
        _groups.append((cond, ids))
    _built = True


def _has_sel(e):
    try:
        for c in e.get_carets():
            if c[2] >= 0 and c[3] >= 0 and (c[2], c[3]) != (c[0], c[1]):
                return True
    except Exception:
        pass
    return False


def update_visibility(e):
    sel = _has_sel(e)
    for cond, ids in _groups:
        vis = (cond == 'always') or (cond == 'sel' and sel) or (cond == 'nosel' and not sel)
        for i in ids:
            menu_proc(i, MENU_SET_VISIBLE, command=vis)


def run_plugin_item(*args, **kwargs):
    info = kwargs.get('info')
    if info is None and args:
        info = args[-1]
    try:
        app_proc(PROC_EXEC_PLUGIN, _run_table[int(info)])
    except Exception:
        print(traceback.format_exc())


# --- command picker ---

def collect_commands():
    res = []
    for c in app_proc(PROC_GET_COMMANDS, '') or []:
        typ = c.get('type')
        name = clean_text(c.get('name'))
        if not name:
            continue
        ja = clean_text(tr_name(name))
        if typ == 'cmd':
            code = c.get('cmd')
            if not isinstance(code, int) or code <= 0:
                continue
            res.append({
                'cat': category_of(name),
                'label': ja,
                'search': (ja + ' ' + name).lower(),
                'item': {'t': 'cmd', 'cmd': code, 'name': name, 'caption': strip_prefix(ja)},
            })
        elif typ == 'plugin':
            mod = c.get('p_module')
            meth = c.get('p_method')
            if not mod or not meth:
                continue
            res.append({
                'cat': CAT_PLUGIN,
                'label': ja,
                'search': (ja + ' ' + name).lower(),
                'item': {'t': 'plugin', 'module': mod, 'method': meth,
                         'params': str(c.get('p_method_params') or ''),
                         'name': name, 'caption': ja},
            })
    res.sort(key=lambda r: (CATEGORY_ORDER.index(r['cat']), r['label'].lower()))
    return res


_pick = None


def cb_pick(id_dlg, id_ctl, data='', info=''):
    if _pick:
        _pick.dispatch(info)


def _cbp(name):
    return "module=%s;func=cb_pick;info='%s';" % (MOD, name)


class CommandPicker:
    W, H = 560, 440

    def __init__(self):
        self.cmds = collect_commands()
        used = set(c['cat'] for c in self.cmds)
        self.cat_ids = [None] + [c for c in CATEGORY_ORDER if c in used]
        self.view = []
        self.result = None
        self.h = dlg_proc(0, DLG_CREATE)
        self._build()

    def _add(self, typ, name, **props):
        n = dlg_proc(self.h, DLG_CTL_ADD, typ)
        props['name'] = name
        dlg_proc(self.h, DLG_CTL_PROP_SET, index=n, prop=props)

    def _set(self, name, **props):
        dlg_proc(self.h, DLG_CTL_PROP_SET, name=name, prop=props)

    def _get(self, name):
        return dlg_proc(self.h, DLG_CTL_PROP_GET, name=name).get('val')

    def _build(self):
        dlg_proc(self.h, DLG_PROP_SET, prop={
            'cap': _('Add command'), 'w': self.W, 'h': self.H, 'border': DBORDER_DIALOG})
        self._add('label', 'lbl_cat', cap=_('Category:'), x=12, y=18, w=60)
        self._add('combo_ro', 'cmb_cat', x=76, y=14, w=190, act=True, on_change=_cbp('cat'))
        self._add('label', 'lbl_flt', cap=_('Filter:'), x=282, y=18, w=64)
        self._add('edit', 'edt_flt', x=350, y=14, w=196, act=True, on_change=_cbp('flt'))
        self._add('listbox', 'lst_cmd', x=12, y=50, w=534, h=330, on_click_dbl=_cbp('add'))
        self._add('button', 'btn_add', cap=_('Add'), x=360, y=396, w=90, h=28,
                  on_change=_cbp('add'))
        self._add('button', 'btn_cancel', cap=_('Cancel'), x=456, y=396, w=90, h=28,
                  on_change=_cbp('cancel'))
        names = [_(CAT_ALL)] + [_(c) for c in self.cat_ids[1:]]
        self._set('cmb_cat', items='\t'.join(names), val=0)
        self.populate()
        dlg_proc(self.h, DLG_SCALE)

    def populate(self):
        try:
            ci = int(self._get('cmb_cat'))
        except Exception:
            ci = 0
        cat = self.cat_ids[ci] if 0 <= ci < len(self.cat_ids) else None
        flt = (self._get('edt_flt') or '').lower().strip()
        self.view = [c for c in self.cmds
                     if (cat is None or c['cat'] == cat)
                     and (not flt or flt in c['search'])]
        self._set('lst_cmd', items='\t'.join(c['label'] for c in self.view),
                  val=0 if self.view else -1)

    def dispatch(self, info):
        try:
            if info in ('cat', 'flt'):
                self.populate()
            elif info == 'add':
                try:
                    i = int(self._get('lst_cmd'))
                except Exception:
                    i = -1
                if 0 <= i < len(self.view):
                    self.result = copy.deepcopy(self.view[i]['item'])
                    dlg_proc(self.h, DLG_HIDE)
            elif info == 'cancel':
                dlg_proc(self.h, DLG_HIDE)
        except Exception:
            print(traceback.format_exc())

    def show(self):
        global _pick
        _pick = self
        try:
            dlg_proc(self.h, DLG_SHOW_MODAL)
        finally:
            _pick = None
            dlg_proc(self.h, DLG_FREE)
        return self.result


# --- main dialog ---

_dlg = None


def cb_main(id_dlg, id_ctl, data='', info=''):
    if _dlg:
        _dlg.dispatch(info)


def _cbm(name):
    return "module=%s;func=cb_main;info='%s';" % (MOD, name)


def _disp(s):
    return clean_text(s).replace('&&', '\x01').replace('&', '').replace('\x01', '&')


class ConfigDialog:
    W, H = 640, 500
    SEP = '----------------'

    def __init__(self):
        self.cfg = load_cfg()
        if not self.cfg['menus']:
            self.cfg['menus'].append(new_menu(_('Menu')))
        self.cur = 0
        self.busy = False
        self.ok = False
        self.rows = []
        self.ex_cache = {}
        self.h = dlg_proc(0, DLG_CREATE)
        self._build()

    # --- helpers ---
    def _add(self, typ, name, **props):
        n = dlg_proc(self.h, DLG_CTL_ADD, typ)
        props['name'] = name
        dlg_proc(self.h, DLG_CTL_PROP_SET, index=n, prop=props)

    def _set(self, name, **props):
        dlg_proc(self.h, DLG_CTL_PROP_SET, name=name, prop=props)

    def _val(self, name):
        try:
            return int(dlg_proc(self.h, DLG_CTL_PROP_GET, name=name).get('val'))
        except Exception:
            return -1

    def menu(self):
        ms = self.cfg['menus']
        return ms[self.cur] if 0 <= self.cur < len(ms) else None

    def existing(self, target):
        if target not in self.ex_cache:
            self.ex_cache[target] = existing_items(target)
        return self.ex_cache[target]

    def overrides(self, target):
        return self.cfg.setdefault('overrides', {}).setdefault(target, [])

    def find_ov(self, target, it):
        for o in self.overrides(target):
            if o.get('orig') == it['cap'] and o.get('cmd') == it['cmd']:
                return o
        return None

    def set_ov(self, target, it, **kw):
        o = self.find_ov(target, it)
        if o is None:
            o = {'cmd': it['cmd'], 'orig': it['cap'], 'caption': '', 'hide': False}
            self.overrides(target).append(o)
        o.update(kw)
        if not o.get('caption') and not o.get('hide'):
            self.overrides(target).remove(o)

    def sel_row(self):
        i = self._val('lst_items')
        return self.rows[i] if 0 <= i < len(self.rows) else None

    # --- UI ---
    def _build(self):
        dlg_proc(self.h, DLG_PROP_SET, prop={
            'cap': _('Edit menus'), 'w': self.W, 'h': self.H, 'border': DBORDER_DIALOG})
        self._add('label', 'lbl_menu', cap=_('Menu:'), x=12, y=18, w=90)
        self._add('combo_ro', 'cmb_menu', x=104, y=14, w=300, act=True, on_change=_cbm('menu'))
        self._add('button', 'btn_mnew', cap=_('New menu...'), x=420, y=12, w=100, h=26,
                  on_change=_cbm('mnew'))
        self._add('button', 'btn_mren', cap=_('Rename...'), x=526, y=12, w=100, h=26,
                  on_change=_cbm('mren'))
        self._add('label', 'lbl_target', cap=_('Target:'), x=12, y=56, w=90)
        self._add('combo_ro', 'cmb_target', x=104, y=52, w=300, act=True, on_change=_cbm('target'))
        self._add('button', 'btn_mdel', cap=_('Delete menu'), x=420, y=50, w=100, h=26,
                  on_change=_cbm('mdel'))
        self._add('label', 'lbl_cond', cap=_('Condition:'), x=12, y=94, w=90)
        self._add('combo_ro', 'cmb_cond', x=104, y=90, w=300, act=True, on_change=_cbm('cond'))
        self._add('label', 'lbl_mode', cap=_('Mode:'), x=12, y=132, w=90)
        self._add('combo_ro', 'cmb_mode', x=104, y=128, w=300, act=True, on_change=_cbm('mode'))
        self._add('label', 'lbl_items', cap=_('Contents:'), x=12, y=166, w=90)
        self._add('listbox', 'lst_items', x=12, y=188, w=400, h=250, act=True,
                  on_change=_cbm('sel'), on_click_dbl=_cbm('ren'))
        bx, bw, bh = 428, 190, 26
        self._add('button', 'btn_add', cap=_('Add command...'), x=bx, y=188, w=bw, h=bh,
                  on_change=_cbm('add'))
        self._add('button', 'btn_sep', cap=_('Add separator'), x=bx, y=222, w=bw, h=bh,
                  on_change=_cbm('sep'))
        self._add('button', 'btn_ren', cap=_('Change display name...'), x=bx, y=256, w=bw, h=bh,
                  on_change=_cbm('ren'))
        self._add('button', 'btn_del', cap=_('Delete'), x=bx, y=290, w=bw, h=bh,
                  on_change=_cbm('del'))
        self._add('button', 'btn_tog', cap=_('Hide existing item'), x=bx, y=324, w=bw, h=bh,
                  on_change=_cbm('tog'))
        self._add('button', 'btn_up', cap=_('Move up'), x=bx, y=372, w=bw, h=bh,
                  on_change=_cbm('up'))
        self._add('button', 'btn_down', cap=_('Move down'), x=bx, y=406, w=bw, h=bh,
                  on_change=_cbm('down'))
        self._add('button', 'btn_ok', cap=_('OK'), x=432, y=456, w=90, h=28, on_change=_cbm('ok'))
        self._add('button', 'btn_cancel', cap=_('Cancel'), x=528, y=456, w=90, h=28,
                  on_change=_cbm('cancel'))
        self._set('cmb_target', items='\t'.join(_(l) for _k, l in TARGETS))
        self._set('cmb_cond', items='\t'.join(_(l) for _k, l in COND_LABELS))
        self._set('cmb_mode', items='\t'.join(_(l) for _k, l in MODE_LABELS))
        self.refresh_all()
        dlg_proc(self.h, DLG_SCALE)

    @staticmethod
    def _index(table, key, default=0):
        keys = [k for k, _l in table]
        return keys.index(key) if key in keys else default

    def refresh_all(self):
        self.busy = True
        try:
            ms = self.cfg['menus']
            if self.cur >= len(ms):
                self.cur = len(ms) - 1
            if self.cur < 0:
                self.cur = 0
            self._set('cmb_menu', items='\t'.join(clean_text(m.get('title')) for m in ms),
                      val=self.cur if ms else -1)
            m = self.menu()
            has = m is not None
            is_text = has and m.get('target', 'text') == 'text'
            self._set('cmb_target', val=self._index(TARGETS, m.get('target', 'text')) if has else -1,
                      en=has)
            self._set('cmb_cond', val=self._index(COND_LABELS, m.get('cond', 'always')) if has else -1,
                      en=bool(is_text))
            self._set('cmb_mode', val=self._index(MODE_LABELS, m.get('mode', 'inline')) if has else -1,
                      en=has)
            self._set('btn_mren', en=has)
            self._set('btn_mdel', en=has)
            self.refresh_items()
        finally:
            self.busy = False

    def refresh_items(self, sel_us=None, sel_idx=None):
        m = self.menu()
        rows, texts = [], []
        if m:
            target = m.get('target', 'text')
            for it in self.existing(target):
                if it['sep']:
                    texts.append(_('[Existing] ') + self.SEP)
                else:
                    o = self.find_ov(target, it)
                    cap = o.get('caption') if (o and o.get('caption')) else it['cap']
                    t = _('[Existing] ') + _disp(cap) + (' >' if it['sub'] else '')
                    if o and o.get('hide'):
                        t += ' ' + _('(hidden)')
                    texts.append(t)
                rows.append(('ex', it))
            for i, it in enumerate(m['items']):
                texts.append(self.SEP if it.get('t') == 'sep' else item_caption(it))
                rows.append(('us', i))
        n_ex = sum(1 for r in rows if r[0] == 'ex')
        if sel_us is not None:
            sel = n_ex + sel_us
        elif sel_idx is not None:
            sel = sel_idx
        else:
            sel = self._val('lst_items')
        if sel >= len(rows):
            sel = len(rows) - 1
        if sel < 0 and rows:
            sel = 0
        self.rows = rows
        prev = self.busy
        self.busy = True
        try:
            self._set('lst_items', items='\t'.join(texts), val=sel if rows else -1)
        finally:
            self.busy = prev
        self.update_buttons()

    def update_buttons(self):
        m = self.menu()
        has = m is not None
        row = self.sel_row()
        kind = row[0] if row else None
        us = (kind == 'us')
        ex = (kind == 'ex' and not row[1]['sep'])
        self._set('btn_add', en=has)
        self._set('btn_sep', en=has)
        self._set('btn_ren', en=us or ex)
        self._set('btn_del', en=us)
        n = len(m['items']) if has else 0
        self._set('btn_up', en=us and row[1] > 0)
        self._set('btn_down', en=us and row[1] < n - 1)
        hidden = False
        if ex:
            o = self.find_ov(m.get('target', 'text'), row[1])
            hidden = bool(o and o.get('hide'))
        self._set('btn_tog', en=ex, cap=_('Show existing item') if hidden else _('Hide existing item'))

    # --- actions ---
    def dispatch(self, info):
        if self.busy:
            return
        try:
            getattr(self, 'do_' + info)()
        except Exception:
            print(traceback.format_exc())

    def do_sel(self):
        self.update_buttons()

    def do_menu(self):
        self.cur = max(self._val('cmb_menu'), 0)
        self.refresh_all()

    def do_target(self):
        m = self.menu()
        i = self._val('cmb_target')
        if m and 0 <= i < len(TARGETS):
            m['target'] = TARGETS[i][0]
            if m['target'] != 'text':
                m['cond'] = 'always'
            self.refresh_all()

    def do_cond(self):
        m = self.menu()
        i = self._val('cmb_cond')
        if m and 0 <= i < len(COND_LABELS):
            m['cond'] = COND_LABELS[i][0]

    def do_mode(self):
        m = self.menu()
        i = self._val('cmb_mode')
        if m and 0 <= i < len(MODE_LABELS):
            m['mode'] = MODE_LABELS[i][0]

    def do_mnew(self):
        name = dlg_input(_('Name of the new menu:'), '')
        name = clean_text(name)
        if not name:
            return
        self.cfg['menus'].append(new_menu(name))
        self.cur = len(self.cfg['menus']) - 1
        self.refresh_all()

    def do_mren(self):
        m = self.menu()
        if not m:
            return
        name = dlg_input(_('Menu name:'), m.get('title', ''))
        name = clean_text(name)
        if name:
            m['title'] = name
            self.refresh_all()

    def do_mdel(self):
        m = self.menu()
        if not m:
            return
        if msg_box(_('Delete menu "%s"?') % m.get('title', ''),
                   MB_YESNO + MB_ICONQUESTION) != ID_YES:
            return
        del self.cfg['menus'][self.cur]
        self.refresh_all()

    def _user_idx(self):
        row = self.sel_row()
        return row[1] if (row and row[0] == 'us') else -1

    def _insert(self, it):
        m = self.menu()
        if not m:
            return
        sel = self._user_idx()
        pos = sel + 1 if sel >= 0 else len(m['items'])
        m['items'].insert(pos, it)
        self.refresh_items(sel_us=pos)

    def do_add(self):
        if not self.menu():
            return
        it = CommandPicker().show()
        if it:
            self._insert(it)

    def do_sep(self):
        self._insert({'t': 'sep'})

    def do_ren(self):
        m = self.menu()
        row = self.sel_row()
        if not m or not row:
            return
        if row[0] == 'us':
            i = row[1]
            it = m['items'][i]
            if it.get('t') == 'sep':
                return
            name = dlg_input(_('Display name:'), item_caption(it))
            if name is None:
                return
            name = clean_text(name)
            if name:
                it['caption'] = name
                self.refresh_items(sel_us=i)
        else:
            it = row[1]
            if it['sep']:
                return
            target = m.get('target', 'text')
            o = self.find_ov(target, it)
            cur = (o.get('caption') if o else '') or it['cap']
            name = dlg_input(_('Display name (empty = restore original):'), cur)
            if name is None:
                return
            name = clean_text(name)
            if name == it['cap']:
                name = ''
            self.set_ov(target, it, caption=name)
            self.refresh_items()

    def do_tog(self):
        m = self.menu()
        row = self.sel_row()
        if not m or not row or row[0] != 'ex' or row[1]['sep']:
            return
        target = m.get('target', 'text')
        o = self.find_ov(target, row[1])
        self.set_ov(target, row[1], hide=not bool(o and o.get('hide')))
        self.refresh_items()

    def do_del(self):
        m = self.menu()
        i = self._user_idx()
        if not m or not (0 <= i < len(m['items'])):
            return
        del m['items'][i]
        n = len(m['items'])
        if n:
            self.refresh_items(sel_us=min(i, n - 1))
        else:
            self.refresh_items()

    def _move(self, d):
        m = self.menu()
        i = self._user_idx()
        j = i + d
        if not m or not (0 <= i < len(m['items'])) or not (0 <= j < len(m['items'])):
            return
        m['items'][i], m['items'][j] = m['items'][j], m['items'][i]
        self.refresh_items(sel_us=j)

    def do_up(self):
        self._move(-1)

    def do_down(self):
        self._move(1)

    def do_ok(self):
        self.ok = True
        dlg_proc(self.h, DLG_HIDE)

    def do_cancel(self):
        dlg_proc(self.h, DLG_HIDE)

    def show(self):
        global _dlg
        _dlg = self
        try:
            dlg_proc(self.h, DLG_SHOW_MODAL)
        finally:
            _dlg = None
            dlg_proc(self.h, DLG_FREE)
        if self.ok:
            save_cfg(self.cfg)
            rebuild()


# --- plugin entry ---

class Command:
    def config(self):
        ConfigDialog().show()

    def on_start(self, ed_self):
        rebuild()

    def on_click_right(self, ed_self, state):
        if not _built:
            rebuild()
        update_visibility(ed_self)
