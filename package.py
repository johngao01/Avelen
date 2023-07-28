import os
import time
import zipfile

folder = r'/root/download/weibo/'

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
        os.remove(file_path)

z.close()
end = time.time()

print(f"Cost {end - start} second")
