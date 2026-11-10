export async function requestJson<T>(path:string,options:RequestInit & {errorMessage?:string}={}):Promise<T>{
 const timeout=new AbortController(),timer=setTimeout(()=>timeout.abort(),20000);
 const cancel=()=>timeout.abort();if(options.signal?.aborted)timeout.abort();options.signal?.addEventListener('abort',cancel,{once:true});
 try{const response=await fetch(path,{...options,headers:{'Content-Type':'application/json',...options.headers},signal:timeout.signal});
 const data=await response.json();if(!response.ok)throw new Error(data.error?.message??options.errorMessage??'API error');return data as T;
 }finally{clearTimeout(timer);options.signal?.removeEventListener('abort',cancel);}
}
