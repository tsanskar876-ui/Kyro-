"""Kyro Task Manager - logic only (no input/print).

Kyro Core / voice module later isi file ko import karke use karenge.
"""

import json
import os
import shutil
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DATA_FILE = os.path.join(DATA_DIR, "tasks.json")
BACKUP_FILE = os.path.join(DATA_DIR, "tasks.json.bak")
LEGACY_FILE = os.path.join(BASE_DIR, "tasks.json")  # purana version ka file

PENDING = "pending"
DONE = "done"


class TaskError(Exception):
    """Normal, user-facing error (galat id, empty task, etc.)."""


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _new_store():
    return {"version": 2, "next_id": 1, "tasks": []}


def _make_task(task_id, title, status=PENDING):
    return {
        "id": task_id,
        "title": title,
        "status": status,
        "created": _now(),
        "completed_at": _now() if status == DONE else None,
        # aage ke features ke liye jagah (abhi use nahi ho rahe)
        "due": None,
        "priority": "normal",
        "category": "general",
    }


def _migrate(data):
    """Naye format ko as-is lo, purane {pending, completed} format ko convert karo."""
    if isinstance(data, dict) and isinstance(data.get("tasks"), list) \
            and isinstance(data.get("next_id"), int):
        return data

    if isinstance(data, dict) and ("pending" in data or "completed" in data):
        store = _new_store()
        for status, key in ((PENDING, "pending"), (DONE, "completed")):
            for title in data.get(key, []):
                store["tasks"].append(_make_task(store["next_id"], str(title), status))
                store["next_id"] += 1
        return store

    raise ValueError("Unknown data format")


def _quarantine(path):
    """Kharab file ko delete nahi karte, naam badal kar side me rakh dete hain."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        os.replace(path, f"{path}.corrupt-{stamp}")
    except OSError:
        pass


def load_store():
    """Return (store, source_path). Order: main file -> backup -> purana file."""
    for path in (DATA_FILE, BACKUP_FILE, LEGACY_FILE):
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                return _migrate(json.load(f)), path
        except (OSError, ValueError, TypeError):
            if path == DATA_FILE:
                _quarantine(path)
    return _new_store(), None


def save_store(store):
    """Crash-safe save: pehle backup, phir temp file, phir atomic replace."""
    os.makedirs(DATA_DIR, exist_ok=True)

    if os.path.exists(DATA_FILE):
        try:
            shutil.copy2(DATA_FILE, BACKUP_FILE)
        except OSError:
            pass

    tmp_path = DATA_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=4, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, DATA_FILE)  # beech me light gayi to bhi purani file safe


class TaskManager:
    def __init__(self):
        self.store, source = load_store()
        self.notice = None
        if source == BACKUP_FILE:
            self.notice = "Main file kharab thi, backup se tasks load kiye gaye."
        elif source == LEGACY_FILE:
            self.notice = "Purani tasks.json se tasks import kiye gaye."

    # ---------- helpers ----------
    def _save(self):
        save_store(self.store)

    def _find(self, task_id):
        for task in self.store["tasks"]:
            if task["id"] == task_id:
                return task
        raise TaskError(f"Task #{task_id} nahi mila.")

    @staticmethod
    def _clean_title(title):
        clean = " ".join(str(title).split())
        if not clean:
            raise TaskError("Task khaali nahi ho sakta.")
        return clean

    # ---------- actions ----------
    def add(self, title):
        task = _make_task(self.store["next_id"], self._clean_title(title))
        self.store["next_id"] += 1
        self.store["tasks"].append(task)
        self._save()
        return dict(task)

    def complete(self, task_id):
        task = self._find(task_id)
        if task["status"] == DONE:
            raise TaskError(f"Task #{task_id} pehle se completed hai.")
        task["status"] = DONE
        task["completed_at"] = _now()
        self._save()
        return dict(task)

    def reopen(self, task_id):
        task = self._find(task_id)
        if task["status"] == PENDING:
            raise TaskError(f"Task #{task_id} pehle se pending hai.")
        task["status"] = PENDING
        task["completed_at"] = None
        self._save()
        return dict(task)

    def edit(self, task_id, new_title):
        task = self._find(task_id)
        task["title"] = self._clean_title(new_title)
        self._save()
        return dict(task)

    def delete(self, task_id):
        task = self._find(task_id)
        self.store["tasks"].remove(task)
        self._save()
        return dict(task)

    def clear_completed(self):
        before = len(self.store["tasks"])
        self.store["tasks"] = [t for t in self.store["tasks"] if t["status"] != DONE]
        removed = before - len(self.store["tasks"])
        if removed:
            self._save()
        return removed

    # ---------- queries ----------
    def list(self, status=None):
        return [dict(t) for t in self.store["tasks"]
                if status is None or t["status"] == status]

    def search(self, text):
        needle = text.strip().lower()
        if not needle:
            raise TaskError("Search ke liye kuch likho.")
        return [dict(t) for t in self.store["tasks"] if needle in t["title"].lower()]
