"""网页成品短期暂存，不进入永久音乐库索引。"""
from dataclasses import dataclass
from pathlib import Path
from time import time
import re


@dataclass
class Artifact:
    path: Path
    identifier: str
    expires: float


class BrowserArtifacts:
    def __init__(self, ttl):
        self.ttl = ttl
        self.entries = {}

    def add(self, task, path, identifier):
        artifact = Artifact(path, identifier, time() + self.ttl)
        self.entries[task] = artifact
        return artifact

    def get(self, task):
        artifact = self.entries.get(task)
        if not artifact or artifact.expires <= time() or not artifact.path.is_file():
            return None
        return artifact

    def find(self, identifier):
        for artifact in self.entries.values():
            if artifact.identifier == identifier and artifact.expires > time():
                return artifact.path
        raise FileNotFoundError()

    def sweep(self, readers):
        for task, artifact in list(self.entries.items()):
            if artifact.expires <= time() and not readers.get(artifact.identifier):
                try:
                    artifact.path.unlink(missing_ok=True)
                    del self.entries[task]
                except OSError:
                    # 外部占用时留待下轮清理，不能终止其他后台清理。
                    continue

    def clean_old_processes(self, parent, process_exists):
        if not parent.exists():
            return
        for folder in parent.iterdir():
            match = re.fullmatch(r'web-([0-9]+)-[a-f0-9]{32}', folder.name)
            if not match or folder.is_symlink() or not folder.is_dir() or process_exists(int(match[1])):
                continue
            for path in folder.iterdir():
                try:
                    if path.is_file() and not path.is_symlink() and path.stat().st_mtime + self.ttl < time():
                        path.unlink()
                except OSError:
                    continue
            try:
                folder.rmdir()
            except OSError:
                pass
