from dataclasses import dataclass
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
