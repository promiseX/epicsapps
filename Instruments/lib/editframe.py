import sys
import time
import wx
import wx.lib.scrolledpanel as scrolled

import epics
from epics.wx import EpicsFunction

from epics.wx.utils import  (empty_bitmap, add_button, add_menu,
                             Closure, NumericCombo, pack, popup, SimpleText,
                             FileSave, FileOpen, SelectWorkdir)

from utils import GUIColors, HideShow, YesNo, set_font_with_children, get_pvtypes
import instrument

class PVTypeChoice(wx.Choice):
    def __init__(self, parent, choices=None, size=(95, -1), **kws):
        wx.Choice.__init__(self, parent, -1, size=size)
        if choices is None:
            choices = ('',)
        self.SetChoices(choices)
        self.SetSelection(0)

    def SetChoices(self, choices):
        self.Clear()
        self.SetItems(choices)
        self.choices = choices


class pvNameCtrl(wx.TextCtrl):
    def __init__(self, owner, panel,  value='', **kws):
        self.owner = owner
        wx.TextCtrl.__init__(self, panel, wx.ID_ANY, value='', **kws)
        self.Bind(wx.EVT_CHAR, self.onChar)
        self.Bind(wx.EVT_KILL_FOCUS, self.onFocus)

    def onFocus(self, evt=None):
        self.owner.connect_pv(self.Value, wid=self.GetId())
        evt.Skip()

    def onChar(self, event):
        key   = event.GetKeyCode()
        entry = wx.TextCtrl.GetValue(self).strip()
        pos   = wx.TextCtrl.GetSelection(self)
        if (key == wx.WXK_RETURN):
            self.owner.connect_pv(entry, wid=self.GetId())
        event.Skip()

class FocusEventFrame(wx.Window):
    """mixin for Frames that all EVT_KILL_FOCUS/EVT_SET_FOCUS events"""
    def Handle_FocusEvents(self, closeEventHandler=None):
        self._closeHandler = closeEventHandler
        self.Bind(wx.EVT_CLOSE, self.closeFrame)

    def closeFrame(self, event):
        win = wx.Window_FindFocus()
        if win is not None:
            win.Disconnect(-1, -1, wx.wxEVT_KILL_FOCUS)
        if self._closeHandler is not None:
            self._closeHandler(event)
        else:
            event.Skip()

class NewPositionFrame(wx.Frame, FocusEventFrame) :
    """ Edit / Add Instrument"""
    def __init__(self, parent=None, pos=(-1, -1),
                 inst=None, db=None, page=None):

        title = 'New Position'
        if inst is not None:
            title = 'New Position for Instrument  %s ' % inst.name

        style = wx.DEFAULT_FRAME_STYLE|wx.TAB_TRAVERSAL
        wx.Frame.__init__(self, None, -1, title, size=(350, 450), 
                          style=style, pos=pos)
        self.Handle_FocusEvents()

        panel = scrolled.ScrolledPanel(self, size=(400, 500), style=wx.GROW|wx.TAB_TRAVERSAL)
        
        colors = GUIColors()

        font = self.GetFont()
        if parent is not None:
            font = parent.GetFont()

        titlefont  = font
        titlefont.PointSize += 1
        titlefont.SetWeight(wx.BOLD)

        panel.SetBackgroundColour(colors.bg)

        self.parent = parent
        self.page = page
        self.db = db
        self.inst = db.get_instrument(inst)

        STY  = wx.GROW|wx.ALL|wx.ALIGN_CENTER_VERTICAL
        LSTY = wx.ALIGN_LEFT|wx.GROW|wx.ALL|wx.ALIGN_CENTER_VERTICAL
        RSTY = wx.ALIGN_RIGHT|STY
        CSTY = wx.ALIGN_CENTER|STY
        CEN  = wx.ALIGN_CENTER|wx.GROW|wx.ALL
        LEFT = wx.ALIGN_LEFT|wx.GROW|wx.ALL


        self.name =  wx.TextCtrl(panel, value='', size=(200, -1))


        sizer = wx.GridBagSizer(12, 3)

        ir = 0
        sizer.Add(SimpleText(panel, " New Position for '%s'" % self.inst.name,
                             font=titlefont,  colour=colors.title),
                  (ir, 0), (1, 2), LSTY, 2)

        ir += 1        
        sizer.Add(SimpleText(panel, 'Position Name:'),  (ir, 0), (1, 1), LSTY, 2)
        sizer.Add(self.name,                            (ir, 1), (1, 2), LSTY, 2)
        ir += 1
        sizer.Add(SimpleText(panel, 'PV Name:'),        (ir, 0), (1, 1), LSTY, 2)
        sizer.Add(SimpleText(panel, 'Position:'),       (ir, 1), (1, 1), LSTY, 2)

        ir += 1
        sizer.Add(wx.StaticLine(panel, size=(195, -1), style=wx.LI_HORIZONTAL),
                  (ir, 0), (1, 3), CEN, 2)

        self.positions = []
        ir += 1
        for p in self.inst.pvs:
            val =  wx.TextCtrl(panel, value='', size=(150, -1))            
            sizer.Add(SimpleText(panel, p.name), (ir, 0), (1, 1), LSTY, 2)
            sizer.Add(val,                       (ir, 1), (1, 1), LSTY, 2)            
            self.positions.append(val)
            ir += 1
            
        sizer.Add(wx.StaticLine(panel, size=(195, -1), style=wx.LI_HORIZONTAL),
                  (ir, 0), (1, 3), CEN, 2)

        btn_panel = wx.Panel(panel, size=(75, -1))
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_ok     = add_button(btn_panel, 'OK',     size=(70, -1),
                                action=self.onOK)
        btn_cancel = add_button(btn_panel, 'Cancel', size=(70, -1), action=self.onCancel)

        btn_sizer.Add(btn_ok,     0, wx.ALIGN_LEFT,  2)
        btn_sizer.Add(btn_cancel, 0, wx.ALIGN_RIGHT,  2)
        pack(btn_panel, btn_sizer)

        ir += 1
        sizer.Add(btn_panel,  (ir, 0), (1, 3), CEN, 2)
        ir += 1
       
        sizer.Add(wx.StaticLine(panel, size=(195, -1), style=wx.LI_HORIZONTAL),
                  (ir, 0), (1, 3), CEN, 2)

        pack(panel, sizer)
        panel.SetupScrolling()
        self.Layout()
        self.Show()
        self.Raise()

    def onOK(self, evt=None):
        posname = self.name.GetValue()
        values = {}
        valid = len(posname) > 0
        for pv, newval in zip(self.inst.pvs, self.positions):
            val = str(newval.GetValue())
            values[pv.name] = val
            valid = valid and len(val) > 0
        if valid:
            self.db.save_position(posname, self.inst, values)
            if self.page is not None:
                poslist = self.page.pos_list
                if posname not in poslist.GetItems():
                    poslist.Append(posname)
        self.Destroy()
        
    def onCancel(self, evt=None):
        self.Destroy()            

class EditInstrumentFrame(wx.Frame, FocusEventFrame) :
    """ Edit / Add Instrument"""
    def __init__(self, parent=None, pos=(-1, -1),
                 inst=None, db=None, epics_pvs=None):

        self.epics_pvs = epics_pvs
        if self.epics_pvs is None:
            self.epics_pvs = {}

        title = 'Add New Instrument'
        if inst is not None:
            title = 'Edit Instrument  %s ' % inst.name

        style = wx.DEFAULT_FRAME_STYLE|wx.TAB_TRAVERSAL
        wx.Frame.__init__(self, None, -1, title,
                          style=style, pos=pos)
        self.Handle_FocusEvents()

        panel = scrolled.ScrolledPanel(self, size=(500, 650), style=wx.GROW|wx.TAB_TRAVERSAL, name='p1')

        self.colors = GUIColors()

        font = self.GetFont()
        if parent is not None:
            font = parent.GetFont()

        titlefont  = font
        titlefont.PointSize += 1
        titlefont.SetWeight(wx.BOLD)

        panel.SetBackgroundColour(self.colors.bg)

        self.parent = parent
        self.db = db
        self.inst = db.get_instrument(inst)
        self.connecting_pvs = {}

        STY  = wx.GROW|wx.ALL|wx.ALIGN_CENTER_VERTICAL
        LSTY = wx.ALIGN_LEFT|wx.GROW|wx.ALL|wx.ALIGN_CENTER_VERTICAL
        RSTY = wx.ALIGN_RIGHT|STY
        CSTY = wx.ALIGN_CENTER|STY
        CEN  = wx.ALIGN_CENTER|wx.GROW|wx.ALL
        LEFT = wx.ALIGN_LEFT|wx.GROW|wx.ALL

        self.etimer = wx.Timer(self)
        self.etimer_count = 0
        self.Bind(wx.EVT_TIMER, self.onTimer, self.etimer)

        sizer = wx.GridBagSizer(12, 3)

        # Name row
        label  = SimpleText(panel, 'Instrument Name: ',
                            minsize=(150, -1), style=LSTY)
        self.name =  wx.TextCtrl(panel, value='', size=(260, -1))

        sizer.Add(label,      (0, 0), (1, 1), LSTY, 2)
        sizer.Add(self.name,  (0, 1), (1, 2), LSTY, 2)
        sizer.Add(wx.StaticLine(panel, size=(195, -1), style=wx.LI_HORIZONTAL),
                  (1, 0), (1, 3), CEN, 2)

        irow = 2
        self.curpvs, self.newpvs = [], {}
        if inst is not None:
            self.name.SetValue(inst.name)
            sizer.Add(SimpleText(panel, 'Current PVs:', font=titlefont,
                                 colour=self.colors.title, style=LSTY),
                      (2, 0), (1, 1), LSTY, 2)
            sizer.Add(SimpleText(panel, 'Display Type:',
                                 colour=self.colors.title, style=CSTY),
                      (2, 1), (1, 1), LSTY, 2)
            sizer.Add(SimpleText(panel, 'Remove?:',
                                 colour=self.colors.title, style=CSTY),
                      (2, 2), (1, 1), RSTY, 2)

            opvs  = db.get_ordered_instpvs(inst)

            for instpvs in self.db.get_ordered_instpvs(inst):
                pv = instpvs.pv
                irow += 1
                if pv.name in self.epics_pvs:
                    pvchoices = get_pvtypes(self.epics_pvs[pv.name], instrument)
                else:
                    pvchoices = get_pvtypes(pv, instrument)

                label= SimpleText(panel, pv.name,  minsize=(175, -1),
                                  style=LSTY)

                try:
                    itype = pvchoices.index(pv.pvtype.name)
                except ValueError:
                    itype = 0

                pvtype = PVTypeChoice(panel, choices=pvchoices)
                pvtype.SetSelection(itype)
                pvtype.SetStringSelection(pv.pvtype.name)
                del_pv = YesNo(panel, defaultyes=False)
                self.curpvs.append((pv.name, label, pvtype, del_pv))

                sizer.Add(label,     (irow, 0), (1, 1), LSTY,  3)
                sizer.Add(pvtype,    (irow, 1), (1, 1), CSTY,  3)
                sizer.Add(del_pv,    (irow, 2), (1, 1), RSTY,  3)

            irow += 1
            sizer.Add(wx.StaticLine(panel, size=(150, -1),
                                    style=wx.LI_HORIZONTAL),
                      (irow, 0), (1, 3), CEN, 0)
            irow += 1


        txt =SimpleText(panel, 'New PVs:', font=titlefont,
                        colour=self.colors.title, style=LSTY)

        sizer.Add(txt, (irow, 0), (1, 1), LEFT, 3)
        sizer.Add(SimpleText(panel, 'Display Type',
                             colour=self.colors.title, style=CSTY),
                  (irow, 1), (1, 1), LSTY, 2)
        sizer.Add(SimpleText(panel, 'Remove?',
                             colour=self.colors.title, style=CSTY),
                  (irow, 2), (1, 1), RSTY, 2)
        # New PVs
        for npv in range(5):
            irow += 1
            name = pvNameCtrl(self, panel, value='', size=(175, -1))
            pvtype = PVTypeChoice(panel)
            del_pv = YesNo(panel, defaultyes=False)
            pvtype.Disable()
            del_pv.Disable()
            sizer.Add(name,     (irow, 0), (1, 1), LSTY,  3)
            sizer.Add(pvtype,   (irow, 1), (1, 1), CSTY,  3)
            sizer.Add(del_pv,   (irow, 2), (1, 1), RSTY,  3)

            self.newpvs[name.GetId()] = dict(index=npv, name=name,
                                             type=pvtype, delpv=del_pv)

        btn_panel = wx.Panel(panel, size=(75, -1))
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_ok     = add_button(btn_panel, 'Done',     size=(70, -1),
                                action=self.OnDone)
        btn_cancel = add_button(btn_panel, 'Cancel', size=(70, -1), action=self.onCancel)

        btn_sizer.Add(btn_ok,     0, wx.ALIGN_LEFT,  2)
        btn_sizer.Add(btn_cancel, 0, wx.ALIGN_RIGHT,  2)
        pack(btn_panel, btn_sizer)

        irow += 1
        sizer.Add(wx.StaticLine(panel, size=(150, -1), style=wx.LI_HORIZONTAL),
                  (irow, 0), (1, 3), CEN, 2)
        sizer.Add(btn_panel, (irow+1, 1), (1, 2), CEN, 2)
        sizer.Add(wx.StaticLine(panel, size=(150, -1), style=wx.LI_HORIZONTAL),
                  (irow+2, 0), (1, 3), CEN, 2)

        set_font_with_children(self, font)

        pack(panel, sizer)
        panel.SetupScrolling()

        mainsizer = wx.BoxSizer(wx.VERTICAL)
        mainsizer.Add(panel, 1, LSTY)
        pack(self, mainsizer)

        self.Layout()
        self.Show()
        self.Raise()

    def get_page_map(self):
        out = {}
        for i in range(self.parent.nb.GetPageCount()):
            out[self.parent.nb.GetPageText(i)] = i
        return out

    @EpicsFunction
    def connect_pv(self, pvname, wid=None):
        """try to connect newly added epics PVs"""
        if pvname is None or len(pvname) < 1:
            return
        if pvname not in self.connecting_pvs:
            if pvname not in self.epics_pvs:
                self.epics_pvs[pvname] = epics.PV(pvname)
            self.connecting_pvs[pvname] = (wid, time.time())

            if not self.etimer.IsRunning():
                self.etimer.Start(150)

    def onTimer(self, event=None):
        "timer event handler: look for connecting_pvs give up after 30 seconds"
        if len(self.connecting_pvs) == 0:
            self.etimer.Stop()
        for pvname in self.connecting_pvs:
            self.new_pv_connected(pvname)
            if time.time() - self.connecting_pvs[pvname][1] > 30:
                self.connecting_pvs.pop(pvname)

    @EpicsFunction
    def new_pv_connected(self, pvname):
        """if a new epics PV has connected, fill in the form data"""
        if pvname not in self.epics_pvs:
            pv = self.epics_pvs[pvname] = epics.PV(pvname)
        else:
            pv = self.epics_pvs[pvname]
            pv.poll()

        if not pv.connected:
            return
        try:
            wid, itime = self.connecting_pvs.pop(pvname)
        except KeyError:
            wid = None
        pv.get_ctrlvars()

        self.newpvs[wid]['type'].Enable()
        self.newpvs[wid]['delpv'].Enable()

        pvchoices = get_pvtypes(pv, instrument)
        self.newpvs[wid]['type'].SetChoices(pvchoices)
        self.newpvs[wid]['type'].SetSelection(0)
        self.newpvs[wid]['delpv'].SetStringSelection('No')

    def OnDone(self, event=None):
        """ Done Button Event: save and exit"""
        instpanel = self.parent.nb.GetCurrentPage()
        db = instpanel.db
        inst = instpanel.inst
        pagemap = self.get_page_map()
        page = pagemap.get(inst.name, None)

        newname = self.name.GetValue()
        oldname = inst.name
        if newname != oldname:
            inst.name = newname
        if page is not None:
            self.parent.nb.SetPageText(page, newname)
            instpanel.inst_title.SetLabel(' %s ' % newname)

        # make sure newpvs from dictionary are inserted in order
        # of "index", as appear on the GUI screen.
        new_pvs = [None]* len(self.newpvs)
        for entry in self.newpvs.values():
            if entry['delpv'].GetSelection() == 0 and entry['type'].Enabled:
                pvname = str(entry['name'].GetValue().strip())
                if len(pvname) > 0:
                    pvtype = str(entry['type'].GetStringSelection())
                    new_pvs[entry['index']] = (pvname, pvtype)

        for newpvs in new_pvs:
            if newpvs is not None:
                pvname, pvtype = newpvs
                db.add_pv(pvname, pvtype=pvtype)
                inst.pvs.append(db.get_pv(pvname))
                instpanel.add_pv(pvname)

        for pvname, lctrl, typectrl, delctrl in  self.curpvs:
            if delctrl.GetSelection() == 1:
                instpv = db.get_pv(pvname)
                inst.pvs.remove(instpv)
                instpanel.undisplay_pv(pvname)
            else:
                newtype = typectrl.GetStringSelection()
                curtype= db.get_pv(pvname).pvtype.name
                if newtype != curtype:
                    db.set_pvtype(pvname, newtype)
                    instpanel.PV_Panel(pvname)

        db.commit()
        # set order for PVs (as for next time)
        ordered_inst_pvs = db.get_ordered_instpvs(inst)
        for opv in ordered_inst_pvs:
            opv.display_order = -1

        for i, pv in enumerate(inst.pvs):
            for opv in ordered_inst_pvs:
                if opv.pv == pv:
                    opv.display_order = i

        for opv in ordered_inst_pvs:
            if opv.display_order == -1:
                i = i + 1
                opv.display_order = i


            #for opv in ordered_inst_pvs:
            #    if opv == pv:
            #        opv.display_order = i+1

        db.commit()
        # for pv in self.db.get_instrument_pvs(inst)

        # instpanel.redraw_leftpanel(announce=True)

        #         instpanel = self.parent.nb.GetCurrentPage()
        #         inst = instpanel.inst
        #         db = instpanel.db
        #         print 'self.parent.inst: ', inst, inst.pvs, db
        #         db.add_pv(pvname, pvtype=pvtype)
        #         # db.commit()
        #         inst.pvs.append(db.get_pv(pvname))
        #         self.parent.add_pv(pv)

        self.Destroy()

    def onCancel(self, event=None):
        self.Destroy()
