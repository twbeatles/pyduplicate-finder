use std::fs::File;
use std::io::{self, Read, Seek, SeekFrom};
use std::path::Path;

use blake2::Blake2b;
use digest::consts::U32;
use digest::Digest;
use rayon::prelude::*;

use crate::cancellation::CancellationToken;
use crate::models::HashResult;

pub const DEFAULT_BUFFER_SIZE: usize = 1024 * 1024; // 1 MiB
pub const PARTIAL_CHUNK_SIZE: usize = 4096;
pub const PARTIAL_SIZE_THRESHOLD: u64 = 8192;

type Blake2b32 = Blake2b<U32>;

/// Single file hash calculation matching Python ScanHashingMixin.get_file_hash
pub fn compute_file_hash(
    path: &Path,
    partial: bool,
    known_size: Option<u64>,
    block_size: usize,
    cancel_token: Option<&CancellationToken>,
) -> Result<String, io::Error> {
    if let Some(token) = cancel_token {
        if token.is_set() {
            return Err(io::Error::new(io::ErrorKind::Interrupted, "Cancelled"));
        }
    }

    let mut file = File::open(path)?;
    let file_size = match known_size {
        Some(s) => s,
        None => file.metadata()?.len(),
    };

    let mut hasher = Blake2b32::new();

    if partial {
        let mut head_buf = vec![0u8; PARTIAL_CHUNK_SIZE];
        let bytes_read = file.read(&mut head_buf)?;
        hasher.update(&head_buf[..bytes_read]);

        if file_size > PARTIAL_SIZE_THRESHOLD {
            if let Some(token) = cancel_token {
                if token.is_set() {
                    return Err(io::Error::new(io::ErrorKind::Interrupted, "Cancelled"));
                }
            }
            file.seek(SeekFrom::End(-(PARTIAL_CHUNK_SIZE as i64)))?;
            let mut tail_buf = vec![0u8; PARTIAL_CHUNK_SIZE];
            let bytes_read = file.read(&mut tail_buf)?;
            hasher.update(&tail_buf[..bytes_read]);
        }
    } else {
        let mut buffer = vec![0u8; block_size];
        loop {
            if let Some(token) = cancel_token {
                if token.is_set() {
                    return Err(io::Error::new(io::ErrorKind::Interrupted, "Cancelled"));
                }
            }

            let bytes_read = file.read(&mut buffer)?;
            if bytes_read == 0 {
                break;
            }
            hasher.update(&buffer[..bytes_read]);
        }
    }

    let result = hasher.finalize();
    Ok(format!("{:x}", result))
}

/// Batch hash calculation for multiple files in parallel using Rayon.
pub fn compute_hashes_batch(
    items: &[(String, u64, f64)],
    partial: bool,
    max_workers: Option<usize>,
    cancel_token: Option<&CancellationToken>,
) -> Vec<HashResult> {
    let pool_builder = rayon::ThreadPoolBuilder::new();
    let pool = if let Some(workers) = max_workers {
        pool_builder.num_threads(workers.max(1)).build().ok()
    } else {
        None
    };

    let process_items = || {
        items
            .par_iter()
            .map(|(path_str, size, mtime)| {
                if let Some(token) = cancel_token {
                    if token.is_set() {
                        return HashResult {
                            path: path_str.clone(),
                            size: *size,
                            mtime: *mtime,
                            digest: None,
                            status: "cancelled".to_string(),
                            error: Some("Operation cancelled".to_string()),
                        };
                    }
                }

                let path = Path::new(path_str);
                match compute_file_hash(
                    path,
                    partial,
                    Some(*size),
                    DEFAULT_BUFFER_SIZE,
                    cancel_token,
                ) {
                    Ok(digest) => HashResult {
                        path: path_str.clone(),
                        size: *size,
                        mtime: *mtime,
                        digest: Some(digest),
                        status: "ok".to_string(),
                        error: None,
                    },
                    Err(e) => {
                        let is_cancelled = e.kind() == io::ErrorKind::Interrupted
                            || cancel_token.is_some_and(|t| t.is_set());
                        HashResult {
                            path: path_str.clone(),
                            size: *size,
                            mtime: *mtime,
                            digest: None,
                            status: if is_cancelled {
                                "cancelled".to_string()
                            } else {
                                "error".to_string()
                            },
                            error: Some(e.to_string()),
                        }
                    }
                }
            })
            .collect::<Vec<HashResult>>()
    };

    if let Some(p) = pool {
        p.install(process_items)
    } else {
        process_items()
    }
}
