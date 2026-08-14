use std::{fs, process::Command};

fn binary() -> &'static str {
    env!("CARGO_BIN_EXE_kio-eval")
}

#[test]
fn generate_corpus_subcommand_preserves_the_canonical_cli_contract() {
    let temporary = tempfile::tempdir().unwrap();
    let corpus = temporary.path().join("corpus");
    let output = Command::new(binary())
        .args(["generate-corpus", "--out"])
        .arg(&corpus)
        .output()
        .unwrap();

    assert!(output.status.success(), "{:?}", output);
    assert!(output.stderr.is_empty());
    let expected = format!(
        "[ok] コーパス生成: {}\n\
         \x20\x20\x20\x20\x20files=305 anchors=31 scopes=7\n\
         \x20\x20\x20\x20\x20\x20\x20- research    : 45 files\n\
         \x20\x20\x20\x20\x20\x20\x20- notes       : 45 files\n\
         \x20\x20\x20\x20\x20\x20\x20- downloads   : 45 files\n\
         \x20\x20\x20\x20\x20\x20\x20- projects-a  : 44 files\n\
         \x20\x20\x20\x20\x20\x20\x20- projects-b  : 43 files\n\
         \x20\x20\x20\x20\x20\x20\x20- specs       : 42 files\n\
         \x20\x20\x20\x20\x20\x20\x20- journal     : 41 files\n\
         \x20\x20\x20\x20\x20manifest: {}\n",
        corpus.display(),
        corpus.join("corpus-manifest.json").display(),
    );
    assert_eq!(String::from_utf8(output.stdout).unwrap(), expected);
    let manifest_path = corpus.join("corpus-manifest.json");
    assert!(manifest_path.is_file());
    let manifest: serde_json::Value =
        serde_json::from_slice(&fs::read(&manifest_path).unwrap()).unwrap();
    assert_eq!(manifest["generator"], "kio-eval generate-corpus");

    let nonempty = Command::new(binary())
        .args(["generate-corpus", "--out"])
        .arg(&corpus)
        .output()
        .unwrap();
    assert_eq!(nonempty.status.code(), Some(1));
    assert!(nonempty.stdout.is_empty());
    assert_eq!(
        String::from_utf8(nonempty.stderr).unwrap(),
        format!(
            "[error] 出力先が空でない: {} (--force で上書き)\n",
            corpus.display()
        )
    );
    assert!(fs::metadata(corpus.join("corpus-manifest.json")).is_ok());
}

#[test]
fn generate_corpus_requires_out_with_clap_invalid_usage() {
    let output = Command::new(binary())
        .arg("generate-corpus")
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(2));
    assert!(!output.stderr.is_empty());
}

#[test]
fn generate_corpus_accepts_a_relative_parent_path() {
    let temporary = tempfile::tempdir().unwrap();
    let working = temporary.path().join("working");
    fs::create_dir(&working).unwrap();
    let output = Command::new(binary())
        .current_dir(&working)
        .args(["generate-corpus", "--out", "../nested/corpus"])
        .output()
        .unwrap();
    assert!(output.status.success(), "{:?}", output);
    assert!(
        temporary
            .path()
            .join("nested/corpus/corpus-manifest.json")
            .is_file()
    );
}
