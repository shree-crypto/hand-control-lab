# SPDX-License-Identifier: GPL-3.0-only
"""Native desktop launcher. Tkinter is imported only when the GUI is opened."""
import queue
import threading


MODE_DESCRIPTIONS = {
    "preview": "Try hand tracking and gestures without moving your computer's pointer. Start here to check your camera and hand labels.",
    "control": "Control the Windows pointer with your chosen hand gestures. The camera window starts paused; F8 enables or pauses control and Escape quits.",
    "finger-drums": "Play percussion with individual fingers. Choose your personal finger profile to use the fingers and movement ranges that work comfortably for you.",
    "four-limb": "Try a four-part drum layout using both hands and body movements. Keep enough of your body in the camera view for tracking.",
    "hand-calibration": "Capture comfortable released and pinched states for the fingers you choose. This saves personal settings without controlling the desktop.",
    "piano": "Play a virtual piano using hand movement. Enable live MIDI only when you want to send notes to the selected MIDI output.",
    "drums": "Play the virtual drum kit. Try the camera preview first, then add MIDI output or a recording when you are ready.",
    "workbench": "Grab, rotate, and scale a 3D object with hand gestures. This is a playground; it does not edit your modeling application's scene.",
    "gaze": "Calibrate estimated gaze on large targets, then experiment with pinch, deliberate eye closure, or dwell selection inside the playground.",
    "draw": "Draw with a pinch and use your other hand to change the brush. All drawing stays inside this playground.",
    "music": "Use hand movement to control a simple instrument. Start at low speaker volume while trying continuous sound controls.",
    "gestures": "Open a palm command wheel and try selecting commands inside the playground. Choose comfortable movements before experimenting with app-specific actions.",
    "face": "Calibrate a relaxed face, then try deliberate facial expressions. This playground does not click desktop controls.",
    "camera-lab": "Inspect the camera's actual frame rate and available sources. Infrared and depth availability depend on the camera and driver.",
    "backends": "See which local vision and acceleration options are available. Hardware marketing specifications do not guarantee a particular model will use the NPU.",
}


def describe_mode(mode):
    return MODE_DESCRIPTIONS.get(mode, "Choose an experiment and press Start to open its camera window.")


def model_status_text(status):
    if not status:
        return "Models: not checked"
    missing = [name for name, available in status.items() if not available]
    if not missing:
        return "Models ready"
    return "Models needed: " + ", ".join(missing)


def worker_status(running, exit_code=None):
    if running:
        return "Running — use the experiment's window to interact"
    if exit_code is None:
        return "Ready — choose an experiment"
    if exit_code == 0:
        return "Finished — choose another experiment or start again"
    return "Stopped with a problem — see Activity for details"


class App:
    def __init__(self, root, tk, ttk, messagebox, filedialog, services):
        self.root, self.tk, self.ttk = root, tk, ttk
        self.messagebox, self.filedialog, self.services = messagebox, filedialog, services
        self.controller = services.Controller()
        self.events = queue.Queue()
        self.closed = False
        self.downloading = False
        self.refreshing_ports = False
        self.last_log = None
        self.was_running = False
        self.exit_code = None
        self.labels = dict(services.MODE_LABELS)
        self.modes = list(self.labels)
        self.vars = {}
        self.status = tk.StringVar(value=worker_status(False))
        self.model_text = tk.StringVar(value="Models: checking")
        self.description = tk.StringVar(value=describe_mode("preview"))
        self.action_note = tk.StringVar(value="Nothing runs until you press Start.")
        load_error = None
        try:
            settings = services.load_settings()
        except Exception as exc:
            settings = services.Settings()
            load_error = str(exc)
        self._build(settings)
        self._refresh_model_status()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(150, self._tick)
        if load_error:
            root.after(0, lambda: self.messagebox.showwarning("Settings reset", "Saved settings could not be loaded. Defaults are shown.\n\n" + load_error, parent=root))

    def _build(self, settings):
        tk, ttk, root = self.tk, self.ttk, self.root
        root.title("Hand Control — experiment studio")
        root.geometry("920x800")
        root.minsize(800, 740)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        header = ttk.Frame(root, padding=(20, 14))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="Hand Control", font=("Segoe UI", 19, "bold")).pack(anchor="w")
        ttk.Label(header, text="Hands, eyes, music, and motion — try one experiment at a time.").pack(anchor="w", pady=(3, 0))
        self.tabs = ttk.Notebook(root)
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=16)
        play = ttk.Frame(self.tabs, padding=14)
        setup = ttk.Frame(self.tabs, padding=14)
        activity = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(play, text="Experiments")
        self.tabs.add(setup, text="Settings")
        self.tabs.add(activity, text="Activity")
        play.columnconfigure(0, weight=1)
        play.columnconfigure(1, weight=2)
        play.rowconfigure(1, weight=1)
        ttk.Label(play, text="Choose an experiment", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 8))
        list_frame = ttk.Frame(play)
        list_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 18))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        self.mode_list = tk.Listbox(list_frame, exportselection=False, height=15, activestyle="none", font=("Segoe UI", 10), borderwidth=1)
        self.mode_list.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(list_frame, command=self.mode_list.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.mode_list.configure(yscrollcommand=scroll.set)
        for mode in self.modes:
            self.mode_list.insert("end", self.labels[mode])
        initial = self.modes.index("preview") if "preview" in self.modes else 0
        if self.modes:
            self.mode_list.selection_set(initial)
        self.mode_list.bind("<<ListboxSelect>>", self._choose_mode)
        detail = ttk.Frame(play)
        detail.grid(row=1, column=1, sticky="nsew")
        self.mode_title = ttk.Label(detail, text=self.labels.get("preview", "Experiment"), font=("Segoe UI", 14, "bold"))
        self.mode_title.pack(anchor="w", pady=(0, 12))
        ttk.Label(detail, textvariable=self.description, wraplength=440, justify="left").pack(anchor="w", fill="x")
        ttk.Separator(detail).pack(fill="x", pady=18)
        tips = "First time?\n\n1. Open your camera's privacy shutter.\n2. Download the models below if needed.\n3. Try Hand preview before desktop control.\n4. For personal finger mappings, calibrate first.\n\nExperiment windows explain their own keys."
        ttk.Label(detail, text=tips, wraplength=440, justify="left").pack(anchor="w")
        ttk.Button(detail, text="First-use guide", command=self.help).pack(anchor="w", pady=(18, 0))
        models = ttk.LabelFrame(play, text="Tracking models", padding=10)
        models.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        models.columnconfigure(0, weight=1)
        ttk.Label(models, textvariable=self.model_text, wraplength=610).grid(row=0, column=0, sticky="w")
        self.download_button = ttk.Button(models, text="Download models", command=self.download)
        self.download_button.grid(row=0, column=1, padx=(12, 0))

        # Settings use a compact grid so the native window remains usable on a laptop.
        setup.columnconfigure(1, weight=1)
        for name in ("camera", "fps", "midi_port", "record_path", "finger_profile", "pinch_profile", "other_pinch_profile", "hand_mode", "sensitivity", "dominant_hand", "primary_finger", "secondary_finger"):
            self.vars[name] = tk.StringVar(value=str(getattr(settings, name)))
        self.vars["live_midi"] = tk.BooleanVar(value=settings.live_midi)
        def field(row, label, name, width=12):
            ttk.Label(setup, text=label).grid(row=row, column=0, sticky="w", pady=5)
            entry = ttk.Entry(setup, textvariable=self.vars[name], width=width)
            entry.grid(row=row, column=1, sticky="ew", padx=(12, 8), pady=5)
            return entry
        field(0, "Camera number", "camera")
        ttk.Label(setup, text="Instrument camera FPS").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Combobox(setup, textvariable=self.vars["fps"], values=("30", "60", "120"), state="readonly").grid(row=1, column=1, sticky="ew", padx=(12, 8), pady=5)
        field(2, "Instrument sensitivity", "sensitivity")
        ttk.Label(setup, text="Hand tracking mode").grid(row=3, column=0, sticky="w", pady=5)
        ttk.Combobox(setup, textvariable=self.vars["hand_mode"], values=("palm", "markers"), state="readonly", width=20).grid(row=3, column=1, sticky="ew", padx=(12, 8), pady=5)
        ttk.Separator(setup).grid(row=4, column=0, columnspan=3, sticky="ew", pady=9)
        ttk.Label(setup, text="MIDI output").grid(row=5, column=0, sticky="w", pady=5)
        self.port_choice = ttk.Combobox(setup, textvariable=self.vars["midi_port"], values=(settings.midi_port,) if settings.midi_port else (), width=32)
        self.port_choice.grid(row=5, column=1, sticky="ew", padx=(12, 8), pady=5)
        self.port_refresh = ttk.Button(setup, text="Refresh", command=self.refresh_ports)
        self.port_refresh.grid(row=5, column=2)
        ttk.Checkbutton(setup, text="Send live MIDI notes to this output", variable=self.vars["live_midi"]).grid(row=6, column=1, sticky="w", padx=(12, 0), pady=4)
        field(7, "Optional MIDI recording", "record_path")
        ttk.Button(setup, text="Browse…", command=lambda: self.browse("record_path", save=True)).grid(row=7, column=2)
        ttk.Separator(setup).grid(row=8, column=0, columnspan=3, sticky="ew", pady=9)
        for row, label, name in ((9, "Finger profile", "finger_profile"), (10, "Pointer hand pinch profile", "pinch_profile"), (11, "Other hand pinch profile", "other_pinch_profile")):
            field(row, label, name)
            ttk.Button(setup, text="Browse…", command=lambda key=name: self.browse(key)).grid(row=row, column=2)
        contact = ttk.LabelFrame(setup, text="Desktop gesture calibration", padding=(8, 4))
        contact.grid(row=12, column=0, columnspan=3, sticky="ew", pady=(9, 0))
        for col, label, name, values in (
                (0, "Calibration hand", "dominant_hand", ("Right", "Left")),
                (1, "Primary contact", "primary_finger", ("index", "middle", "ring", "pinky")),
                (2, "Secondary contact", "secondary_finger", ("index", "middle", "ring", "pinky"))):
            contact.columnconfigure(col, weight=1)
            group = ttk.Frame(contact)
            group.grid(row=0, column=col, sticky="ew", padx=4)
            ttk.Label(group, text=label).pack(anchor="w")
            ttk.Combobox(group, textvariable=self.vars[name], values=values,
                         state="readonly", width=14).pack(fill="x", pady=(2, 4))
        ttk.Label(setup, text="Settings apply on Start. Leave optional paths empty for defaults.\nCamera FPS may be lower than requested. Calibration uses the contacts selected above.", wraplength=690, foreground="#666666").grid(row=13, column=0, columnspan=3, sticky="w", pady=(10, 6))
        ttk.Button(setup, text="Save settings", command=self.save).grid(row=14, column=1, sticky="w", padx=(12, 0))

        activity.columnconfigure(0, weight=1)
        activity.rowconfigure(1, weight=1)
        ttk.Label(activity, text="Messages from the current experiment").grid(row=0, column=0, sticky="w", pady=(0, 7))
        self.log = tk.Text(activity, wrap="word", state="disabled", font=("Consolas", 9), background="#f6f6f6", foreground="#202020", borderwidth=1)
        self.log.grid(row=1, column=0, sticky="nsew")
        logscroll = ttk.Scrollbar(activity, command=self.log.yview)
        logscroll.grid(row=1, column=1, sticky="ns")
        self.log.configure(yscrollcommand=logscroll.set)
        footer = ttk.Frame(root, padding=(18, 12))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status, wraplength=620).grid(row=0, column=0, sticky="w")
        ttk.Label(footer, textvariable=self.action_note, wraplength=620, foreground="#666666").grid(row=1, column=0, sticky="w", pady=(3, 0))
        buttons = ttk.Frame(footer)
        buttons.grid(row=0, column=1, rowspan=2, padx=(12, 0))
        self.start_button = ttk.Button(buttons, text="Start", command=self.start, width=12)
        self.start_button.pack(side="left", padx=(0, 8))
        self.stop_button = ttk.Button(buttons, text="Stop", command=self.stop, state="disabled", width=10)
        self.stop_button.pack(side="left")

    def selected_mode(self):
        selected = self.mode_list.curselection()
        return self.modes[selected[0]] if selected else self.modes[0]

    def _choose_mode(self, event=None):
        if self.modes:
            mode = self.selected_mode()
            self.mode_title.configure(text=self.labels[mode])
            self.description.set(describe_mode(mode))

    def _settings(self):
        try:
            settings = self.services.Settings(
                camera=int(self.vars["camera"].get()), fps=int(self.vars["fps"].get()),
                midi_port=self.vars["midi_port"].get().strip(), live_midi=bool(self.vars["live_midi"].get()),
                record_path=self.vars["record_path"].get().strip(),
                finger_profile=self.vars["finger_profile"].get().strip(),
                pinch_profile=self.vars["pinch_profile"].get().strip(),
                other_pinch_profile=self.vars["other_pinch_profile"].get().strip(),
                hand_mode=self.vars["hand_mode"].get(), sensitivity=float(self.vars["sensitivity"].get()),
                dominant_hand=self.vars["dominant_hand"].get(),
                primary_finger=self.vars["primary_finger"].get(),
                secondary_finger=self.vars["secondary_finger"].get())
        except ValueError as exc:
            raise ValueError("Camera and FPS must be whole numbers; sensitivity must be a number.") from exc
        self.services.validate_settings(settings)
        return settings

    def save(self):
        try:
            self.services.save_settings(self._settings())
            self.action_note.set("Settings saved for your next session.")
        except Exception as exc:
            self.messagebox.showerror("Could not save settings", str(exc), parent=self.root)

    def start(self):
        if self.controller.running:
            return
        try:
            settings = self._settings()
            # Validate the mode-specific options before saving or starting anything.
            self.services.launch_arguments(self.selected_mode(), settings)
            self.services.save_settings(settings)
            self.controller.start(self.selected_mode(), settings)
        except Exception as exc:
            self.messagebox.showerror("Could not start experiment", str(exc), parent=self.root)
            return
        self.was_running = True
        self.exit_code = None
        self.last_log = None
        self.status.set(worker_status(True))
        self.action_note.set("The experiment opens in its own window. Stop ends it.")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")

    def stop(self):
        try:
            self.controller.stop()
            self.action_note.set("Stopping experiment…")
        except Exception as exc:
            self.messagebox.showerror("Could not stop experiment", str(exc), parent=self.root)

    def browse(self, name, save=False):
        if save:
            path = self.filedialog.asksaveasfilename(parent=self.root, title="Save MIDI recording", defaultextension=".mid", filetypes=[("MIDI file", "*.mid"), ("All files", "*")])
        else:
            path = self.filedialog.askopenfilename(parent=self.root, title="Choose personal profile", filetypes=[("Profile JSON", "*.json"), ("All files", "*")])
        if path:
            self.vars[name].set(path)

    def _background(self, kind, function):
        def work():
            try:
                self.events.put((kind, True, function()))
            except Exception as exc:
                self.events.put((kind, False, str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def refresh_ports(self):
        if self.refreshing_ports:
            return
        self.refreshing_ports = True
        self.port_refresh.configure(state="disabled")
        self.action_note.set("Looking for MIDI outputs…")
        self._background("ports", self.services.available_midi_ports)

    def download(self):
        if self.downloading:
            return
        self.downloading = True
        self.download_button.configure(state="disabled")
        self.model_text.set("Downloading models… You can keep using the launcher.")
        self._background("models", self.services.download_models)

    def _refresh_model_status(self):
        try:
            self.model_text.set(model_status_text(self.services.model_status()))
        except Exception as exc:
            self.model_text.set("Could not check models: " + str(exc))

    def _tick(self):
        if self.closed:
            return
        while True:
            try:
                kind, ok, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "models":
                self.downloading = False
                self.download_button.configure(state="normal")
                self._refresh_model_status()
                if ok:
                    self.action_note.set("Model download finished.")
                else:
                    self.messagebox.showerror("Model download failed", value, parent=self.root)
            elif kind == "ports":
                self.refreshing_ports = False
                self.port_refresh.configure(state="normal")
                if ok:
                    self.port_choice.configure(values=value or ())
                    self.action_note.set(f"Found {len(value or [])} MIDI output(s). Choose one in Settings.")
                else:
                    self.messagebox.showerror("Could not list MIDI outputs", value, parent=self.root)
                    self.action_note.set("Live MIDI remains optional; the playgrounds can run without it.")
        try:
            exit_code = self.controller.poll()
            running = self.controller.running
            if self.was_running and not running:
                self.was_running = False
                self.exit_code = exit_code
                self.action_note.set("See Activity for the experiment's messages.")
            self.status.set(worker_status(running, self.exit_code))
            self.start_button.configure(state="disabled" if running else "normal")
            self.stop_button.configure(state="normal" if running else "disabled")
            text = self.controller.read_log()
            if text != self.last_log:
                self.log.configure(state="normal")
                self.log.delete("1.0", "end")
                self.log.insert("1.0", text or "No experiment messages yet.")
                self.log.see("end")
                self.log.configure(state="disabled")
                self.last_log = text
        except Exception as exc:
            self.status.set("Could not read experiment status: " + str(exc))
        self.root.after(200, self._tick)

    def help(self):
        self.messagebox.showinfo("First-use guide",
            "Start with Hand preview and good lighting. Open the camera privacy shutter.\n\n"
            "Use Personal pinch calibration to choose comfortable finger movements; you do not need a particular open-hand shape. Save the profile, then choose its file in Settings.\n\n"
            "For MIDI instruments, choose an output in Settings and enable live MIDI only when you want notes sent to it. Recording is optional.\n\n"
            "Desktop control starts paused. F8 enables/pauses it and Escape quits. Other playgrounds stay inside their own windows and show their controls there.\n\n"
            "If a camera cannot open, close other camera apps, check Windows camera permissions, or try a different camera number. Press Stop before switching experiments.", parent=self.root)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="disabled")
        self.status.set("Stopping experiment before closing…")
        try:
            self.controller.stop()
        except Exception as exc:
            self.closed = False
            self.messagebox.showerror("Could not stop experiment", str(exc), parent=self.root)
            self.root.after(200, self._tick)
            return
        self.root.after(50, self._finish_close)

    def _finish_close(self):
        # The service escalates a graceful stop to terminate/kill as needed.
        # Keep polling until it has reaped the worker; destroying Tk first could
        # otherwise leave a camera/MIDI worker running without its launcher.
        try:
            self.controller.poll()
            running = self.controller.running
        except Exception as exc:
            self.closed = False
            self.messagebox.showerror("Could not finish closing", str(exc), parent=self.root)
            self.root.after(200, self._tick)
            return
        if running:
            self.root.after(100, self._finish_close)
        else:
            self.root.destroy()


def main():
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox, filedialog
    except ImportError:
        print("The desktop launcher needs Tkinter. Install Python with Tcl/Tk support, or use the experiment commands.")
        return 1
    from . import desktop_services
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"Could not open the desktop window: {exc}")
        return 1
    try:
        App(root, tk, ttk, messagebox, filedialog, desktop_services)
        root.mainloop()
        return 0
    except Exception as exc:
        try:
            messagebox.showerror("Hand Control could not open", str(exc), parent=root)
            root.destroy()
        except tk.TclError:
            pass
        return 1
