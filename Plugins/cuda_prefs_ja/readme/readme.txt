オプションエディタ 日本語版 (cuda_prefs_ja)

CudaText の Options Editor Lite (halfbrained/cuda_prefs) の日本語版です。
コマンド「オプションエディタ 日本語版...」で、user.json のオプションを一覧表示・変更できます。

【日本語化の方法】
- オプションの説明と選択肢のラベルは、このプラグインに同梱の default_ja.json から表示します。
  構造 (入力欄の種類・選択肢の値など) は CudaText 本体の settings_default\default.json から読み込むため、
  本体の default.json は英語のままで動作します (書き換える必要はありません)。
- 章ツリー (Font, UI, Tabs ...) は日本語で表示します。フィルターで使う名前 (@UI/Tabs など) は英語のままです。
- オプション名 (font_name など) は user.json のキーそのものなので、翻訳していません。
- ボタンなどの文字列は data\langpy\ja_JP\LC_MESSAGES\cuda_prefs_ja.mo、
  なければ cuda_prefs.mo から読み込みます。

【メニュー名】
- install.inf のタイトルとコマンド名は英語 (Options Editor Jp / Options Editor Jp...) です。
  日本語表示は data\langmenu\cuda_prefs_ja\ja_JP.ini の [menu] で行います:
    Options Editor Jp=オプションエディタ 日本語版
    Options Editor Jp...=*オプションエディタ 日本語版...

【フォント】
- ダイアログの文字は Yu Gothic UI で表示します (インストールされている場合のみ)。
- 変更するには settings\cuda_prefs_ja.json を作成します。
    {"font_name": "Yu Gothic UI", "font_size": 11}
  font_name を "" にすると、フォントを指定しません。font_size が 0 のときは大きさを変えません (既定は 11)。

【元のプラグインとの違い】
- default.json の説明文を翻訳しても開けなくなりません (表示用の文字列だけを差し替えるため)。
- 開けなくなる原因だった KeyError を防ぐ修正を含みます。

元のプラグイン: Andrey Kvichansky (kvichans) / halfbrained (https://github.com/halfbrained/cuda_prefs)
日本語版: coolvitto
License: MIT

--------------------------------
作者: coolvitto
元の作者: Andrey Kvichansky (kvichans) / halfbrained
バージョン: 1.0
作成日時: 2026-11-03 16:21
URL: https://coolvitto.hateblo.jp
