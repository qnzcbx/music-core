//! 有界前缀探查与原格式保存基础检查；深度解码仅保留供离线诊断。
use serde_json::{json, Value};
use std::{io::Cursor, path::Path};
use symphonia::core::{
    codecs::*,
    formats::FormatOptions,
    io::{MediaSource, MediaSourceStream, MediaSourceStreamOptions, ReadOnlySource},
    meta::MetadataOptions,
    probe::Hint,
};

pub const PREFIX_BYTES: usize = 262_144;

pub fn satisfies(rep: &Value, quality: &str) -> bool {
    let bitrate = rep["bitrateBps"].as_u64();
    match quality {
        "auto" => true,
        "standard" => rep["lossless"] == false && bitrate.is_some_and(|n| n > 0),
        "high" => rep["lossless"] == true || bitrate.is_some_and(|n| n >= 188160),
        "lossless" => rep["lossless"] == true,
        _ => false,
    }
}
fn analyze(
    source: Box<dyn MediaSource>,
    size: Option<u64>,
    full: bool,
    expected: f64,
    mp4: bool,
    mp4_payload: Option<u64>,
) -> Result<Value, String> {
    let stream = MediaSourceStream::new(source, MediaSourceStreamOptions::default());
    let probed = symphonia::default::get_probe()
        .format(
            &Hint::new(),
            stream,
            &FormatOptions::default(),
            &MetadataOptions::default(),
        )
        .map_err(|_| "media_unavailable")?;
    let mut format = probed.format;
    let track = format.default_track().ok_or("media_unavailable")?;
    let params = track.codec_params.clone();
    let id = track.id;
    let (codec, extension, lossless) = match params.codec {
        CODEC_TYPE_MP3 => ("mp3", "mp3", false),
        CODEC_TYPE_AAC if mp4 => ("aac", "m4a", false),
        CODEC_TYPE_FLAC if !mp4 => ("flac", "flac", true),
        CODEC_TYPE_ALAC if mp4 => ("alac", "m4a", true),
        _ => return Err("capability_unsupported".into()),
    };
    let average_aac_bitrate = mp4_payload
        .filter(|_| params.codec == CODEC_TYPE_AAC && format.tracks().len() == 1)
        .and_then(|bytes| {
            let time = params.time_base?.calc_time(params.n_frames?);
            let seconds = time.seconds as f64 + time.frac;
            (seconds > 0.0).then(|| (bytes as f64 * 8.0 / seconds).round() as u64)
        });
    let mut decoder = symphonia::default::get_codecs()
        .make(&params, &DecoderOptions { verify: true })
        .map_err(|_| "media_unavailable")?;
    let mut frames = 0u64;
    let mut rate = 0u32;
    let mut encoded = 0u64;
    let mut packets = 0u64;
    loop {
        let packet = match format.next_packet() {
            Ok(packet) => packet,
            Err(symphonia::core::errors::Error::IoError(e))
                if e.kind() == std::io::ErrorKind::UnexpectedEof =>
            {
                break
            }
            Err(_) => return Err("source_verification_failed".into()),
        };
        if packet.track_id() != id {
            continue;
        }
        let audio = decoder
            .decode(&packet)
            .map_err(|_| "source_decode_failed")?;
        if rate != 0 && rate != audio.spec().rate {
            return Err("source_verification_failed".into());
        }
        rate = audio.spec().rate;
        frames += audio.frames() as u64;
        encoded += packet.data.len() as u64;
        packets += 1;
        if !full && packets >= 8 {
            break;
        }
    }
    if frames == 0 || rate == 0 {
        return Err("media_unavailable".into());
    }
    let seconds = frames as f64 / rate as f64;
    if full && (expected <= 0.0 || (seconds - expected).abs() > 2.0f64.max(expected * 0.02)) {
        return Err("source_duration_mismatch".into());
    }
    if full && decoder.finalize().verify_ok == Some(false) {
        return Err("source_checksum_failed".into());
    }
    let bitrate =
        average_aac_bitrate.unwrap_or_else(|| (encoded as f64 * 8.0 / seconds).round() as u64);
    Ok(
        json!({"codec":codec,"container":match extension {"mp3"=>"mpeg-audio","flac"=>"flac",_=>"mp4"},"extension":extension,
        "lossless":lossless,"sampleRateHz":rate,"bitrateBps":if lossless && !full {None} else {Some(bitrate)},"sizeBytes":size,"durationSeconds":if full {Some(seconds)} else {None}}),
    )
}

fn mp4_payload_size(bytes: &[u8], total: u64) -> Option<u64> {
    let mut offset = 0usize;
    loop {
        let header = bytes.get(offset..offset.checked_add(8)?)?;
        let short_size = u32::from_be_bytes(header[..4].try_into().ok()?);
        let (size, header_size) = match short_size {
            0 => (total.checked_sub(offset as u64)?, 8),
            1 => {
                let extended = bytes.get(offset.checked_add(8)?..offset.checked_add(16)?)?;
                (u64::from_be_bytes(extended.try_into().ok()?), 16)
            }
            _ => (u64::from(short_size), 8),
        };
        let end = (offset as u64).checked_add(size)?;
        if size < header_size || end > total {
            return None;
        }
        if &header[4..8] == b"mdat" {
            // 只使用覆盖文件末尾的单个媒体数据块，避免将其他容器数据计入平均码率。
            return (end == total && size > header_size).then_some(size - header_size);
        }
        offset = usize::try_from(end).ok()?;
    }
}

pub fn prefix(bytes: Vec<u8>, size: Option<u64>) -> Result<Value, String> {
    let mp4 = bytes.get(4..8) == Some(b"ftyp");
    let mp4_payload = size
        .filter(|_| mp4)
        .and_then(|total| mp4_payload_size(&bytes, total));
    let incomplete = size.map_or(bytes.len() == PREFIX_BYTES, |total| {
        total > bytes.len() as u64
    });
    let source: Box<dyn MediaSource> = if mp4 && incomplete {
        // 前缀的 mdat 长度描述整份文件。按流读取，避免把前缀末尾当成容器边界。
        Box::new(ReadOnlySource::new(Cursor::new(bytes)))
    } else {
        Box::new(Cursor::new(bytes))
    };
    analyze(source, size, false, 0.0, mp4, mp4_payload)
}
/// 原格式保存只读取有界前缀确认格式和品质，不解码整首、不扫描末帧、不核对 PCM MD5。
pub fn inspect_original(path: &Path, quality: &str) -> Result<Value, String> {
    use std::io::Read;
    let file = std::fs::File::open(path).map_err(|_| "file_io_error")?;
    let size = file.metadata().map_err(|_| "file_io_error")?.len();
    if size == 0 {
        return Err("upstream_invalid_response".into());
    }
    let mut bytes = Vec::new();
    file.take(PREFIX_BYTES as u64)
        .read_to_end(&mut bytes)
        .map_err(|_| "file_io_error")?;
    let known_header = bytes.starts_with(b"ID3")
        || bytes.starts_with(b"fLaC")
        || bytes.get(4..8) == Some(b"ftyp")
        || (bytes.len() >= 2 && bytes[0] == 255 && bytes[1] & 224 == 224);
    if !known_header {
        return Err("upstream_invalid_response".into());
    }
    let rep = prefix(bytes, Some(size))?;
    if !satisfies(&rep, quality) {
        return Err("media_unavailable".into());
    }
    Ok(rep)
}

// 深度检查仅用于独立诊断与其测试，原格式保存不得调用此函数。
#[allow(dead_code)]
pub fn inspect(path: &Path, expected: f64, quality: &str) -> Result<Value, String> {
    let mut file = std::fs::File::open(path).map_err(|_| "file_io_error")?;
    let size = file.metadata().map_err(|_| "file_io_error")?.len();
    use std::io::{Read, Seek, SeekFrom};
    let mut head = [0; 12];
    file.read_exact(&mut head)
        .map_err(|_| "source_verification_failed")?;
    file.seek(SeekFrom::Start(0)).map_err(|_| "file_io_error")?;
    let rep = analyze(
        Box::new(file),
        Some(size),
        true,
        expected,
        head.get(4..8) == Some(b"ftyp"),
        None,
    )?;
    if rep["codec"] == "mp3" {
        validate_mp3(path)?;
    }
    if !satisfies(&rep, quality) {
        return Err("media_unavailable".into());
    }
    Ok(rep)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn faststart_aac_prefix_can_end_inside_media_data() {
        // 短静音测试文件。保留 moov 和首批音频包，模拟 HTTP 只返回前缀。
        let complete = include_bytes!("../tests/fixtures/aac-faststart.m4a");
        let prefix_bytes = &complete[..complete.len() - 12];
        let rep = prefix(prefix_bytes.to_vec(), Some(complete.len() as u64)).unwrap();
        assert_eq!(rep["codec"], "aac");
        assert_eq!(rep["extension"], "m4a");
        assert_eq!(rep["sampleRateHz"], 44100);
        assert!(mp4_payload_size(prefix_bytes, complete.len() as u64).is_some());
        assert!(mp4_payload_size(prefix_bytes, complete.len() as u64 - 1).is_none());
        assert!(satisfies(&rep, "standard"));
        assert!(!satisfies(&rep, "lossless"));
        assert!(prefix(prefix_bytes[..32].to_vec(), Some(complete.len() as u64)).is_err());
    }
    #[test]
    fn truncated_mpeg_frame_is_not_normal_eof() {
        let path =
            std::env::temp_dir().join(format!("music-core-media-{}.mp3", uuid::Uuid::new_v4()));
        let mut frame = vec![0; 417];
        frame[..4].copy_from_slice(&[255, 251, 144, 0]);
        let mut bytes = frame.repeat(20);
        std::fs::write(&path, &bytes).unwrap();
        assert!(validate_mp3(&path).is_ok());
        bytes.pop();
        std::fs::write(&path, &bytes).unwrap();
        assert!(validate_mp3(&path).is_err());
        std::fs::remove_file(path).unwrap();
    }
    #[test]
    fn qualities_are_not_kuwo_cbr_rules() {
        let a = json!({"codec":"aac","lossless":false,"bitrateBps":128000});
        assert!(satisfies(&a, "standard"));
        assert!(!satisfies(&a, "high"));
        let aac_192 = json!({"codec":"aac","lossless":false,"bitrateBps":191800});
        assert!(satisfies(&aac_192, "standard"));
        assert!(!satisfies(&aac_192, "lossless"));
        let f = json!({"codec":"flac","lossless":true});
        assert!(satisfies(&f, "high"));
        assert!(satisfies(&f, "lossless"));
        assert!(!satisfies(&f, "standard"));
        assert!(prefix(b"<html>not audio</html>".to_vec(), None).is_err());
    }
}

// 解码器的正常 EOF 不能单独证明末帧完整；MP3 额外逐帧检查物理边界，支持 VBR 和 MPEG 1/2/2.5。
fn validate_mp3(path: &Path) -> Result<(), String> {
    use std::io::{Read, Seek, SeekFrom};
    let mut file = std::fs::File::open(path).map_err(|_| "file_io_error")?;
    let mut end = file.metadata().map_err(|_| "file_io_error")?.len();
    let mut h = [0u8; 10];
    file.read_exact(&mut h)
        .map_err(|_| "source_verification_failed")?;
    let mut pos = if &h[..3] == b"ID3" {
        if h[6..].iter().any(|b| b & 128 != 0) {
            return Err("source_verification_failed".into());
        }
        10 + h[6..].iter().fold(0u64, |n, b| (n << 7) | *b as u64)
            + if h[5] & 16 != 0 { 10 } else { 0 }
    } else {
        0
    };
    if pos > 1024 * 1024 {
        return Err("source_verification_failed".into());
    }
    if end >= 128 {
        file.seek(SeekFrom::Start(end - 128))
            .map_err(|_| "file_io_error")?;
        let mut tag = [0; 3];
        file.read_exact(&mut tag).map_err(|_| "file_io_error")?;
        if &tag == b"TAG" {
            end -= 128;
        }
    }
    if end >= 32 {
        file.seek(SeekFrom::Start(end - 32))
            .map_err(|_| "file_io_error")?;
        let mut tag = [0; 32];
        file.read_exact(&mut tag).map_err(|_| "file_io_error")?;
        if &tag[..8] == b"APETAGEX" {
            let length = u32::from_le_bytes(tag[12..16].try_into().unwrap()) as u64;
            if !(32..=1024 * 1024).contains(&length) || length > end - pos {
                return Err("source_verification_failed".into());
            }
            end -= length;
        }
    }
    let mut count = 0;
    while pos < end {
        file.seek(SeekFrom::Start(pos))
            .map_err(|_| "file_io_error")?;
        let mut raw = [0; 4];
        file.read_exact(&mut raw)
            .map_err(|_| "source_verification_failed")?;
        let h = u32::from_be_bytes(raw);
        let version = (h >> 19) & 3;
        let index = (h >> 12) & 15;
        let sr = (h >> 10) & 3;
        if h >> 21 != 2047
            || version == 1
            || (h >> 17) & 3 != 1
            || index == 0
            || index == 15
            || sr == 3
        {
            return Err("source_verification_failed".into());
        }
        let kbps = if version == 3 {
            [
                0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320,
            ][index as usize]
        } else {
            [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160][index as usize]
        };
        let rate = [44100, 48000, 32000][sr as usize]
            / if version == 3 {
                1
            } else if version == 2 {
                2
            } else {
                4
            };
        let length = (if version == 3 { 144 } else { 72 }) * kbps * 1000 / rate + ((h >> 9) & 1);
        pos += length as u64;
        count += 1;
        if pos > end {
            return Err("source_verification_failed".into());
        }
    }
    if count == 0 {
        return Err("source_verification_failed".into());
    }
    Ok(())
}
