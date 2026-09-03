use pyo3::prelude::*;

#[pyclass(get_all)]
#[derive(Clone, Debug)]
pub struct HashResult {
    pub path: String,
    pub size: u64,
    pub mtime: f64,
    pub digest: Option<String>,
    pub status: String,
    pub error: Option<String>,
}

#[pymethods]
impl HashResult {
    #[new]
    #[pyo3(signature = (path, size, mtime, digest=None, status="ok".to_string(), error=None))]
    pub fn new(
        path: String,
        size: u64,
        mtime: f64,
        digest: Option<String>,
        status: String,
        error: Option<String>,
    ) -> Self {
        Self {
            path,
            size,
            mtime,
            digest,
            status,
            error,
        }
    }

    fn __repr__(&self) -> String {
        format!(
            "HashResult(path='{}', size={}, digest={:?}, status='{}')",
            self.path, self.size, self.digest, self.status
        )
    }

    pub fn to_dict<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, pyo3::types::PyDict>> {
        let dict = pyo3::types::PyDict::new(py);
        dict.set_item("path", &self.path)?;
        dict.set_item("size", self.size)?;
        dict.set_item("mtime", self.mtime)?;
        dict.set_item("digest", &self.digest)?;
        dict.set_item("status", &self.status)?;
        dict.set_item("error", &self.error)?;
        Ok(dict)
    }
}
