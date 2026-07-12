use std::path::PathBuf;

use kcs_core::cas::ObjectStore;
use kcs_core::scope::{InspectedObject, Repository};
use serde_json::json;

const MAX_BOUNDED_BYTES: usize = 1_048_576;

fn main() {
    let mut args = std::env::args().skip(1);
    let root = PathBuf::from(args.next().expect("temporary scope path"));
    let object_bytes = args
        .next()
        .expect("bounded object size")
        .parse::<usize>()
        .expect("object size must be an integer");

    assert!(
        (1..=MAX_BOUNDED_BYTES).contains(&object_bytes),
        "object size must be between 1 and {MAX_BOUNDED_BYTES} bytes"
    );

    std::fs::create_dir_all(&root).expect("create temporary scope root");
    let repository = Repository::init(&root).expect("initialize temporary KCS scope");
    let store = ObjectStore::new(repository.kcs_dir().to_path_buf());

    // Build the same hash-consistent on-disk state that a copied store can carry.
    let payload = vec![b'Z'; object_bytes];
    let hash = store.write_raw(&payload).expect("write bounded raw object");
    drop(payload);
    drop(store);
    drop(repository);

    // Reopen the scope before exercising the vulnerable read path.
    let repository = Repository::open(&root).expect("reopen temporary KCS scope");
    let store = ObjectStore::new(repository.kcs_dir().to_path_buf());
    let loaded = store.read_by_hash(&hash).expect("read object by hash");
    let stored_object_vec_bytes = loaded.bytes.len();
    let hash_consistent = loaded.hash == hash;
    drop(loaded);

    let inspect_reported_size_bytes = match repository.inspect(&hash).expect("inspect raw object") {
        InspectedObject::Raw { size_bytes, .. } => size_bytes,
        _ => panic!("expected a raw object"),
    };

    let malformed_hash_rejected_before_lookup = store.read_by_hash("sha256:ab").is_err();

    println!(
        "{}",
        serde_json::to_string_pretty(&json!({
            "bounded_object_bytes": object_bytes,
            "full_vec_retained_by_read_by_hash": stored_object_vec_bytes == object_bytes,
            "hash_consistent": hash_consistent,
            "inspect_reported_size_bytes": inspect_reported_size_bytes,
            "malformed_hash_rejected_before_lookup": malformed_hash_rejected_before_lookup,
            "network_used": false,
            "repository_reopened": true,
            "stored_object_vec_bytes": stored_object_vec_bytes
        }))
        .expect("serialize result")
    );
}
