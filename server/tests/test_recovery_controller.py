"""Node仅用于可选的客户端状态机测试，不是后端运行依赖。"""
from pathlib import Path
import shutil
import subprocess
import pytest


def test_recovery_state_machine():
    node=shutil.which('node')
    if not node:pytest.skip('未安装可选Node，客户端逻辑另由浏览器验收脚本覆盖')
    result=subprocess.run([node,'--test',str(Path(__file__).with_name('recovery.test.mjs'))],
        capture_output=True,text=True,encoding='utf8',timeout=40)
    assert result.returncode==0,result.stdout+result.stderr
