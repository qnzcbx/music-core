import test from 'node:test';
import assert from 'node:assert/strict';
import { downloadQualitySummary } from '../src/utils/download-quality.ts';

test('下载摘要只展示已知格式、码率和音源总大小', () => {
  assert.equal(downloadQualitySummary({codec:'aac',bitrateBps:96000,sampleRateHz:44100,sizeBytes:3670016}), 'AAC · 96 kbps · 3.5 MB');
  assert.equal(downloadQualitySummary({codec:'flac',sizeBytes:53372518,lossless:true}), 'FLAC · 50.9 MB');
  assert.equal(downloadQualitySummary({codec:'flac',sampleRateHz:192000}), 'FLAC');
  assert.equal(downloadQualitySummary({codec:'aac',bitrateBps:96000}), 'AAC · 96 kbps');
  assert.equal(downloadQualitySummary({}), '');
  assert.equal(downloadQualitySummary(null), '');
});
