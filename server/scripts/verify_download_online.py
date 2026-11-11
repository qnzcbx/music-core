"""16 下载界面 其余来源适度在线回归，只输出下载任务和本地文件摘要。"""
import asyncio
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import httpx

ROOT=Path(__file__).resolve().parents[2]
async def main():
    parser=argparse.ArgumentParser(description='对多个来源进行有限真实下载冒烟验证')
    parser.add_argument('--url',default=os.environ.get('MUSIC_CORE_API_URL','http://127.0.0.1:8003'),help='已运行的 Music Core API 地址')
    parser.add_argument('--output',type=Path,default=Path(os.environ.get('MUSIC_CORE_VERIFY_OUT',ROOT/'.runtime/verify-download-online'))/'download-other-sources.json',help='结果 JSON 输出路径')
    parser.add_argument('--downloads-dir',type=Path,default=Path(os.environ.get('MUSIC_CORE_DOWNLOAD_DIR',ROOT/'downloads')),help='被测 Core 配置的下载目录')
    args=parser.parse_args()
    results=[]
    async with httpx.AsyncClient(base_url=args.url.rstrip('/'),timeout=30) as client:
        for provider,pid,title in [('kuwo','9942644','东风志'),('qq','001e7VNQ43nv4W','牵丝戏'),('migu','600929000006452915','一场雨的瞬间')]:
            response=await client.post('/api/downloads',json={'identity':{'providerId':provider,'platformId':pid},'title':title,'artist':'银临'})
            response.raise_for_status();identifier=response.json()['id'];deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                task=(await client.get('/api/downloads/'+identifier)).json()
                if task['status'] in ('completed','failed','cancelled'):break
                await asyncio.sleep(.3)
            else:task=(await client.post('/api/downloads/'+identifier+'/cancel')).json()
            result={'task':task}
            if task['status']=='completed':
                path=args.downloads_dir/task['filename'];digest=hashlib.sha256()
                with path.open('rb') as stream:
                    prefix=stream.read(16);digest.update(prefix)
                    while chunk:=stream.read(65536):digest.update(chunk)
                result['file']={'filename':path.name,'bytes':path.stat().st_size,'prefixHex':prefix.hex(),'sha256':digest.hexdigest()}
                assert path.stat().st_size==task['receivedBytes']
            results.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':asyncio.run(main())
