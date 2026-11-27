"""以隔离曲库对照连接、语句及文件检查次数。在 server 目录用 python -m scripts.bench_library_index 运行。"""
import argparse
from collections import Counter
from pathlib import Path
import sqlite3
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import patch

from app import downloads


def measure(size):
    with TemporaryDirectory(prefix='music-core-index-') as temporary:
        base = Path(temporary)
        roots = [base / name for name in ('library-a', 'library-b')]
        for root in roots:
            root.mkdir()
        manager = downloads.DownloadManager(
            SimpleNamespace(), downloads.DownloadSettings(directory=roots[0], data_directory=base / 'data')
        )
        manager.index.libraries(roots[1])
        paths, identifiers = [], []
        for i in range(size):
            path = roots[i % 2] / f'{i:05}.mp3'
            path.write_bytes(b'ID3' + b'x' * 1021)
            paths.append(path)
            identifiers.append(manager.fingerprint(path, path.stat()))
        for i in range(24):
            manager.index.record(identifiers[i], paths[i], {'title': f'Track {i}'}, published=True)
        for i in (1, 2, 3):
            manager.index.hide(identifiers[i])
        stable = 'a' * 64
        intermediate = 'b' * 64
        manager.index.record(stable, base / 'moved.mp3', {'title': 'Track 0'}, published=True)
        manager.index.relocated(stable, intermediate, base / 'intermediate.mp3', {'title': 'Track 0'}, False)
        manager.index.relocated(intermediate, identifiers[0], paths[0], {'title': 'Track 0'}, False)
        manager.index.record('c' * 64, roots[1] / 'missing.mp3', {'title': 'Missing'}, published=True)

        counts = Counter()
        connect, iterdir, audio_format = sqlite3.connect, Path.iterdir, downloads.audio_format

        def trace(sql):
            counts['SQL'] += 1
            if 'FROM aliases' in sql:
                counts['aliases'] += 1

        def counted_connect(*args, **kwargs):
            counts['connections'] += 1
            db = connect(*args, **kwargs)
            db.set_trace_callback(trace)
            return db

        def counted_iterdir(path):
            counts['scans'] += 1
            return iterdir(path)

        def counted_audio_format(data):
            counts['headers'] += 1
            return audio_format(data)

        with patch.object(sqlite3, 'connect', counted_connect), patch.object(Path, 'iterdir', counted_iterdir), patch.object(downloads, 'audio_format', counted_audio_format):
            def run(action):
                counts.clear()
                start = perf_counter()
                result = action()
                stats = tuple(counts[key] for key in ('connections', 'SQL', 'aliases', 'scans', 'headers'))
                return result, (*stats, (perf_counter() - start) * 1000)

            first, first_stats = run(manager.files)
            refresh, refresh_stats = run(manager.files)
            found, find_stats = run(lambda: manager.find_file(identifiers[-1]))
            candidates, migration_stats = run(manager.library.candidates)

        expected = {paths[i].name: (stable if i == 0 else identifiers[i], f'Track {i}' if i < 24 else None) for i in range(size) if i not in (1, 2, 3)}
        assert {row.filename: (row.fileId, row.title) for row in first} == expected
        assert first == refresh == sorted(first, key=lambda row: (-row.modifiedAt, row.filename))
        assert found[0] == paths[-1]
        assert {identifier: (path, metadata['title'], bool(hidden)) for identifier, path, metadata, hidden in candidates} == {
            identifiers[i]: (paths[i], f'Track {i}', i in (1, 2, 3)) for i in range(24)
        }
        return first_stats, refresh_stats, find_stats, migration_stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    print('size,operation,connections,SQL,aliases,scans,headers,median_ms', flush=True)
    for size in (100, 500, 1000):
        samples = [measure(size) for _ in range(args.repeats)]
        for action, rows in zip(('first', 'refresh', 'find', 'migration'), zip(*samples)):
            counts = [median(column) for column in zip(*rows)]
            print(f'{size},{action},' + ','.join(str(int(value)) for value in counts[:-1]) + f',{counts[-1]:.1f}', flush=True)


if __name__ == '__main__':
    main()
