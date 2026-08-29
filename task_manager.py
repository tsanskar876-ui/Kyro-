tasks = []
while True:
    new_task = input("enter a task ")

   
    if new_task =="done":
        break

    tasks.append(new_task)


print("-------KYRO TASK MANAGER-------")

for number, task in enumerate(tasks, 1):
    print(number, task)

choice = int(input("Which task is comeplete ?"))

index = choice - 1 
tasks[index] = "DONE" + tasks[index]

print("UPDATED TASK")

for number, task in enumerate(task, 1):
    print(number, task)


