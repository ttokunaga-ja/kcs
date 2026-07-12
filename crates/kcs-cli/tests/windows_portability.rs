use std::fs;
use std::path::{Path, PathBuf};

use assert_cmd::Command;
use kcs_core::portable::{portable_leaf_error, portable_tag_leaf, PORTABLE_TAGS_DIRECTORY};
use serde_json::Value;

const TEST_ENV: &[&str] = &[
    "GEMINI_API_KEY",
    "MISTRAL_API_KEY",
    "KCS_FIXED_NOW",
    "KCS_TEST_GEMINI_EMBED",
    "KCS_TEST_MISTRAL_OCR",
    "KCS_TEST_MARKDOWNIZE_ADAPTER",
    "KCS_TEST_QUERY_EMBED_TRACE",
    "KCS_TEST_WINDOWS_PROFILE",
];

fn command(cwd: &Path, device: &Path) -> Command {
    let mut command = Command::cargo_bin("kcs").unwrap();
    for name in TEST_ENV {
        command.env_remove(name);
    }
    command
        .current_dir(cwd)
        .env("XDG_CONFIG_HOME", device.join("config"))
        .env("XDG_DATA_HOME", device.join("data"))
        .env("XDG_CACHE_HOME", device.join("cache"));
    command
}

fn json_success(cwd: &Path, device: &Path, args: &[&str]) -> Value {
    let output = command(cwd, device)
        .arg("--json")
        .args(args)
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    serde_json::from_slice(&output).unwrap()
}

fn json_failure(cwd: &Path, device: &Path, args: &[&str], code: i32) -> Value {
    let output = command(cwd, device)
        .arg("--json")
        .args(args)
        .assert()
        .code(code)
        .get_output()
        .stderr
        .clone();
    serde_json::from_slice(&output).unwrap()
}

#[cfg(windows)]
fn windows_no_home_command(cwd: &Path, profile: &Path) -> Command {
    let mut command = Command::cargo_bin("kcs").unwrap();
    for name in TEST_ENV {
        command.env_remove(name);
    }
    command
        .current_dir(cwd)
        .env_remove("HOME")
        .env_remove("XDG_CONFIG_HOME")
        .env_remove("XDG_DATA_HOME")
        .env_remove("XDG_CACHE_HOME")
        .env("KCS_TEST_WINDOWS_PROFILE", profile);
    command
}

#[cfg(windows)]
fn windows_no_home_json(cwd: &Path, profile: &Path, args: &[&str]) -> Value {
    let output = windows_no_home_command(cwd, profile)
        .arg("--json")
        .args(args)
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    serde_json::from_slice(&output).unwrap()
}

#[cfg(windows)]
#[test]
fn home_and_xdg_unset_use_windows_profile_without_cwd_device_state() {
    let scope = tempfile::tempdir().unwrap();
    let profile = tempfile::tempdir().unwrap();
    windows_no_home_json(scope.path(), profile.path(), &["init"]);
    fs::write(
        scope.path().join("profile.md"),
        "# Profile\n\nwindows profile fallback marker\n",
    )
    .unwrap();
    windows_no_home_json(scope.path(), profile.path(), &["index", "--approve"]);
    let search = windows_no_home_json(
        scope.path(),
        profile.path(),
        &["search", "windows profile fallback"],
    );
    let pointer = search["results"][0]["evidence_pointer"].to_string();
    fs::remove_file(scope.path().join("profile.md")).unwrap();
    let viewed = windows_no_home_json(scope.path(), profile.path(), &["view", &pointer]);

    assert!(profile
        .path()
        .join(".local/share/kcs/scope-registry.sqlite")
        .is_file());
    assert!(profile.path().join(".local/share/kcs/cursor-key").is_file());
    assert!(Path::new(viewed["path"].as_str().unwrap()).starts_with(profile.path().join(".cache")));
    for relative in ["kcs", ".config", ".local", ".cache"] {
        assert!(
            !scope.path().join(relative).exists(),
            "device state must not be created under CWD: {relative}"
        );
    }
}

#[test]
fn tag_names_use_portable_leaves_and_case_insensitive_collisions() {
    let scope = tempfile::tempdir().unwrap();
    let device = tempfile::tempdir().unwrap();
    json_success(scope.path(), device.path(), &["init"]);
    fs::write(scope.path().join("doc.md"), "first").unwrap();
    let first = json_success(scope.path(), device.path(), &["snapshot", "-m", "first"]);

    for invalid in [
        "CON",
        "AUX.txt",
        "COM¹",
        "LPT³.txt",
        "question?",
        "stream:ads",
        "trailing.",
        "trailing ",
    ] {
        let error = json_failure(scope.path(), device.path(), &["tag", invalid], 2);
        assert_eq!(error["error_code"], "KCS-E-CONFIG-USAGE-001", "{invalid:?}");
    }

    let created = json_success(scope.path(), device.path(), &["tag", "Release"]);
    let physical = PathBuf::from(created["path"].as_str().unwrap());
    assert_eq!(
        physical,
        scope
            .path()
            .canonicalize()
            .unwrap()
            .join(".kcs/refs")
            .join(PORTABLE_TAGS_DIRECTORY)
            .join(portable_tag_leaf("Release"))
    );
    let leaf = physical.file_name().unwrap().to_str().unwrap();
    assert_eq!(portable_leaf_error(leaf), None);
    assert_ne!(leaf, "Release");
    assert_eq!(
        fs::read_to_string(&physical).unwrap(),
        first["commit_hash"].as_str().unwrap()
    );

    let collision = json_failure(scope.path(), device.path(), &["tag", "release"], 2);
    assert_eq!(collision["error_code"], "KCS-E-COMMIT-TAG-001");
    json_success(scope.path(), device.path(), &["diff", "release", "HEAD"]);

    let error = json_failure(scope.path(), device.path(), &["tag", "head"], 2);
    assert_eq!(error["error_code"], "KCS-E-CONFIG-USAGE-001");
    let error = json_failure(scope.path(), device.path(), &["diff", "head", "HEAD"], 2);
    assert_eq!(error["error_code"], "KCS-E-CONFIG-USAGE-001");

    // A raw-name Unix legacy ref remains readable. If both representations exist,
    // conflicting targets fail closed rather than choosing by host enumeration.
    let legacy = scope.path().join(".kcs/refs/tags/legacy");
    fs::write(&legacy, first["commit_hash"].as_str().unwrap()).unwrap();
    json_success(scope.path(), device.path(), &["diff", "legacy", "HEAD"]);

    fs::write(scope.path().join("doc.md"), "second").unwrap();
    let second = json_success(scope.path(), device.path(), &["snapshot", "-m", "second"]);

    // A pre-upgrade raw tag whose logical name happens to look exactly like
    // another tag's canonical leaf remains its own ref. The disjoint canonical
    // directory prevents it from aliasing `Release`.
    fs::write(
        scope.path().join(".kcs/refs/tags").join(leaf),
        second["commit_hash"].as_str().unwrap(),
    )
    .unwrap();
    let legacy_copy = json_success(scope.path(), device.path(), &["tag", "legacy-copy", leaf]);
    assert_eq!(legacy_copy["commit_hash"], second["commit_hash"]);
    let canonical_copy = json_success(
        scope.path(),
        device.path(),
        &["tag", "canonical-copy", "Release"],
    );
    assert_eq!(canonical_copy["commit_hash"], first["commit_hash"]);

    fs::write(
        scope.path().join(".kcs/refs/tags/release"),
        second["commit_hash"].as_str().unwrap(),
    )
    .unwrap();
    let conflict = json_failure(scope.path(), device.path(), &["diff", "Release", "HEAD"], 4);
    assert_eq!(conflict["error_code"], "KCS-E-STORE-CORRUPT-001");
}

#[test]
fn open_cache_derives_a_portable_leaf_from_hostile_logical_basename() {
    let scope = tempfile::tempdir().unwrap();
    let device = tempfile::tempdir().unwrap();
    json_success(scope.path(), device.path(), &["init"]);
    fs::write(
        scope.path().join("report.md"),
        "# Cache\n\nportable cache marker text\n",
    )
    .unwrap();
    json_success(scope.path(), device.path(), &["index", "--approve"]);
    let search = json_success(
        scope.path(),
        device.path(),
        &["search", "portable cache marker"],
    );
    let mut pointer = search["results"][0]["evidence_pointer"].clone();
    let hostile = "CON?.PDF:stream. ";
    pointer["path_at_commit"] = Value::String(hostile.to_owned());
    fs::remove_file(scope.path().join("report.md")).unwrap();

    let pointer_text = pointer.to_string();
    let viewed = json_success(scope.path(), device.path(), &["view", &pointer_text]);
    let cache = PathBuf::from(viewed["path"].as_str().unwrap());
    assert!(cache.starts_with(device.path().join("cache/kcs/open")));
    let leaf = cache.file_name().unwrap().to_str().unwrap();
    assert_ne!(leaf, hostile);
    assert_eq!(portable_leaf_error(leaf), None, "{leaf:?}");
    assert!(cache.is_file());
}
