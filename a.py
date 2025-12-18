import subprocess
import os

# Получаем путь к текущей папке, где лежит этот скрипт
current_dir = os.path.dirname(os.path.abspath(__file__))

# Полные пути к файлам
file1 = os.path.join(current_dir, "бот.py")
file3 = os.path.join(current_dir, "freez.py")
file2 = os.path.join(current_dir, "bot.py")

# Проверяем, что файлы существуют
for file in [file1, file2, file3]:
    if not os.path.exists(file):
        print(f"❌ Файл не найден: {file}")
        exit(1)

# Запускаем оба файла параллельно
process1 = subprocess.Popen(["python", file1])
process2 = subprocess.Popen(["python", file2])
process3 = subprocess.Popen(["python", file3])


print("✅ Оба скрипта запущены!")

# Ожидаем завершения обоих
process1.wait()
process2.wait()
process3.wait()



print("✅ Оба скрипта завершили работу.")
