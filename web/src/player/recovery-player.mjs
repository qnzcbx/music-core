// 单首歌曲的恢复协调器；只持有本地能力和稳定身份，不保存上游地址。
export class RecoveryPlayer {
  constructor(audio, {operations, notify = () => {}}) {
    this.audio=audio; this.operations=operations; this.notify=notify;
    this.identity=null; this.session=null; this.generation=0; this.bookmark=0;
    this.desiredPlaying=false; this.automaticUsed=false; this.operation=null; this.binding=false;
    this.abort=null; this.phase='idle';
    this.listeners=[];
    const listen=(event,handler)=>{audio.addEventListener(event,handler);this.listeners.push([event,handler]);};
    listen('timeupdate',()=>this.capture());
    listen('seeked',()=>this.capture());
    listen('playing',()=>{if(this.identity&&this.session&&!this.binding)this.desiredPlaying=true;});
    listen('pause',()=>{if(!this.binding&&!audio.error&&!audio.ended&&audio.readyState>=1)this.desiredPlaying=false;});
    listen('error',()=>{void this.mediaError();});
    // waiting/stalled仅表示缓冲，不自动取链。
  }
  async dispose(){const stopping=this.stop();for(const [event,handler] of this.listeners)this.audio.removeEventListener(event,handler);this.listeners=[];await stopping;}
  state(phase,message) {
    this.phase=phase; this.notify({phase,message,automaticUsed:this.automaticUsed,hasSession:!!this.session});
  }
  capture() {
    if(this.session&&!this.binding&&!this.audio.error&&!this.audio.seeking&&Number.isFinite(this.audio.currentTime)&&this.audio.readyState>=1)
      this.bookmark=this.audio.currentTime;
  }
  async closeId(id) {
    if(!id)return;
    try {await this.operations.close(id);}
    catch { /* 关闭失败交由服务端TTL兜底，不无限重试。 */ }
  }
  async stop() {
    this.generation++; this.abort?.abort(); this.operation=null;
    const old=this.session; this.session=null; this.identity=null; this.desiredPlaying=false;
    this.binding=true; this.audio.pause(); this.audio.removeAttribute('src'); this.audio.load(); this.binding=false;
    this.state('idle','会话已关闭'); await this.closeId(old?.playbackId);
  }
  async select(identity, startAt=0) {
    // 选择立即占用世代，不能让旧close的晚到完成重置新的选择。
    const stopping=this.stop(), generation=this.generation;
    await stopping;
    if(this.generation!==generation)return;
    this.identity={...identity}; this.pendingSeek=undefined;
    this.bookmark=Number.isFinite(startAt)?Math.max(0,startAt):0;
    this.desiredPlaying=true; this.automaticUsed=false;
    return this.reopen(false);
  }
  async setPlaying(value) {
    this.desiredPlaying=value;
    if(value&&['error','network'].includes(this.phase))return this.recover(false);
    const generation=this.generation,session=this.session;
    if(!value){this.audio.pause();if(!this.operation&&session)this.state('ready','已暂停');}
    else if(this.session&&!this.binding) {
      try {await this.audio.play();if(this.generation===generation&&this.session===session&&!this.operation)this.state('ready','正在播放');}
      catch(error) {if(this.generation===generation&&this.session===session&&error.name==='NotAllowedError')this.state('blocked','媒体已就绪，请手动继续播放');}
    }
  }
  seek(seconds){
    if(!Number.isFinite(seconds))return;
    this.bookmark=Math.max(0,seconds);
    if(this.operation){this.pendingSeek=this.bookmark;return;}
    if(this.session&&Number.isFinite(this.audio.duration))this.audio.currentTime=Math.min(this.bookmark,Math.max(0,this.audio.duration-.1));
  }
  async renew() {
    const session=this.session,generation=this.generation;
    if(!session||this.operation)return;
    try {
      await this.operations.renew(session.playbackId);
    } catch (error) {
      if (this.session !== session || generation !== this.generation) return;
      if (['playback_expired', 'playback_closed', 'playback_missing', 'media_expired'].includes(error.code) ||
          [404, 410].includes(error.status)) return this.recover(true);
      if (error.status) this.state('error', error.message);
      else this.state('network', '暂时无法续期');
    }
  }
  recover(automatic=false) {
    if(!this.identity)return Promise.resolve();
    if(this.operation)return this.operation.promise;
    if(automatic&&this.automaticUsed) {this.state('error','自动恢复已使用，请手动重新打开');return Promise.resolve();}
    this.automaticUsed=true; return this.reopen(true);
  }
  async mediaError() {
    const session=this.session,generation=this.generation,code=this.audio.error?.code;
    if(!session||!this.identity||this.operation||code===1)return;
    if(code===3) {this.state('error','媒体解码失败，可手动重试');return;}
    if(this.automaticUsed) {this.state('error','新媒体仍失败，请手动重新打开');return;}
    // MediaError没有HTTP详情，用已有HEAD一次诊断，不增加观察接口。
    const marker={promise:null}; this.operation=marker;
    marker.promise=(async()=>{
      let permitted=true;
      try {
        const response=await this.operations.probe(session.streamUrl);
        if([400,401,403,415,422].includes(response.status)||(code===4&&response.ok))permitted=false;
      } catch { /* 网络不明只允许一次有界重新打开。 */ }
      if(this.generation!==generation||this.session!==session)return;
      this.operation=null;
      if(permitted)return this.recover(true);
      this.state('error','权限或格式问题，不自动重新解析');
    })().finally(()=>{if(this.operation===marker)this.operation=null;});
    return marker.promise;
  }
  reopen(restoring) {
    const generation=this.generation,identity={...this.identity},old=this.session;
    this.capture();
    const saved={time:this.bookmark,volume:this.audio.volume,muted:this.audio.muted,rate:this.audio.playbackRate};
    const operation={promise:null}; this.operation=operation;
    const valid=()=>this.generation===generation&&this.operation===operation;
    this.state('opening',restoring?'重新获取媒体':'正在解析');
    operation.promise=(async()=>{
      let fresh=null;
      try {
        // 不abort打开请求：服务端可能已建Lease，晚到响应仍要接收并关闭。
        fresh = await this.operations.open(identity);
        if (!valid()) return;
        if (fresh.identity?.providerId !== identity.providerId ||
            fresh.identity?.platformId !== identity.platformId) {
          throw new Error('返回歌曲身份不一致');
        }
        this.capture(); saved.time=this.bookmark;
        saved.volume=this.audio.volume; saved.muted=this.audio.muted; saved.rate=this.audio.playbackRate;
        this.session=fresh; this.binding=true; this.audio.pause(); this.abort=new AbortController();
        this.audio.src=fresh.streamUrl; this.audio.load();
        await this.waitMedia(()=>this.audio.readyState>=1&&Number.isFinite(this.audio.duration),['loadedmetadata','durationchange'],this.abort.signal);
        if(!valid())return;
        this.state('positioning','恢复播放位置');
        const target=Math.max(0,Math.min(saved.time,Math.max(0,this.audio.duration-.1)));
        this.audio.volume=saved.volume; this.audio.muted=saved.muted; this.audio.playbackRate=saved.rate;
        this.audio.currentTime=target;
        await this.waitMedia(()=>!this.audio.seeking&&Math.abs(this.audio.currentTime-target)<=.5,['seeked','canplay','timeupdate'],this.abort.signal);
        if(!valid())return;
        if(this.pendingSeek!==undefined){const latest=this.pendingSeek;this.pendingSeek=undefined;this.audio.currentTime=Math.min(latest,Math.max(0,this.audio.duration-.1));}
        this.bookmark=this.audio.currentTime; this.binding=false;
        await this.closeId(old?.playbackId);
        if(!valid())return;
        if(this.desiredPlaying) {
          try {await this.audio.play();}
          catch(error) {
            if(!valid())return;
            if(!this.desiredPlaying&&error.name==='AbortError'){this.audio.pause();this.state('ready','恢复成功，保持暂停');return;}
            if(error.name!=='NotAllowedError')throw error;
            this.state('blocked','位置已恢复，请手动继续播放');return;
          }
        } else this.audio.pause();
        if(valid())this.state('ready',restoring?'恢复成功':'正在播放');
      } catch(error) {
        if(valid()) {
          this.session=null; this.binding=true; this.audio.pause(); this.audio.removeAttribute('src'); this.audio.load();
          this.audio.volume=saved.volume; this.audio.muted=saved.muted; this.audio.playbackRate=saved.rate;
          this.binding=false; this.bookmark=this.pendingSeek??saved.time; this.state('error', error.message || '恢复失败，可手动重新打开');
        }
        if(fresh)await this.closeId(fresh.playbackId);
        await this.closeId(old?.playbackId);
      } finally {
        if(!valid()&&fresh&&this.session!==fresh)await this.closeId(fresh.playbackId);
        if(this.operation===operation){this.operation=null;this.binding=false;}
      }
    })();
    return operation.promise;
  }
  waitMedia(predicate,events,signal) {
    if(signal.aborted)return Promise.reject(new DOMException('恢复已取消','AbortError'));
    if(predicate())return Promise.resolve();
    return new Promise((resolve,reject)=>{
      let timer;
      const cleanup=()=>{
        clearTimeout(timer);events.forEach(event=>this.audio.removeEventListener(event,check));
        this.audio.removeEventListener('error',fail);signal.removeEventListener('abort',cancel);
      };
      const check=()=>{if(predicate()){cleanup();resolve();}};
      const fail=()=>{cleanup();reject(new Error('媒体未能就绪'));};
      const cancel=()=>{cleanup();reject(new DOMException('恢复已取消','AbortError'));};
      events.forEach(event=>this.audio.addEventListener(event,check));this.audio.addEventListener('error',fail);
      signal.addEventListener('abort',cancel);timer=setTimeout(fail,12000);check();
    });
  }
}
