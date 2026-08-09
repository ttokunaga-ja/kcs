//! Does the text a page declares actually come back?
//!
//! `experiments/ocr-verification/fixtures/generated-images/ground-truth.json`
//! states, per input image, a token printed on it. Nothing checked whether that
//! token survives OCR until 2026-08-09, and by then a capture had been shipped
//! that loses its own token — `code-editor-no-crops.json`, whose
//! `G1-01-TOKEN-4827` is in neither `markdown.text` nor any `block_content` of
//! the 613 KB the service returned. A whole class of failure was going
//! unmeasured: the response parses, the shape is right, every count agrees, and
//! the words are gone.
//!
//! # Why this file has no per-capture code
//!
//! `real_layout_parsing_captures.rs` wires each capture in by hand three times —
//! an `include_str!` const, the `captures` array, and `FIGURES`. That is exactly
//! how five captures came to sit in this directory read by nothing while the
//! suite stayed green. Repeating that structure here would rebuild the problem.
//!
//! So this reads its inputs at run time: `capture-manifest.json` says which
//! captures exist and which input each came from, and
//! [`every_capture_in_this_directory_is_read_by_this_test`] fails if the
//! directory holds a capture the manifest does not list. **Adding a capture is
//! adding a row**, and forgetting the row is a test failure rather than silence.
//!
//! # What is asserted, and what is only printed
//!
//! The assertion is binary: does the declared token appear in `markdown.text`.
//! `visible_text` recall is printed and never asserted — the infographic loses
//! 18 fragments that are all chart-internal text, which is correct behaviour and
//! the reason `related_images[]` and `kio open` exist. A pinned rate would fail
//! on healthy variation and teach everyone to edit the number.

use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};

use serde_json::Value;
use unicode_normalization::UnicodeNormalization;

/// The manifest lives beside the captures so that whoever adds one sees it. It
/// is the single name this directory scan must skip.
const MANIFEST: &str = "capture-manifest.json";

fn fixtures() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/layout-parsing")
}

/// Read from the experiment that produced the images rather than copied here:
/// a copy would be one more thing to keep in step, and the point of this test is
/// that the declaration and the measurement are not allowed to drift.
fn ground_truth_file() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../experiments/ocr-verification/fixtures/generated-images/ground-truth.json")
}

fn read_json(path: &Path) -> Value {
    let raw = fs::read_to_string(path)
        .unwrap_or_else(|error| panic!("cannot read {}: {error}", path.display()));
    serde_json::from_str(&raw)
        .unwrap_or_else(|error| panic!("{} is not valid JSON: {error}", path.display()))
}

struct Row {
    capture: String,
    source_image: String,
    /// What was **measured**, not what is wanted. See the manifest.
    token_in_markdown: bool,
    measured: String,
}

fn string_field(entry: &Value, key: &str) -> String {
    entry[key]
        .as_str()
        .unwrap_or_else(|| panic!("a capture-manifest.json row has no string `{key}`: {entry}"))
        .to_owned()
}

fn rows() -> Vec<Row> {
    let manifest = read_json(&fixtures().join(MANIFEST));
    let rows: Vec<Row> = manifest["captures"]
        .as_array()
        .expect("capture-manifest.json carries a `captures` array")
        .iter()
        .map(|entry| Row {
            capture: string_field(entry, "capture"),
            source_image: string_field(entry, "source_image"),
            token_in_markdown: entry["token_in_markdown"].as_bool().unwrap_or_else(|| {
                panic!(
                    "{} has no boolean `token_in_markdown`",
                    string_field(entry, "capture")
                )
            }),
            measured: string_field(entry, "measured"),
        })
        .collect();
    // A floor, not a count: adding captures must never fail, losing them must.
    assert!(
        rows.len() >= 9,
        "capture-manifest.json lists {} captures; it listed 9 on 2026-08-09, so \
         rows have been removed rather than added",
        rows.len()
    );
    rows
}

/// The token `ground-truth.json` declares is printed on an input image.
fn declared_token(ground_truth: &Value, source_image: &str) -> String {
    let entry = ground_truth
        .as_array()
        .expect("ground-truth.json is an array")
        .iter()
        .find(|entry| entry["file"].as_str() == Some(source_image))
        .unwrap_or_else(|| panic!("ground-truth.json declares nothing for {source_image}"));
    let tokens = entry["tokens"].as_array().expect("`tokens` is an array");
    assert_eq!(
        tokens.len(),
        1,
        "{source_image} declares {} tokens; this test reads exactly one",
        tokens.len()
    );
    tokens[0].as_str().expect("a token is a string").to_owned()
}

/// The `visible_text` fragments `ground-truth.json` claims are on the page.
fn declared_fragments(ground_truth: &Value, source_image: &str) -> Vec<String> {
    ground_truth
        .as_array()
        .expect("ground-truth.json is an array")
        .iter()
        .find(|entry| entry["file"].as_str() == Some(source_image))
        .and_then(|entry| entry["visible_text"].as_str())
        .unwrap_or_default()
        .split(';')
        .map(|fragment| fragment.trim().to_owned())
        .filter(|fragment| !fragment.is_empty())
        .collect()
}

/// NFKC, whitespace dropped, case folded.
///
/// NFKC because the service returns full-width forms where the ground truth
/// writes ASCII (`再実行？` against `再実行?`), and counting that as a miss would
/// describe the encoding rather than the OCR. Whitespace because a line break
/// inside a token is a rendering detail, not a lost token.
fn squeeze(text: &str) -> String {
    text.nfkc()
        .filter(|character| !character.is_whitespace())
        .flat_map(char::to_lowercase)
        .collect()
}

fn pages(capture: &Value) -> &[Value] {
    capture["result"]["layoutParsingResults"]
        .as_array()
        .map(Vec::as_slice)
        .expect("a /layout-parsing response carries result.layoutParsingResults")
}

/// Everything Kio would index. `markdown.text` is the only field the adapter
/// reads, so a string absent from here is absent from the archive.
fn markdown_text(capture: &Value) -> String {
    pages(capture)
        .iter()
        .filter_map(|page| page["markdown"]["text"].as_str())
        .collect::<Vec<_>>()
        .join("\n")
}

/// Everything the service recognised, whether or not it reached the Markdown.
/// The difference between this and [`markdown_text`] is the diagnosis: text here
/// but not there was read and then dropped in assembly — `header`, `footer` and
/// `number` blocks are, which is how `期限 7/10` leaves the index.
fn recognised_text(capture: &Value) -> String {
    pages(capture)
        .iter()
        .filter_map(|page| page["prunedResult"]["parsing_res_list"].as_array())
        .flatten()
        .filter_map(|block| block["block_content"].as_str())
        .collect::<Vec<_>>()
        .join("\n")
}

/// A capture placed here and named nowhere is a capture nothing reads. That is
/// not hypothetical: it is what happened to five of these for a day, and what
/// this directory's README describes happening three times before that.
#[test]
fn every_capture_in_this_directory_is_read_by_this_test() {
    let on_disk: BTreeSet<String> = fs::read_dir(fixtures())
        .expect("the fixtures directory exists")
        .map(|entry| entry.expect("a readable directory entry").file_name())
        .map(|name| name.to_string_lossy().into_owned())
        .filter(|name| name.ends_with(".json") && name != MANIFEST)
        .collect();
    let listed: BTreeSet<String> = rows().into_iter().map(|row| row.capture).collect();

    let unlisted: Vec<&String> = on_disk.difference(&listed).collect();
    assert!(
        unlisted.is_empty(),
        "these captures sit in the fixtures directory and no test reads them: \
         {unlisted:?}\n\n\
         Add a row to {MANIFEST} naming the input image it came from and whether \
         that image's declared token comes back. Placing the file is not enough — \
         being read is the whole point of keeping real captures."
    );

    let missing: Vec<&String> = listed.difference(&on_disk).collect();
    assert!(
        missing.is_empty(),
        "{MANIFEST} lists captures that are not in the directory: {missing:?}"
    );

    println!("{} captures on disk, all listed in {MANIFEST}", on_disk.len());
}

#[test]
fn every_declared_token_comes_back_exactly_as_the_manifest_measured() {
    let ground_truth = read_json(&ground_truth_file());
    let mut table = String::from(
        "\n  token   recall  capture                             declared token\n\
           \x20 ------  ------  ----------------------------------  --------------------\n",
    );

    for row in rows() {
        let capture = read_json(&fixtures().join(&row.capture));
        let token = declared_token(&ground_truth, &row.source_image);
        assert!(
            token.is_ascii(),
            "{} declares a non-ASCII token {token:?}; the comparison below assumes \
             ASCII and would need rethinking rather than loosening",
            row.source_image
        );

        let needle = squeeze(&token);
        let in_markdown = squeeze(&markdown_text(&capture)).contains(&needle);
        let recognised = squeeze(&recognised_text(&capture)).contains(&needle);

        let fragments = declared_fragments(&ground_truth, &row.source_image);
        let indexed = squeeze(&markdown_text(&capture));
        let recovered = fragments
            .iter()
            .filter(|fragment| indexed.contains(&squeeze(fragment)))
            .count();

        table.push_str(&format!(
            "  {:<6}  {:>2}/{:<3}  {:<34}  {}\n",
            if in_markdown { "yes" } else { "NO" },
            recovered,
            fragments.len(),
            row.capture,
            token
        ));

        if in_markdown == row.token_in_markdown {
            continue;
        }
        if in_markdown {
            panic!(
                "{}: {token} now appears in markdown.text, and {MANIFEST} records that it \
                 does not.\n\n\
                 This is the service getting better, and the test is saying so rather than \
                 accepting either answer. The `false` recorded on {} is a measurement of a \
                 defect, never a target — nothing is supposed to keep returning nothing.\n\n\
                 Set \"token_in_markdown\": true for this row, and say in the commit what \
                 changed: a new image digest, new weights, a re-taken capture. Do not relax \
                 this assertion to tolerate both answers, because then neither direction is \
                 detected.",
                row.capture, row.measured
            );
        }
        panic!(
            "{}: ground-truth.json declares {token} for {}, and it is no longer in \
             markdown.text.\n\n\
             Present in some block_content: {recognised}.\n\
             {}\n\n\
             Measured present on {}.",
            row.capture,
            row.source_image,
            if recognised {
                "  -> the service still read the text; the loss is in how markdown.text is \
                 assembled. `header`, `footer` and `number` blocks are dropped from it — see \
                 this directory's README."
            } else {
                "  -> the text was not recognised at all, the way the code editor page's \
                 whole window collapsed into one `content` block."
            },
            row.measured
        );
    }

    println!("{table}");
}
