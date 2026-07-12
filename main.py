import json
import os
import threading
import datetime
import copy
import sys

import wx

from garmin_manager import GarminManager
# from llm_connectors import OllamaConnector

def get_base_path():
    """ Get absolute path for user-specific data (Mac/Win/Linux) """
    if sys.platform == 'darwin':
        # macOS: ~/Library/Application Support/GarminCoach
        base_path = os.path.expanduser("~/Library/Application Support/GarminCoach")
    elif sys.platform == 'win32':
        # Windows: %APPDATA%/GarminCoach
        base_path = os.path.join(os.environ['APPDATA'], 'GarminCoach')
    else:
        # Linux/other: ~/.garmin_coach
        base_path = os.path.expanduser("~/.garmin_coach")
    
    if not os.path.exists(base_path):
        os.makedirs(base_path)
    return base_path

BASE_PATH = get_base_path()
CONFIG_FILE = os.path.join(BASE_PATH, "config.json")
DEFAULT_PROMPT_LENGTH = 64000
DEFAULT_MAX_ACTIVITIES = 5
QUERY_FILE = os.path.join(BASE_PATH, "query.txt")
CACHE_DIR = os.path.join(BASE_PATH, ".cache")

# Initialization: Create a blank config if none exists for this user
if not os.path.exists(CONFIG_FILE):
    initial_config = {
        "users": [], # Start empty so the app prompts for a new user
        "questions": [
            {"id": 1, "text": "Evaluate my last workout"},
            {"id": 2, "text": "What should I do for my next running workout?"},
            {"id": 3, "text": "What should I do for my next cycling workout?"},
            {"id": 4, "text": "What should I do for my next swimming workout?"},
            {"id": 5, "text": "When should my next workout be?"}
        ],
        "custom_questions": []
    }
    with open(CONFIG_FILE, "w") as f:
        json.dump(initial_config, f, indent=4)

# ── Config helpers ─────────────────────────────────────────────────────────────

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {"users": [], "questions": [], "custom_questions": []}

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

# ── App entry point ────────────────────────────────────────────────────────────

class GarminCoachApp(wx.App):
    def OnInit(self):
        config = load_config()
        # If no users, prompt to add one immediately
        if not config["users"]:
            dlg = wx.TextEntryDialog(None, "No users found. Enter name for first user:", "Welcome")
            if dlg.ShowModal() == wx.ID_OK:
                name = dlg.GetValue()
                dlg_email = wx.TextEntryDialog(None, f"Enter Garmin email for {name}:", "Setup")
                if dlg_email.ShowModal() == wx.ID_OK:
                    email = dlg_email.GetValue()
                    config["users"].append({"name": name, "email": email})
                    save_config(config)
                else: return False
            else: return False
            
        frame = MainFrame(config)
        frame.Show()
        frame.Raise()
        frame.SetFocus()
        return True

# ── Main window ────────────────────────────────────────────────────────────────

class MainFrame(wx.Frame):
    def __init__(self, config):
        super().__init__(
            None,
            title="Garmin Coach",
            size=(740, 860),
            style=wx.DEFAULT_FRAME_STYLE,
        )
        self.config = config
        self.garmin_data = None
        self.gm = GarminManager(cache_dir=CACHE_DIR)
        self.questions = self.config["questions"]

        self._build_ui()
        self.Centre()
        self._refresh_data_status()

    def _build_ui(self):
        self.scroll = wx.ScrolledWindow(self, style=wx.VSCROLL)
        self.scroll.SetScrollRate(0, 12)
        root = wx.BoxSizer(wx.VERTICAL)

        root.Add(self._build_user_section(),      flag=wx.EXPAND | wx.ALL, border=16)
        root.Add(wx.StaticLine(self.scroll),      flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=16)
        root.Add(self._build_data_section(),      flag=wx.EXPAND | wx.ALL, border=16)
        root.Add(wx.StaticLine(self.scroll),      flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=16)
        root.Add(self._build_questions_section(), flag=wx.EXPAND | wx.ALL, border=16)
        root.Add(wx.StaticLine(self.scroll),      flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=16)
        root.Add(self._build_ask_section(),       flag=wx.EXPAND | wx.ALL, border=16)
        root.Add(wx.StaticLine(self.scroll),      flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=16)
        root.Add(self._build_response_section(),  flag=wx.EXPAND | wx.ALL, border=16)

        self.scroll.SetSizer(root)
        frame_sizer = wx.BoxSizer(wx.VERTICAL)
        frame_sizer.Add(self.scroll, proportion=1, flag=wx.EXPAND)
        self.SetSizer(frame_sizer)

    def _section_title(self, text):
        lbl = wx.StaticText(self.scroll, label=text)
        lbl.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        lbl.SetForegroundColour(wx.Colour(90, 90, 90))
        return lbl

    def _build_user_section(self):
        box = wx.BoxSizer(wx.VERTICAL)
        box.Add(self._section_title("1 — Select User"), flag=wx.BOTTOM, border=8)

        row = wx.BoxSizer(wx.HORIZONTAL)
        self.user_choice = wx.Choice(self.scroll, choices=self._user_display_names())
        self.user_choice.SetSelection(0)
        self.user_choice.Bind(wx.EVT_CHOICE, self._on_user_changed)
        row.Add(self.user_choice, proportion=1, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=8)

        add_btn = wx.Button(self.scroll, label="Add", size=(60, -1))
        edit_btn = wx.Button(self.scroll, label="Edit", size=(60, -1))
        remove_btn = wx.Button(self.scroll, label="Remove", size=(70, -1))
        add_btn.Bind(wx.EVT_BUTTON, self._on_add_user)
        edit_btn.Bind(wx.EVT_BUTTON, self._on_edit_user)
        remove_btn.Bind(wx.EVT_BUTTON, self._on_remove_user)
        row.Add(add_btn, flag=wx.RIGHT, border=4)
        row.Add(edit_btn, flag=wx.RIGHT, border=4)
        row.Add(remove_btn)

        box.Add(row, flag=wx.EXPAND)
        return box

    def _user_display_names(self):
        return [f"{u['name']}  ({u['email']})" for u in self.config["users"]]

    def _build_data_section(self):
        box = wx.BoxSizer(wx.VERTICAL)
        box.Add(self._section_title("2 — Garmin Data"), flag=wx.BOTTOM, border=8)
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.data_status_lbl = wx.StaticText(self.scroll, label="Checking cache…")
        self.fetch_btn = wx.Button(self.scroll, label="Fetch from Garmin")
        self.fetch_btn.Bind(wx.EVT_BUTTON, self._on_fetch)
        row.Add(self.data_status_lbl, proportion=1, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=8)
        row.Add(self.fetch_btn, flag=wx.ALIGN_CENTER_VERTICAL)
        box.Add(row, flag=wx.EXPAND)
        self.fetch_gauge = wx.Gauge(self.scroll, range=100)
        self.fetch_gauge.Hide()
        box.Add(self.fetch_gauge, flag=wx.EXPAND | wx.TOP, border=8)
        return box

    def _build_questions_section(self):
        box = wx.BoxSizer(wx.VERTICAL)
        box.Add(self._section_title("3 — Select Questions"), flag=wx.BOTTOM, border=8)
        self.checklist = wx.CheckListBox(self.scroll, size=(-1, 120), style=wx.LB_SINGLE)
        for q in self.questions:
            self.checklist.Append(f"{q['text']}")
        box.Add(self.checklist, flag=wx.EXPAND)
        self.checklist.Check(0, True)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        sel_all_btn = wx.Button(self.scroll, label="Select All")
        clr_all_btn = wx.Button(self.scroll, label="Clear All")
        sel_all_btn.Bind(wx.EVT_BUTTON, self._on_select_all)
        clr_all_btn.Bind(wx.EVT_BUTTON, self._on_clear_all)
        btn_row.Add(sel_all_btn, flag=wx.RIGHT, border=8)
        btn_row.Add(clr_all_btn)
        box.Add(btn_row, flag=wx.TOP, border=8)

        box.Add(wx.StaticText(self.scroll, label="Custom question (optional):"), flag=wx.TOP, border=12)
        self.custom_input = wx.TextCtrl(self.scroll)
        self.custom_input.SetHint("Type a one-off question here…")
        box.Add(self.custom_input, flag=wx.EXPAND | wx.TOP, border=4)
        return box

    def _build_ask_section(self):
        box = wx.BoxSizer(wx.VERTICAL)
        box.Add(self._section_title("4 — Reduce prompt size, useful for prompts including all the training history"),
                flag=wx.BOTTOM, border=8)

        settings_grid = wx.FlexGridSizer(1, 4, 8, 8)
        settings_grid.AddGrowableCol(1)
        settings_grid.AddGrowableCol(3)
        settings_grid.Add(wx.StaticText(self.scroll, label="Max Prompt Length in chars:"), flag=wx.ALIGN_CENTER_VERTICAL)
        self.max_len_ctrl = wx.TextCtrl(self.scroll, value=str(DEFAULT_PROMPT_LENGTH))
        settings_grid.Add(self.max_len_ctrl, flag=wx.EXPAND)
        settings_grid.Add(wx.StaticText(self.scroll, label="Max Activities:"), flag=wx.ALIGN_CENTER_VERTICAL)
        self.max_act_ctrl = wx.TextCtrl(self.scroll, value=str(DEFAULT_MAX_ACTIVITIES))
        settings_grid.Add(self.max_act_ctrl, flag=wx.EXPAND)
        box.Add(settings_grid, flag=wx.EXPAND | wx.BOTTOM, border=12)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        # self.ask_btn = wx.Button(self.scroll, label="Ask Coach", size=(-1, 42))
        # self.ask_btn.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        # self.ask_btn.Bind(wx.EVT_BUTTON, self._on_ask)
        self.create_query_btn = wx.Button(self.scroll, label="Create query", size=(-1, 42))
        self.create_query_btn.Bind(wx.EVT_BUTTON, self._on_create_query_only)
        self.copy_btn = wx.Button(self.scroll, label="Copy Response")
        self.copy_btn.Bind(wx.EVT_BUTTON, self._on_copy_response)
        # box.Add(copy_btn, flag=wx.TOP | wx.ALIGN_RIGHT, border=6)

        # btn_row.Add(self.ask_btn, proportion=2, flag=wx.EXPAND | wx.RIGHT, border=8)
        btn_row.Add(self.create_query_btn, proportion=1, flag=wx.EXPAND)
        btn_row.AddSpacer(10)
        btn_row.Add(self.copy_btn, proportion=1, flag=wx.EXPAND)
        box.Add(btn_row, flag=wx.EXPAND)
        return box

    def _build_response_section(self):
        box = wx.BoxSizer(wx.VERTICAL)
        box.Add(self._section_title("5 — Prompt, past this in your favorite LLM"), flag=wx.BOTTOM, border=8)
        self.response_text = wx.TextCtrl(self.scroll, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP | wx.BORDER_SIMPLE, size=(-1, 200))
        box.Add(self.response_text, flag=wx.EXPAND)
        return box

    def _current_user(self):
        return self.config["users"][self.user_choice.GetSelection()]

    def _refresh_user_choice(self, select_index=None):
        """Rebuild the user dropdown from self.config['users'], keeping (or setting) a selection."""
        current_sel = self.user_choice.GetSelection()
        self.user_choice.Set(self._user_display_names())
        if not self.config["users"]:
            # No users left at all — nothing to select.
            return
        if select_index is None:
            select_index = current_sel
        select_index = max(0, min(select_index, len(self.config["users"]) - 1))
        self.user_choice.SetSelection(select_index)
        self._refresh_data_status()

    def _email_taken(self, email, ignore_index=None):
        for i, u in enumerate(self.config["users"]):
            if i == ignore_index:
                continue
            if u["email"].strip().lower() == email.strip().lower():
                return True
        return False

    def _on_add_user(self, _event):
        dlg = wx.TextEntryDialog(self, "Enter name for the new user:", "Add User")
        if dlg.ShowModal() != wx.ID_OK:
            return
        name = dlg.GetValue().strip()
        if not name:
            wx.MessageBox("Name cannot be empty.", "Error", wx.ICON_WARNING)
            return

        email_dlg = wx.TextEntryDialog(self, f"Enter Garmin email for {name}:", "Add User")
        if email_dlg.ShowModal() != wx.ID_OK:
            return
        email = email_dlg.GetValue().strip()
        if not email:
            wx.MessageBox("Email cannot be empty.", "Error", wx.ICON_WARNING)
            return
        if self._email_taken(email):
            wx.MessageBox("A user with that email already exists.", "Error", wx.ICON_WARNING)
            return

        self.config["users"].append({"name": name, "email": email})
        save_config(self.config)
        self._refresh_user_choice(select_index=len(self.config["users"]) - 1)

    def _on_edit_user(self, _event):
        if not self.config["users"]:
            wx.MessageBox("No users to edit.", "Error", wx.ICON_WARNING)
            return
        idx = self.user_choice.GetSelection()
        if idx == wx.NOT_FOUND:
            wx.MessageBox("Select a user first.", "Error", wx.ICON_WARNING)
            return
        user = self.config["users"][idx]

        dlg = wx.TextEntryDialog(self, "Edit name:", "Edit User", value=user["name"])
        if dlg.ShowModal() != wx.ID_OK:
            return
        new_name = dlg.GetValue().strip()
        if not new_name:
            wx.MessageBox("Name cannot be empty.", "Error", wx.ICON_WARNING)
            return

        email_dlg = wx.TextEntryDialog(self, "Edit Garmin email:", "Edit User", value=user["email"])
        if email_dlg.ShowModal() != wx.ID_OK:
            return
        new_email = email_dlg.GetValue().strip()
        if not new_email:
            wx.MessageBox("Email cannot be empty.", "Error", wx.ICON_WARNING)
            return
        if self._email_taken(new_email, ignore_index=idx):
            wx.MessageBox("Another user already has that email.", "Error", wx.ICON_WARNING)
            return

        old_email = user["email"]
        user["name"] = new_name
        user["email"] = new_email
        save_config(self.config)

        # If the email changed, migrate any cached Garmin data/credentials to the new key.
        if new_email != old_email:
            if hasattr(self.gm, "rename_user"):
                try:
                    self.gm.rename_user(old_email, new_email)
                except Exception:
                    pass

        self._refresh_user_choice(select_index=idx)

    def _on_remove_user(self, _event):
        if not self.config["users"]:
            wx.MessageBox("No users to remove.", "Error", wx.ICON_WARNING)
            return
        idx = self.user_choice.GetSelection()
        if idx == wx.NOT_FOUND:
            wx.MessageBox("Select a user first.", "Error", wx.ICON_WARNING)
            return
        user = self.config["users"][idx]

        confirm = wx.MessageDialog(
            self,
            f"Remove user '{user['name']}' ({user['email']})?\nThis will also delete their cached data and saved password.",
            "Confirm Removal",
            wx.YES_NO | wx.ICON_WARNING,
        )
        if confirm.ShowModal() != wx.ID_YES:
            return

        # Clean up cached data / stored credentials if the GarminManager supports it.
        if hasattr(self.gm, "delete_user_data"):
            try:
                self.gm.delete_user_data(user["email"])
            except Exception:
                pass
        elif hasattr(self.gm, "delete_password"):
            try:
                self.gm.delete_password(user["email"])
            except Exception:
                pass

        del self.config["users"][idx]
        save_config(self.config)

        if not self.config["users"]:
            # Prompt immediately for a replacement user, same as first-run flow.
            self._refresh_user_choice()
            wx.MessageBox("No users remain. Please add a new user.", "Add User", wx.ICON_INFORMATION)
            self._on_add_user(None)
            return

        new_idx = min(idx, len(self.config["users"]) - 1)
        self._refresh_user_choice(select_index=new_idx)

    def _set_status(self, text, ok=True):
        self.data_status_lbl.SetLabel(text)
        colour = wx.Colour(30, 140, 60) if ok else wx.Colour(180, 30, 30)
        self.data_status_lbl.SetForegroundColour(colour)
        self.scroll.Layout()

    def _refresh_data_status(self):
        user = self._current_user()
        cached = self.gm.get_cached_data(user["email"])
        if cached:
            self.garmin_data = cached
            fetch_date_str = cached.get("fetch_date")
            status_text = f"✓  Cached data loaded for {user['name']}"
            if fetch_date_str:
                try:
                    fetch_date = datetime.date.fromisoformat(fetch_date_str)
                    age = (datetime.date.today() - fetch_date).days
                    status_text = f"✓  Cached data ({age}d old) for {user['name']}"
                    if age >= 1:
                        self._set_status(status_text + " (stale, re-fetching...)", ok=False)
                        wx.CallAfter(self._on_fetch, None, auto=True)
                        return
                except: pass
            self._set_status(status_text, ok=True)
        else:
            self.garmin_data = None
            self._set_status(f"No cached data for {user['name']}", ok=False)

    def _on_user_changed(self, _event):
        self._refresh_data_status()

    def _on_select_all(self, _event):
        for i in range(self.checklist.GetCount()): self.checklist.Check(i, True)

    def _on_clear_all(self, _event):
        for i in range(self.checklist.GetCount()): self.checklist.Check(i, False)

    def _on_fetch(self, _event, auto=False):
        user = self._current_user()
        if not auto and self.garmin_data:
            dlg = wx.MessageDialog(self, f"Refresh fresh data from Garmin for {user['name']}?", "Confirm", wx.YES_NO | wx.ICON_QUESTION)
            if dlg.ShowModal() != wx.ID_YES: return

        password = self.gm.get_password(user["email"])
        if not password:
            pwd_dlg = wx.PasswordEntryDialog(self, f"Enter Garmin password for {user["email"]}:", "Login")
            if pwd_dlg.ShowModal() != wx.ID_OK: return
            password = pwd_dlg.GetValue()
            self.gm.save_password(user["email"], password)

        self._start_fetch(user, password)

    def _start_fetch(self, user, password):
        self.fetch_btn.Disable()
        self.fetch_gauge.Show(); self.fetch_gauge.Pulse()
        self._set_status(f"Fetching data for {user['name']}…", ok=True)
        def worker():
            try:
                data = self.gm.fetch_user_data(user["email"], password)
                wx.CallAfter(self._fetch_done, data, None, user, password)
            except Exception as exc:
                wx.CallAfter(self._fetch_done, None, str(exc), user, password)
        threading.Thread(target=worker, daemon=True).start()

    def _fetch_done(self, data, error, user=None, password=None):
        self.fetch_gauge.Hide(); self.fetch_btn.Enable()
        if error:
            self._set_status(f"Fetch failed: {error}", ok=False)
            choice = wx.MessageDialog(
                self,
                f"Login failed for {user['name']}:\n\n{error}\n\nThis often happens if your Garmin password changed.",
                "Fetch Error",
                wx.YES_NO | wx.CANCEL | wx.ICON_ERROR,
            )
            choice.SetYesNoCancelLabels("New Password", "Retry", "Cancel")
            result = choice.ShowModal()
            if result == wx.ID_YES:
                pwd_dlg = wx.PasswordEntryDialog(self, f"Enter new Garmin password for {user['name']}:", "Login")
                if pwd_dlg.ShowModal() == wx.ID_OK:
                    new_password = pwd_dlg.GetValue()
                    self.gm.save_password(user["email"], new_password)
                    self._start_fetch(user, new_password)
            elif result == wx.ID_NO:
                self._start_fetch(user, password)
            # else: Cancel — do nothing
        else:
            self.garmin_data = data
            self._set_status(f"✓  Live data fetched for {self._current_user()['name']}", ok=True)
            self._on_create_query_only(None)

    def _on_create_query_only(self, _event):
        prompt = self._get_prompt()
        if prompt: self.response_text.SetValue(prompt)

    def _get_prompt(self):
        if not self.garmin_data:
            wx.MessageBox("No Garmin data loaded.", "Error", wx.ICON_WARNING)
            return None
        checked_indices = list(self.checklist.GetCheckedItems())
        questions = [self.questions[i]["text"] for i in checked_indices]
        custom = self.custom_input.GetValue().strip()
        if custom: questions.append(custom)
        if not questions:
            wx.MessageBox("No questions selected.", "Error", wx.ICON_WARNING)
            return None
        
        try: max_len = int(self.max_len_ctrl.GetValue())
        except: max_len = DEFAULT_PROMPT_LENGTH
        try: max_act = int(self.max_act_ctrl.GetValue())
        except: max_act = DEFAULT_MAX_ACTIVITIES

        data_to_serialize = copy.deepcopy(self.garmin_data)
        if "activities" in data_to_serialize:
            data_to_serialize["activities"] = data_to_serialize["activities"][:max_act]
        json_data = json.dumps(data_to_serialize, indent=2)
        if len(json_data) > max_len:
            json_data = "... [Truncated] ...\n" + json_data[-max_len:]

        prompt = f"User Garmin Data Context:\n{json_data}\n\nQuestions:\n"
        for q in questions: prompt += f"- {q}\n"
        return prompt

    # def _on_ask(self, _event):
    #     prompt = self._get_prompt()
    #     if not prompt: return
    #     with open(QUERY_FILE, "w") as f: f.write(prompt)
    #
    #     self.ask_btn.Disable(); self.ask_btn.SetLabel("Consulting Coach…")
    #     self.response_text.SetValue("Waiting for response…")
        # def worker():
            # try:
                # connector = OllamaConnector(manage_server=True)
                # answer = connector.ask(prompt)
                # wx.CallAfter(self._ask_done, answer, None)
            # except Exception as exc: wx.CallAfter(self._ask_done, None, str(exc))
        # threading.Thread(target=worker, daemon=True).start()

    # def _ask_done(self, response, error):
    #     self.ask_btn.Enable(); self.ask_btn.SetLabel("Ask Coach")
    #     if error: self.response_text.SetValue(f"Error: {error}")
    #     else:
    #         self.response_text.SetValue(response)
    #         self.response_text.SetInsertionPoint(0)

    def _on_copy_response(self, _event):
        text = self.response_text.GetValue()
        if not text or text == "Waiting for response…": return
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(text))
            wx.TheClipboard.Close()

if __name__ == "__main__":
    app = GarminCoachApp()
    app.MainLoop()
