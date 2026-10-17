"""Kyro Brain - Kyro ko chalane wala hissa.

Ye file kyro_core se sab kuch IMPORT karti hai. Engines/modules yahan nahi
jude - wo sab kyro_core ke zariye jude hain. Brain ka kaam sirf:

    1. Core banana aur start karna
    2. Loop: user se suno -> core ko do -> jawab dikhao
    3. Band hote waqt core.stop() karna

Aage GUI, wake-word, voice loop jaisi cheezein yahin jodenge.

Chalane ka tareeka (kyro folder ke andar se):
    python3 core/kyro_brain.py
    ya
    python3 -m core.kyro_brain
"""

import os
import sys

# Root folder ko path me daalo taaki "core.kyro_core" aur "task_manager" mil jayein.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.kyro_core import KyroCore, __version__  # noqa: E402


class KyroBrain:
    def __init__(self, core=None):
        self.core = core if core is not None else KyroCore()

    def banner(self):
        name = self.core.config.get("assistant_name", "Kyro")
        line = "=" * 32
        self.core.say(f"{line}\n   {name.upper()}  (core {__version__})\n{line}", speak=False)
        self.core.say("Command likho. Madad ke liye: help   |   Band karne ke liye: exit", speak=False)
        if self.core.modules.failed:
            self.core.say("Dhyan do: kuch modules load nahi hue. 'modules' likh kar dekho.", speak=False)

    def run(self):
        self.core.start()
        try:
            self.banner()
            while self.core.running:
                text = self.core.hear("\nKyro> ")
                if text is None:        # Ctrl+D ya input khatam
                    break
                self.core.handle(text)
        except KeyboardInterrupt:
            print()
        finally:
            self.core.stop()
            print("\nKyro band.")


def main():
    KyroBrain().run()


if __name__ == "__main__":
    main()
