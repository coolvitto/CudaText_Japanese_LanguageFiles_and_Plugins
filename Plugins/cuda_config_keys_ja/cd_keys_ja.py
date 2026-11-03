# Japanese display-name mapping for Configure Hotkeys.
# Original command identifiers and command execution remain unchanged.
import json
import os

with open(os.path.join(os.path.dirname(__file__), 'command_names_ja.json'), encoding='utf-8') as _f:
    _COMMAND_NAMES_JA = json.load(_f)

# Prefix of commands that are not listed in the JSON (e.g. other plugins).
_PLUGIN_PREFIX = 'plugin: '
_PLUGIN_PREFIX_JA = 'プラグイン: '

def translate_command_name(name):
    ja = _COMMAND_NAMES_JA.get(name)
    if ja is not None:
        return ja
    # Fallback: translate only the "plugin: " prefix.
    if name.startswith(_PLUGIN_PREFIX):
        return _PLUGIN_PREFIX_JA + name[len(_PLUGIN_PREFIX):]
    return name
