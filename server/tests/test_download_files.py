"""文件清单只读、目录隔离及任务历史丢失后的边界。"""
from pathlib import Path
from types import SimpleNamespace
import httpx
import pytest
from fastapi.testclient import TestClient
from app.downloads import DownloadManager,DownloadSettings
from app.main import create_app

def test_files_survive_empty_task_history(tmp_path):
    (tmp_path/'人工.mp3').write_bytes(b'ID3'+b'x'*32)
    (tmp_path/'人工.m4a').write_bytes(b'\0\0\0\x10ftyp'+b'xxxx')
    (tmp_path/'broken.mp3').write_text('not audio')
    (tmp_path/'.music-core-123-00000000000000000000000000000000.part').write_bytes(b'ID3unfinished')
    first=DownloadManager(SimpleNamespace(),DownloadSettings(directory=tmp_path))
    restarted=DownloadManager(SimpleNamespace(),DownloadSettings(directory=tmp_path))
    assert not restarted.jobs
    rows=restarted.files();assert {row.filename for row in rows}=={'人工.mp3','人工.m4a'}
    assert {row.format for row in rows}=={'mp3','m4a'}
    assert next(row.sizeBytes for row in rows if row.filename.endswith('.mp3'))==35
    assert not any('identity' in row.model_dump() or 'path' in row.model_dump() for row in rows)
    assert first.files()==rows

def test_file_list_cannot_read_other_paths(tmp_path):
    root=tmp_path/'downloads';root.mkdir();(tmp_path/'private.mp3').write_bytes(b'ID3private')
    (root/'子目录').mkdir();(root/'子目录'/'nested.mp3').write_bytes(b'ID3nested')
    try:(root/'link.mp3').symlink_to(tmp_path/'private.mp3')
    except OSError:pass
    app=create_app(download_settings=DownloadSettings(directory=root),transport=httpx.MockTransport(lambda r:httpx.Response(500)))
    with TestClient(app) as client:
        response=client.get('/api/downloads/files',params={'path':str(tmp_path)})
        assert response.status_code==200 and response.json()==[]
        assert client.get('/api/downloads/no-such-task').status_code==404
        assert client.post('/api/downloads/no-such-task/retry').status_code==404

def test_unreadable_file_directory_reports_error(tmp_path,monkeypatch):
    manager=DownloadManager(SimpleNamespace(),DownloadSettings(directory=tmp_path))
    monkeypatch.setattr(Path,'iterdir',lambda self:(_ for _ in ()).throw(PermissionError()))
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:manager.files()
    assert error.value.status_code==503
    with TestClient(create_app(download_settings=DownloadSettings(directory=tmp_path))) as client:
        response=client.get('/api/downloads/files')
        assert response.status_code==503 and response.json()['error']['code']=='file_io_error'
