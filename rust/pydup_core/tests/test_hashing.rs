use pydup_core::byte_compare::files_equal;
use pydup_core::cancellation::CancellationToken;
use pydup_core::hashing::{compute_file_hash, compute_hashes_batch, DEFAULT_BUFFER_SIZE};
use std::fs::File;
use std::io::Write;

#[test]
fn test_small_file_hash() {
    let dir = tempfile::tempdir().unwrap();
    let file_path = dir.path().join("small.txt");
    let mut file = File::create(&file_path).unwrap();
    file.write_all(b"hello world").unwrap();

    let hash_res = compute_file_hash(&file_path, false, None, DEFAULT_BUFFER_SIZE, None).unwrap();
    assert_eq!(hash_res.len(), 64); // 32 bytes hex = 64 hex chars
}

#[test]
fn test_partial_hash() {
    let dir = tempfile::tempdir().unwrap();
    let file_path = dir.path().join("large.bin");
    let mut file = File::create(&file_path).unwrap();
    // 16 KB file
    let data = vec![0x42u8; 16384];
    file.write_all(&data).unwrap();

    let partial_hash =
        compute_file_hash(&file_path, true, Some(16384), DEFAULT_BUFFER_SIZE, None).unwrap();
    let full_hash =
        compute_file_hash(&file_path, false, Some(16384), DEFAULT_BUFFER_SIZE, None).unwrap();
    assert_eq!(partial_hash.len(), 64);
    assert_eq!(full_hash.len(), 64);
}

#[test]
fn test_byte_compare() {
    let dir = tempfile::tempdir().unwrap();
    let f1 = dir.path().join("f1.bin");
    let f2 = dir.path().join("f2.bin");
    let f3 = dir.path().join("f3.bin");

    std::fs::write(&f1, b"identical content").unwrap();
    std::fs::write(&f2, b"identical content").unwrap();
    std::fs::write(&f3, b"different content").unwrap();

    assert!(files_equal(&f1, &f2, None).unwrap());
    assert!(!files_equal(&f1, &f3, None).unwrap());
}

#[test]
fn test_cancellation() {
    let dir = tempfile::tempdir().unwrap();
    let file_path = dir.path().join("cancelled.bin");
    std::fs::write(&file_path, vec![0u8; 1024 * 1024]).unwrap();

    let token = CancellationToken::new();
    token.cancel();

    let res = compute_file_hash(&file_path, false, None, DEFAULT_BUFFER_SIZE, Some(&token));
    assert!(res.is_err());

    let batch = compute_hashes_batch(
        &[(file_path.to_str().unwrap().to_string(), 1024 * 1024, 0.0)],
        false,
        Some(1),
        Some(&token),
    );
    assert_eq!(batch[0].status, "cancelled");
}
