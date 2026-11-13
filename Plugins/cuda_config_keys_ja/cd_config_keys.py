""" Plugin for CudaText editor
Authors:
    Andrey Kvichansky (kvichans on github) / coolvitto (日本語化)
Version:
    '2.1.13 2026-11-13'
"""
#! /usr/bin/env python3

import os, json, re, collections, itertools
from    fnmatch         import fnmatch
import  cudatext            as app
import  cudatext_cmd        as cmds
from    cudatext        import ed
import  cudax_lib           as apx
from    .cd_plug_lib    import *
from    .cd_keys_report import *
from    .cd_keys_ja import translate_command_name
from    .cd_keys_kind import KINDS, kind_of      # 日本語版: 種類での絞り込み

pass;                           LOG     = (-9== 9)  # Do or dont logging.
pass;                           from pprint import pformat
pass;                           pf=lambda d:pformat(d,width=150)

# I18N
_       = get_translation(__file__)

c9, c10, c13    = chr(9), chr(10), chr(13) 
GAP     = 5

sndt        = None
try:    # Is plugin cuda_snip2call acitive?
    from cuda_snip2call import SnipData
    sndt    = SnipData()
except ImportError as ex:
    pass;
    pass

VERSION     = re.split('Version:', __doc__)[1].split("'")[1]
VERSION_V,  \
VERSION_D   = VERSION.split(' ')

# ---------------------------------------------------------------- 日本語版: ホットキー文字列の扱い
def hk_tokens(chord):
    """ 'Ctrl+Shift+A' -> {'CTRL','SHIFT','A'} (順序に依存しない比較用) """
    chord   = (chord or '').strip()
    if not chord:           return frozenset()
    if chord=='+':          return frozenset(['+'])
    if chord.endswith('++'):head, key = chord[:-2], '+'
    else:                   head, _s, key = chord.rpartition('+')
    toks    = [t for t in head.split('+') if t] + [key]
    return frozenset(t.upper() for t in toks)

def hk_chords(keys):
    """ 'Ctrl+K * Ctrl+C' (連続ホットキー) -> ['Ctrl+K', 'Ctrl+C'] """
    return [c.strip() for c in (keys or '').split(' * ') if c.strip()]

MOD_VKS     = {16, 17, 18, 91, 92, 160, 161, 162, 163, 164, 165}      # Shift/Ctrl/Alt/Win のみのキー
VK_NAMES    = {8:'BkSp', 9:'Tab', 13:'Enter', 19:'Pause', 27:'Esc', 32:'Space'
              ,33:'PgUp', 34:'PgDown', 35:'End', 36:'Home', 37:'Left', 38:'Up', 39:'Right', 40:'Down'
              ,45:'Ins', 46:'Del'
              ,106:'Num*', 107:'Num+', 109:'Num-', 110:'Num.', 111:'Num/'
              ,186:';', 187:'=', 188:',', 189:'-', 190:'.', 191:'/', 192:'`'
              ,219:'[', 220:'\\', 221:']', 222:"'"}
def vk_name(vk):
    """ 仮想キーコード -> CudaText のキー名 (対応できないキーは None) """
    if 65<=vk<=90 or 48<=vk<=57:    return chr(vk)
    if 112<=vk<=135:                return 'F'+str(vk-111)
    if 96<=vk<=105:                 return 'Num'+str(vk-96)
    return VK_NAMES.get(vk)


class CommandResizable:
    def dlg_config_keys_resizable(self):
# if app.app_api_version()<'1.0.136':     # dlg_hotkey, PROC_GET_HOTKEY, PROC_SET_HOTKEY
        if app.app_api_version()<'1.0.212':     # depr PROC_GET_COMMAND, PROC_GET_COMMAND_PLUGIN
            return app.msg_status(_('Need update CudaText'))
        CfgKeysDlg().show()

def collect_keys():
    keys_json   = os.path.join(app.app_path(app.APP_DIR_SETTINGS), 'keys.json')
    keys        = apx._json_loads(open(keys_json).read()) if os.path.isfile(keys_json) else {}

    cmdinfos    = []
    pass;
# if True: # app.app_api_version()>='1.0.212':
    lcmds       = app.app_proc(app.PROC_GET_COMMANDS, '')
    cmdinfos    = [('Plugins'
                   ,cmd['name']
                   ,cmd['key1']
                   ,cmd['key2']
                   ,f('{},{},{}', cmd['p_module'], cmd['p_method'], cmd['p_method_params']).rstrip(',')
                   )
                        if cmd['type']=='plugin' else 
                   ('Commands'
                   ,cmd['name']
                   ,cmd['key1']
                   ,cmd['key2']
                   ,cmd['cmd']
                   )
                        for cmd in lcmds
                        if cmd['type'] in ('plugin', 'cmd')
# if cmd['type']!='lexer'
                ]
    return cmdinfos

class CfgKeysDlg():
    @staticmethod
    def prep_keys_info():
        cmdCNKKIs   = collect_keys()
        pass;
        pass;
        pass;                  # return
        nkki_l      =  [(nm,k1,k2,id)   for (ch,nm,k1,k2,id) in cmdCNKKIs]
        id2nkks     =  {id:[nm,k1,k2]   for (ch,nm,k1,k2,id) in cmdCNKKIs}
        ks2id       =  {k1:id           for (ch,nm,k1,k2,id) in cmdCNKKIs}
        ks2id.update(  {k2:id           for (ch,nm,k1,k2,id) in cmdCNKKIs})
        return nkki_l, id2nkks, ks2id

    COL_WS      = [310, 160, 160, 135]
    COL_WS      = [COL_WS[0]+COL_WS[3]]+COL_WS[1:3]+[0] if not sndt else COL_WS
    LST_W, LST_H= sum(COL_WS)+20, 200-5
    DLG_W, DLG_H= 5+LST_W+5, 5+LST_H+105+5+3+17     # 日本語版: 右側のボタン列をなくし、2行目に移動
    lfk1        = 5+COL_WS[0]+5
    lfk2        = 5+COL_WS[0]+COL_WS[1]+5
    lfsn        = 5+COL_WS[0]+COL_WS[1]+COL_WS[2]+5
    lrpt        = DLG_W-5-100
    KIND_ITEMS  = [''] + [_(k) for k in KINDS]     # 日本語版: 先頭の空欄 = 絞り込みなし (表示は翻訳、判定は英語の名前)
    BT_W        = 98
    LIST_T      = 5+64
    ccnd_h      = _('Suitable command names will contain all specified words.'
                    '\nTips:'
                  '\n · Use "_" for word boundary.'
                  '\n   "_up" selects "upper" but not "group".')
    kcnd_h      = _('Suitable command hotkeys will contain all specified words.'
                  '\nTips:'
                  '\n · Use "_" for key-name boundary.'
                  '\n   "_f" selects "F1" and "Ctrl+F" but not "Left".')
    scnd_h      = _('Suitable command snips will match specified string.'
                  '\nUsage:'
                  '\n · Type "/" and snip string and push Tab-key.'
                  '\nTips:'
                  '\n · Use ? for any character and * for any fragment.')
    keyp_h      = _('In the hotkey field, press keys to search for the commands which use them.'
                  '\n · Backspace/Delete: clear the field'
                  '\n · Tab/Enter/Esc (alone): normal operation')
    kind_h      = _('Filter commands by kind (commands of plugins are "Plugin commands").')
    mods_h      = _('Show only commands whose hotkeys include all checked modifier keys.')
    dbl_h       = _('Double-click a row to open the hotkey dialog.'
                  '\n(In the column Hotkey-2: for Hotkey-2, otherwise: for Hotkey-1. An existing hotkey is replaced.)'
                  '\nTo make a series hotkey, use the buttons "Set/Add" below.')
    reset_h     = _('Reset all filters and the sorting to the initial state.')
    addk_h      = _('Set hotkey for command (if no one).'
                  '\nExtend to series hotkeys (if command already has hotkeys).')
    hrpt_h      = _('Shows HTML page with report of all hotkeys in editor.'
                  '\nThe report is usefull to analyze hotkeys in a whole.')
    trpt_h      = _('Show compact report of hotkeys in new tab.'
                  '\nThe report is usefull to find free hotkeys.')
    cpnm_h      = _('Copy command name to clipboard')
    open_h      = _('Open source of plugin code')
    sort_h      = _('Sort data by click on table header' # or by hotkeys Alt+1, Alt+2, Alt+3'
                  '\n3-stage loop of sorting:'
                  '\n · in alphabetical order,'
                  '\n · in reverse alphabetical order,'
                  '\n · in natural order (as at start)'
                    )
    reND    = re.compile(r'\W')

    def __init__(self):
        m,M         = self,self.__class__

        m.sort      = ('', True)
        m.cmd_id    = ''
        m.ccnd      = ''
        pass;                  # m.ccnd      = 'space'
        m.kcnd      = ''
        m.scnd      = ''
        m.orcn      = False
        m.orsn      = False
        m.kind      = 0         # 日本語版: 種類 (0: 絞り込みなし)
        m.msft      = False     # 日本語版: Shift/Ctrl/Alt を含むホットキー
        m.mctl      = False
        m.malt      = False
        m.kchord    = ''        # 日本語版: キー入力された検索文字列 (これと同じ内容の間は「キー入力」として検索)
        m.fid       = 'ccnd'

        m.nkki_l,   \
        m.id2nkks,  \
        m.ks2id     = M.prep_keys_info()
        pass;
    
    def show(self):
        m,M         = self,self.__class__
        m.ag    = DlgAgent(
            form =dict(cap     = f(_('Configure Hotkeys ({})'), VERSION_V)
                      ,resize  = True                              # !!
                      ,border  = app.DBORDER_SIZE                   # Resizable window frame
                      ,w       = M.DLG_W,   w_min   = M.DLG_W
                      ,h       = M.DLG_H,   h_min   = M.DLG_H
                      ,on_key_down = m.on_key_down                  # 日本語版: ホットキー欄でキー入力
                      )
        ,   ctrls=self.get_cnts()
        ,   vals =self.get_vals()
        ,   fid  =m.fid
                            ,   options = {
                               # 'gen_repro_to_file':'repro_dlg_cfg_keys.py',
                                }
        )
        try:    # 日本語版: 一覧のダブルクリックで設定ダイアログを開く
            app.dlg_proc(m.ag.id_dlg, app.DLG_CTL_PROP_SET, name='lwks', prop={'on_click_dbl': m.do_dbl})
        except Exception as ex:
            log('Fail to set on_click_dbl: {}', ex)
        m.ag.show()
    
    def get_cnts(self, what=''):
        m,M         = self,self.__class__
        open_src    = apx.get_opt('config_keys_with_open', False)
        sndt_b      = bool(sndt)
        def is_cond4snps(cond, sns_l):
            if not cond:    return  True
            if not sns_l:   return  False
            return any(map(lambda sn:fnmatch(sn, cond), sns_l))
        def test_cond(cnd_s, text, text2='', what='cmds'):
            if not cnd_s:       return True
            if not text+text2:  return False
            text    = text + ' ' + text2
            text    = text.upper()
            if '_' in cnd_s:
                text    = '·' + M.reND.sub('·', text)    + '·'
                cnd_s   = ' ' + cnd_s + ' '
                cnd_s   = cnd_s.replace(' _', ' ·').replace('_ ', '· ')
            pass;
            return all(map(lambda c:c in text, cnd_s.split()))
        def bmix(val1, bor12, val2, bor23, val3):
            val12   = val1  or val2     if bor12 else        val1  and val2
            return    val12 or val3     if bor23 else        val12 and val3
# def bmix(bor12, bor23, val1, val2, val3):
# return    val12 or val3     if bor23 else        val12 and val3

        ccnd_u  = m.ccnd.upper()
        kcnd_u  = m.kcnd.upper()
        pass;
        nkkis_l = [    (nm, k1, k2, id, sndt.get_snips(id) if sndt else [])
                   for (nm, k1, k2, id)   in m.nkki_l]
        pass;
        fl_NKKISs=[    (nm, k1, k2, id, sns)
                   for (nm, k1, k2, id, sns)   in nkkis_l
                   if  bmix( (not ccnd_u or test_cond(ccnd_u, nm) or test_cond(ccnd_u, translate_command_name(nm)))
                                ,m.orcn and (ccnd_u and kcnd_u)
                            ,(not kcnd_u or (m.kchord_match(k1, k2)  if m.kcnd==m.kchord else  test_cond(kcnd_u, k1, k2, 'keys')))
                                ,m.orsn and (m.scnd)
                            ,(not m.scnd or not sndt   or is_cond4snps(m.scnd, sns)) 
                            )
                  ]
# if  bmix(m.orcn, m.orsn
        # 日本語版: 種類と修飾キーでさらに絞り込み (AND)
        kind_nm = KINDS[m.kind-1] if 0<m.kind<=len(KINDS) else ''
        mods_rq = {t for t,on in (('SHIFT',m.msft), ('CTRL',m.mctl), ('ALT',m.malt)) if on}
        if kind_nm:
            fl_NKKISs   = [x for x in fl_NKKISs if ('Plugin commands' if isinstance(x[3], str) else kind_of(x[0]))==kind_nm]
        if mods_rq:
            fl_NKKISs   = [x for x in fl_NKKISs if any(mods_rq<=hk_tokens(c) for c in hk_chords(x[1])+hk_chords(x[2]))]
        sort_n  = apx.icase(m.sort[0]=='nm',0, m.sort[0]=='k1',1, m.sort[0]=='k2',2, m.sort[0]=='sn',4, 0)   # index in item of fl_NKKISs
        sort_c  = '' if not m.sort[0] else ' ▲' if m.sort[1] else ' ▼'
        if m.sort[0]: 
            fl_NKKISs   = sorted(fl_NKKISs, key=lambda mkkis:('_' if not mkkis[sort_n] and not m.sort[1] else mkkis[sort_n]), reverse=m.sort[1])
        stat_c  = f(' ({}/{})',len(fl_NKKISs), len(nkkis_l))                                + (sort_c if m.sort[0]=='nm' else '')
        stat_k1 = f(' ({}/{})',sum(1 if k1  else 0 for (nm, k1, k2, id, sns) in fl_NKKISs)  
                              ,sum(1 if k1  else 0 for (nm, k1, k2, id, sns) in nkkis_l))   + (sort_c if m.sort[0]=='k1' else '')
        stat_k2 = f(' ({}/{})',sum(1 if k2  else 0 for (nm, k1, k2, id, sns) in fl_NKKISs)
                              ,sum(1 if k2  else 0 for (nm, k1, k2, id, sns) in nkkis_l))   + (sort_c if m.sort[0]=='k2' else '')
        stat_s  = f(' ({}/{})',sum(1 if sns else 0 for (nm, k1, k2, id, sns) in fl_NKKISs)
                              ,sum(1 if sns else 0 for (nm, k1, k2, id, sns) in nkkis_l))   + (sort_c if m.sort[0]=='sn' else '')
        m.fl_Is = [id         for (nm, k1, k2, id, sn) in fl_NKKISs ]   # !!
        itms    = (list(zip([_('Command')+stat_c, _('Hotkey-1')+stat_k1, _('Hotkey-2')+stat_k2, _('Snips')+stat_s], map(str, M.COL_WS)))
                  ,         [ (translate_command_name(nm), k1, k2, ', '.join(sns)) 
                                for  (nm, k1, k2, id, sns) in fl_NKKISs ]
                  )
        if what=='lwks':
            return [('lwks',dict(items=itms))]

        cnts    =[
  ('fltr',dict(tp='bt'  ,t=5+32         ,l=M.DLG_W-5-4*M.BT_W-3*8,w=M.BT_W,cap=_('&Filter')  ,ex0='1'   ,a='LR'         ,call=m.do_fltr )) # &f  default
 ,('drop',dict(tp='bt'  ,t=5+32         ,l=M.DLG_W-5-3*M.BT_W-2*8,w=M.BT_W,cap=_('&All')                    ,a='LR'         ,call=m.do_fltr )) # &a
 ,('rset',dict(tp='bt'  ,t=5+32         ,l=M.DLG_W-5-2*M.BT_W-1*8,w=M.BT_W,cap=_('Reset')  ,hint=M.reset_h ,a='LR'         ,call=m.do_fltr ))
 ,('help',dict(tp='bt'  ,t=5+32         ,l=M.DLG_W-5-1*M.BT_W    ,w=M.BT_W,cap=_('Hel&p')                    ,a='LR'         ,call=m.do_shlp )) # &p
 ,('orcn',dict(tp='ch'  ,t=5+3          ,l=380      ,w=66   ,cap=_('&OR')                                           ,call=m.do_fltr )) # &o
 ,('orsn',dict(tp='ch'  ,t=5+3          ,l=M.lfsn-60,w=40   ,cap=_('O&R')                               ,vis=sndt_b ,call=m.do_fltr )) # &r
 ,('ccn_',dict(tp='lb'  ,t=5+4          ,l=10       ,w=104  ,cap=_('In &Command:')      ,hint=M.ccnd_h                              )) # &c
 ,('ccnd',dict(tp='ed'  ,t=5            ,l=116      ,w=190                                                                          ))
 ,('kcn_',dict(tp='lb'  ,t=5+4          ,l=450      ,w=102  ,cap=_('In &Hotkeys:')      ,hint=M.kcnd_h+'\n\n'+M.keyp_h               )) # &h
 ,('kcnd',dict(tp='ed'  ,t=5            ,l=556      ,w=100  ,hint=M.keyp_h                                                          ))
 ,('kmsg',dict(tp='lb'  ,t=5+4          ,l=662      ,w=128  ,cap=_('(* Press a key)')                                       ))
                                                                                                                            
 ,('scn_',dict(tp='lb'  ,t=5+4          ,l=M.lfsn   ,w=50   ,cap=_('In &Snip(s):')        ,hint=M.scnd_h  ,vis=sndt_b                 )) # &s
 ,('shlp',dict(tp='bt'  ,t=5+4          ,l=M.lfsn+80,w=20   ,cap=_('&?')                                ,vis=sndt_b ,call=m.do_shlp )) # &?
 ,('scnd',dict(tp='ed'  ,t=5            ,l=M.lfsn   ,w=100                                              ,vis=sndt_b                 ))
                                                                                                                                    
 ,('knd_',dict(tp='lb'  ,t=5+32+4       ,l=5+5      ,w=45   ,cap=_('Kind:')            ,hint=M.kind_h                              ))
 ,('kind',dict(tp='cbr' ,t=5+32         ,l=5+55     ,w=140  ,items=M.KIND_ITEMS         ,hint=M.kind_h                  ,call=m.do_fltr ))
 ,('msft',dict(tp='ch'  ,t=5+32+3       ,l=5+205    ,w=55   ,cap=_('Shift')               ,hint=M.mods_h                  ,call=m.do_fltr ))
 ,('mctl',dict(tp='ch'  ,t=5+32+3       ,l=5+265    ,w=50   ,cap=_('Ctrl')                ,hint=M.mods_h                  ,call=m.do_fltr ))
 ,('malt',dict(tp='ch'  ,t=5+32+3       ,l=5+320    ,w=45   ,cap=_('Alt')                 ,hint=M.mods_h                  ,call=m.do_fltr ))
                                                                                                                                    
 ,('lwks',dict(tp='lvw' ,t=M.LIST_T     ,l=5        ,w=M.LST_W,h=M.LST_H    ,items=itms ,ex0='1'        ,a='lRtB'   ,hint=M.dbl_h                
                                                                ,on_click_header=lambda idd, idc, data:m.wn_sort(data)              )) # grid
                                                                                                                                    
 ,('cpnm',dict(tp='bt'  ,t=M.DLG_H-60   ,l=5+5      ,w=110  ,cap=_('Copy &name')        ,hint=M.cpnm_h  ,a='TB'     ,call=m.do_code )) # &n
 ,('open',dict(tp='bt'  ,t=M.DLG_H-30   ,l=5+5      ,w=110  ,cap=_('Open code &#')      ,hint=M.open_h  ,a='TB'     ,call=m.do_code )) # &#
 ,('hrpt',dict(tp='bt'  ,t=M.DLG_H-60   ,l=130      ,w=150  ,cap=_('Report to HT&ML')   ,hint=M.hrpt_h  ,a='TB'     ,call=m.do_rprt )) # &m
 ,('trpt',dict(tp='bt'  ,t=M.DLG_H-30   ,l=130      ,w=150  ,cap=_('Report to new &Tab'),hint=M.trpt_h  ,a='TB'     ,call=m.do_rprt )) # &t
 ,('add1',dict(tp='bt'  ,t=M.DLG_H-60   ,l=M.lfk1   ,w=150  ,cap=_('Set/Add Hotkey-&1') ,hint=M.addk_h  ,a='TB'     ,call=m.do_work )) # &1
 ,('del1',dict(tp='bt'  ,t=M.DLG_H-30   ,l=M.lfk1   ,w=150  ,cap=_('Remove Hotkey-1 &!')                ,a='TB'     ,call=m.do_work )) # &!
 ,('add2',dict(tp='bt'  ,t=M.DLG_H-60   ,l=M.lfk2   ,w=150  ,cap=_('Set/Add Hotkey-&2') ,hint=M.addk_h  ,a='TB'     ,call=m.do_work )) # &2
 ,('del2',dict(tp='bt'  ,t=M.DLG_H-30   ,l=M.lfk2   ,w=150  ,cap=_('Remove Hotkey-2 &@')                ,a='TB'     ,call=m.do_work )) # &@
 ,('asnp',dict(tp='bt'  ,t=M.DLG_H-60   ,l=M.lfsn   ,w=150  ,cap=_('Set/A&dd Snip')     ,vis=sndt_b     ,a='TB'     ,call=m.do_work )) # &d
 ,('rsnp',dict(tp='bt'  ,t=M.DLG_H-30   ,l=M.lfsn   ,w=150  ,cap=_('R&emove Snip(s)')   ,vis=sndt_b     ,a='TB'     ,call=m.do_work )) # &e
                ]
        return cnts
    
    def get_vals(self, what=''):
        m,M         = self,self.__class__
        lwks_n  = -1                                 \
                    if 0==len(m.fl_Is)          else \
                   0                                 \
                    if m.cmd_id not in m.fl_Is  else \
                   m.fl_Is.index(m.cmd_id)
        if what=='lwks':
            return      dict(lwks=lwks_n)
        
        vals    =       dict(ccnd=m.ccnd
                            ,kcnd=m.kcnd
                            ,orcn=m.orcn
                            ,kind=m.kind
                            ,msft=m.msft
                            ,mctl=m.mctl
                            ,malt=m.malt
                            ,lwks=lwks_n)
        if sndt:
            vals.update(dict(scnd=m.scnd
                            ,orsn=m.orsn
            ))
        return vals
    
    def do_rprt(self, aid, ag, data=''):
        m,M         = self,self.__class__
        if False:pass
        elif aid=='trpt':
            # Compact report to tab
            app.file_open('')
            ed.set_text_all(get_str_report())

        elif aid=='hrpt':
            # Full report to HTML
            htm_file = os.path.join(tempfile.gettempdir(), '{}_keymapping.html'.format(app_name))
            do_report(htm_file)
            webbrowser.open_new_tab('file://'+htm_file)
            app.msg_status(_('Opened browser with file ')+htm_file)
        return []
    
    def do_shlp(self, aid, ag, data=''):
        m,M         = self,self.__class__
        DW, DH      = 500-2*GAP, 500-2*GAP
        dlg_wrapper(_('Help for "Config Hotkeys"'), 500, 500,
             [dict(cid='htxt',tp='me'    ,t=GAP  ,h=DH-28,l=GAP          ,w=DW   ,ex0='1', ex1='0', ex2='1'  ) # ro,mono,border
             ,dict(cid='-'   ,tp='bt'    ,t=GAP+DH-23    ,l=GAP+DW-80    ,w=80   ,cap=_('&Close'))
             ], dict(htxt=
                     f(_('• In Command.\n{}'
                       '\n\n• In Hotkeys.\n{}'
                       '{}'
                       '\n\n• Set/Add.\n{}'
                       '\n\n• HTML-report.\n{}'
                       '\n\n• Tab-report.\n{}'
                       '\n\n• Sorting.\n{}'),
                       M.ccnd_h, M.kcnd_h,
                       f(_('\n\n• In Snip.\n{}'), M.scnd_h) if sndt else '',
                       M.addk_h, M.hrpt_h, M.trpt_h, M.sort_h)
                     + f(_('\n\n• Kind and modifier keys.\n{}\n{}'
                           '\n\n• Hotkey field.\n{}'
                           '\n\n• Double-click.\n{}'
                           '\n\n• Reset.\n{}'),
                         M.kind_h, M.mods_h, M.keyp_h, M.dbl_h, M.reset_h)       # 日本語版で追加した機能
                    ), focus_cid='htxt')
        return []
    
    def do_code(self, aid, ag, data=''):
        m,M         = self,self.__class__
        
        lwks_n  = ag.cval('lwks')
        if lwks_n==-1:                      return [] # continue#while
        m.cmd_id  = m.fl_Is[lwks_n]
        pass;
        pass;
        if False:pass
        elif aid=='cpnm':
            cmd_nkk = m.id2nkks[m.cmd_id]
            app.app_proc(app.PROC_SET_CLIP, cmd_nkk[0])
        
        elif aid=='open':
            pass;               LOG and log('m.cmd_id={}',(m.cmd_id))
            if type(m.cmd_id)!=str:         return [] # continue#while
            plug_mdl,   \
            plug_mth    = m.cmd_id.split(',')[0:2]
            plug_mth    = 'def '+ plug_mth + '(self):'
            plug_dir    = app.app_path(app.APP_DIR_PY)+os.sep+plug_mdl
            plug_py     = plug_dir+os.sep+'__init__.py'
            plug_body   = open(plug_py, encoding='UTF-8').read()
            pass;               LOG and log('plug_mdl,plug_mth,plug_dir,plug_py={}',(plug_mdl,plug_mth,plug_dir,plug_py))
            mch         = re.search(r'from\s+\.(\w+)\s+import\s+Command', plug_body)
            if mch:
                plug_py = plug_dir+os.sep+mch.group(1)+'.py'
                pass;           LOG and log('plug_py={}',(plug_py))
                plug_body=open(plug_py, encoding='UTF-8').read()
            if plug_mth not in plug_body:   return [] # continue#while
            # Open
            app.file_open(plug_py)
            # Locate
            user_opt= app.app_proc(app.PROC_GET_FINDER_PROP, '') \
                        if app.app_api_version()>='1.0.248' else \
                      app.app_proc(app.PROC_GET_FIND_OPTIONS, '')   # Deprecated
            ed.cmd(cmds.cmd_FinderAction, chr(1).join([]
                +['findnext']
                +[plug_mth]
                +['']
                +['fa']
            ))
            if app.app_api_version()>='1.0.248':
                app.app_proc(app.PROC_SET_FINDER_PROP, user_opt)
            else:
                app.app_proc(app.PROC_SET_FIND_OPTIONS, user_opt)   # Deprecated
            return None # break#while
        return []
    
    def wn_sort(self, col):
        pass;
        m,M         = self,self.__class__

        col_s       = 'nm' if col==0 else \
                      'k1' if col==1 else \
                      'k2' if col==2 else \
                      'sn'
        srt_s       = m.sort[0]
        m.sort      = (col_s, False)                            \
                        if not srt_s                      else  \
                      (col_s, False)                            \
                        if srt_s!=col_s                   else  \
                      (srt_s, True)                             \
                        if srt_s==col_s and not m.sort[1] else  \
                      ('', True)
        pass;
        lwks_n      = m.ag.cval('lwks')
        pass;
        m.cmd_id    = '' if lwks_n==-1 else m.fl_Is[lwks_n]
        lwks_its_v  = odict(             self.get_cnts('lwks'))
        lwks_its_v['lwks'].update({'val':self.get_vals('lwks')['lwks']})    if lwks_n>0 else 0  # Save "non-trivial" selection
        m.ag.update(
                    ctrls=lwks_its_v
                )
        return []
    
    def do_sort(self, aid, ag, data=''):
        return self.wn_sort(int(aid[3]))    # srtN
    
    def _sync_state(self, ag, with_kcnd=True):
        """ 日本語版: 画面の入力内容を状態変数に取り込む """
        m,M         = self,self.__class__
        m.ccnd  = ag.cval('ccnd').strip()
        if with_kcnd:
            m.kcnd  = ag.cval('kcnd').strip()
        m.scnd  = ag.cval('scnd').strip()   if sndt else ''
        m.orcn  = ag.cval('orcn')
        m.orsn  = ag.cval('orsn')           if sndt else False
        m.kind  = ag.cval('kind')
        m.msft  = ag.cval('msft')
        m.mctl  = ag.cval('mctl')
        m.malt  = ag.cval('malt')

    def kchord_match(self, k1, k2):
        """ 日本語版: キー入力された検索 - 押したキーと同じ組み合わせ (順序は問わない) を持つか """
        want    = hk_tokens(self.kcnd)
        return  bool(want) and any(hk_tokens(c)==want for c in hk_chords(k1)+hk_chords(k2))

    def do_fltr(self, aid, ag, data=''):
        m,M         = self,self.__class__

        lwks_n      = ag.cval('lwks')
        m.cmd_id    = '' if lwks_n==-1 else m.fl_Is[lwks_n]
        if False:pass
        elif aid in ('fltr', 'orcn', 'orsn', 'kind', 'msft', 'mctl', 'malt'):
            m._sync_state(ag)
            fid     = 'lwks'    if aid=='fltr' else aid
            return dict(ctrls=self.get_cnts('lwks')
                    ,   vals =self.get_vals('lwks')
                    ,   fid  =fid
                    )
        elif aid in ('drop', 'rset'):
            # すべて: 検索文字列・種類・修飾キーを解除  /  リセット: さらに並べ替えと OR も初期状態へ
            m.ccnd  = ''
            m.kcnd  = ''
            m.kchord= ''
            m.scnd  = ''
            m.kind  = 0
            m.msft  = m.mctl = m.malt = False
            if aid=='rset':
                m.orcn  = m.orsn = False
                m.sort  = ('', True)
            m.cmd_id= ''
            vals    = m.get_vals()
            vals    = {k:v for k,v in vals.items() if k!='orsn' or sndt}
            return dict(ctrls=self.get_cnts('lwks')
                    ,   vals =vals
                    ,   fid  ='ccnd'
                    )
        return dict(ctrls=self.get_cnts('lwks')
                ,   vals =self.get_vals('lwks')
                ,   fid  ='lwks'
                )

    def on_key_down(self, id_dlg, id_ctl=0, data='', info=''):
        """ 日本語版: ホットキー欄にフォーカスがあるとき、押したキーを検索文字列にする
            (返り値 False: キー本来の動作 (文字入力など) をさせない) """
        m,M         = self,self.__class__
        try:
            key     = int(id_ctl)
            state   = str(data or '')
        except (TypeError, ValueError):
            try:
                key     = int(data)
                state   = str(id_ctl or '')
            except (TypeError, ValueError):
                return
        try:
            if m.ag.fattr('focused')!='kcnd':   return          # 他の欄では通常どおり
        except Exception:
            return
        if key in MOD_VKS:                      return          # 修飾キーだけのときは何もしない
        state   = state.lower()
        plain   = not any(c in state for c in 'cam')
        if plain and key in (8, 46):                            # Backspace/Delete: 欄をクリア
            m._key_search('')
            return False
        if plain and key in (9, 13, 27):                        # Tab/Enter/Esc (単独): 通常の操作
            return
        name    = vk_name(key)
        if not name:                            return
        mods    = [n for c,n in (('c','Ctrl'), ('s','Shift'), ('a','Alt'), ('m','Meta')) if c in state]
        m._key_search('+'.join(mods+[name]))
        return False

    def _key_search(self, text):
        m,M         = self,self.__class__
        m._sync_state(m.ag, with_kcnd=False)
        m.kcnd      = text
        m.kchord    = text
        lwks_n      = m.ag.cval('lwks')
        m.cmd_id    = '' if lwks_n==-1 or lwks_n>=len(m.fl_Is) else m.fl_Is[lwks_n]
        vals        = m.get_vals('lwks')
        vals['kcnd']= text
        m.ag._update_on_call(dict(ctrls=m.get_cnts('lwks'), vals=vals))

    def do_dbl(self, id_dlg, id_ctl=0, data='', info=''):
        """ 日本語版: 一覧のダブルクリック -> ホットキーの設定ダイアログ """
        m,M         = self,self.__class__
        try:
            lwks_n  = m.ag.cval('lwks')
            if lwks_n<0 or lwks_n>=len(m.fl_Is):    return
            x, y    = None, None
            if isinstance(data, (tuple, list)) and len(data)>=2:
                x, y    = int(data[0]), int(data[1])
            elif isinstance(data, str) and ',' in data:
                x, y    = (int(float(v)) for v in data.split(',')[:2])
            if y is not None and y<24:              return      # 見出し行のダブルクリックは無視
            aid     = 'set1'
            if x is not None:
                aid     = 'set2' if x>=m._col_edge(1) else 'set1'
            upds    = m.do_work(aid, m.ag)
            if upds:
                m.ag._update_on_call(upds)
        except Exception as ex:
            log('Fail on double click: {}', ex)

    def _col_edge(self, ind):
        """ 一覧の ind 列目の右端の x 座標 (実際の画面上の値)。取得できなければ見積もり """
        m,M         = self,self.__class__
        try:
            pr      = app.dlg_proc(m.ag.id_dlg, app.DLG_CTL_PROP_GET, name='lwks')
            cols    = [c.split('\r') for c in pr['columns'].split('\t')]
            return  sum(int(float(c[1])) for c in cols[:ind+1])
        except Exception:
            pass
        pr          = app.dlg_proc(m.ag.id_dlg, app.DLG_CTL_PROP_GET, name='lwks')
        return      int(pr.get('w', 0) * sum(M.COL_WS[:ind+1]) / max(1, M.LST_W))

    def dlg_keys(self, aid):
        """ 日本語版: ホットキーの設定ダイアログ (現在のキー / 新しいキー / 競合するコマンド)
            キー欄ではキーを押して入力する。空欄の欄は変更なし。 """
        m,M         = self,self.__class__
        cid         = m.cmd_id
        nkk         = m.id2nkks[cid]                        # [name, key1, key2]
        ind         = 2 if aid.endswith('2') else 1
        pre         = ['', '']
        if aid.startswith('add') and nkk[ind]:
            pre[ind-1]  = nkk[ind] + ' * '                  # 連続ホットキーの続きを入力する
        S           = dict(conf=None, ok=False, plan={}, other={})
        INPUTS      = ('nk1', 'nk2', 'ck1', 'ck2')

        def L(t):                       # ラベルの文字列は空にできない (cd_plug_lib の制約)
            return  t if t else ' '
        def clean(t):
            t   = (t or '').strip()
            return  '' if (not t or t.endswith(' *')) else t
        def find_owner(key):
            for oid,(onm,o1,o2) in m.id2nkks.items():
                if oid!=cid and key in (o1,o2):     return oid
            return None
        def show_conflict(ag):
            conf, ctext = None, ''
            for t in (clean(ag.cval('nk1')), clean(ag.cval('nk2'))):
                oid = find_owner(t) if t else None
                if oid is not None:
                    conf, ctext = oid, t
                    break
            S['conf']   = conf
            if conf is None:
                ctrls   = [('cft', dict(cap=' ')), ('cmd2', dict(cap=' ')), ('cc1', dict(cap=' ')), ('cc2', dict(cap=' '))]
                vals    = dict(ck1='', ck2='')
            else:
                onm,o1,o2   = m.id2nkks[conf]
                rest        = [k for k in (o1,o2) if k and k!=ctext]
                ctrls   = [('cft', dict(cap=_('The hotkey is already in use'))), ('cmd2', dict(cap=L(translate_command_name(onm)))), ('cc1', dict(cap=L(o1))), ('cc2', dict(cap=L(o2)))]
                vals    = dict(ck1=(rest+['',''])[0], ck2=(rest+['',''])[1])
            ag._update_on_call(dict(ctrls=ctrls, vals=vals))

        def on_kd(id_dlg, id_ctl=0, data='', info=''):
            try:
                key, state  = int(id_ctl), str(data or '')
            except (TypeError, ValueError):
                try:
                    key, state  = int(data), str(id_ctl or '')
                except (TypeError, ValueError):
                    return
            try:
                foc     = kag.fattr('focused')
            except Exception:
                return
            if foc not in INPUTS or key in MOD_VKS:     return
            state   = state.lower()
            plain   = not any(c in state for c in 'cam')
            if plain and key in (9, 13, 27):            return      # Tab/Enter/Esc (単独) は通常の操作
            if plain and key in (8, 46):                            # Backspace/Delete: 欄をクリア
                text    = ''
            else:
                name    = vk_name(key)
                if not name:                            return
                mods    = [n for c,n in (('c','Ctrl'), ('s','Shift'), ('a','Alt'), ('m','Meta')) if c in state]
                cur     = kag.cval(foc).rstrip()
                if cur.endswith(' *'):          prefix = cur + ' '                  # 連続ホットキーの続き
                elif ' * ' in cur:              prefix = cur.rsplit(' * ', 1)[0] + ' * '
                else:                           prefix = ''
                text    = prefix + '+'.join(mods+[name])
            kag._update_on_call(dict(vals={foc:text}))
            if foc in ('nk1', 'nk2'):
                show_conflict(kag)
            return False

        def do_ok(aid_, ag, data=''):
            cur     = [nkk[1], nkk[2]]
            new     = [clean(ag.cval('nk1')) or cur[0], clean(ag.cval('nk2')) or cur[1]]
            if new[0] and new[0]==new[1]:   new[1] = ''
            if not new[0] and new[1]:       new = [new[1], '']
            plan    = {}
            if new!=cur:                    plan[cid] = new
            if S['conf'] is not None:
                ck  = []
                for k in (clean(ag.cval('ck1')), clean(ag.cval('ck2'))):
                    if k and k not in ck:   ck.append(k)
                plan[S['conf']] = (ck+['',''])[:2]
            other   = {}                    # 計画に無いコマンドから外すキー
            for tid,keys in list(plan.items()):
                for k in keys:
                    if not k:   continue
                    for oid,(onm,o1,o2) in m.id2nkks.items():
                        if oid in plan or k not in (o1,o2):     continue
                        if app.msg_box(f(_('Hotkey "{}" is already assigned '
                                           '\nto command "{}".'
                                           '\n'
                                           '\nDo you want to reassign the hotkey '
                                           '\nto selected command "{}"?')
                                        , k, translate_command_name(onm), translate_command_name(m.id2nkks[tid][0])), app.MB_OKCANCEL)==app.ID_CANCEL:
                            return []       # ダイアログに戻る
                        rem = [x for x in other.get(oid, [o1,o2]) if x and x!=k]
                        other[oid]  = (rem+['',''])[:2]
            S['plan'], S['other'], S['ok'] = plan, other, True
            return None

        cnts    = [
  ('cmdn',dict(tp='lb'  ,t=8        ,l=10 ,w=300 ,cap=translate_command_name(nkk[0])                                       ))
 ,('h1'  ,dict(tp='lb'  ,t=32       ,l=102,w=94  ,cap=_('Key 1')                                   ))
 ,('h2'  ,dict(tp='lb'  ,t=32       ,l=208,w=94  ,cap=_('Key 2')                                   ))
 ,('cur_',dict(tp='lb'  ,t=54       ,l=10 ,w=90  ,cap=_('Current key:')                              ))
 ,('cur1',dict(tp='lb'  ,t=54       ,l=102,w=100 ,cap=L(nkk[1])                                      ))
 ,('cur2',dict(tp='lb'  ,t=54       ,l=208,w=100 ,cap=L(nkk[2])                                      ))
 ,('new_',dict(tp='lb'  ,t=80       ,l=10 ,w=90  ,cap=_('New key:')                              ))
 ,('nk1' ,dict(tp='ed'  ,t=76       ,l=102,w=94                                                      ))
 ,('nk2' ,dict(tp='ed'  ,t=76       ,l=208,w=94                                                      ))
 ,('hnt' ,dict(tp='lb'  ,t=104      ,l=102,w=200 ,cap=_('Press a key...')                   ))
 ,('sep' ,dict(tp='pn'  ,t=128      ,l=10 ,w=292 ,h=1  ,color=0xA0A0A0                              ))
 ,('cft' ,dict(tp='lb'  ,t=136      ,l=10 ,w=292 ,cap=' '                                           ))
 ,('cmd_',dict(tp='lb'  ,t=160      ,l=10 ,w=90  ,cap=_('Command:')                                ))
 ,('cmd2',dict(tp='lb'  ,t=160      ,l=102,w=200 ,cap=' '                                           ))
 ,('cc_' ,dict(tp='lb'  ,t=182      ,l=10 ,w=90  ,cap=_('Current key:')                              ))
 ,('cc1' ,dict(tp='lb'  ,t=182      ,l=102,w=100 ,cap=' '                                           ))
 ,('cc2' ,dict(tp='lb'  ,t=182      ,l=208,w=100 ,cap=' '                                           ))
 ,('ck_' ,dict(tp='lb'  ,t=208      ,l=10 ,w=90  ,cap=_('New key:')                              ))
 ,('ck1' ,dict(tp='ed'  ,t=204      ,l=102,w=94                                                      ))
 ,('ck2' ,dict(tp='ed'  ,t=204      ,l=208,w=94                                                      ))
 ,('hnt2',dict(tp='lb'  ,t=232      ,l=102,w=200 ,cap=_('Press a key...')                   ))
 ,('cncl',dict(tp='bt'  ,t=258      ,l=130,w=84  ,cap=_('Cancel')                    ,call=lambda aid_,ag,data='':None ))
 ,('ok'  ,dict(tp='bt'  ,t=258      ,l=220,w=84  ,cap=_('OK')           ,ex0='1'          ,call=do_ok     ))
        ]
        kag     = DlgAgent(
            form =dict(cap=_('Hotkey'), w=320, h=292, on_key_down=on_kd)
        ,   ctrls=cnts
        ,   vals =dict(nk1=pre[0], nk2=pre[1], ck1='', ck2='')
        ,   fid  ='nk'+str(ind)
        )
        kag.show()
        if not S['ok']:                     return False
        changes = {}
        changes.update(S['other'])
        changes.update(S['plan'])
        for oid,keys in changes.items():
            k1, k2  = keys
            set_ok  = app.app_proc(app.PROC_SET_HOTKEY, f('{}|{}|{}', oid, k1, k2))
            if not set_ok:  log('Fail to use PROC_SET_HOTKEY for cmd "{}"', oid)
        m.nkki_l,   \
        m.id2nkks,  \
        m.ks2id     = M.prep_keys_info()
        return True

    def do_work(self, aid, ag, data=''):
        m,M         = self,self.__class__

        lwks_n      = ag.cval('lwks')
        if lwks_n==-1:                      return [] # continue#while
        m.cmd_id    = m.fl_Is[lwks_n]
        if False:pass
        elif aid in ('del1', 'del2'):
            # Delete the hotkeys
            cmd_nkk = m.id2nkks[m.cmd_id]
            del_i   = 1 if aid=='del1' else 2
            if not cmd_nkk[del_i]:          return [] # continue#while
            cmd_nkk[del_i]  = ''
            if  cmd_nkk[2]:
                cmd_nkk[1]  = cmd_nkk[2]
                cmd_nkk[2]  = ''
            set_ok  = app.app_proc(app.PROC_SET_HOTKEY, f('{}|{}|{}', m.cmd_id, cmd_nkk[1], cmd_nkk[2]))
            if not set_ok:  log('Fail to use PROC_SET_HOTKEY for cmd "{}"', m.cmd_id)
            m.nkki_l,   \
            m.id2nkks,  \
            m.ks2id     = M.prep_keys_info()
        
        elif aid in ('add1', 'add2', 'set1', 'set2'):     # 日本語版: 専用のホットキー設定ダイアログ (set: ダブルクリック)
            m.dlg_keys(aid)
        
        elif aid=='asnp' and sndt:
            cnm     = sndt.get_name(m.cmd_id)
            new_sn  = app.dlg_input(f(_('Add snip for "{}"'), cnm), '') 
            if not new_sn:                  return [] # continue#while
            while not SnipData.is_snip(new_sn):
                app.msg_status(SnipData.msg_correct_snip)
                new_sn  = app.dlg_input(f(_('Snip for "{}"'), cnm), new_sn) 
                if not new_sn:  break
            if not new_sn:                  return [] # continue#while
            pre_cid = sndt.get_cmdid(new_sn)
            if pre_cid:
                pre_cnm = sndt.get_name(pre_cid)
                if app.msg_box(f(_('Snippet "{}" is already assigned'
                                   '\nto command "{}".'
                                   '\n'
                                   '\nDo you want to reassign the snippet'
                                   '\nto command "{}"?')
                                , new_sn, pre_cnm, cnm), app.MB_OKCANCEL)==app.ID_CANCEL: return [] # continue#while
            sndt.set(new_sn, cmd_id)

        elif aid=='rsnp' and sndt: 
            cnm     = sndt.get_name(m.cmd_id)
            snp_l   = sndt.get_snips(m.cmd_id)
            snps    = ', '.join(snp_l)
            if app.msg_box(f(_('Do you want to remove snip(s) '
                               '\n    {}'
                               '\nfor command "{}"?')
                            , snps, cnm), app.MB_OKCANCEL)==app.ID_CANCEL: return [] # continue#while
            for snp in snp_l:
                sndt.free(snp)

        return dict(ctrls=self.get_cnts('lwks')
                ,   vals =self.get_vals('lwks')
                ,   fid  ='lwks'
                )
    

if __name__ == '__main__':
    pass;                       print('OK')

