"""basic - chhote, safe commands. Naya module likhna seekhne ke liye sabse aasan namuna."""

from datetime import datetime

from core.kyro_core import KyroModule


class BasicModule(KyroModule):
    name = "basic"
    version = "1.0"
    description = "Samay, tareekh, hello, echo"

    def on_load(self):
        self.add_command(["time", "samay"], self.cmd_time, help="Abhi ka samay", usage="time")
        self.add_command(["date", "tareekh"], self.cmd_date, help="Aaj ki tareekh", usage="date")
        self.add_command(["hello", "namaste", "hi"], self.cmd_hello, help="Namaste", usage="hello")
        self.add_command(["echo"], self.cmd_echo, help="Jo likho wahi wapas bolo (test)", usage="echo <text>")

    def cmd_time(self, ctx):
        now = datetime.now()
        return f"Abhi {now.strftime('%I:%M %p')} baje hain."

    def cmd_date(self, ctx):
        return datetime.now().strftime("Aaj %A, %d %B %Y hai.")

    def cmd_hello(self, ctx):
        name = self.core.config.get("assistant_name", "Kyro")
        return f"Namaste! Main {name} hoon."

    def cmd_echo(self, ctx):
        return ctx.need("echo <text>")
