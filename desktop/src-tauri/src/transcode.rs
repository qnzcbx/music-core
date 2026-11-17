//! 安装包附带的工具；不搜索 PATH，不把原格式下载变成整首解码。
use serde_json::{json, Value};
use std::{
    path::{Path, PathBuf},
    process::Stdio,
    time::Duration,
};
use tokio::{io::AsyncReadExt, process::Command};

pub fn available(dir: &Path) -> bool {
    dir.join("ffmpeg.exe").is_file() && dir.join("ffprobe.exe").is_file()
}
fn command(path: PathBuf) -> Command {
    let mut cmd = Command::new(path);
    cmd.stdin(Stdio::null())
        .stderr(Stdio::null())
        .kill_on_drop(true);
    #[cfg(windows)]
    cmd.creation_flags(0x08000000);
    cmd
}
async fn probe(dir: &Path, path: &Path) -> Result<Value, String> {
    let output = command(dir.join("ffprobe.exe"))
        .args([
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name,sample_rate,channels,duration,bit_rate:format=duration",
            "-of",
            "json",
        ])
        .arg(path)
        .output()
        .await
        .map_err(|_| "conversion_unavailable")?;
    if !output.status.success() || output.stdout.len() > 65536 {
        return Err("conversion_probe_failed".into());
    }
    serde_json::from_slice(&output.stdout).map_err(|_| "conversion_probe_failed".into())
}
fn number(value: &Value) -> f64 {
    value
        .as_f64()
        .or_else(|| value.as_str().and_then(|s| s.parse().ok()))
        .unwrap_or(0.0)
}
// 数实际输出的 PCM 样本，避免仅凭退出码或容器时长认定完整。
async fn decode(dir: &Path, path: &Path, rate: u64, channels: u64) -> Result<u64, String> {
    let mut child = command(dir.join("ffmpeg.exe"))
        .args([
            "-nostdin",
            "-v",
            "error",
            "-xerror",
            "-err_detect",
            "crccheck+bitstream+buffer+explode",
            "-i",
        ])
        .arg(path)
        .args([
            "-map",
            "0:a:0",
            "-vn",
            "-c:a",
            "pcm_s32le",
            "-f",
            "s32le",
            "pipe:1",
        ])
        .stdout(Stdio::piped())
        .spawn()
        .map_err(|_| "conversion_unavailable")?;
    let mut stdout = child.stdout.take().ok_or("conversion_decode_failed")?;
    let mut buffer = vec![0u8; 65536];
    let mut bytes = 0u64;
    loop {
        let n = stdout
            .read(&mut buffer)
            .await
            .map_err(|_| "conversion_decode_failed")?;
        if n == 0 {
            break;
        }
        bytes += n as u64;
        if bytes > 4 * 1024 * 1024 * 1024u64 {
            return Err("media_capacity".into());
        }
    }
    let status = child.wait().await.map_err(|_| "conversion_decode_failed")?;
    if !status.success() || channels == 0 || rate == 0 || bytes == 0 || bytes % (channels * 4) != 0
    {
        return Err("conversion_decode_failed".into());
    }
    Ok(bytes / (channels * 4))
}
pub async fn convert(
    dir: &Path,
    source: &Path,
    output: &Path,
    bitrate: u64,
) -> Result<Value, String> {
    tokio::time::timeout(
        Duration::from_secs(600),
        convert_inner(dir, source, output, bitrate),
    )
    .await
    .map_err(|_| "conversion_timeout".to_string())?
}
async fn convert_inner(
    dir: &Path,
    source: &Path,
    output: &Path,
    bitrate: u64,
) -> Result<Value, String> {
    if !available(dir) || ![320000, 192000].contains(&bitrate) {
        return Err("conversion_unavailable".into());
    }
    let metadata = probe(dir, source).await?;
    let stream = &metadata["streams"][0];
    let rate = number(&stream["sample_rate"]) as u64;
    let channels = number(&stream["channels"]) as u64;
    let declared = number(&stream["duration"]).max(number(&metadata["format"]["duration"]));
    if stream["codec_name"] != "flac" || channels == 0 || channels > 2 || declared <= 0.0 {
        return Err("conversion_source_invalid".into());
    }
    // 源只探查格式与 STREAMINFO 时长；不在转换前整首解码，也不因尾部杂字节拒绝。
    let duration = declared;
    // output 由任务独占创建，转换只覆盖自己拥有的临时文件。
    let output_rate = if [32000, 44100, 48000].contains(&rate) {
        rate
    } else {
        rate.min(48000)
    };
    let status = command(dir.join("ffmpeg.exe"))
        .args(["-nostdin", "-v", "error", "-i"])
        .arg(source)
        .args([
            "-map",
            "0:a:0",
            "-vn",
            "-map_metadata",
            "-1",
            "-c:a",
            "libmp3lame",
            "-b:a",
        ])
        .arg(bitrate.to_string())
        .arg("-ar")
        .arg(output_rate.to_string())
        .arg("-fs")
        .arg(crate::downloads::MAX_DOWNLOAD_BYTES.to_string())
        .args(["-f", "mp3", "-y"])
        .arg(output)
        .status()
        .await
        .map_err(|_| "conversion_unavailable")?;
    if !status.success() {
        return Err("conversion_encode_failed".into());
    }
    let metadata = probe(dir, output).await?;
    let stream = &metadata["streams"][0];
    let output_channels = number(&stream["channels"]) as u64;
    if stream["codec_name"] != "mp3"
        || (number(&stream["bit_rate"]) - bitrate as f64).abs() > 1000.0
        || output_channels != channels
    {
        return Err("conversion_output_invalid".into());
    }
    let output_samples = decode(dir, output, output_rate, output_channels).await?;
    let output_duration = output_samples as f64 / output_rate as f64;
    if (output_duration - duration).abs() > 2.0 / output_rate as f64 {
        return Err("conversion_output_incomplete".into());
    }
    let size = tokio::fs::metadata(output)
        .await
        .map_err(|_| "file_io_error")?
        .len();
    Ok(
        json!({"extension":"mp3","container":"mpeg-audio","codec":"mp3","lossless":false,
        "bitrateBps":bitrate,"sampleRateHz":output_rate,"sizeBytes":size,"durationSeconds":output_duration,
        "decodedSamples":output_samples,"sourceDurationSeconds":declared,"sourceSampleRateHz":rate}),
    )
}
