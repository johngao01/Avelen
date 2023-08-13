import os
import subprocess
import time
import zipfile

folder = r'/root/download/'

z = zipfile.ZipFile("/media/media.zip", 'a')
os.chdir(folder)

start = time.time()
count = 0
for root, dirs, files in os.walk(folder):
    for file in files:
        file_path = os.path.join(root, file)
        count += 1
        relative_path = os.path.relpath(file_path, folder)
        print(count, relative_path)
        z.write(file_path, relative_path)
        if file.endswith(".json"):
            continue
        os.remove(file_path)

z.close()
end = time.time()
print(f"Zip Files Cost {end - start} Second")
result = subprocess.run('curl -4 ip.sb', shell=True, capture_output=True, text=True)
ipv4 = result.stdout.strip()

print("clear empty folder start --------------->")
for root, dirs, files in os.walk(folder, topdown=False):
    for folder in dirs:
        folder_to_check = os.path.join(root, folder)
        if not os.listdir(folder_to_check):  # Check if the folder is empty
            try:
                os.rmdir(folder_to_check)  # Remove the empty folder
                print(f"Deleted empty folder: {folder_to_check}")
            except OSError as e:
                print(f"Error deleting folder: {folder_to_check} - {e}")

print('Zip Download Link: ', f"http://{ipv4}:9999/media.zip")
