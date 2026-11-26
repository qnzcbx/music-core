use std::path::{Path, PathBuf};

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct FileIdentity {
    volume: u64,
    file: [u8; 16],
}

#[cfg(not(windows))]
pub fn snapshot(_: &Path, _: &[PathBuf]) -> Result<FileIdentity, &'static str> {
    Err("local_recycle_unavailable")
}
#[cfg(not(windows))]
pub fn recycle(_: &Path, _: &FileIdentity, _: &[PathBuf]) -> Result<(), &'static str> {
    Err("local_recycle_unavailable")
}

#[cfg(windows)]
pub use native::{recycle, snapshot};

#[cfg(windows)]
mod native {
    use super::*;
    use std::{
        cell::Cell,
        fs,
        os::windows::{
            ffi::{OsStrExt, OsStringExt},
            fs::{MetadataExt, OpenOptionsExt},
            io::AsRawHandle,
        },
        path::{Component, Prefix},
    };
    use windows::{
        core::{implement, Ref, HRESULT, HSTRING, PCWSTR},
        Win32::{
            Foundation::{
                ERROR_FILE_NOT_FOUND, ERROR_PATH_NOT_FOUND, ERROR_SUCCESS, E_ABORT, HANDLE,
            },
            Storage::FileSystem::*,
            System::{Com::*, Registry::*, WindowsProgramming::DRIVE_FIXED},
            UI::Shell::*,
        },
    };

    fn checked_path(path: &Path) -> Result<(), &'static str> {
        let Some(Component::Prefix(prefix)) = path.components().next() else {
            return Err("local_recycle_unsafe_path");
        };
        let drive = match prefix.kind() {
            Prefix::Disk(letter) | Prefix::VerbatimDisk(letter) => letter,
            _ => return Err("local_recycle_unsafe_path"),
        };
        if !path.is_absolute() || path.components().any(|c| matches!(c, Component::ParentDir | Component::CurDir)
            || matches!(c, Component::Normal(part) if part.encode_wide().any(|c| c == 58 || c == 0) || matches!(part.encode_wide().last(), Some(32 | 46))))
        {
            return Err("local_recycle_unsafe_path");
        }
        let root = HSTRING::from(format!("{}:\\", char::from(drive)));
        // SAFETY: 字符串以 NUL 结尾，调用期间有效。
        if unsafe { GetDriveTypeW(&root) } != DRIVE_FIXED {
            return Err("local_recycle_unsafe_path");
        }
        for part in path.ancestors() {
            if !part.has_root() {
                break;
            }
            let info = fs::symlink_metadata(part).map_err(|_| "local_recycle_changed")?;
            if info.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT.0 != 0
                || (part != path && !info.is_dir())
                || (part == path && !info.is_file())
            {
                return Err("local_recycle_unsafe_path");
            }
        }
        Ok(())
    }

    fn capture(path: &Path) -> Result<FileIdentity, &'static str> {
        checked_path(path)?;
        let file = fs::OpenOptions::new()
            .access_mode(FILE_READ_ATTRIBUTES.0)
            .custom_flags(FILE_FLAG_OPEN_REPARSE_POINT.0)
            .open(path)
            .map_err(|_| "local_recycle_changed")?;
        let metadata = file.metadata().map_err(|_| "local_recycle_changed")?;
        if !metadata.is_file() || metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT.0 != 0 {
            return Err("local_recycle_unsafe_path");
        }
        let mut id = FILE_ID_INFO::default();
        // SAFETY: 句柄和文件标识输出缓冲区在同步调用期间有效。
        unsafe {
            let handle = HANDLE(file.as_raw_handle());
            GetFileInformationByHandleEx(
                handle,
                FileIdInfo,
                (&mut id as *mut FILE_ID_INFO).cast(),
                size_of::<FILE_ID_INFO>() as u32,
            )
            .map_err(|_| "local_recycle_identity_unavailable")?;
        }
        Ok(FileIdentity {
            volume: id.VolumeSerialNumber,
            file: id.FileId.Identifier,
        })
    }

    pub fn snapshot(path: &Path, protected: &[PathBuf]) -> Result<FileIdentity, &'static str> {
        if !path
            .extension()
            .and_then(|s| s.to_str())
            .is_some_and(|ext| {
                ["mp3", "flac", "m4a"]
                    .iter()
                    .any(|allowed| ext.eq_ignore_ascii_case(allowed))
            })
        {
            return Err("local_recycle_unsafe_path");
        }
        let identity = capture(path)?;
        let canonical = path.canonicalize().map_err(|_| "local_recycle_changed")?;
        if canonical.components().skip(2).next().is_some_and(|part| {
            ["$Recycle.Bin", "System Volume Information"]
                .iter()
                .any(|name| part.as_os_str().eq_ignore_ascii_case(name))
        }) {
            return Err("local_recycle_unsafe_path");
        }
        let key = canonical.to_string_lossy().to_lowercase();
        if protected
            .iter()
            .filter_map(|root| root.canonicalize().ok())
            .any(|root| Path::new(&key).starts_with(root.to_string_lossy().to_lowercase()))
        {
            return Err("local_recycle_unsafe_path");
        }
        Ok(identity)
    }

    fn verify(
        path: &Path,
        expected: &FileIdentity,
        protected: &[PathBuf],
    ) -> Result<(), &'static str> {
        if &snapshot(path, protected)? != expected {
            return Err("local_recycle_changed");
        }
        Ok(())
    }

    fn ensure_recycle_enabled(root: &HSTRING) -> Result<(), &'static str> {
        fn disabled(hive: HKEY, key: &HSTRING, name: PCWSTR) -> Result<bool, &'static str> {
            let mut value = 0u32;
            let mut bytes = size_of::<u32>() as u32;
            // SAFETY: 注册表字符串和 DWORD 缓冲区在调用期间有效。
            let result = unsafe {
                RegGetValueW(
                    hive,
                    key,
                    name,
                    RRF_RT_REG_DWORD,
                    None,
                    Some((&mut value as *mut u32).cast()),
                    Some(&mut bytes),
                )
            };
            match result {
                ERROR_SUCCESS => Ok(value != 0),
                ERROR_FILE_NOT_FOUND | ERROR_PATH_NOT_FOUND => Ok(false),
                _ => Err("local_recycle_unavailable"),
            }
        }
        let policy = HSTRING::from(r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer");
        for hive in [HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE] {
            if disabled(hive, &policy, windows::core::w!("NoRecycleFiles"))? {
                return Err("local_recycle_unavailable");
            }
        }
        let mut volume = [0u16; 64];
        // SAFETY: 根路径及卷 GUID 缓冲区在同步调用期间有效。
        unsafe { GetVolumeNameForVolumeMountPointW(root, &mut volume) }
            .map_err(|_| "local_recycle_unavailable")?;
        let volume = String::from_utf16_lossy(
            &volume[..volume
                .iter()
                .position(|unit| *unit == 0)
                .unwrap_or(volume.len())],
        );
        let (_, guid) = volume.split_once('{').ok_or("local_recycle_unavailable")?;
        let guid = guid.split_once('}').ok_or("local_recycle_unavailable")?.0;
        let volume_key = HSTRING::from(format!(
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\BitBucket\Volume\{{{guid}}}"
        ));
        if disabled(
            HKEY_CURRENT_USER,
            &volume_key,
            windows::core::w!("NukeOnDelete"),
        )? {
            return Err("local_recycle_unavailable");
        }
        Ok(())
    }

    fn verify_shell_item(item: &IShellItem, expected_path: &Path) -> Result<(), &'static str> {
        // SAFETY: Shell 分配的路径由 CoTaskMemFree 释放。
        let path = unsafe {
            let raw = item
                .GetDisplayName(SIGDN_FILESYSPATH)
                .map_err(|_| "local_recycle_changed")?;
            if raw.is_null() {
                return Err("local_recycle_changed");
            }
            let path = PathBuf::from(std::ffi::OsString::from_wide(raw.as_wide()));
            CoTaskMemFree(Some(raw.0.cast()));
            path
        };
        if path.canonicalize().ok() != expected_path.canonicalize().ok() {
            return Err("local_recycle_changed");
        }
        Ok(())
    }

    #[implement(IFileOperationProgressSink)]
    struct Sink {
        path: PathBuf,
        expected: FileIdentity,
        protected: Vec<PathBuf>,
        pre: Cell<bool>,
        outcome: Cell<Option<Result<(), &'static str>>>,
    }

    impl IFileOperationProgressSink_Impl for Sink_Impl {
        fn PreDeleteItem(&self, flags: u32, item: Ref<IShellItem>) -> windows::core::Result<()> {
            if flags & TSF_DELETE_RECYCLE_IF_POSSIBLE.0 as u32 == 0 {
                self.outcome.set(Some(Err("local_recycle_unavailable")));
                return Err(E_ABORT.into());
            }
            let checked = item
                .as_ref()
                .ok_or("local_recycle_changed")
                .and_then(|item| verify_shell_item(item, &self.path))
                .and_then(|_| verify(&self.path, &self.expected, &self.protected));
            if let Err(error) = checked {
                self.outcome.set(Some(Err(error)));
                return Err(E_ABORT.into());
            }
            self.pre.set(true);
            Ok(())
        }

        fn PostDeleteItem(
            &self,
            flags: u32,
            _: Ref<IShellItem>,
            result: HRESULT,
            recycled: Ref<IShellItem>,
        ) -> windows::core::Result<()> {
            if !self.pre.get() {
                return Ok(());
            }
            let outcome = if [
                COPYENGINE_E_USER_CANCELLED,
                COPYENGINE_E_CANCELLED,
                COPYENGINE_S_USER_IGNORED,
            ]
            .contains(&result)
            {
                Err("local_recycle_cancelled")
            } else if result.is_err() {
                Err("local_recycle_failed")
            } else if recycled.is_some() && flags & TSF_DELETE_RECYCLE_IF_POSSIBLE.0 as u32 != 0 {
                Ok(())
            } else {
                Err("local_recycle_uncertain")
            };
            self.outcome.set(Some(outcome));
            Ok(())
        }
        fn StartOperations(&self) -> windows::core::Result<()> {
            Ok(())
        }
        fn FinishOperations(&self, _: HRESULT) -> windows::core::Result<()> {
            Ok(())
        }
        fn PreRenameItem(
            &self,
            _: u32,
            _: Ref<IShellItem>,
            _: &PCWSTR,
        ) -> windows::core::Result<()> {
            Err(E_ABORT.into())
        }
        fn PostRenameItem(
            &self,
            _: u32,
            _: Ref<IShellItem>,
            _: &PCWSTR,
            _: HRESULT,
            _: Ref<IShellItem>,
        ) -> windows::core::Result<()> {
            Ok(())
        }
        fn PreMoveItem(
            &self,
            _: u32,
            _: Ref<IShellItem>,
            _: Ref<IShellItem>,
            _: &PCWSTR,
        ) -> windows::core::Result<()> {
            Err(E_ABORT.into())
        }
        fn PostMoveItem(
            &self,
            _: u32,
            _: Ref<IShellItem>,
            _: Ref<IShellItem>,
            _: &PCWSTR,
            _: HRESULT,
            _: Ref<IShellItem>,
        ) -> windows::core::Result<()> {
            Ok(())
        }
        fn PreCopyItem(
            &self,
            _: u32,
            _: Ref<IShellItem>,
            _: Ref<IShellItem>,
            _: &PCWSTR,
        ) -> windows::core::Result<()> {
            Err(E_ABORT.into())
        }
        fn PostCopyItem(
            &self,
            _: u32,
            _: Ref<IShellItem>,
            _: Ref<IShellItem>,
            _: &PCWSTR,
            _: HRESULT,
            _: Ref<IShellItem>,
        ) -> windows::core::Result<()> {
            Ok(())
        }
        fn PreNewItem(&self, _: u32, _: Ref<IShellItem>, _: &PCWSTR) -> windows::core::Result<()> {
            Err(E_ABORT.into())
        }
        fn PostNewItem(
            &self,
            _: u32,
            _: Ref<IShellItem>,
            _: &PCWSTR,
            _: &PCWSTR,
            _: u32,
            _: HRESULT,
            _: Ref<IShellItem>,
        ) -> windows::core::Result<()> {
            Ok(())
        }
        fn UpdateProgress(&self, _: u32, _: u32) -> windows::core::Result<()> {
            Ok(())
        }
        fn ResetTimer(&self) -> windows::core::Result<()> {
            Ok(())
        }
        fn PauseTimer(&self) -> windows::core::Result<()> {
            Ok(())
        }
        fn ResumeTimer(&self) -> windows::core::Result<()> {
            Ok(())
        }
    }

    pub fn recycle(
        path: &Path,
        identity: &FileIdentity,
        protected: &[PathBuf],
    ) -> Result<(), &'static str> {
        verify(path, identity, protected)?;
        // SAFETY: COM 初始化、调用和释放均在同一阻塞工作线程。
        unsafe { CoInitializeEx(None, COINIT_APARTMENTTHREADED) }
            .ok()
            .map_err(|_| "local_recycle_unavailable")?;
        struct Apartment;
        impl Drop for Apartment {
            fn drop(&mut self) {
                unsafe { CoUninitialize() };
            }
        }
        let _apartment = Apartment;
        // Shell 需要常规 DOS 路径。路径校验已拒绝 UNC 和设备命名空间。
        let wide: Vec<_> = path.as_os_str().encode_wide().collect();
        let dos = wide.strip_prefix(&[92, 92, 63, 92]).unwrap_or(&wide);
        let name = HSTRING::from_wide(dos);
        let root = HSTRING::from_wide(&dos[..3]);
        ensure_recycle_enabled(&root)?;
        let mut bin = SHQUERYRBINFO {
            cbSize: size_of::<SHQUERYRBINFO>() as u32,
            ..Default::default()
        };
        let sink = windows::core::ComObject::new(Sink {
            path: path.to_owned(),
            expected: identity.clone(),
            protected: protected.to_owned(),
            pre: Cell::new(false),
            outcome: Cell::new(None),
        });
        let callback: IFileOperationProgressSink = sink.to_interface();
        // SAFETY: 所有 COM 对象、缓冲区及路径在调用期间有效。
        unsafe {
            SHQueryRecycleBinW(&root, &mut bin).map_err(|_| "local_recycle_unavailable")?;
            let op: IFileOperation = CoCreateInstance(&FileOperation, None, CLSCTX_INPROC_SERVER)
                .map_err(|_| "local_recycle_unavailable")?;
            op.SetOperationFlags(
                FOFX_RECYCLEONDELETE
                    | FOFX_EARLYFAILURE
                    | FOF_NOERRORUI
                    | FOF_SILENT
                    | FOF_NOCONFIRMATION
                    | FOF_NOCONFIRMMKDIR,
            )
            .map_err(|_| "local_recycle_unavailable")?;
            let item: IShellItem =
                SHCreateItemFromParsingName(&name, None).map_err(|_| "local_recycle_changed")?;
            verify_shell_item(&item, path)?;
            op.DeleteItem(&item, &callback)
                .map_err(|_| "local_recycle_failed")?;
            verify(path, identity, protected)?;
            let result = op.PerformOperations();
            if let Some(outcome) = sink.outcome.get() {
                return outcome.and_then(|_| {
                    if capture(path).is_ok_and(|current| {
                        current.volume == identity.volume && current.file == identity.file
                    }) {
                        return Err("local_recycle_uncertain");
                    }
                    Ok(())
                });
            }
            if op
                .GetAnyOperationsAborted()
                .is_ok_and(|value| value.as_bool())
            {
                return Err("local_recycle_cancelled");
            }
            if !sink.pre.get() && result.is_err() {
                return Err("local_recycle_failed");
            }
            Err("local_recycle_uncertain")
        }
    }

    #[cfg(test)]
    mod tests {
        use super::*;

        #[test]
        fn identity_rejects_replaced_and_protected_files() {
            let dir = tempfile::tempdir().unwrap();
            let path = dir.path().join("sample.mp3");
            let replacement = dir.path().join("other.mp3");
            fs::write(&path, b"before").unwrap();
            let identity = capture(&path).unwrap();
            assert_eq!(verify(&path, &identity, &[]), Ok(()));
            assert_eq!(
                verify(&path, &identity, &[dir.path().into()]),
                Err("local_recycle_unsafe_path")
            );
            fs::write(&replacement, b"after!").unwrap();
            let timestamp = fs::metadata(&path).unwrap().modified().unwrap();
            fs::OpenOptions::new()
                .write(true)
                .open(&replacement)
                .unwrap()
                .set_modified(timestamp)
                .unwrap();
            fs::rename(&path, dir.path().join("old.mp3")).unwrap();
            assert_eq!(verify(&path, &identity, &[]), Err("local_recycle_changed"));
            fs::rename(&replacement, &path).unwrap();
            let swapped = capture(&path).unwrap();
            assert_eq!(fs::metadata(&path).unwrap().modified().unwrap(), timestamp);
            assert_eq!(fs::metadata(&path).unwrap().len(), 6);
            assert_eq!(swapped.volume, identity.volume);
            assert_ne!(swapped.file, identity.file);
            assert_eq!(verify(&path, &identity, &[]), Err("local_recycle_changed"));
            fs::write(&path, b"edited").unwrap();
            assert_eq!(verify(&path, &swapped, &[]), Ok(()));
        }

        #[test]
        fn rejects_parent_junction_and_network_path() {
            let dir = tempfile::tempdir().unwrap();
            let real = dir.path().join("real");
            fs::create_dir(&real).unwrap();
            let sample = real.join("audio.mp3");
            fs::write(&sample, b"audio").unwrap();
            let link = dir.path().join("junction");
            let status = std::process::Command::new("cmd.exe")
                .args(["/d", "/c", "mklink", "/J"])
                .arg(&link)
                .arg(&real)
                .output()
                .unwrap();
            assert!(
                status.status.success(),
                "{}",
                String::from_utf8_lossy(&status.stderr)
            );
            assert_eq!(
                capture(&link.join("audio.mp3")),
                Err("local_recycle_unsafe_path")
            );
            assert_eq!(
                capture(Path::new(r"\\server\share\audio.mp3")),
                Err("local_recycle_unsafe_path")
            );
            fs::remove_dir(&link).unwrap();
            assert_eq!(fs::read(sample).unwrap(), b"audio");
        }

        #[test]
        #[ignore = "Windows 系统回收与恢复专项，使用人工临时文件"]
        fn native_recycle_and_restore() {
            let dir = tempfile::tempdir().unwrap();
            let name = format!(
                "music-core-recycle-test-{}.mp3",
                uuid::Uuid::new_v4().simple()
            );
            let path = dir.path().join(&name);
            fs::write(&path, b"isolated recycle test").unwrap();
            let identity = capture(&path).unwrap();
            let config = dir.path().join("history.json");
            let mut history =
                crate::download_history::History::open(config.clone(), dir.path().into()).unwrap();
            history
                .add(crate::download_history::SavedDownload {
                    id: "native-recycle-fixture".into(),
                    identity: serde_json::Value::Null,
                    title: "fixture".into(),
                    artist: String::new(),
                    path: path.clone(),
                    format: "mp3".into(),
                    size_bytes: fs::metadata(&path).unwrap().len(),
                    saved_at: 1,
                    source_preserved: false,
                })
                .unwrap();
            let id = crate::local_library::path_key(&path);
            fs::rename(&config, dir.path().join("history-before.json")).unwrap();
            fs::create_dir(&config).unwrap();
            assert_eq!(recycle(&path, &identity, &[]), Ok(()));
            assert!(!path.exists());
            assert!(!history.complete_recycle(&id, &["native-recycle-fixture".into()], true));
            assert!(history.list().is_empty());
            fs::remove_dir(&config).unwrap();
            assert!(history.reconcile());
            let reopened =
                crate::download_history::History::open(config, dir.path().into()).unwrap();
            assert!(reopened.list().is_empty());

            super::super::restore_test_file(&path);
            assert_eq!(fs::read(path).unwrap(), b"isolated recycle test");
        }
    }
}

#[cfg(all(test, windows))]
pub(crate) fn restore_test_file(path: &Path) {
    let script = r#"
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject Shell.Application
$items = @($shell.Namespace(10).Items() | Where-Object { $_.Name -eq $env:MUSIC_CORE_RECYCLE_TEST_NAME -or ($_.Name + $env:MUSIC_CORE_RECYCLE_TEST_EXTENSION) -eq $env:MUSIC_CORE_RECYCLE_TEST_NAME })
if ($items.Count -ne 1) { throw 'Expected exactly one test item in Recycle Bin' }
$items[0].InvokeVerb('undelete')
for ($i = 0; $i -lt 50; $i++) {
    if (Test-Path -LiteralPath $env:MUSIC_CORE_RECYCLE_TEST_PATH) { exit 0 }
    Start-Sleep -Milliseconds 100
}
throw 'Test item was not restored'
"#;
    let output = std::process::Command::new("powershell.exe")
        .args(["-NoProfile", "-NonInteractive", "-Command", script])
        .env("MUSIC_CORE_RECYCLE_TEST_NAME", path.file_name().unwrap())
        .env(
            "MUSIC_CORE_RECYCLE_TEST_EXTENSION",
            format!(".{}", path.extension().unwrap().to_string_lossy()),
        )
        .env("MUSIC_CORE_RECYCLE_TEST_PATH", path)
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
}
