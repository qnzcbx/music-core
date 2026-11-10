"""40-D.3.1：对照旧参数和新参数，仅保存公开搜索元数据。"""
import asyncio
import json
from pathlib import Path
import httpx
from app.providers.kuwo import KuwoProvider,SEARCH_URL,decode_response,candidate_from

OUT=Path(__file__).resolve().parents[2]/'docs/migration/40-D-3-1'
BASE={'all':'洛神赋 银临','ft':'music','client':'kt','rformat':'json','encoding':'utf8','mobi':'1'}
EXTRA={'vipver':'1','cluster':'0','strategy':'2012','issubtitle':'1','show_copyright_off':'1'}

async def main():
    async with httpx.AsyncClient(timeout=25) as client:
        async def probe(label,extra,limit,page=0,url=SEARCH_URL):
            params={**BASE,**extra,'rn':limit,'pn':page}
            response=await client.get(url,params=params,headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.kuwo.cn/'})
            result={'label':label,'url':url,'params':params,'http':response.status_code}
            if response.status_code==200:
                data=decode_response(response.content);rows=data.get('abslist',[])
                result.update(total=data.get('TOTAL'),rows=[{'rank':i+1,'id':row.get('MUSICRID'),'title':row.get('SONGNAME'),'artist':row.get('ARTIST'),'album':row.get('ALBUM'),'duration':row.get('DURATION'),'accepted':candidate_from(row) is not None} for i,row in enumerate(rows)])
            return result
        cases=[('core-10',{},10,0),('old-10',EXTRA,10,0),('core-15',{},15,0),('old-15',EXTRA,15,0),('core-10-page2',{},10,1),('core-10-page3',{},10,2),('cluster-only',{'cluster':'0'},10,0),('strategy-only',{'strategy':'2012'},10,0),('old-http',EXTRA,10,0,'http://www.kuwo.cn/search/searchMusicBykeyWord')]
        cases += [(f'only-{key}',{key:value},10,0) for key,value in EXTRA.items() if key not in ('cluster','strategy')]
        cases += [(f'old-without-{key}',{k:v for k,v in EXTRA.items() if k!=key},10,0) for key in EXTRA]
        cases += [(f'core-10-page{p+1}',{},10,p) for p in range(3,10)]
        results=await asyncio.gather(*(probe(*case) for case in cases))
        OUT.mkdir(parents=True,exist_ok=True);(OUT/'kuwo-comparison.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        for result in results:print(json.dumps({'label':result['label'],'http':result['http'],'total':result.get('total'),'rows':[(r['rank'],r['id'],r['title'],r['artist']) for r in result.get('rows',[])]},ensure_ascii=False))

if __name__=='__main__':asyncio.run(main())
