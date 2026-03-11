from dataclasses import dataclass
from typing import Iterable, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

import requests

from tools.utils import save_content


@dataclass
class DownloadTask:
    url: str
    save_path: str
    headers: dict | None = None
    timeout: int = 30


def download_one(task: DownloadTask):
    r = requests.get(task.url, headers=task.headers, stream=True, timeout=task.timeout)
    if r.status_code == 200:
        os.makedirs(os.path.dirname(task.save_path), exist_ok=True)
        return save_content(task.save_path, r), r
    return False, r


def download_many(tasks: Iterable[DownloadTask], max_workers: int = 4,
                  on_done: Callable[[DownloadTask, bool, object], None] | None = None):
    tasks = list(tasks)
    if not tasks:
        return []
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(download_one, task): task for task in tasks}
        for fut in as_completed(futures):
            task = futures[fut]
            ok, resp = fut.result()
            results.append((task, ok, resp))
            if on_done:
                on_done(task, ok, resp)
    return results
