use std::fs::File;
use std::io::{self, Read};
use std::path::Path;

use crate::cancellation::CancellationToken;
use crate::hashing::DEFAULT_BUFFER_SIZE;

pub fn files_equal(
    path_a: &Path,
    path_b: &Path,
    cancel_token: Option<&CancellationToken>,
) -> Result<bool, io::Error> {
    if let Some(token) = cancel_token {
        if token.is_set() {
            return Err(io::Error::new(io::ErrorKind::Interrupted, "Cancelled"));
        }
    }

    let mut file_a = File::open(path_a)?;
    let mut file_b = File::open(path_b)?;

    // Fast check: if metadata sizes differ, they cannot be equal.
    let meta_a = file_a.metadata()?;
    let meta_b = file_b.metadata()?;
    if meta_a.len() != meta_b.len() {
        return Ok(false);
    }

    let mut buf_a = vec![0u8; DEFAULT_BUFFER_SIZE];
    let mut buf_b = vec![0u8; DEFAULT_BUFFER_SIZE];

    loop {
        if let Some(token) = cancel_token {
            if token.is_set() {
                return Err(io::Error::new(io::ErrorKind::Interrupted, "Cancelled"));
            }
        }

        let n_a = file_a.read(&mut buf_a)?;
        let n_b = file_b.read(&mut buf_b)?;

        if n_a != n_b {
            return Ok(false);
        }

        if n_a == 0 {
            // EOF reached on both files simultaneously and all bytes matched.
            return Ok(true);
        }

        if buf_a[..n_a] != buf_b[..n_b] {
            return Ok(false);
        }
    }
}
