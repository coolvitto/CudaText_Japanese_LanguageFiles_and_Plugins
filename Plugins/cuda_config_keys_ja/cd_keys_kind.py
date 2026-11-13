# -*- coding: utf-8 -*-
''' ホットキーの設定 (日本語版): コマンドの「種類」判定
    コマンドの英語名 (CudaText 本体が返す名前) から種類を決める。
    種類は絞り込み用の表示だけに使い、コマンドの動作には影響しない。
    種類の名前は英語 (msgid) で持ち、表示するときに翻訳する (langpy の .po / .mo)。
'''
import re

# 表示順。KIND_NONE は「絞り込みなし」(空欄)
KIND_NONE   = ''
KINDS       = ['File commands', 'Cursor movement commands', 'Clipboard commands', 'Delete commands', 'Insert commands',
               'Other editing commands', 'Find commands', 'Window commands', 'Menu/Macro commands', 'Plugin commands', 'Other commands']

_re = lambda p: re.compile(p, re.I)
# (種類, 正規表現) を上から順に判定する。最初に一致したものを採用。
_RULES = [
    ('Plugin commands',       _re(r'^plugins?:')),
    ('Menu/Macro commands',  _re(r'^menu:|macro|main menu')),
    ('Clipboard commands', _re(r'^clipboard:|^paste|^copy|^cut')),
    ('Find commands',          _re(r'^find|^dialog: (find|replace)|^go to last editing')),
    ('File commands',      _re(r'^file:|^change (encoding|line ends)')),
    ('Delete commands',          _re(r'delete|^remove|remove (first|last) caret')),
    ('Insert commands',          _re(r'^insert|insert (line|tab|empty)|^duplicate|^tabulation key|^force final|^paste')),
    ('Cursor movement commands',   _re(r'^caret |^go to|^scroll|^column select|^carets extend|^bookmarks:|^markers:|^brackets:|^code tree:|^url:|^selection: (expand|split|select words|select lines)')),
    ('Window commands',     _re(r'^ui:|^groups:|^split tab:|^dialog:|^toggle (word-wrap|show|line numbers|folding|ruler|mini|micro|window)|^folding:|^repaint|^current document font')),
    ('Other editing commands',       _re(r'^selection:|^toggle|^perform|^redo|^\(without undo\)|^sort|^convert|^trim|^indent|^unindent|^move selected|^repeat|^cancel|^mouse|^keyboard|^tabulation|^convert')),
]


def kind_of(name):
    ''' コマンドの英語名 → 種類 '''
    nm = (name or '').strip()
    for kind, rx in _RULES:
        if rx.search(nm):
            return kind
    return 'Other commands'
