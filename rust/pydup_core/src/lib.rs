use pyo3::prelude::*;
use std::path::Path;

pub mod byte_compare;
pub mod cancellation;
pub mod discovery;
pub mod hashing;
pub mod models;

use cancellation::CancellationToken;
use discovery::{DiscoveredDirRecord, DiscoveredFileRecord, DiscoveryResult};
use models::HashResult;

#[pyfunction]
pub fn is_available() -> bool {
    true
}

#[pyfunction]
#[pyo3(signature = (path, partial=false, size=None, block_size=None, cancel_token=None))]
pub fn hash_file(
    py: Python<'_>,
    path: String,
    partial: bool,
    size: Option<u64>,
    block_size: Option<usize>,
    cancel_token: Option<CancellationToken>,
) -> PyResult<(Option<String>, Option<String>)> {
    let bs = block_size.unwrap_or(hashing::DEFAULT_BUFFER_SIZE);
    let token = cancel_token;

    // Release the GIL during file I/O and hashing
    let res = py.detach(|| {
        let p = Path::new(&path);
        hashing::compute_file_hash(p, partial, size, bs, token.as_ref())
    });

    match res {
        Ok(digest) => Ok((Some(digest), None)),
        Err(e) => Ok((None, Some(e.to_string()))),
    }
}

#[pyfunction]
#[pyo3(signature = (items, partial=false, max_workers=None, cancel_token=None))]
pub fn hash_files_batch(
    py: Python<'_>,
    items: Vec<(String, u64, f64)>,
    partial: bool,
    max_workers: Option<usize>,
    cancel_token: Option<CancellationToken>,
) -> PyResult<Vec<HashResult>> {
    let token = cancel_token;

    // Release GIL during Rayon parallel hashing
    let results =
        py.detach(|| hashing::compute_hashes_batch(&items, partial, max_workers, token.as_ref()));

    Ok(results)
}

#[pyfunction]
#[pyo3(signature = (path_a, path_b, cancel_token=None))]
pub fn files_equal(
    py: Python<'_>,
    path_a: String,
    path_b: String,
    cancel_token: Option<CancellationToken>,
) -> PyResult<bool> {
    let token = cancel_token;

    let res = py.detach(|| {
        let p_a = Path::new(&path_a);
        let p_b = Path::new(&path_b);
        byte_compare::files_equal(p_a, p_b, token.as_ref())
    });

    match res {
        Ok(equal) => Ok(equal),
        Err(_) => Ok(false), // Match Python OSError fallback behavior
    }
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
#[pyo3(signature = (
    folders,
    extensions=None,
    min_size=0,
    skip_hidden=false,
    follow_symlinks=false,
    protect_system=true,
    protected_paths=Vec::new(),
    include_patterns=Vec::new(),
    exclude_patterns=Vec::new(),
    cancel_token=None
))]
pub fn discover_files(
    py: Python<'_>,
    folders: Vec<String>,
    extensions: Option<Vec<String>>,
    min_size: u64,
    skip_hidden: bool,
    follow_symlinks: bool,
    protect_system: bool,
    protected_paths: Vec<String>,
    include_patterns: Vec<String>,
    exclude_patterns: Vec<String>,
    cancel_token: Option<CancellationToken>,
) -> PyResult<DiscoveryResult> {
    let token = cancel_token;

    let res = py.detach(|| {
        let config = discovery::DiscoveryConfig {
            extensions: extensions.as_deref(),
            min_size,
            skip_hidden,
            follow_symlinks,
            protect_system,
            protected_paths: &protected_paths,
            include_patterns: &include_patterns,
            exclude_patterns: &exclude_patterns,
        };
        discovery::run_discovery(&folders, &config, token.as_ref())
    });

    Ok(res)
}

#[pymodule]
fn pydup_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(is_available, m)?)?;
    m.add_function(wrap_pyfunction!(hash_file, m)?)?;
    m.add_function(wrap_pyfunction!(hash_files_batch, m)?)?;
    m.add_function(wrap_pyfunction!(files_equal, m)?)?;
    m.add_function(wrap_pyfunction!(discover_files, m)?)?;
    m.add_class::<CancellationToken>()?;
    m.add_class::<HashResult>()?;
    m.add_class::<DiscoveredFileRecord>()?;
    m.add_class::<DiscoveredDirRecord>()?;
    m.add_class::<DiscoveryResult>()?;
    Ok(())
}
