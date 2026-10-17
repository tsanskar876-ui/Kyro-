"""NAYA MODULE BANANE KA TEMPLATE.

Kaise use karein:
    1. Is file ki copy banao, naam do jaise  notes_module.py
       (NOTE: jo file "_" se shuru ho wo Kyro load nahi karta - isliye copy ka
        naam "_" se shuru mat karna)
    2. `name` badlo (unique rakho), commands badlo.
    3. Kyro me likho:  module on notes   ya Kyro dobara chalao.
    4. Code badal kar:  module reload notes   (Kyro band kiye bina)
"""

from core.kyro_core import CommandError, KyroModule, Result


class TemplateModule(KyroModule):
    name = "template"                    # unique naam
    version = "1.0"
    description = "Ye sirf namuna hai"
    depends = ()                         # jaise ("tasks",) - pehle wo load hoga

    def on_load(self):
        # command jodo: [naam, alias, alias...], handler, madad, use kaise karein
        self.add_command(["template hello"], self.cmd_hello,
                         help="Namuna command", usage="template hello <naam>")

        # dusre module ke event sunna ho to:
        # self.subscribe("task.added", self.on_task_added)

    def on_unload(self):
        pass  # file/thread band karni ho to yahan

    def cmd_hello(self, ctx):
        naam = ctx.need("template hello <naam>")     # khaali ho to khud error dega
        if len(naam) > 30:
            raise CommandError("Naam bahut lamba hai.")   # user ko seedha dikhega
        return Result(True, f"Namaste {naam}!", spoken=f"Namaste {naam}")
