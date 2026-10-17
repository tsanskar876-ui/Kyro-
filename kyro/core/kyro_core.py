"""Kyro Core - Kyro ka engine room.

Is file me SIRF "dhaancha" hai. Koi bhi kaam (task, app kholna, bolna, sunna)
yahan hard-code nahi hai. Sab kuch plug-in ki tarah jud-ta hai:

    MODULE  -> kaam karne wali cheez (task manager, app launcher, ...)
               file rakho  modules/  folder me, class bano KyroModule se.
    ENGINE  -> input/output/sunna/bolna ka tareeka
               file rakho  engines/  folder me, class bano InputEngine /
               OutputEngine / ListenEngine / SpeakEngine se.

Core ko kabhi badalna nahi padega - bas naya file folder me daalo.

Ye file akeli run nahi hoti. Chalane ke liye:  python3 core/kyro_brain.py

Padhne ka order (upar se neeche):
    1. Config + Logger          (settings aur diary)
    2. EventBus                 (modules ke beech message board)
    3. Result / Command / Router(command samajhna aur dhoondhna)
    4. Engines                  (input / output / listen / speak)
    5. KyroModule + ModuleManager (plug-in system)
    6. KyroCore                 (sab ko jodne wala boss)
"""

from __future__ import annotations

import difflib
import importlib.util
import inspect
import json
import logging
import os
import sys
import time
from collections import deque
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from typing import Any, Callable, Dict, List, Optional, Tuple

__version__ = "1.0.0"

# ----------------------------------------------------------------------------
# Folder ke raste. core/ ke ek level upar = kyro ka root folder.
# ----------------------------------------------------------------------------
CORE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CORE_DIR)

# Root ko import path me daalte hain taaki modules/ ke andar se
# "import task_manager" jaisa purana code seedha chal sake.
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


# ============================================================================
# 0. Errors
# ============================================================================
class KyroError(Exception):
    """Kyro ke andar ki normal samasya (galat engine ka naam, conflict, ...)."""


class CommandError(KyroError):
    """User ko dikhane layak error. Message seedha user ko dikhta hai.

    Module ka handler jab user ki galti pakde (galat id, khaali text) to
    ye raise kare: raise CommandError("Task #5 nahi mila.")
    """


# ============================================================================
# 1. Config + Logger
# ============================================================================
DEFAULT_CONFIG: Dict[str, Any] = {
    "version": 1,
    "assistant_name": "Kyro",
    "debug": False,
    "speak_replies": True,       # SPEAK engine active ho to jawab bolna
    "history_size": 50,
    "engines": {                 # kaun sa engine active rahe (None = koi nahi)
        "input": "console",
        "output": "console",
        "listen": None,
        "speak": None,
    },
    "modules": {"disabled": []},  # band kiye hue modules ke naam
    "module_settings": {},        # har module ki apni settings yahan
}


def _merge(base: Dict[str, Any], extra: Dict[str, Any]) -> None:
    """extra ki values ko base me daal do (andar ke dict bhi merge hote hain)."""
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value


class Config:
    """JSON settings file. Dotted naam se access: config.get("engines.output")."""

    def __init__(self, path: str, log: Optional[logging.Logger] = None):
        self.path = path
        self.log = log
        self.data: Dict[str, Any] = json.loads(json.dumps(DEFAULT_CONFIG))
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
        except ValueError:
            self._quarantine()
            return
        except OSError:
            return
        if isinstance(loaded, dict):
            _merge(self.data, loaded)

    def _quarantine(self) -> None:
        """Kharab file delete nahi karte, naam badal kar side me rakh dete hain."""
        stamp = time.strftime("%Y%m%d-%H%M%S")
        try:
            os.replace(self.path, f"{self.path}.corrupt-{stamp}")
        except OSError:
            pass

    def get(self, key: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in key.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return default
        return node

    def set(self, key: str, value: Any, save: bool = True) -> None:
        parts = key.split(".")
        node = self.data
        for part in parts[:-1]:
            nxt = node.get(part)
            if not isinstance(nxt, dict):
                nxt = node[part] = {}
            node = nxt
        node[parts[-1]] = value
        if save:
            self.save()

    def save(self) -> bool:
        """Crash-safe save: temp file me likho, phir ek jhatke me replace."""
        tmp = self.path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
            return True
        except OSError as e:
            if self.log:
                self.log.error("Config save nahi hua: %s", e)
            return False


def make_logger(log_file: str, debug: bool = False) -> logging.Logger:
    """Diary: data/kyro.log me likhta hai (500KB se bada ho to purani rotate)."""
    logger = logging.getLogger("kyro")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    if not logger.handlers:
        try:
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            handler: logging.Handler = RotatingFileHandler(
                log_file, maxBytes=500_000, backupCount=2, encoding="utf-8"
            )
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
            )
        except OSError:
            handler = logging.NullHandler()
        logger.addHandler(handler)
        if debug:
            logger.addHandler(logging.StreamHandler(sys.stderr))
    return logger


# ============================================================================
# 2. EventBus - modules ek dusre ko import kiye bina baat kar sakte hain
# ============================================================================
class EventBus:
    """Message board. Koi "task.added" chillata hai, jise sunna ho wo sun leta hai.

        bus.subscribe("task.added", my_function)
        bus.emit("task.added", task={...})

    Callback ka signature:  my_function(event_name, data_dict)
    "*" par subscribe karoge to har event milega.
    """

    def __init__(self, log: logging.Logger):
        self._subs: Dict[str, List[Tuple[Callable, Optional[str]]]] = {}
        self._log = log

    def subscribe(self, event: str, callback: Callable, owner: Optional[str] = None) -> None:
        self._subs.setdefault(event, []).append((callback, owner))

    def unsubscribe_owner(self, owner: str) -> None:
        for event in list(self._subs):
            self._subs[event] = [(cb, o) for cb, o in self._subs[event] if o != owner]

    def emit(self, event: str, **data: Any) -> None:
        for key in (event, "*"):
            for callback, _owner in list(self._subs.get(key, [])):
                try:
                    callback(event, data)
                except Exception:  # ek ka error baaki ko na roke
                    self._log.exception("Event '%s' ka listener fail hua", event)


# ============================================================================
# 3. Result / Command / Router
# ============================================================================
@dataclass
class Result:
    """Har command ka nateeja.

    ok      - kaam hua ya nahi
    message - screen par dikhane wala text
    spoken  - bolne ke liye chhota version (None = message hi bolo)
    speak   - False ho to bolna hi nahi
    data    - kisi aur code ke liye (GUI/modules) extra cheez
    """

    ok: bool = True
    message: str = ""
    spoken: Optional[str] = None
    speak: bool = True
    data: Any = None


@dataclass
class CommandContext:
    """Handler ko milne wali jaankari."""

    core: "KyroCore"
    raw: str            # user ne jo poora likha
    command: str        # jo command match hua (jaise "task add")
    args: str = ""      # command ke baad ka hissa (jaise "doodh lao")
    source: str = "text"

    @property
    def words(self) -> List[str]:
        return self.args.split()

    def need(self, usage: str) -> str:
        """args khaali ho to CommandError, warna args wapas do."""
        if not self.args.strip():
            raise CommandError(f"Kuch likhna bhool gaye. Aise likho: {usage}")
        return self.args.strip()


@dataclass
class Command:
    name: str                       # pehla (main) naam
    phrases: Tuple[str, ...]        # saare naam (aliases ke saath), lowercase
    handler: Callable[[CommandContext], Any]
    help: str = ""
    usage: str = ""
    owner: str = "core"
    hidden: bool = False


def _norm(word: str) -> str:
    return word.lower().strip(".,!?;:")


class CommandRouter:
    """Text ko command se milata hai. Sabse LAMBA phrase pehle match hota hai.

    "task add doodh lao"  ->  phrase ("task","add"), args "doodh lao"
    """

    def __init__(self) -> None:
        self._table: Dict[Tuple[str, ...], Command] = {}
        self._max_len = 1

    def add(self, command: Command) -> None:
        keys = [tuple(_norm(w) for w in p.split() if _norm(w)) for p in command.phrases]
        for key in keys:
            if not key:
                raise KyroError(f"Command '{command.name}' me khaali phrase hai.")
            old = self._table.get(key)
            if old is not None:
                raise KyroError(
                    f"'{' '.join(key)}' pehle se '{old.owner}' ke paas hai "
                    f"(naya: '{command.owner}')."
                )
        for key in keys:
            self._table[key] = command
        self._max_len = max([self._max_len] + [len(k) for k in keys])

    def remove_owner(self, owner: str) -> None:
        self._table = {k: c for k, c in self._table.items() if c.owner != owner}
        self._max_len = max([1] + [len(k) for k in self._table])

    def match(self, text: str) -> Optional[Tuple[Command, str]]:
        words = text.split()
        norm = [_norm(w) for w in words]
        for n in range(min(len(words), self._max_len), 0, -1):
            command = self._table.get(tuple(norm[:n]))
            if command is not None:
                return command, " ".join(words[n:])
        return None

    def suggest(self, text: str, limit: int = 3) -> List[str]:
        """Galat likhne par milte-julte commands (difflib se)."""
        phrases = [" ".join(k) for k, c in self._table.items() if not c.hidden]
        words = [_norm(w) for w in text.split()]
        guess = " ".join(words[: self._max_len])
        found = difflib.get_close_matches(guess, phrases, n=limit, cutoff=0.6)
        if not found and words:
            found = difflib.get_close_matches(words[0], phrases, n=limit, cutoff=0.6)
        return found

    def commands(self) -> List[Command]:
        unique: Dict[int, Command] = {}
        for command in self._table.values():
            unique[id(command)] = command
        return sorted(unique.values(), key=lambda c: (c.owner != "core", c.owner, c.name))


# ============================================================================
# 4. Engines
# ============================================================================
INPUT, OUTPUT, LISTEN, SPEAK = "input", "output", "listen", "speak"
ENGINE_KINDS = (INPUT, OUTPUT, LISTEN, SPEAK)


class Engine:
    """Sab engines ki base class.

    Naya engine banane ke liye: neeche wali 4 me se ek se inherit karo,
    `name` do, aur ek hi method bharo. Baaki Core sambhal lega.
    """

    kind: str = ""
    name: str = ""            # khaali = ye base class hai, register nahi hogi
    description: str = ""

    def start(self, core: "KyroCore") -> None:
        """Activate hone par ek baar bulaya jaata hai (mic kholna, etc.)."""

    def stop(self) -> None:
        """Band hone par bulaya jaata hai."""

    def is_available(self) -> bool:
        """False ho to activate nahi hoga (jaise mic/library nahi mili)."""
        return True


class InputEngine(Engine):
    """Typed input. read() text de, ya None (input khatam)."""

    kind = INPUT

    def read(self, prompt: str = "") -> Optional[str]:
        raise NotImplementedError


class OutputEngine(Engine):
    """Screen par likhna (ya GUI window me)."""

    kind = OUTPUT

    def write(self, text: str) -> None:
        raise NotImplementedError


class ListenEngine(Engine):
    """AWAAZ -> TEXT ka slot (mic wala engine baad me yahan judega)."""

    kind = LISTEN

    def listen(self, timeout: Optional[float] = None) -> Optional[str]:
        """Text do. "" = kuch nahi suna. None = sunna band."""
        raise NotImplementedError


class SpeakEngine(Engine):
    """TEXT -> AWAAZ ka slot (bolne wala engine baad me yahan judega)."""

    kind = SPEAK

    def speak(self, text: str) -> None:
        raise NotImplementedError

    def stop_speaking(self) -> None:
        """Beech me chup karane ke liye (optional)."""


class ConsoleInput(InputEngine):
    name = "console"
    description = "Keyboard se type karna"

    def read(self, prompt: str = "") -> Optional[str]:
        try:
            return input(prompt)
        except EOFError:       # Ctrl+D -> band
            return None
        except KeyboardInterrupt:  # Ctrl+C -> sirf line cancel
            print()
            return ""


class ConsoleOutput(OutputEngine):
    name = "console"
    description = "Terminal screen par print karna"

    def write(self, text: str) -> None:
        print(text)


class EngineRegistry:
    """Har kind ke engines ki list + kaun sa active hai."""

    def __init__(self, core: "KyroCore"):
        self._core = core
        self._engines: Dict[str, Dict[str, Engine]] = {k: {} for k in ENGINE_KINDS}
        self._active: Dict[str, Optional[Engine]] = {k: None for k in ENGINE_KINDS}
        self.failed: Dict[str, str] = {}

    # ---- register / unregister -------------------------------------------
    def register(self, engine: Engine, activate: bool = False) -> None:
        if not isinstance(engine, Engine):
            raise KyroError("Engine class, Engine se inherit honi chahiye.")
        if engine.kind not in ENGINE_KINDS:
            raise KyroError(f"Engine kind galat: '{engine.kind}'. Sahi: {ENGINE_KINDS}")
        if not engine.name:
            raise KyroError("Engine ka `name` set nahi hai.")
        if engine.name in self._engines[engine.kind]:
            raise KyroError(f"{engine.kind} engine '{engine.name}' pehle se hai.")
        self._engines[engine.kind][engine.name] = engine
        if activate:
            self.activate(engine.kind, engine.name)

    def unregister(self, kind: str, name: str) -> None:
        engine = self._engines.get(kind, {}).get(name)
        if engine is None:
            return
        if self._active[kind] is engine:
            self.deactivate(kind)
        del self._engines[kind][name]

    # ---- activate / deactivate -------------------------------------------
    def activate(self, kind: str, name: str) -> None:
        if kind not in ENGINE_KINDS:
            raise KyroError(f"Kind galat: '{kind}'. Sahi: {', '.join(ENGINE_KINDS)}")
        engine = self._engines[kind].get(name)
        if engine is None:
            have = ", ".join(self.names(kind)) or "koi nahi"
            raise KyroError(f"{kind} engine '{name}' nahi mila. Mile hue: {have}")
        if self._active[kind] is engine:
            return
        try:
            usable = engine.is_available()
        except Exception as e:
            raise KyroError(f"'{name}' ki jaanch fail: {e}") from e
        if not usable:
            raise KyroError(f"{kind} engine '{name}' abhi available nahi hai.")
        try:
            engine.start(self._core)
        except Exception as e:
            raise KyroError(f"'{name}' start nahi hua: {e}") from e
        old = self._active[kind]
        self._active[kind] = engine
        if old is not None:
            self._safe_stop(old)
        self._core.events.emit("engine.activated", kind=kind, name=name)

    def deactivate(self, kind: str) -> None:
        old = self._active.get(kind)
        if old is not None:
            self._active[kind] = None
            self._safe_stop(old)
            self._core.events.emit("engine.deactivated", kind=kind, name=old.name)

    def _safe_stop(self, engine: Engine) -> None:
        try:
            engine.stop()
        except Exception:
            self._core.log.exception("Engine '%s' stop me fail", engine.name)

    def stop_all(self) -> None:
        for kind in ENGINE_KINDS:
            self.deactivate(kind)

    # ---- jaankari ----------------------------------------------------------
    def active(self, kind: str) -> Optional[Engine]:
        return self._active.get(kind)

    def names(self, kind: str) -> List[str]:
        return sorted(self._engines.get(kind, {}))

    def get(self, kind: str, name: str) -> Optional[Engine]:
        return self._engines.get(kind, {}).get(name)

    # ---- engines/ folder se auto-load -------------------------------------
    def load_folder(self, folder: str) -> None:
        for path in _py_files(folder):
            fname = os.path.basename(path)
            try:
                pymod = _import_file(path, "kyro_engines")
            except KyroError as e:
                self.failed[fname] = str(e)
                self._core.log.error("Engine file %s: %s", fname, e)
                continue
            for cls in _classes_of(pymod, Engine):
                if not cls.name:
                    continue  # base/abstract class
                try:
                    self.register(cls())
                except Exception as e:
                    self.failed[f"{fname}:{cls.__name__}"] = str(e)
                    self._core.log.error("Engine %s register fail: %s", cls.__name__, e)


# ============================================================================
# 5. Plug-in loading helpers + KyroModule + ModuleManager
# ============================================================================
def _py_files(folder: str) -> List[str]:
    """folder ki .py files. "_" se shuru hone wali (template) chhod di jaati hain."""
    if not os.path.isdir(folder):
        return []
    return [
        os.path.join(folder, n)
        for n in sorted(os.listdir(folder))
        if n.endswith(".py") and not n.startswith("_")
    ]


def _import_file(path: str, prefix: str):
    """Kisi bhi .py file ko seedha path se import karo (taaza copy)."""
    mod_name = f"{prefix}.{os.path.splitext(os.path.basename(path))[0]}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise KyroError(f"'{os.path.basename(path)}' import nahi ho sakti.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    try:
        spec.loader.exec_module(module)
    except (Exception, SystemExit) as e:   # plug-in ki galti Kyro ko na girae
        sys.modules.pop(mod_name, None)
        raise KyroError(f"import fail: {type(e).__name__}: {e}") from e
    return module


def _classes_of(pymod, base: type) -> List[type]:
    """pymod me jo classes `base` se bani hain aur isi file me likhi gayi hain."""
    return [
        cls
        for _name, cls in inspect.getmembers(pymod, inspect.isclass)
        if issubclass(cls, base) and cls.__module__ == pymod.__name__
    ]


class KyroModule:
    """Har module ki base class. Naya module banane ka tareeka:

        from core.kyro_core import KyroModule

        class Hello(KyroModule):
            name = "hello"
            description = "Namaste bolta hai"

            def on_load(self):
                self.add_command(["hello", "namaste"], self.cmd_hello,
                                 help="Namaste bolo", usage="hello")

            def cmd_hello(self, ctx):
                return "Namaste!"

    File ko modules/ folder me rakho. Bas.
    """

    name: str = ""            # zaroori: unique naam
    version: str = "1.0"
    description: str = ""
    depends: Tuple[str, ...] = ()   # in modules ke baad hi load hoga

    def __init__(self, core: "KyroCore"):
        self.core = core
        self.log = core.log.getChild(self.name)
        self.commands: List[Command] = []

    # ---- jinhe module override karta hai --------------------------------
    def on_load(self) -> None:
        """Load hone par. Yahan commands/events register karo."""

    def on_unload(self) -> None:
        """Hatne par. Files band karo, threads roko, etc."""

    # ---- madad ke tools ----------------------------------------------------
    def add_command(
        self,
        phrases,
        handler: Callable[[CommandContext], Any],
        help: str = "",
        usage: str = "",
        hidden: bool = False,
    ) -> None:
        if isinstance(phrases, str):
            phrases = [phrases]
        phrases = [p.lower().strip() for p in phrases]
        command = Command(
            name=phrases[0],
            phrases=tuple(phrases),
            handler=handler,
            help=help,
            usage=usage or phrases[0],
            owner=self.name,
            hidden=hidden,
        )
        self.core.router.add(command)
        self.commands.append(command)

    def subscribe(self, event: str, callback: Callable) -> None:
        self.core.events.subscribe(event, callback, owner=self.name)

    def emit(self, event: str, **data: Any) -> None:
        self.core.events.emit(event, **data)

    def say(self, text: str, speak: Optional[bool] = None) -> None:
        self.core.say(text, speak=speak)

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self.core.config.get(f"module_settings.{self.name}.{key}", default)

    def set_setting(self, key: str, value: Any) -> None:
        self.core.config.set(f"module_settings.{self.name}.{key}", value)


class ModuleManager:
    """modules/ folder ko padhta hai aur modules load/unload/reload karta hai."""

    def __init__(self, core: "KyroCore"):
        self.core = core
        self._loaded: Dict[str, KyroModule] = {}
        self._files: Dict[str, str] = {}
        self._available: Dict[str, Tuple[type, str]] = {}
        self.failed: Dict[str, str] = {}

    # ---- jaankari ----------------------------------------------------------
    def names(self) -> List[str]:
        return list(self._loaded)

    def get(self, name: str) -> Optional[KyroModule]:
        return self._loaded.get(name)

    def is_loaded(self, name: str) -> bool:
        return name in self._loaded

    def disabled_names(self) -> List[str]:
        return list(self.core.config.get("modules.disabled", []))

    # ---- sab load karna ----------------------------------------------------
    def load_all(self) -> None:
        self.failed.clear()
        found: List[Tuple[type, str]] = []
        seen = set()

        for path in _py_files(self.core.modules_dir):
            fname = os.path.basename(path)
            try:
                pymod = _import_file(path, "kyro_modules")
            except KyroError as e:
                self.failed[fname] = str(e)
                self.core.log.error("Module file %s: %s", fname, e)
                continue
            for cls in _classes_of(pymod, KyroModule):
                if not cls.name:
                    self.failed[f"{fname}:{cls.__name__}"] = "`name` set nahi hai"
                    continue
                if cls.name in seen:
                    self.failed[cls.name] = f"naam '{cls.name}' dobara use hua ({fname})"
                    continue
                seen.add(cls.name)
                found.append((cls, path))
                self._available[cls.name] = (cls, path)

        disabled = set(self.disabled_names())
        pending = [(c, p) for c, p in found if c.name not in disabled]

        progress = True
        while pending and progress:   # depends wale baad me, jab unke dost load ho jayein
            progress = False
            for item in list(pending):
                cls, path = item
                if all(d in self._loaded for d in cls.depends):
                    pending.remove(item)
                    progress = True
                    self._load_class(cls, path)

        for cls, _path in pending:
            missing = [d for d in cls.depends if d not in self._loaded]
            self.failed[cls.name] = f"in modules ki zaroorat hai: {', '.join(missing)}"

    def _load_class(self, cls: type, path: str) -> bool:
        name = cls.name
        try:
            module = cls(self.core)
            module.on_load()
        except Exception as e:
            self.core.log.exception("Module '%s' load fail", name)
            self.failed[name] = f"{type(e).__name__}: {e}"
            self._cleanup(name)       # aadhe register hue commands hata do
            return False
        self._loaded[name] = module
        self._files[name] = path
        self.failed.pop(name, None)
        self.core.log.info("Module loaded: %s v%s", name, module.version)
        self.core.events.emit("module.loaded", name=name)
        return True

    def _cleanup(self, name: str) -> None:
        self.core.router.remove_owner(name)
        self.core.events.unsubscribe_owner(name)

    # ---- ek module ----------------------------------------------------------
    def unload(self, name: str, force: bool = False) -> None:
        module = self._loaded.get(name)
        if module is None:
            raise KyroError(f"Module '{name}' loaded nahi hai.")
        if not force:
            users = [n for n, m in self._loaded.items() if name in m.depends]
            if users:
                raise KyroError(f"Pehle inhe band karo: {', '.join(users)} (ye '{name}' use karte hain)")
        try:
            module.on_unload()
        except Exception:
            self.core.log.exception("Module '%s' on_unload fail", name)
        del self._loaded[name]
        self._cleanup(name)
        self.core.events.emit("module.unloaded", name=name)

    def reload(self, name: str) -> None:
        """File dobara padho (code badla ho to naya chalega)."""
        if name not in self._loaded:
            raise KyroError(f"Module '{name}' loaded nahi hai.")
        path = self._files[name]
        self.unload(name)
        pymod = _import_file(path, "kyro_modules")
        cls = next((c for c in _classes_of(pymod, KyroModule) if c.name == name), None)
        if cls is None:
            raise KyroError(f"Reload ke baad '{name}' class file me nahi mili.")
        self._available[name] = (cls, path)
        if not self._load_class(cls, path):
            raise KyroError(self.failed.get(name, "load fail"))

    def enable(self, name: str) -> None:
        if name in self._loaded:
            raise KyroError(f"Module '{name}' pehle se chal raha hai.")
        if name not in self._available:
            raise KyroError(f"Module '{name}' nahi mila. 'modules' likh kar dekho.")
        cls, path = self._available[name]
        missing = [d for d in cls.depends if d not in self._loaded]
        if missing:
            raise KyroError(f"Pehle ye chalao: {', '.join(missing)}")
        if not self._load_class(cls, path):
            raise KyroError(self.failed.get(name, "load fail"))

    def unload_all(self) -> None:
        for name in reversed(list(self._loaded)):
            try:
                self.unload(name, force=True)
            except KyroError:
                pass

    def describe(self) -> List[KyroModule]:
        return list(self._loaded.values())


# ============================================================================
# 6. KyroCore - boss
# ============================================================================
class KyroCore:
    """Sab ko jodta hai. Brain/GUI isi ko import karke use karte hain.

        core = KyroCore()
        core.start()
        core.handle("task add doodh lao")   # chalao + screen par dikhao
        core.stop()
    """

    def __init__(self, root_dir: str = ROOT_DIR):
        self.root_dir = root_dir
        self.data_dir = os.path.join(root_dir, "data")
        self.modules_dir = os.path.join(root_dir, "modules")
        self.engines_dir = os.path.join(root_dir, "engines")

        self.config = Config(os.path.join(self.data_dir, "kyro_config.json"))
        self.log = make_logger(
            os.path.join(self.data_dir, "kyro.log"), bool(self.config.get("debug"))
        )
        self.config.log = self.log

        self.events = EventBus(self.log)
        self.router = CommandRouter()
        self.engines = EngineRegistry(self)
        self.modules = ModuleManager(self)

        self.running = False
        self.started_at: Optional[float] = None
        self.history: deque = deque(maxlen=int(self.config.get("history_size", 50)))

        self.engines.register(ConsoleInput())
        self.engines.register(ConsoleOutput())
        self._register_builtin_commands()

    # ---- start / stop --------------------------------------------------------
    def start(self) -> None:
        if self.running:
            return
        self.engines.load_folder(self.engines_dir)
        self._apply_engine_config()
        self.modules.load_all()
        if not os.path.exists(self.config.path):
            self.config.save()
        self.running = True
        self.started_at = time.monotonic()
        self.log.info("Kyro Core %s start", __version__)
        self.events.emit("core.started")

    def stop(self) -> None:
        if not self.running and self.started_at is None:
            return
        self.running = False
        self.modules.unload_all()
        self.engines.stop_all()
        self.config.save()
        self.log.info("Kyro Core stop")
        self.events.emit("core.stopped")
        self.started_at = None

    def _apply_engine_config(self) -> None:
        for kind in ENGINE_KINDS:
            wanted = self.config.get(f"engines.{kind}")
            default = "console" if kind in (INPUT, OUTPUT) else None
            for name in (wanted, default):
                if not name:
                    continue
                try:
                    self.engines.activate(kind, name)
                    break
                except KyroError as e:
                    self.log.warning("Engine %s/%s active nahi hua: %s", kind, name, e)

    # ---- input / output ---------------------------------------------------------
    def say(self, text: str, speak: Optional[bool] = None, spoken: Optional[str] = None) -> None:
        """Jawab do: OUTPUT engine par dikhao, SPEAK engine active ho to bolo bhi."""
        if not text:
            return
        out = self.engines.active(OUTPUT)
        try:
            if out is not None:
                out.write(text)
            else:
                print(text)
        except Exception:
            self.log.exception("Output engine fail")
        self.events.emit("core.say", text=text)

        if speak is None:
            speak = bool(self.config.get("speak_replies", True))
        talker = self.engines.active(SPEAK)
        if speak and talker is not None:
            try:
                talker.speak(spoken or text)
            except Exception:
                self.log.exception("Speak engine fail")

    def hear(self, prompt: str = "") -> Optional[str]:
        """User se agla command lo. LISTEN engine active ho to mic se, warna keyboard se.

        None = input khatam (loop band kar do).
        """
        listener = self.engines.active(LISTEN)
        try:
            if listener is not None:
                return listener.listen()
            reader = self.engines.active(INPUT)
            if reader is not None:
                return reader.read(prompt)
            return input(prompt)
        except EOFError:
            return None

    # ---- command chalana -----------------------------------------------------
    def process(self, text: str, source: str = "text") -> Result:
        """Text samjho aur command chalao. Kuch print nahi karta, Result lautata hai."""
        text = (text or "").strip()
        if not text:
            return Result(True, "", speak=False)

        self.history.append(text)
        self.events.emit("command.received", text=text, source=source)

        found = self.router.match(text)
        if found is None:
            self.events.emit("command.unknown", text=text)
            hint = self.router.suggest(text)
            msg = "Samajh nahi aaya."
            if hint:
                msg += " Shayad aapka matlab: " + ", ".join(hint)
            msg += "  ('help' likho)"
            return Result(False, msg)

        command, args = found
        ctx = CommandContext(self, text, command.name, args, source)
        try:
            result = self._to_result(command.handler(ctx))
        except KyroError as e:          # CommandError bhi yahin aata hai (uska bhai)
            result = Result(False, str(e))
        except Exception as e:
            self.log.exception("Command '%s' me error", command.name)
            self.events.emit("command.error", command=command.name, error=str(e))
            result = Result(False, f"'{command.name}' me gadbad ho gayi: {type(e).__name__}: {e}")

        self.events.emit("command.done", command=command.name, ok=result.ok)
        return result

    @staticmethod
    def _to_result(value: Any) -> Result:
        if value is None:
            return Result(True, "", speak=False)
        if isinstance(value, Result):
            return value
        return Result(True, str(value))

    def handle(self, text: str, source: str = "text") -> Result:
        """process() + jawab screen par dikhao/bolo. Brain isi ko bulata hai."""
        result = self.process(text, source)
        if result.message:
            self.say(result.message, speak=result.speak, spoken=result.spoken)
        return result

    # ---- built-in commands (core ke apne) ---------------------------------------
    def _builtin(self, phrases, handler, help, usage="") -> None:
        phrases = [p.lower() for p in phrases]
        self.router.add(
            Command(phrases[0], tuple(phrases), handler, help, usage or phrases[0], "core")
        )

    def _register_builtin_commands(self) -> None:
        b = self._builtin
        b(["help", "madad"], self._cmd_help, "Saare commands ya ek command ki madad", "help [command]")
        b(["status"], self._cmd_status, "Kyro ki halat")
        b(["modules", "module list"], self._cmd_modules, "Modules ki list")
        b(["module reload", "reload"], self._cmd_reload, "Module dobara load karo", "module reload <naam>")
        b(["module off"], self._cmd_module_off, "Module band karo (yaad rahega)", "module off <naam>")
        b(["module on"], self._cmd_module_on, "Module chalu karo", "module on <naam>")
        b(["engines", "engine list"], self._cmd_engines, "Engines ki list")
        b(["engine use"], self._cmd_engine_use, "Engine badlo", "engine use <input|output|listen|speak> <naam>")
        b(["engine off"], self._cmd_engine_off, "Engine band karo", "engine off <kind>")
        b(["history"], self._cmd_history, "Pichhle commands")
        b(["exit", "quit", "bye", "band karo"], self._cmd_exit, "Kyro band karo")

    def _cmd_help(self, ctx: CommandContext) -> Result:
        if ctx.args:
            found = self.router.match(ctx.args)
            if found is None:
                raise CommandError(f"'{ctx.args}' naam ka koi command nahi.")
            c = found[0]
            lines = [f"{c.name}   (module: {c.owner})", f"  {c.help or '(koi madad nahi likhi)'}",
                     f"  Use: {c.usage}"]
            if len(c.phrases) > 1:
                lines.append("  Dusre naam: " + ", ".join(c.phrases[1:]))
            return Result(True, "\n".join(lines), speak=False)

        lines = [f"{self.config.get('assistant_name', 'Kyro')} {__version__} - commands:"]
        owner = None
        for c in self.router.commands():
            if c.hidden:
                continue
            if c.owner != owner:
                owner = c.owner
                lines.append(f"\n[{owner}]")
            lines.append(f"  {c.usage:<36} {c.help}")
        lines.append("\nEk command ki detail: help <command>")
        return Result(True, "\n".join(lines), spoken="Commands screen par dikha diye.")

    def _cmd_status(self, ctx: CommandContext) -> Result:
        up = int(time.monotonic() - (self.started_at or time.monotonic()))
        active = {k: (self.engines.active(k).name if self.engines.active(k) else "-") for k in ENGINE_KINDS}
        lines = [
            f"Kyro Core {__version__}",
            f"Chalu hue: {up // 60} min {up % 60} sec",
            f"Modules loaded: {len(self.modules.names())}   fail: {len(self.modules.failed)}",
            "Engines: " + ", ".join(f"{k}={v}" for k, v in active.items()),
            f"Commands: {len(self.router.commands())}",
        ]
        return Result(True, "\n".join(lines), speak=False)

    def _cmd_modules(self, ctx: CommandContext) -> Result:
        lines = ["Loaded modules:"]
        for m in self.modules.describe():
            lines.append(f"  {m.name} v{m.version} - {m.description}")
        if not self.modules.names():
            lines.append("  (koi nahi)")
        if self.modules.failed:
            lines.append("Fail hue:")
            for key, why in self.modules.failed.items():
                lines.append(f"  {key}: {why}")
        off = self.modules.disabled_names()
        if off:
            lines.append("Band (disabled): " + ", ".join(off))
        return Result(True, "\n".join(lines), spoken=f"{len(self.modules.names())} modules chal rahe hain.")

    def _cmd_reload(self, ctx: CommandContext) -> Result:
        name = ctx.need("module reload <naam>").split()[0].lower()
        self.modules.reload(name)
        return Result(True, f"Module '{name}' dobara load ho gaya.")

    def _cmd_module_off(self, ctx: CommandContext) -> Result:
        name = ctx.need("module off <naam>").split()[0].lower()
        self.modules.unload(name)
        off = self.modules.disabled_names()
        if name not in off:
            self.config.set("modules.disabled", off + [name])
        return Result(True, f"Module '{name}' band. (Wapas: module on {name})")

    def _cmd_module_on(self, ctx: CommandContext) -> Result:
        name = ctx.need("module on <naam>").split()[0].lower()
        self.modules.enable(name)
        self.config.set("modules.disabled", [n for n in self.modules.disabled_names() if n != name])
        return Result(True, f"Module '{name}' chalu ho gaya.")

    def _cmd_engines(self, ctx: CommandContext) -> Result:
        lines = []
        for kind in ENGINE_KINDS:
            act = self.engines.active(kind)
            names = [("*" if act is not None and act.name == n else "") + n for n in self.engines.names(kind)]
            lines.append(f"{kind:<7}: " + (", ".join(names) if names else "(koi nahi)"))
        lines.append("(* = abhi active)")
        for key, why in self.engines.failed.items():
            lines.append(f"fail {key}: {why}")
        return Result(True, "\n".join(lines), speak=False)

    def _cmd_engine_use(self, ctx: CommandContext) -> Result:
        words = ctx.words
        if len(words) != 2:
            raise CommandError("Aise likho: engine use <input|output|listen|speak> <naam>")
        kind, name = words[0].lower(), words[1].lower()
        self.engines.activate(kind, name)
        self.config.set(f"engines.{kind}", name)
        return Result(True, f"{kind} engine ab '{name}' hai.")

    def _cmd_engine_off(self, ctx: CommandContext) -> Result:
        kind = ctx.need("engine off <kind>").split()[0].lower()
        if kind not in ENGINE_KINDS:
            raise CommandError(f"Kind galat. Sahi: {', '.join(ENGINE_KINDS)}")
        if kind in (INPUT, OUTPUT):
            raise CommandError("input/output band nahi kar sakte, 'engine use' se badlo.")
        self.engines.deactivate(kind)
        self.config.set(f"engines.{kind}", None)
        return Result(True, f"{kind} engine band.")

    def _cmd_history(self, ctx: CommandContext) -> Result:
        if not self.history:
            return Result(True, "Abhi koi history nahi.", speak=False)
        lines = [f"{i}. {t}" for i, t in enumerate(self.history, 1)]
        return Result(True, "\n".join(lines), speak=False)

    def _cmd_exit(self, ctx: CommandContext) -> Result:
        self.running = False
        return Result(True, "Alvida!", spoken="Alvida")


if __name__ == "__main__":
    print("Ye file seedha run nahi hoti. Chalane ke liye:  python3 core/kyro_brain.py")
