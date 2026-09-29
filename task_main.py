"""Kyro Task Manager - console menu. Logic task_manager.py me hai."""

from task_manager import TaskManager, TaskError, PENDING, DONE


class Cancelled(Exception):
    """Ctrl+C / Ctrl+D dabane par current action cancel."""


def ask(prompt):
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise Cancelled


def ask_id(prompt):
    raw = ask(prompt).lstrip("#")
    if not raw.isdigit():
        raise TaskError("Sahi number daalo.")
    return int(raw)


def print_tasks(heading, tasks, empty_msg):
    print(f"\n========== {heading} ==========")
    if not tasks:
        print(empty_msg)
        return
    for t in tasks:
        print(f"#{t['id']}. {t['title']}")


def show_tasks(tm):
    print_tasks("PENDING TASKS", tm.list(PENDING), "Koi pending task nahi.")
    print_tasks("COMPLETED TASKS", tm.list(DONE), "Koi completed task nahi.")


def add_task(tm):
    task = tm.add(ask("Apna task likho: "))
    print(f"Task add ho gaya! (#{task['id']})")


def complete_task(tm):
    print_tasks("PENDING TASKS", tm.list(PENDING), "Koi pending task nahi.")
    if tm.list(PENDING):
        tm.complete(ask_id("Complete karne ke liye task number: "))
        print("Task complete!")


def reopen_task(tm):
    print_tasks("COMPLETED TASKS", tm.list(DONE), "Koi completed task nahi.")
    if tm.list(DONE):
        tm.reopen(ask_id("Wapas pending karne ke liye task number: "))
        print("Task wapas pending me aa gaya.")


def delete_task(tm):
    show_tasks(tm)
    if not tm.list():
        return
    task_id = ask_id("Delete karne ke liye task number: ")
    if ask("Pakka delete karna hai? (y/n): ").lower() != "y":
        print("Delete nahi kiya.")
        return
    print("Deleted:", tm.delete(task_id)["title"])


def edit_task(tm):
    print_tasks("PENDING TASKS", tm.list(PENDING), "Koi pending task nahi.")
    if tm.list(PENDING):
        task_id = ask_id("Edit karne ke liye task number: ")
        tm.edit(task_id, ask("Naya task likho: "))
        print("Task update ho gaya!")


def search_tasks(tm):
    results = tm.search(ask("Kya dhoondhna hai: "))
    print_tasks("SEARCH RESULTS", results, "Kuch nahi mila.")


def clear_completed(tm):
    if not tm.list(DONE):
        print("Koi completed task nahi.")
        return
    if ask("Saare completed tasks hata dun? (y/n): ").lower() == "y":
        print(f"{tm.clear_completed()} task hata diye.")
    else:
        print("Kuch nahi hataya.")


ACTIONS = {
    "1": add_task,
    "2": show_tasks,
    "3": complete_task,
    "4": delete_task,
    "5": edit_task,
    "6": reopen_task,
    "7": search_tasks,
    "8": clear_completed,
}


def main():
    try:
        tm = TaskManager()
    except OSError as e:
        print("Data load nahi ho paya:", e)
        return

    print("================================")
    print("        KYRO TASK MANAGER")
    print("================================")
    if tm.notice:
        print(tm.notice)

    while True:
        print("\n1. Add Task")
        print("2. Show Tasks")
        print("3. Complete Task")
        print("4. Delete Task")
        print("5. Edit Task")
        print("6. Reopen Task")
        print("7. Search")
        print("8. Clear Completed")
        print("0. Exit")

        try:
            choice = ask("\nEnter your choice: ").lower()
        except Cancelled:
            break

        if choice in ("0", "exit", "done", "q"):
            break

        action = ACTIONS.get(choice)
        if action is None:
            print("Galat choice. Dobara try karo.")
            continue

        try:
            action(tm)
        except Cancelled:
            print("Cancel kiya.")
        except TaskError as e:
            print(e)
        except OSError as e:
            print("File save nahi ho payi:", e)
        except Exception as e:  # koi bhi surprise error program band na kare
            print("Unexpected error:", e)

    print("\nKyro Task Manager band.")


if __name__ == "__main__":
    main()
