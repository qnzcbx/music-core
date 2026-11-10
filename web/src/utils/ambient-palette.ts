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
}
export const defaultAmbientPalette: AmbientPalette = Object.freeze({
  key: 'media-lab-default', base: '#f3f2e9', baseLeft: '#e7eedc', baseRight: '#f4f2dd', left: '#dce9cb', center: '#edf0dd', right: '#f5efcf', accent: '#34533d', evidence: 'fallback',
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
export function createPaletteLoader(extract: (url: string) => Promise<RGB[]>, now = Date.now, capacity=48) {
  const cache=new Map<string,CacheEntry>();
  return async (url?: string|null): Promise<AmbientPalette> => {
    if(!url)return defaultAmbientPalette;
    const existing=cache.get(url);
    if(existing&&existing.expires>now()) {cache.delete(url);cache.set(url,existing);return existing.promise;}
    cache.delete(url);
    const entry:CacheEntry={expires:Infinity,promise:Promise.resolve(defaultAmbientPalette)};
    entry.promise=Promise.resolve().then(()=>extract(url)).then(colors=>{
      const palette=makeAmbientPalette(colors,url);
      if(palette.evidence==='fallback')entry.expires=now()+30000;
      return palette;
    }).catch(()=>{entry.expires=now()+30000;return defaultAmbientPalette;});
    cache.set(url,entry);
    while(cache.size>capacity)cache.delete(cache.keys().next().value!);
    return entry.promise;
  };
}

export function extractCoverColors(url: string): Promise<RGB[]> {
  return new Promise((resolve,reject)=>{
    const image=new Image();image.crossOrigin='anonymous';image.referrerPolicy='no-referrer';image.decoding='async';
    let timer:ReturnType<typeof setTimeout>;
    function done(error?: Error, colors?: RGB[]) {
      clearTimeout(timer);image.onload=null;image.onerror=null;
      error?reject(error):resolve(colors??[]);
    }
    image.onload=()=>{
      try {
        if(!image.naturalWidth||!image.naturalHeight)throw new Error('empty cover');
        const canvas=document.createElement('canvas');canvas.width=64;canvas.height=64;
        const context=canvas.getContext('2d',{willReadFrequently:true});if(!context)throw new Error('canvas unavailable');
        context.drawImage(image,0,0,64,64);done(undefined,representativeColors(context.getImageData(0,0,64,64).data));
        canvas.width=canvas.height=0;
      } catch(error) {done(error instanceof Error?error:new Error('cover unreadable'));}
    };
    image.onerror=()=>done(new Error('cover CORS or network failure'));
    timer=setTimeout(()=>{done(new Error('cover timeout'));image.src='';},4500);
    image.src=url;
  });
}
export const loadCoverPalette=createPaletteLoader(extractCoverColors);

/** Only the latest consumer selection may commit; shared extraction is not cancelled. */
export function createPaletteSelection(load: typeof loadCoverPalette, commit: (palette:AmbientPalette)=>void) {
  let generation=0;
  return { async select(url?:string|null) {const current=++generation;const palette=await load(url);if(current===generation)commit(palette);},
    dispose(){generation++;} };
}
