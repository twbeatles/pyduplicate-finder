use std::collections::HashSet;
use std::fs;
use std::path::Path;
use std::time::UNIX_EPOCH;

use globset::{GlobBuilder, GlobSet, GlobSetBuilder};
use pyo3::prelude::*;

use crate::cancellation::CancellationToken;

#[pyclass(get_all, from_py_object)]
#[derive(Clone, Debug)]
pub struct DiscoveredFileRecord {
    pub path: String,
    pub size: u64,
    pub mtime: f64,
}

#[pymethods]
impl DiscoveredFileRecord {
    #[new]
    pub fn new(path: String, size: u64, mtime: f64) -> Self {
        Self { path, size, mtime }
    }
}

#[pyclass(get_all, from_py_object)]
#[derive(Clone, Debug)]
pub struct DiscoveredDirRecord {
    pub path: String,
    pub mtime: Option<f64>,
}

#[pymethods]
impl DiscoveredDirRecord {
    #[new]
    pub fn new(path: String, mtime: Option<f64>) -> Self {
        Self { path, mtime }
    }
}

#[pyclass(get_all, from_py_object)]
#[derive(Clone, Debug, Default)]
pub struct DiscoveryResult {
    pub files: Vec<DiscoveredFileRecord>,
    pub dirs: Vec<DiscoveredDirRecord>,
    pub errors: Vec<(String, String)>,
}

#[pymethods]
impl DiscoveryResult {
    #[new]
    pub fn new() -> Self {
        Self::default()
    }
}

#[derive(Clone, Debug)]
pub struct DiscoveryConfig<'a> {
    pub extensions: Option<&'a [String]>,
    pub min_size: u64,
    pub skip_hidden: bool,
    pub follow_symlinks: bool,
    pub protect_system: bool,
    pub protected_paths: &'a [String],
    pub include_patterns: &'a [String],
    pub exclude_patterns: &'a [String],
}

struct DiscoveryContext<'a> {
    config: &'a DiscoveryConfig<'a>,
    norm_extensions: Option<HashSet<String>>,
    include_set: Option<GlobSet>,
    exclude_set: Option<GlobSet>,
}

fn get_file_handle(path: &Path) -> Option<same_file::Handle> {
    same_file::Handle::from_path(path).ok()
}

pub fn system_time_to_mtime(t: std::time::SystemTime) -> f64 {
    match t.duration_since(UNIX_EPOCH) {
        Ok(dur) => dur.as_secs_f64(),
        Err(e) => -(e.duration().as_secs_f64()),
    }
}

fn is_hidden_or_system_name(name: &str) -> bool {
    if name.starts_with('.') {
        return true;
    }
    name.eq_ignore_ascii_case("thumbs.db")
        || name.eq_ignore_ascii_case("desktop.ini")
        || name.eq_ignore_ascii_case(".ds_store")
}

fn is_path_protected(path: &str, protected_paths: &[String]) -> bool {
    #[cfg(windows)]
    {
        let path_norm = path.replace('/', "\\").to_lowercase();
        for p in protected_paths {
            let prot_norm = p.replace('/', "\\").to_lowercase();
            if path_norm.starts_with(&prot_norm) {
                return true;
            }
        }
        false
    }
    #[cfg(not(windows))]
    {
        for p in protected_paths {
            if path.starts_with(p) {
                return true;
            }
        }
        false
    }
}

fn build_globset(patterns: &[String]) -> Option<GlobSet> {
    if patterns.is_empty() {
        return None;
    }
    let mut builder = GlobSetBuilder::new();
    let mut count = 0;
    for p in patterns {
        let pat_str = p.trim();
        if pat_str.is_empty() {
            continue;
        }
        let glob = GlobBuilder::new(pat_str)
            .case_insensitive(true)
            .literal_separator(false)
            .build();
        if let Ok(g) = glob {
            builder.add(g);
            count += 1;
        }
    }
    if count > 0 {
        builder.build().ok()
    } else {
        None
    }
}

fn matches_set(set: &GlobSet, full_path: &str, filename: &str) -> bool {
    set.is_match(full_path) || set.is_match(filename)
}

pub fn run_discovery(
    folders: &[String],
    config: &DiscoveryConfig,
    cancel_token: Option<&CancellationToken>,
) -> DiscoveryResult {
    let mut result = DiscoveryResult::default();
    let mut seen_inodes = HashSet::new();

    let norm_extensions: Option<HashSet<String>> = config.extensions.map(|exts| {
        exts.iter()
            .map(|e| e.trim().trim_start_matches('.').to_ascii_lowercase())
            .filter(|e| !e.is_empty())
            .collect()
    });

    let include_set = build_globset(config.include_patterns);
    let exclude_set = build_globset(config.exclude_patterns);

    let ctx = DiscoveryContext {
        config,
        norm_extensions,
        include_set,
        exclude_set,
    };

    for folder in folders {
        if cancel_token.is_some_and(|t| t.is_set()) {
            break;
        }

        let folder_path = Path::new(folder);
        let folder_str = folder_path.to_string_lossy().to_string();

        if config.protect_system && is_path_protected(&folder_str, config.protected_paths) {
            continue;
        }

        let folder_meta = if config.follow_symlinks {
            fs::metadata(folder_path)
        } else {
            fs::symlink_metadata(folder_path)
        };

        let folder_mtime = folder_meta
            .ok()
            .and_then(|m| m.modified().ok().map(system_time_to_mtime));
        result.dirs.push(DiscoveredDirRecord {
            path: folder_str,
            mtime: folder_mtime,
        });

        discover_recursive(
            folder_path,
            &ctx,
            cancel_token,
            &mut seen_inodes,
            &mut result,
        );
    }

    result
}

fn discover_recursive(
    dir_path: &Path,
    ctx: &DiscoveryContext,
    cancel_token: Option<&CancellationToken>,
    seen_inodes: &mut HashSet<same_file::Handle>,
    result: &mut DiscoveryResult,
) {
    if cancel_token.is_some_and(|t| t.is_set()) {
        return;
    }

    let read_dir = match fs::read_dir(dir_path) {
        Ok(rd) => rd,
        Err(e) => {
            result
                .errors
                .push((dir_path.to_string_lossy().to_string(), e.to_string()));
            return;
        }
    };

    for entry_res in read_dir {
        if cancel_token.is_some_and(|t| t.is_set()) {
            break;
        }

        let entry = match entry_res {
            Ok(e) => e,
            Err(err) => {
                result
                    .errors
                    .push((dir_path.to_string_lossy().to_string(), err.to_string()));
                continue;
            }
        };

        let path = entry.path();
        let name_os = entry.file_name();
        let name_str = name_os.to_string_lossy();

        if ctx.config.skip_hidden && is_hidden_or_system_name(&name_str) {
            continue;
        }

        let path_str = path.to_string_lossy().to_string();

        if let Some(ref ex_set) = ctx.exclude_set {
            if matches_set(ex_set, &path_str, &name_str) {
                continue;
            }
        }

        let meta = if ctx.config.follow_symlinks {
            fs::metadata(&path)
        } else {
            fs::symlink_metadata(&path)
        };

        let metadata = match meta {
            Ok(m) => m,
            Err(err) => {
                result.errors.push((path_str, err.to_string()));
                continue;
            }
        };

        let is_dir = metadata.is_dir();
        let is_file = metadata.is_file();

        if is_dir {
            if ctx.config.protect_system && is_path_protected(&path_str, ctx.config.protected_paths)
            {
                continue;
            }

            let dir_mtime = metadata.modified().ok().map(system_time_to_mtime);
            result.dirs.push(DiscoveredDirRecord {
                path: path_str,
                mtime: dir_mtime,
            });

            discover_recursive(&path, ctx, cancel_token, seen_inodes, result);
        } else if is_file {
            let size = metadata.len();
            if size < ctx.config.min_size {
                continue;
            }

            if let Some(ref exts) = ctx.norm_extensions {
                let ext = path
                    .extension()
                    .and_then(|e| e.to_str())
                    .map(|e| e.to_ascii_lowercase())
                    .unwrap_or_default();
                if !exts.contains(&ext) {
                    continue;
                }
            }

            if let Some(ref inc_set) = ctx.include_set {
                if !matches_set(inc_set, &path_str, &name_str) {
                    continue;
                }
            }

            #[cfg(windows)]
            {
                if ctx.config.follow_symlinks && metadata.is_symlink() {
                    if let Some(handle) = get_file_handle(&path) {
                        if !seen_inodes.insert(handle) {
                            continue;
                        }
                    }
                }
            }
            #[cfg(unix)]
            {
                if let Some(handle) = get_file_handle(&path) {
                    if !seen_inodes.insert(handle) {
                        continue;
                    }
                }
            }

            let mtime = metadata
                .modified()
                .ok()
                .map(system_time_to_mtime)
                .unwrap_or(0.0);

            result.files.push(DiscoveredFileRecord {
                path: path_str,
                size,
                mtime,
            });
        }
    }
}
