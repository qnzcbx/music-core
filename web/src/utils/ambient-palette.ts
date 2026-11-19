import { CLOVER_COVER } from './displayed-cover.ts';
import { apiFetch, isDesktop } from '../api/transport.ts';
export type RGB = readonly [number, number, number];
export interface AmbientPalette {
  key: string;
  base: string;
  baseLeft: string;
  baseRight: string;
  left: string;
  center: string;
  right: string;
  accent: string;
  evidence: 'cover' | 'neutral' | 'fallback';
  diagnostic?: {status:string;via:'direct'|'relay'|'none';initialFailure?:string};
}
export const defaultAmbientPalette: AmbientPalette = Object.freeze({
  key: 'media-lab-default', base: '#eeedeb', baseLeft: '#e5e3df', baseRight: '#f3f1ee', left: '#dedbd6', center: '#eeece9', right: '#e5e4e1', accent: '#414b50', evidence: 'fallback',
});
const clamp = (n: number, a: number, b: number) => Math.max(a, Math.min(b, n));
export function rgbToHsl([r, g, b]: RGB): RGB {
  r /= 255; g /= 255; b /= 255;
  const high = Math.max(r, g, b), low = Math.min(r, g, b), d = high-low, l = (high+low)/2;
  if (!d) return [0,0,l];
  const s = d/(1-Math.abs(2*l-1));
  const h = high === r ? ((g-b)/d)%6 : high === g ? (b-r)/d+2 : (r-g)/d+4;
  return [(h*60+360)%360,s,l];
}
const hsl = (h: number, s: number, l: number) => `hsl(${Math.round(h)} ${Math.round(s*100)}% ${Math.round(l*100)}%)`;
function pastel(color: RGB, lightness: number, saturationScale=1): RGB {
  const [h,s]=rgbToHsl(color), saturation=clamp((.5+s*.55)*saturationScale,.45,.95);
  const chroma=(1-Math.abs(2*lightness-1))*saturation;
  const x=chroma*(1-Math.abs((h/60)%2-1)), m=lightness-chroma/2;
  const sectors:RGB[]=[[chroma,x,0],[x,chroma,0],[0,chroma,x],[0,x,chroma],[x,0,chroma],[chroma,0,x]];
  return sectors[Math.floor(h/60)]!.map(v=>(v+m)*255) as unknown as RGB;
}
const mix = (a:RGB,b:RGB,t:number):RGB => [a[0]*(1-t)+b[0]*t,a[1]*(1-t)+b[1]*t,a[2]*(1-t)+b[2]*t];
const hex = (rgb:RGB) => '#'+rgb.map(v=>Math.round(v).toString(16).padStart(2,'0')).join('');
const hueDistance = (a: number, b: number) => Math.min(Math.abs(a-b),360-Math.abs(a-b));

/** Small quantized histogram; no per-frame canvas or media/player dependencies. */
export function representativeColors(pixels: ArrayLike<number>): RGB[] {
  const buckets = new Map<number, { count: number; r: number; g: number; b: number }>();
  let r=0,g=0,b=0,count=0;
  for (let i=0;i+3<pixels.length;i+=4) {
    if (pixels[i+3]!<128) continue;
    const red=pixels[i]!,green=pixels[i+1]!,blue=pixels[i+2]!;
    r+=red;g+=green;b+=blue;count++;
    const [,s,l]=rgbToHsl([red,green,blue]);
    if(s<.09||l<.06||l>.96)continue;
    const key=(red>>4)*256+(green>>4)*16+(blue>>4);
    const bucket=buckets.get(key)??{count:0,r:0,g:0,b:0};
    bucket.count++;bucket.r+=red;bucket.g+=green;bucket.b+=blue;buckets.set(key,bucket);
  }
  if (!count) return [];
  const candidates=[...buckets.values()].filter(bucket=>bucket.count>=Math.max(2,count*.006))
    .map(bucket=>({color:[bucket.r/bucket.count,bucket.g/bucket.count,bucket.b/bucket.count] as RGB,weight:bucket.count}));
  candidates.sort((a,b)=>b.weight*(.35+rgbToHsl(b.color)[1])-a.weight*(.35+rgbToHsl(a.color)[1]));
  const chosen: RGB[]=[];
  for(const item of candidates) {
    if(!chosen.length||chosen.every(color=>hueDistance(rgbToHsl(color)[0],rgbToHsl(item.color)[0])>28))chosen.push(item.color);
    if(chosen.length===3)break;
  }
  return chosen.length?chosen:[[r/count,g/count,b/count]];
}

/** Harmonize independently of extraction: preserve mono palettes; keep text colors dark. */
export function makeAmbientPalette(colors: readonly RGB[], key: string): AmbientPalette {
  if(!colors.length)return defaultAmbientPalette;
  const [h,s]=rgbToHsl(colors[0]!);
  if(s<.09) return {key,base:'#f2f2ee',baseLeft:'#e7e8e3',baseRight:'#f4f4ee',left:'#dedfdb',center:'#efefea',right:'#e7e8e4',accent:'#35453c',evidence:'neutral'};
  // High HSL saturation at high lightness is still a pale pastel, not neon.
  const left=pastel(colors[0]!,.90),right=pastel(colors[1]??colors[0]!, .94);
  const overlap=mix(left,right,.5);
  // RGB mixing gives a soft overlap without inventing an intermediate hue.
  const center=colors[2]?mix(overlap,pastel(colors[2],.94),.2):overlap;
  return {key,base:hex(mix(overlap,[255,255,255],.4)),
    baseLeft:hex(mix(left,[255,255,255],.35)),baseRight:hex(mix(right,[255,255,255],.22)),
    left:hex(left),center:hex(center),right:hex(right),
    accent:hsl(h,clamp(s*.4,.14,.34),.27),evidence:'cover'};
}

type CacheEntry = { promise: Promise<AmbientPalette>; expires: number };
export function createPaletteLoader(extract: (url: string) => Promise<RGB[]|{colors:RGB[];diagnostic:NonNullable<AmbientPalette['diagnostic']>}>, now = Date.now, capacity=48) {
  const cache=new Map<string,CacheEntry>();
  return async (url?: string|null): Promise<AmbientPalette> => {
    if(!url)return {...defaultAmbientPalette,diagnostic:{status:'no-cover',via:'none'}};
    const existing=cache.get(url);
    if(existing&&existing.expires>now()) {cache.delete(url);cache.set(url,existing);return existing.promise;}
    cache.delete(url);
    const entry:CacheEntry={expires:Infinity,promise:Promise.resolve(defaultAmbientPalette)};
    entry.promise=Promise.resolve().then(()=>extract(url)).then(result=>{
      const colors=Array.isArray(result)?result:result.colors;
      const generated=makeAmbientPalette(colors,url);
      const palette:AmbientPalette={...generated,diagnostic:generated.evidence==='fallback'?{status:'palette-failed',via:'none'}:Array.isArray(result)?{status:'success',via:'direct'}:result.diagnostic};
      if(palette.evidence==='fallback')entry.expires=now()+30000;
      return palette;
    }).catch(error=>{entry.expires=now()+30000;return {...defaultAmbientPalette,diagnostic:{status:error instanceof CoverPaletteError?error.stage:'palette-failed',via:'none' as const}};});
    cache.set(url,entry);
    while(cache.size>capacity)cache.delete(cache.keys().next().value!);
    return entry.promise;
  };
}

/** 开发诊断只描述失败环节，不保存图片内容或平台凭据。 */
export class CoverPaletteError extends Error {
  stage:string;
  constructor(stage:string){super(stage);this.stage=stage;}
}
export function coverReadUrl(value:string):string|null {
  try{const url=new URL(value);if(url.protocol==='https:'&&['y.gtimg.cn','d.musicapp.migu.cn'].includes(url.hostname))return '/api/covers?url='+encodeURIComponent(value);}catch{/* 无效地址由图片加载器报告。 */}
  return null;
}
async function paletteRelayUrl(value: string): Promise<string | null> {
  if (!isDesktop) return coverReadUrl(value);
  if (!value.startsWith('https://')) return null;
  const response = await apiFetch('/api/covers/palette', { method: 'POST', body: JSON.stringify({url: value}) });
  if (!response.ok) return null;
  const result = await response.json();
  return typeof result?.url === 'string' && /^http:\/\/127\.0\.0\.1:\d+\/covers\/[a-f0-9]{32}$/.test(result.url)
    ? result.url : null;
}
function readPixels(url:string,anonymous=true,timeoutMs=4500,sample?: (image:HTMLImageElement)=>RGB[]):Promise<RGB[]> {
  return new Promise((resolve,reject)=>{
    const image=new Image();if(anonymous)image.crossOrigin='anonymous';image.referrerPolicy='no-referrer';image.decoding='async';
    let timer:ReturnType<typeof setTimeout>,settled=false;
    function done(error?:CoverPaletteError,colors?:RGB[]){if(settled)return;settled=true;clearTimeout(timer);image.onload=null;image.onerror=null;error?reject(error):resolve(colors??[]);}
    image.onload=async()=>{
      try{await image.decode();}catch{done(new CoverPaletteError('image-decode-failed'));return;}
      if(settled)return;
      if(!image.naturalWidth||!image.naturalHeight){done(new CoverPaletteError('image-decode-failed'));return;}
      const canvas=document.createElement('canvas');canvas.width=canvas.height=64;
      try{
        const context=canvas.getContext('2d',{willReadFrequently:true});if(!context)throw new CoverPaletteError('pixel-sampling-failed');
        context.drawImage(image,0,0,64,64);const colors=sample?sample(image):representativeColors(context.getImageData(0,0,64,64).data);
        if(!colors.length)throw new CoverPaletteError('pixel-sampling-failed');done(undefined,colors);
      }catch(error){done(error instanceof CoverPaletteError?error:new CoverPaletteError(error instanceof DOMException&&error.name==='SecurityError'?'canvas-cors-denied':'pixel-sampling-failed'));}
      finally{canvas.width=canvas.height=0;}
    };
    image.onerror=()=>done(new CoverPaletteError('image-request-failed'));
    timer=setTimeout(()=>{done(new CoverPaletteError('image-timeout'));image.src='';},timeoutMs);
    image.src=url;
  });
}
export const extractCoverColors=(url:string)=>readPixels(url);
export async function extractWithDiagnostic(url:string,sample?: (image:HTMLImageElement)=>RGB[]){
  try{return {colors:await readPixels(url,true,4500,sample),diagnostic:{status:'success',via:'direct' as const}};}
  catch(first){
    let failure=first;
    const canRelay=url !== CLOVER_COVER && (isDesktop || !!coverReadUrl(url));
    // 匿名加载失败时，区分“展示也失败”和“可展示但像素被跨域保护”。
    if(canRelay&&first instanceof CoverPaletteError&&first.stage==='image-request-failed'){
      try{return {colors:await readPixels(url,false,4500,sample),diagnostic:{status:'success',via:'direct' as const}};}catch(probe){failure=probe;}
    }
    const relay=canRelay ? await paletteRelayUrl(url).catch(() => null) : null;
    if(!relay)throw failure;
    try{return {colors:await readPixels(relay,true,10000,sample),diagnostic:{status:'success',via:'relay' as const,initialFailure:failure instanceof CoverPaletteError?failure.stage:'image-request-failed'}};}
    catch(error){throw new CoverPaletteError('relay-'+(error instanceof CoverPaletteError?error.stage:'image-request-failed'));}
  }
}
export const loadCoverPalette=createPaletteLoader(extractWithDiagnostic);

/** Only the latest consumer selection may commit; shared extraction is not cancelled. */
export function createPaletteSelection(load: typeof loadCoverPalette, commit: (palette:AmbientPalette)=>void) {
  let generation=0;
  return { async select(url?:string|null) {const current=++generation;const palette=await load(url);if(current===generation)commit(palette);},
    dispose(){generation++;} };
}
