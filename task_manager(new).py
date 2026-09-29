import json
import os

FILE_NAME = "tasks.json"


def load_tasks():
    if not os.path.exists(FILE_NAME):
        return {
            "pending": [],
            "completed": []
        }

    try:
        with open(FILE_NAME, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return {
            "pending": [],
            "completed": []
        }


def save_tasks(tasks):
    with open(FILE_NAME, "w", encoding="utf-8") as file:
        json.dump(tasks, file, indent=4, ensure_ascii=False)


def show_tasks(tasks):
    print("\n========== PENDING TASKS ==========")

    if not tasks["pending"]:
        print("No pending tasks.")
    else:
        for number, task in enumerate(tasks["pending"], start=1):
            print(str(number) + ". " + task)

    print("\n========== COMPLETED TASKS ==========")

    if not tasks["completed"]:
        print("No completed tasks.")
    else:
        for number, task in enumerate(tasks["completed"], start=1):
            print(str(number) + ". " + task)

    print()


def add_task(tasks):
    task = input("Enter your task: ").strip()

    if task == "":
        print("Task cannot be empty.")
        return

    tasks["pending"].append(task)
    save_tasks(tasks)

    print("Task added successfully!")


def complete_task(tasks):
    if not tasks["pending"]:
        print("No pending tasks.")
        return

    print("\nPending Tasks:")
    for number, task in enumerate(tasks["pending"], start=1):
        print(str(number) + ". " + task)

    try:
        number = int(input("Enter task number to complete: "))
    except ValueError:
        print("Please enter a valid number.")
        return

    if number < 1 or number > len(tasks["pending"]):
        print("Invalid task number.")
        return

    task = tasks["pending"].pop(number - 1)
    tasks["completed"].append(task)

    save_tasks(tasks)

    print("Task completed!")


def delete_task(tasks):
    if not tasks["pending"]:
        print("No pending tasks.")
        return

    print("\nPending Tasks:")
    for number, task in enumerate(tasks["pending"], start=1):
        print(str(number) + ". " + task)

    try:
        number = int(input("Enter task number to delete: "))
    except ValueError:
        print("Please enter a valid number.")
        return

    if number < 1 or number > len(tasks["pending"]):
        print("Invalid task number.")
        return

    deleted_task = tasks["pending"].pop(number - 1)

    save_tasks(tasks)

    print("Deleted:", deleted_task)


def edit_task(tasks):
    if not tasks["pending"]:
        print("No pending tasks.")
        return

    print("\nPending Tasks:")
    for number, task in enumerate(tasks["pending"], start=1):
        print(str(number) + ". " + task)

    try:
        number = int(input("Enter task number to edit: "))
    except ValueError:
        print("Please enter a valid number.")
        return

    if number < 1 or number > len(tasks["pending"]):
        print("Invalid task number.")
        return

    new_task = input("Enter new task: ").strip()

    if new_task == "":
        print("Task cannot be empty.")
        return

    tasks["pending"][number - 1] = new_task
    save_tasks(tasks)

    print("Task updated successfully!")


def main():
    tasks = load_tasks()

    print("================================")
    print("        KYRO TASK MANAGER")
    print("================================")

    while True:
        print("\n1. Add Task")
        print("2. Show Tasks")
        print("3. Complete Task")
        print("4. Delete Task")
        print("5. Edit Task")
        print("6. Exit")

        choice = input("\nEnter your choice: ").strip()

        if choice == "1":
            add_task(tasks)

        elif choice == "2":
            show_tasks(tasks)

        elif choice == "3":
            complete_task(tasks)

        elif choice == "4":
            delete_task(tasks)

        elif choice == "5":
            edit_task(tasks)

        elif choice == "6" or choice.lower() == "done":
            print("\nKyro Task Manager closed.")
            break

        else:
            print("Invalid choice. Please try again.")


if __name__ == "__main__":
    main()
