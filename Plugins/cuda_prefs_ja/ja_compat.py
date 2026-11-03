# -*- coding: utf-8 -*-
''' オプションエディタ 日本語版: 日本語化のための補助モジュール
    - 翻訳ファイル (.mo) の読み込み
    - 章 (カテゴリ) ツリーの表示名の日本語化 (内部名は英語のまま)
    - ダイアログのフォント指定
'''
import os
import json
import gettext

import cudatext as app
import cudax_lib as apx

# .mo の検索順: 日本語版専用 → 元のプラグイン (cuda_prefs) の翻訳
MO_DOMAINS = ('cuda_prefs_ja', 'cuda_prefs')


def get_translation(plugin_filename):
    ''' apx.get_translation の代わり。data/langpy/<言語>/LC_MESSAGES/ から
        cuda_prefs_ja.mo と cuda_prefs.mo を順に探して連結する。
        どちらも無ければ apx.get_translation にまかせる。 '''
    try:
        lng = app.app_proc(app.PROC_GET_LANG, '')
        localedir = os.path.join(app.app_path(app.APP_DIR_DATA), 'langpy')
        tr = None
        if lng:
            for dom in MO_DOMAINS:
                try:
                    t = gettext.translation(dom, localedir=localedir, languages=[lng])
                except (OSError, TypeError):
                    continue
                if tr is None:
                    tr = t
                else:
                    tr.add_fallback(t)
        if tr is not None:
            return tr.gettext
    except Exception as ex:
        print('NOTE: cuda_prefs_ja: translation load failed:', ex)
    return apx.get_translation(plugin_filename)


# ---------------------------------------------------------------- 章ツリー
# 表示名のみ。フィルターの "@UI/Tabs" などに使う内部名は英語のまま。
CHP_JA = {
    'Font': 'フォント', 'Renderer': '描画',
    'UI': 'UI', 'Tabs': 'タブ', 'Listbox': 'リストボックス', 'History': '履歴',
    'Tree': 'ツリー', 'Statusbar': 'ステータスバー', 'Sessions': 'セッション', 'Panels': 'パネル',
    'File': 'ファイル', 'Notifications': '通知', 'Detection': '判定', 'Saving': '保存', 'Export': 'エクスポート',
    'Text': 'テキスト', 'Look': '外観', 'Folding': '折りたたみ', 'Commands': 'コマンド',
    'Tabulations': 'タブ文字', 'VerticalLines': '縦線', 'Wrap': '折り返し', 'Undo': '元に戻す',
    'Caret': 'カーソル', 'NewDocument': '新規ドキュメント', 'Indent': 'インデント', 'Completion': '自動補完',
    'Lexers': 'Lexer',
    'View': '表示', 'Gutter': 'ガター', 'LineNumbers': '行番号', 'Scrolling': 'スクロール',
    'Ruler': 'ルーラー', 'Minimap': 'ミニマップ', 'Micromap': 'マイクロマップ',
    'Unprinted': '不可視文字', 'Web': 'Web', 'Brackets': '括弧',
    'Mouse': 'マウス', 'Keys': 'キー',
    'Find': '検索', 'Hotkeys': 'ホットキー',
    'Python': 'Python', 'Viewer': 'ビューアー', 'Log': 'ログ', 'Emmet': 'Emmet',
}
CHP_JA2EN = {}
for _en, _ja in CHP_JA.items():
    CHP_JA2EN.setdefault(_ja, _en)


def chp_label(name):
    ''' 内部名 → 表示名 '''
    return CHP_JA.get(name, name)


def chp_name(text):
    ''' 表示名 → 内部名 (フィルター用のパス作成に使う) '''
    return CHP_JA2EN.get(text, text)


# ---------------------------------------------------------------- フォント
CFG_NAME = 'cuda_prefs_ja.json'      # settings フォルダー (任意)
DEFAULT_FONT_NAME = 'Yu Gothic UI'
DEFAULT_FONT_SIZE = 11               # 0: 変更しない


def _font_cfg():
    name, size = DEFAULT_FONT_NAME, DEFAULT_FONT_SIZE
    fn = os.path.join(app.app_path(app.APP_DIR_SETTINGS), CFG_NAME)
    if os.path.isfile(fn):
        try:
            with open(fn, encoding='utf-8') as f:
                j = json.load(f)
            name = j.get('font_name', name)
            size = int(j.get('font_size', size))
        except Exception as ex:
            print('NOTE: cuda_prefs_ja: bad {}: {}'.format(CFG_NAME, ex))
    return name, size


def apply_font(h):
    ''' ダイアログ h のすべてのコントロールにフォントを設定する。
        指定フォントが未インストールなら何もしない。 '''
    try:
        name, size = _font_cfg()
        if not name:
            return
        installed = {f.lower() for f in app.app_proc(app.PROC_ENUM_FONTS, '')}
        if name.lower() not in installed:
            return
        prop = {'font_name': name}
        if size > 0:
            prop['font_size'] = size
        for n in range(app.dlg_proc(h, app.DLG_CTL_COUNT)):
            app.dlg_proc(h, app.DLG_CTL_PROP_SET, index=n, prop=prop)
    except Exception as ex:
        print('NOTE: cuda_prefs_ja: font setting failed:', ex)
