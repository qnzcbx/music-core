"""下载发布和本机迁移共用的安全文件名规则。"""
import re
import unicodedata


def safe_stem(value):
    value = ''.join('_' if unicodedata.category(c) in ('Cc','Cs') else c for c in value)
    value = re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]', '_', value).strip(' .')
    # 按UTF-16长度约束，保留补码字符；避免Windows路径及保留设备名。
    value = value.encode('utf-16-le', errors='replace')[:240].decode('utf-16-le', errors='ignore').rstrip(' .')
    if not value:
        value = '未命名'
    if re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?', value, re.I):
        value = '_' + value
    return value
