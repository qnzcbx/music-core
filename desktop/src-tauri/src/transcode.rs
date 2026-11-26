//! 安装包附带的工具；不搜索 PATH，不把原格式下载变成整首解码。
use serde_json::{json, Value};
use std::{
    path::{Path, PathBuf},
    process::{ExitStatus, Stdio},
    time::Duration,
};
use tokio::{
    io::AsyncReadExt,
    process::{ChildStdout, Command},
    time::Instant,
};
use tokio_util::sync::CancellationToken;

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
async fn run_child<T>(
    command: &mut Command,
    cancel: &CancellationToken,
    deadline: Instant,
    io_error: &'static str,
    read: impl AsyncFnOnce(Option<ChildStdout>) -> Result<T, String>,
) -> Result<(ExitStatus, T), String> {
    if cancel.is_cancelled() {
        return Err("cancelled".into());
    }
    if Instant::now() >= deadline {
        return Err("conversion_timeout".into());
    }
    let mut child = command.spawn().map_err(|_| "conversion_unavailable")?;
    let stdout = child.stdout.take();
    // 等待进程时并行读取 stdout，避免子进程因管道写满而无法退出。
    let result = tokio::select! {
        biased;
        _ = cancel.cancelled() => Err("cancelled".into()),
        _ = tokio::time::sleep_until(deadline) => Err("conversion_timeout".into()),
        result = async {
            tokio::try_join!(
                async { child.wait().await.map_err(|_| io_error.to_string()) },
                read(stdout)
            )
        } => result,
    };
    if result.is_err() {
        // select 已释放管道读取及 wait 的借用。调用方须等待本进程真正退出后再碰临时文件。
        let _ = child.start_kill();
        if !matches!(
            tokio::time::timeout(Duration::from_secs(2), child.wait()).await,
            Ok(Ok(_))
        ) {
            eprintln!("转换子进程终止后无法确认退出");
            return Err("conversion_cleanup_failed".into());
        }
    }
    result
}

async fn probe(
    dir: &Path,
    path: &Path,
    cancel: &CancellationToken,
    deadline: Instant,
) -> Result<Value, String> {
    let mut cmd = command(dir.join("ffprobe.exe"));
    cmd.args([
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
    .stdout(Stdio::piped());
    let (status, output) = run_child(
        &mut cmd,
        cancel,
        deadline,
        "conversion_probe_failed",
        async |stdout| {
            let mut output = Vec::new();
            stdout
                .ok_or("conversion_probe_failed")?
                .take(65537)
                .read_to_end(&mut output)
                .await
                .map_err(|_| "conversion_probe_failed")?;
            if output.len() > 65536 {
                return Err("conversion_probe_failed".into());
            }
            Ok(output)
        },
    )
    .await?;
    if !status.success() {
        return Err("conversion_probe_failed".into());
    }
    serde_json::from_slice(&output).map_err(|_| "conversion_probe_failed".into())
}
fn number(value: &Value) -> f64 {
    value
        .as_f64()
        .or_else(|| value.as_str().and_then(|s| s.parse().ok()))
        .unwrap_or(0.0)
}
// 数实际输出的 PCM 样本，避免仅凭退出码或容器时长认定完整。
async fn decode(
    dir: &Path,
    path: &Path,
    rate: u64,
    channels: u64,
    cancel: &CancellationToken,
    deadline: Instant,
) -> Result<u64, String> {
    let mut cmd = command(dir.join("ffmpeg.exe"));
    cmd.args([
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
    .stdout(Stdio::piped());
    let (status, bytes) = run_child(
        &mut cmd,
        cancel,
        deadline,
        "conversion_decode_failed",
        async |stdout| {
            let mut stdout = stdout.ok_or("conversion_decode_failed")?;
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
            Ok(bytes)
        },
    )
    .await?;
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
    cancel: &CancellationToken,
) -> Result<Value, String> {
    convert_before(
        dir,
        source,
        output,
        bitrate,
        cancel,
        Instant::now() + Duration::from_secs(600),
    )
    .await
}

async fn convert_before(
    dir: &Path,
    source: &Path,
    output: &Path,
    bitrate: u64,
    cancel: &CancellationToken,
    deadline: Instant,
) -> Result<Value, String> {
    if !available(dir) || ![320000, 192000].contains(&bitrate) {
        return Err("conversion_unavailable".into());
    }
    let metadata = probe(dir, source, cancel, deadline).await?;
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
    let mut cmd = command(dir.join("ffmpeg.exe"));
    cmd.args(["-nostdin", "-v", "error", "-i"])
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
        .stdout(Stdio::null());
    let (status, ()) = run_child(
        &mut cmd,
        cancel,
        deadline,
        "conversion_unavailable",
        async |_| Ok(()),
    )
    .await?;
    if !status.success() {
        return Err("conversion_encode_failed".into());
    }
    let metadata = probe(dir, output, cancel, deadline).await?;
    let stream = &metadata["streams"][0];
    let output_channels = number(&stream["channels"]) as u64;
    if stream["codec_name"] != "mp3"
        || (number(&stream["bit_rate"]) - bitrate as f64).abs() > 1000.0
        || output_channels != channels
    {
        return Err("conversion_output_invalid".into());
    }
    let output_samples =
        decode(dir, output, output_rate, output_channels, cancel, deadline).await?;
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

#[cfg(all(test, windows))]
mod tests {
    use super::*;
    use windows::Win32::{
        Foundation::{CloseHandle, HANDLE, WAIT_OBJECT_0, WAIT_TIMEOUT},
        System::Threading::{OpenProcess, WaitForSingleObject, PROCESS_SYNCHRONIZE},
    };

    struct ProcessHandle(HANDLE);
    impl Drop for ProcessHandle {
        fn drop(&mut self) {
            // SAFETY: 测试通过 OpenProcess 获得并独占该句柄。
            let _ = unsafe { CloseHandle(self.0) };
        }
    }

    #[tokio::test]
    async fn cancellation_and_deadline_reap_the_actual_child_at_each_stage() {
        let root = tempfile::tempdir().unwrap();
        let source_code = root.path().join("fixture.rs");
        std::fs::write(&source_code, r##"
use std::{env, fs, path::Path, thread, time::Duration};

fn main() {
    let args: Vec<_> = env::args_os().collect();
    let executable = Path::new(&args[0]);
    let dir = executable.parent().unwrap();
    let target = args.last().unwrap();
    let stage = if executable.file_stem().unwrap() == "ffprobe" {
        if Path::new(target).ends_with("source.flac") { "source-probe" } else { "output-probe" }
    } else if target == "pipe:1" { "decode" } else { "encode" };
    if fs::read_to_string(dir.join("hold")).unwrap() == stage {
        fs::write(dir.join("pid"), std::process::id().to_string()).unwrap();
        thread::sleep(Duration::from_secs(60));
        return;
    }
    match stage {
        "source-probe" => println!("{}", r#"{ "streams": [{ "codec_name": "flac", "channels": 1, "sample_rate": 44100, "duration": 1 }] }"#),
        "output-probe" => println!("{}", r#"{ "streams": [{ "codec_name": "mp3", "channels": 1, "bit_rate": 320000 }] }"#),
        "encode" => fs::write(target, b"test MP3").unwrap(),
        _ => unreachable!(),
    }
}
"##).unwrap();
        // 测试程序模拟工具输出，停在哪一阶段由目录内的标记决定。
        let built =
            std::process::Command::new(std::env::var_os("RUSTC").unwrap_or_else(|| "rustc".into()))
                .arg(&source_code)
                .arg("-o")
                .arg(root.path().join("ffprobe.exe"))
                .output()
                .unwrap();
        assert!(
            built.status.success(),
            "{}",
            String::from_utf8_lossy(&built.stderr)
        );
        std::fs::copy(
            root.path().join("ffprobe.exe"),
            root.path().join("ffmpeg.exe"),
        )
        .unwrap();
        let source = root.path().join("source.flac");
        let output = root.path().join("output.mp3");
        let marker = root.path().join("pid");
        std::fs::write(&source, b"test FLAC").unwrap();

        let other_dir = tempfile::tempdir().unwrap();
        let other_exe = other_dir.path().join("ffprobe.exe");
        std::fs::copy(root.path().join("ffprobe.exe"), &other_exe).unwrap();
        std::fs::write(other_dir.path().join("hold"), "source-probe").unwrap();
        let mut other = command(other_exe)
            .arg(&source)
            .stdout(Stdio::null())
            .spawn()
            .unwrap();

        for (stage, timeout) in [
            ("source-probe", false),
            ("encode", false),
            ("output-probe", false),
            ("decode", false),
            ("encode", true),
        ] {
            if marker.exists() {
                std::fs::remove_file(&marker).unwrap();
            }
            std::fs::write(root.path().join("hold"), stage).unwrap();
            let cancel = CancellationToken::new();
            let deadline = Instant::now() + Duration::from_secs(if timeout { 3 } else { 15 });
            let control = async {
                let process = tokio::time::timeout_at(deadline, async {
                    loop {
                        if let Some(pid) = std::fs::read_to_string(&marker)
                            .ok()
                            .and_then(|text| text.parse::<u32>().ok())
                        {
                            // SAFETY: 仅打开测试程序刚报告的 PID，访问权限仅限等待。
                            let handle =
                                unsafe { OpenProcess(PROCESS_SYNCHRONIZE, false, pid) }.unwrap();
                            break ProcessHandle(handle);
                        }
                        tokio::time::sleep(Duration::from_millis(5)).await;
                    }
                })
                .await
                .unwrap();
                // 0ms 检查确认拿到的是仍在运行的实例。
                assert_eq!(unsafe { WaitForSingleObject(process.0, 0) }, WAIT_TIMEOUT);
                if !timeout {
                    cancel.cancel();
                }
                process
            };
            let (result, process) = tokio::join!(
                convert_before(root.path(), &source, &output, 320000, &cancel, deadline),
                control
            );
            assert_eq!(
                result.unwrap_err(),
                if timeout {
                    "conversion_timeout"
                } else {
                    "cancelled"
                },
                "{stage}"
            );
            assert_eq!(
                unsafe { WaitForSingleObject(process.0, 0) },
                WAIT_OBJECT_0,
                "{stage}"
            );
            assert!(other.try_wait().unwrap().is_none(), "独立进程不应受影响");
        }
        other.kill().await.unwrap();
    }
}
