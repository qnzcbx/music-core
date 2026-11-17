/** 根据本期新Core OpenAPI核对生成的公开契约。 */
export type Capabilities = { "search"?: boolean; "resolve"?: boolean; "lyrics"?: boolean; "download"?: boolean };
export type DownloadRequest = { album?:string|null;cover?:string|null; outputMode?:OutputMode;expectedSourceCodec?:'flac'|null; quality?:DownloadQuality; "identity": TrackIdentity; "title"?: string | null; "artist"?: string | null };
export type DownloadTask = { deliveryMode?:'browser'|'library'|'desktop';artifactUrl?:string|null;artifactExpiresAt?:number|null; album?:string|null;cover?:string|null; outputMode?:OutputMode;expectedSourceCodec?:'flac'|null;sourcePreserved?:boolean;phase?:'downloading'|'source_verifying'|'transcoding'|'output_verifying'|'publishing'|'verifying'|'completed'|null;sourceMedia?:MediaRepresentation|null;transcoded?:boolean;finalSizeBytes?:number|null; quality?:DownloadQuality;actualMedia?:MediaRepresentation|null; "id": string; "identity": TrackIdentity; "title": string | null; "artist": string | null; "status": "queued" | "resolving" | "downloading" | "completed" | "failed" | "cancelled"; "receivedBytes"?: number; "totalBytes"?: number | null; "progress"?: number | null; "filename"?: string | null; "fileId"?: string | null; "format"?: string | null; "errorCode"?: string | null; "createdAt": number; "updatedAt": number };
export type ErrorDetail = { "code": string; "message": string; "retryable": boolean };
export type ErrorResponse = { "error": ErrorDetail };
export type Health = { "status": string; "version": string; "configurationFallback": boolean };
export type LyricDocument = { "identity": TrackIdentity; "status": "synced" | "plain" | "instrumental" | "unavailable"; "lines"?: (LyricLine)[]; "plainText"?: string | null; "sourceFormat"?: string | null; "unalignedTranslation"?: string | null };
export type LyricLine = { "startMs": number; "endMs"?: number | null; "text": string; "translation"?: string | null; "romanization"?: string | null };
export type MediaRepresentation = { sampleRateHz?:number|null; "container"?: string | null; "codec"?: string | null; "contentType"?: string | null; "providerQualityId"?: string | null; "sizeBytes"?: number | null; "bitrateBps"?: number | null; "lossless"?: boolean | null };
export type OpenRequest = { "identity": TrackIdentity };
export type OpenResponse = { "playbackId": string; "streamUrl": string; "media": PublicMedia; "expiresInSeconds": number };
export type ProviderInfo = { "id": "kuwo" | "qq" | "netease" | "migu"; "name": string; "order": number; "defaultSelected": boolean; "implementationStatus"?: string; "capabilities"?: Capabilities };
export type PublicMedia = { "id": string; "identity": TrackIdentity; "protocol"?: string; "representation": MediaRepresentation; "resolvedAt": number; "validUntil"?: number | null };
export type SearchPage = { "items": (SongCandidate)[]; "nextCursor"?: string | null };
export type SearchRequest = { "providerId": string; "query": string; "limit"?: number; "cursor"?: string | null };
export type SongCandidate = { downloadAllowed?:boolean|null; "identity": TrackIdentity; "title": string; "artists"?: (string)[]; "album"?: string | null; "durationSeconds"?: number | null; "cover"?: string | null };
export type TrackIdentity = { "providerId": "kuwo" | "qq" | "netease" | "migu"; "platformId": string };
export type ProviderId = TrackIdentity["providerId"];
export type SavedDownloadFile = {title?:string|null;artist?:string|null;album?:string|null;cover?:string|null;fileId:string;filename:string;sizeBytes:number;format:string;modifiedAt:number};

export type DownloadQuality = 'auto'|'standard'|'high'|'lossless';
export type DownloadQualityOption = {conversion?:{available:boolean;reason:string}|null;quality:DownloadQuality;availability:'available'|'unavailable';representation:MediaRepresentation|null;errorCode:string|null};

export type OutputMode='original'|'mp3_320'|'mp3_192';
