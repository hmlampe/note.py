#!/usr/bin/env python3

# Copyright (c) 2022 Falk Werner
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import tkinter as tk
import ctypes
import os
import io
import markdown
import webbrowser
import base64
from tkinterweb import HtmlFrame
from tkinter import scrolledtext
from tkinter import ttk
from tktooltip import ToolTip
from PIL import ImageFont, ImageDraw, Image, ImageTk

#-------------------------------------------
# Model
#-------------------------------------------

class ModelEvent:
    def __init__(self):
        self.subscribers = []
    
    def subscribe(self, subscriber):
        self.subscribers.append(subscriber)
    
    def unsubscribe(self, subscriber):
        self.subscribers.remove(subscriber)
    
    def fire(self):
        for subscriber in self.subscribers:
            subscriber()

class Note:
    def __init__(self, name, isvalid=True):
        self.__name = name
        self.__contents = ""
        self.name_changed = ModelEvent()
        self.contents_changed = ModelEvent()
        self.isvalid = isvalid

    def __repr__(self):
        return self.__name

    def name(self, value=None):
        if None != value:
            self.__name = value
            self.name_changed.fire()
        return self.__name

    def contents(self, value=None):
        if None != value:
            self.__contents = value
            self.contents_changed.fire()
        return self.__contents

    def matches(self, filter):
        return filter.lower() in self.__name.lower()

class NoteCollection:
    def __init__(self):
        self.notes = dict()
        self.on_changed = ModelEvent()
        self.on_selection_changed = ModelEvent()
        self.invalid_note = Note("", isvalid=False)
        self._selected_note = self.invalid_note
    
    def _generate_name(self):
        name = "Untitled"
        number = 0
        while name in self.notes:
            number += 1
            name = "Untitled %d" % (number)
        return name

    def _rebuild_index(self):
        notes = dict()
        for note in self.notes.values():
            notes[note.name()] = note
        self.notes = notes

    def query(self, filter="", reverse=False):
        notes = []
        for note in self.notes.values():
            if note.matches(filter):
                notes.append(note)
        notes.sort(key=lambda note: note.name(), reverse=reverse)
        return notes

    def add_new(self):
        name = self._generate_name()
        note = Note(name)
        self.notes[name] = note
        note.name_changed.subscribe(self.note_changed)
        self.on_changed.fire()

    def note_changed(self):
        self._rebuild_index()
        self.on_changed.fire()

    def selected_note(self):
        return self._selected_note

    def select(self, note_name):
        self._selected_note = self.notes[note_name] if note_name != None and note_name in self.notes else self.invalid_note
        self.on_selection_changed.fire()

class AppModel:
    def __init__(self):
        self.__name = "note.py"
        self.__geometry = "800x600"
        self.notes = NoteCollection()

    def get_name(self):
        return self.__name

    def get_geometry(self):
        return self.__geometry



#-------------------------------------------
# Widgets
#-------------------------------------------

class Icons:
    def __init__(self, master):
        font_data = base64.b64decode(ICONFONT)
        self.font = ImageFont.truetype(font=io.BytesIO(font_data), size=20)
        self.new = self.draw_text("\uefc2")
        self.search = self.draw_text("\uef7f")
        self.screenshot = self.draw_text("\ueecf")
        self.save = self.draw_text("\ueff6")
        self.delete = self.draw_text("\ueebb")

    def draw_text(self, value):
        left, top, right, bottom = self.font.getbbox(value)
        box = (right - left, bottom - top)
        image = Image.new(mode="RGBA", size=box)
        draw = ImageDraw.Draw(im=image)
        draw.text(xy=(0,0), text=value, fill='black', font=self.font, anchor="lt")
        return ImageTk.PhotoImage(image=image)


class FilterableListbox(ttk.Frame):
    def __init__(self, master, model, icons):
        tk.Frame.__init__(self, master)
        self.model = model
        self.pack()
        self.create_widgets(icons)
        self.model.on_changed.subscribe(self.update)

    def create_widgets(self, icons):
        self.commandframe = ttk.Frame(self)
        self.new_button = ttk.Button(self.commandframe, image=icons.new, command=self.model.add_new)
        self.new_button.pack(side = tk.RIGHT, fill=tk.X)
        ToolTip(self.new_button, msg="add new note", delay=1.0)
        self.label = ttk.Label(self.commandframe, image=icons.search)
        self.label.pack(side=tk.RIGHT, fill=tk.X)
        self.filter = tk.StringVar()
        self.filter.trace("w", lambda *args: self.update() )
        self.entry = ttk.Entry(self.commandframe, textvariable=self.filter)
        self.entry.pack(fill=tk.X, expand=True, padx=5)
        ToolTip(self.entry, msg="filter notes", delay=1.0)
        self.commandframe.pack(side = tk.TOP, fill=tk.X)

        self.listbox = tk.Listbox(self)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar=ttk.Scrollbar(self)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.config(yscrollcommand= self.scrollbar.set)
        self.listbox.bind('<<ListboxSelect>>', self.onselect)
        self.scrollbar.config(command=self.listbox.yview)
        self.update()

    def update(self):
        filter = self.filter.get()
        self.listbox.delete(0, tk.END)
        items = self.model.query(filter)
        selected = self.model.selected_note().name() 
        i = 0
        selected_index = -1
        for item in items:
            self.listbox.insert(tk.END, item)
            if selected == item.name():
                selected_index = i
            i += 1
        if selected_index >= 0:
            self.listbox.select_set(selected_index)

    def onselect(self, event):
        selection = event.widget.curselection()
        if selection:
            index = selection[0]
            result = self.listbox.get(index)
            self.model.select(result)

class NoteFrame(ttk.Frame):
    def __init__(self, master, model, icons):
        tk.Frame.__init__(self, master)
        self.note = None
        self.model = model
        self.pack()
        self.create_widgets(icons)
        model.on_selection_changed.subscribe(self.update)

    def create_widgets(self, icons):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.frame = HtmlFrame(self.notebook, messages_enabled=False)
        #frame.on_link_click(clicked)
        html = markdown.markdown('', extensions=['tables'])
        self.frame.load_html(html)
        self.frame.pack(fill=tk.BOTH, expand=1)
        self.notebook.add(self.frame, text='View')

        editframe = tk.Frame(self.notebook)
        commandframe = ttk.Frame(editframe)
        deletebutton = ttk.Button(commandframe, image=icons.delete)
        deletebutton.pack(side=tk.RIGHT)
        ToolTip(deletebutton, msg="remove this note", delay=1.0)
        updatebutton = ttk.Button(commandframe, image=icons.save, command = self.save)
        updatebutton.pack(side=tk.RIGHT)
        ToolTip(updatebutton, msg="sync changes", delay=1.0)
        screenshotbutton = ttk.Button(commandframe, image=icons.screenshot)
        screenshotbutton.pack(side=tk.RIGHT, padx=5)
        ToolTip(screenshotbutton, msg="take screenshot", delay=1.0)
        self.namevar = tk.StringVar()
        nameedit = tk.Entry(commandframe, textvariable=self.namevar)
        nameedit.pack(fill=tk.BOTH, expand=True)
        ToolTip(nameedit, msg="change title", delay=1.0)

        commandframe.pack(fill=tk.X, side=tk.TOP)

        self.text = scrolledtext.ScrolledText(editframe)
        self.text.pack(fill=tk.BOTH, expand=True)
        self.text.bind('<KeyRelease>', lambda e: self.update_view())
        self.notebook.add(editframe, text='Edit')
        self.activateable_widgets = [ updatebutton, deletebutton, screenshotbutton, nameedit, self.text]
        self.enable(False)

    def enable(self, value=True):
        for widget in self.activateable_widgets:
            widget.configure(state="normal" if value == True else "disabled")

    def update_view(self):
        contents = self.text.get(1.0, tk.END)
        html = markdown.markdown(contents, extensions=['tables'])
        self.frame.load_html(html)

    def update(self):
        self.note = self.model.selected_note()
        if self.note.isvalid:
            self.enable(True)
            contents = self.note.contents()
            html = markdown.markdown(contents, extensions=['tables'])
            self.frame.load_html(html)
            self.text.delete(1.0, tk.END)
            self.text.insert(tk.END, contents)
            self.namevar.set(self.note.name())
        else:
            self.frame.load_html("")
            self.namevar.set("")
            self.text.delete(1.0, tk.END)
            self.enable(False)

    def save(self):
        contents = self.text.get(1.0, tk.END)
        self.note.contents(contents)
        self.note.name(self.namevar.get())



class App:
    def __init__(self, model=AppModel()):
        self.root = tk.Tk()
        self.icons = Icons(self.root)
        self.root.title(model.get_name())
        self.root.geometry(model.get_geometry())

        self.splitPane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.splitPane.pack(fill=tk.BOTH, expand=True)

        self.listbox = FilterableListbox(self.splitPane, model.notes, self.icons)
        self.listbox.pack(fill=tk.BOTH, expand=True)
        self.splitPane.add(self.listbox)

        self.noteframe = NoteFrame(self.splitPane, model.notes, self.icons)
        self.noteframe.pack(fill=tk.BOTH, expand=True)
        self.splitPane.add(self.noteframe)

    def run(self):
        self.root.mainloop()   

ICONFONT = (
    "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"
    "XFj+jwMIA0sDBAYE5QQCAy8ZAgEDSxwaEQ8wKj47hTwEBgEGBOpIPQL+BQRT"
    "BAYEKCM7Nz+siAMDSgMCBOMEBgEEAkgCCQOChYuLXzIwoQMDSwIBBOMEBQQD"
    "LxgDCANSZ11hXEk/LywtAwYFNBoEBxbPswAAAAAFAK7/qAM6AxQACQAZACkA"
    "OQBNAAAXHgEzITI2NxMhBTQ2OwEyFhURFAYrASImNQM0NjsBMhYVERQGKwEi"
    "JjUDNDY7ATIWFREUBisBIiY1ASM1NCYrASIGHQEjIgYdASE1NCb7ARkSAZsR"
    "GgEd/dIBdAsHHQcLCwcdBwt9CwcdBwoKBx0HC30LBxwHCwsHHAcLAci+BQTH"
    "BAa9CxECjBAtEhkZEgJsmgcKCgf+nQcKCgcBYwcKCgf+nQcKCgcBYwcKCgf+"
    "nQcKCgcCpCQEBgYEJBALV1cLEAAAAA4ArgABAAAAAAAAABgAMgABAAAAAAAB"
    "AAkAXwABAAAAAAACAAcAeQABAAAAAAADACYAzwABAAAAAAAEAAkBCgABAAAA"
    "AAAFABABNgABAAAAAAAGAAYBVQADAAEECQAAADAAAAADAAEECQABABIASwAD"
    "AAEECQACAA4AaQADAAEECQADAEwAgQADAAEECQAEABIA9gADAAEECQAFACAB"
    "FAADAAEECQAGAAwBRwBDAG8AcAB5AHIAaQBnAGgAdAAgACgAYwApACAAMgAw"
    "ADIAMgAsACAAdQBzAGUAcgAAQ29weXJpZ2h0IChjKSAyMDIyLCB1c2VyAABV"
    "AG4AdABpAHQAbABlAGQAMQAAVW50aXRsZWQxAABSAGUAZwB1AGwAYQByAABS"
    "ZWd1bGFyAABGAG8AbgB0AEYAbwByAGcAZQAgADIALgAwACAAOgAgAFUAbgB0"
    "AGkAdABsAGUAZAAxACAAOgAgADEANgAtADEAMgAtADIAMAAyADIAAEZvbnRG"
    "b3JnZSAyLjAgOiBVbnRpdGxlZDEgOiAxNi0xMi0yMDIyAABVAG4AdABpAHQA"
    "bABlAGQAMQAAVW50aXRsZWQxAABWAGUAcgBzAGkAbwBuACAAMAAwADEALgAw"
    "ADAAMAAgAABWZXJzaW9uIDAwMS4wMDAgAABuAG8AdABlAHAAeQAAbm90ZXB5"
    "AAAAAAIAAAAAAAD/tQAyAAAAAQAAAAAAAAAAAAAAAAAAAAAACAAAAAEAAgEC"
    "AQMBBAEFAQYGcGx1cy0yBGxvb2sGY2FtZXJhDXNwaW5uZXItYWx0LTMDYmlu"
    "AAAAAAH//wACAAAAAQAAAADeBipuAAAAAN/Ch6oAAAAA38KHqg==")

if __name__ == "__main__":
    app = App()
    app.run()
