import {requestJson} from './http';
import type {TrackIdentity,LyricDocument} from '../types/core';
export const getLyrics=(identity:TrackIdentity,signal?:AbortSignal)=>requestJson<LyricDocument>('/api/lyrics?'+new URLSearchParams({...identity}),{signal});
