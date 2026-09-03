use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use pyo3::prelude::*;

#[pyclass]
#[derive(Clone, Default)]
pub struct CancellationToken {
    cancelled: Arc<AtomicBool>,
}

#[pymethods]
impl CancellationToken {
    #[new]
    pub fn new() -> Self {
        Self {
            cancelled: Arc::new(AtomicBool::new(false)),
        }
    }

    pub fn cancel(&self) {
        self.cancelled.store(true, Ordering::SeqCst);
    }

    pub fn is_cancelled(&self) -> bool {
        self.cancelled.load(Ordering::Relaxed)
    }

    pub fn reset(&self) {
        self.cancelled.store(false, Ordering::SeqCst);
    }
}

impl CancellationToken {
    pub fn is_set(&self) -> bool {
        self.cancelled.load(Ordering::Relaxed)
    }
}
