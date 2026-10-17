"""tasks - tumhara task_manager.py ab Kyro ka module.

task_manager.py me KUCH nahi badla. Ye file sirf ek "pul" (bridge) hai:
    user ka text  ->  TaskManager ke methods  ->  Result
"""

from core.kyro_core import CommandError, KyroModule, Result
from task_manager import DONE, PENDING, TaskError, TaskManager


class TasksModule(KyroModule):
    name = "tasks"
    version = "1.0"
    description = "Task Manager (task_manager.py) ko Kyro se jodta hai"

    def on_load(self):
        self.tm = TaskManager()
        if self.tm.notice:
            self.core.say(self.tm.notice, speak=False)

        add = self.add_command
        add(["task add", "add task", "task jodo"], self.cmd_add,
            help="Naya task jodo", usage="task add <text>")
        add(["task list", "tasks", "show tasks", "task dikhao"], self.cmd_list,
            help="Saare tasks dikhao", usage="task list")
        add(["task done", "task complete", "complete task"], self.cmd_done,
            help="Task poora karo", usage="task done <number>")
        add(["task reopen"], self.cmd_reopen,
            help="Poora hua task wapas pending karo", usage="task reopen <number>")
        add(["task edit"], self.cmd_edit,
            help="Task ka text badlo", usage="task edit <number> <naya text>")
        add(["task delete", "delete task"], self.cmd_delete,
            help="Task hatao", usage="task delete <number>")
        add(["task search"], self.cmd_search,
            help="Task dhoondo", usage="task search <text>")
        add(["task clear"], self.cmd_clear,
            help="Saare completed tasks hatao", usage="task clear")

    # ---- helpers ---------------------------------------------------------
    @staticmethod
    def _id(word):
        word = word.split()[0].lstrip("#")
        if not word.isdigit():
            raise CommandError("Sahi task number likho (jaise 3).")
        return int(word)

    def _guard(self, func, *args):
        """TaskManager ka TaskError -> Kyro ka CommandError."""
        try:
            return func(*args)
        except TaskError as e:
            raise CommandError(str(e)) from e

    @staticmethod
    def _format(tasks):
        return "\n".join(f"  #{t['id']}  {t['title']}" for t in tasks)

    # ---- commands --------------------------------------------------------
    def cmd_add(self, ctx):
        task = self._guard(self.tm.add, ctx.need("task add <text>"))
        self.emit("task.added", task=task)
        return Result(True, f"Task add ho gaya (#{task['id']}): {task['title']}",
                      spoken="Task add ho gaya.")

    def cmd_list(self, ctx):
        pending = self.tm.list(PENDING)
        done = self.tm.list(DONE)
        if not pending and not done:
            return Result(True, "Abhi koi task nahi hai.")
        parts = []
        if pending:
            parts.append(f"Pending ({len(pending)}):\n{self._format(pending)}")
        if done:
            parts.append(f"Completed ({len(done)}):\n{self._format(done)}")
        spoken = f"{len(pending)} pending aur {len(done)} completed task hain."
        return Result(True, "\n".join(parts), spoken=spoken, data={"pending": pending, "done": done})

    def cmd_done(self, ctx):
        task = self._guard(self.tm.complete, self._id(ctx.need("task done <number>")))
        self.emit("task.completed", task=task)
        return Result(True, f"Task #{task['id']} poora hua: {task['title']}", spoken="Task poora hua.")

    def cmd_reopen(self, ctx):
        task = self._guard(self.tm.reopen, self._id(ctx.need("task reopen <number>")))
        return Result(True, f"Task #{task['id']} wapas pending me.")

    def cmd_edit(self, ctx):
        words = ctx.need("task edit <number> <naya text>").split(maxsplit=1)
        if len(words) < 2:
            raise CommandError("Naya text bhi likho: task edit <number> <naya text>")
        task = self._guard(self.tm.edit, self._id(words[0]), words[1])
        return Result(True, f"Task #{task['id']} update ho gaya: {task['title']}")

    def cmd_delete(self, ctx):
        task = self._guard(self.tm.delete, self._id(ctx.need("task delete <number>")))
        return Result(True, f"Task hata diya: {task['title']}")

    def cmd_search(self, ctx):
        found = self._guard(self.tm.search, ctx.need("task search <text>"))
        if not found:
            return Result(True, "Kuch nahi mila.")
        return Result(True, self._format(found), spoken=f"{len(found)} task mile.")

    def cmd_clear(self, ctx):
        count = self.tm.clear_completed()
        return Result(True, f"{count} completed task hata diye.")
