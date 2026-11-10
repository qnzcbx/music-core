import type {TrackIdentity,OpenResponse} from '../types/core';
export class RecoveryPlayer {
 constructor(audio:HTMLAudioElement,options?:{request?:typeof fetch;notify?:(state:{phase:string;message:string;automaticUsed:boolean;hasSession:boolean})=>void});
 session:OpenResponse|null; identity:TrackIdentity|null; operation:unknown; phase:string; desiredPlaying:boolean;
 select(identity:TrackIdentity):Promise<void>;stop():Promise<void>;dispose():Promise<void>;
 setPlaying(value:boolean):Promise<void>;renew():Promise<void>;recover(automatic?:boolean):Promise<void>;seek(seconds:number):void;
}
