# -*- coding: utf-8 -*-
from cudatext import *
from . import grep_runner as gr


class Command:
    def run(self):
        from .grep_dialog import GrepDialog
        o = GrepDialog().show()
        if o is None:
            return
        if o.mode == 'replace':
            gr.run_replace(o)
        else:
            gr.run_grep(o)

    # double-click in the Output panel (lazy event: works after the plugin was used)
    def on_output_nav(self, ed_self, output_line, source_tag):
        info = gr.lookup(output_line)
        if info:
            gr.goto(info)
            return False

    # double-click in a result tab
    def on_click_dbl(self, ed_self, state):
        if ed_self is None or ed_self.get_prop(PROP_TAG) != gr.TAG_RESULT:
            return
        carets = ed_self.get_carets()
        if not carets:
            return
        line = ed_self.get_text_line(carets[0][1])
        info = gr.lookup(line)
        if info:
            gr.goto(info)
            return False
