//! The word lane's segmentation projection.
//!
//! 05 §1.3 drops query units shorter than 3 Unicode scalars from a mixed query.
//! That rule is not carelessness — it replaced an older one that turned the
//! particles of a natural-language query into hard filters and structurally
//! excluded the very chunks it should have found (eval M3-2/M3-3). But it
//! expresses "drop the function words" as "drop the short ones", and in
//! Japanese those are not the same set. Run `期限の確認をした議事録` through
//! `build_query_plan` and the surviving units are the whole token, `をした` and
//! `議事録`: the two content words that identify the document (`期限`, `確認`)
//! are two scalars each and fall out, while a run of pure grammar survives on
//! length alone.
//!
//! Part of speech separates them and length cannot. That is the entire argument
//! for this lane; it is not a general claim that Japanese needs a morphological
//! analyzer. Substring matching, typo tolerance, identifiers, paths and hashes
//! stay with the trigram lane, which is why this is a second table beside it and
//! never a replacement for it.
//!
//! **This projection must never reach identity.** Segmentation depends on the
//! dictionary, so a `chunk_hash` computed over segmented text would let a
//! dictionary upgrade silently change what 07 §9's first-instance-wins has
//! frozen. It lives in the derived index only, next to
//! [`crate::search_projection`], and a dictionary change is answered by a
//! reindex — never by a change of identity.

use std::borrow::Cow;
use std::sync::OnceLock;

use lindera::dictionary::{load_embedded_dictionary, DictionaryKind};
use lindera::mode::Mode;
use lindera::segmenter::Segmenter;

use crate::{IndexError, Result};

/// Top-level IPADIC parts of speech dropped from the word projection.
///
/// The same set `lindera-sqlite`'s shipped `japanese_stop_tags` filter removes,
/// taken at the top level only: the finer tags below `助詞` (`格助詞`, `係助詞`,
/// …) are all reached by dropping the parent, and enumerating them would just be
/// a longer way to say so.
const DROPPED_PARTS_OF_SPEECH: [&str; 7] = [
    "助詞",
    "助動詞",
    "接続詞",
    "記号",
    "その他",
    "フィラー",
    "非言語音",
];

/// Identifies the segmentation that produced a stored word projection.
///
/// Written into the index so a dictionary change is detectable rather than
/// silent. `lindera-ipadic`'s build pins one dated dictionary archive per crate
/// version, so the crate version names the dictionary exactly.
pub const WORD_PROJECTION_ID: &str = "lindera-5.0.2/ipadic";

/// A loaded dictionary and the segmenter over it.
pub struct WordSegmenter {
    segmenter: Segmenter,
}

impl WordSegmenter {
    /// The process-wide segmenter.
    ///
    /// Loading the dictionary is the expensive part and it is immutable once
    /// loaded, so it happens at most once per process — `index` calls this per
    /// chunk and `search` per query. A load failure is cached as a failure too:
    /// retrying it per chunk would turn one broken build into a very slow one.
    pub fn shared() -> Result<&'static Self> {
        static SEGMENTER: OnceLock<std::result::Result<WordSegmenter, String>> = OnceLock::new();
        SEGMENTER
            .get_or_init(|| Self::ipadic().map_err(|error| error.to_string()))
            .as_ref()
            .map_err(|error| IndexError::Contract(error.clone()))
    }

    fn ipadic() -> Result<Self> {
        let dictionary = load_embedded_dictionary(DictionaryKind::IPADIC).map_err(|error| {
            IndexError::Contract(format!(
                "embedded IPADIC dictionary failed to load: {error}"
            ))
        })?;
        Ok(Self {
            segmenter: Segmenter::new(Mode::Normal, dictionary, None),
        })
    }

    /// Segment `text` into the space-joined surfaces the word FTS table indexes.
    ///
    /// The caller passes text that has already been through
    /// [`crate::search_projection`], so both lanes see the same characters and a
    /// backslash the trigram lane never sees cannot become a token here either.
    ///
    /// Surfaces are joined with a single space because the word table is
    /// tokenized by `unicode61`, which splits there. The offsets this shifts are
    /// nobody's: evidence resolves against the original unit markdown, and this
    /// column is never hashed.
    pub fn project(&self, text: &str) -> Result<String> {
        let mut tokens = self
            .segmenter
            .segment(Cow::Borrowed(text))
            .map_err(|error| IndexError::Contract(format!("word segmentation failed: {error}")))?;
        let mut projected = String::with_capacity(text.len());
        for token in &mut tokens {
            let kept = {
                let details = token.details();
                let part = details.first().copied().unwrap_or("UNK");
                !DROPPED_PARTS_OF_SPEECH.contains(&part)
            };
            if !kept {
                continue;
            }
            let surface = token.surface.trim();
            if surface.is_empty() {
                continue;
            }
            if !projected.is_empty() {
                projected.push(' ');
            }
            projected.push_str(surface);
        }
        Ok(projected)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn project(text: &str) -> String {
        WordSegmenter::shared().unwrap().project(text).unwrap()
    }

    #[test]
    fn the_length_rules_casualties_survive_the_word_lane() {
        // The motivating case, measured: `期限の確認をした議事録` projects to
        // `期限 確認 し 議事 録`. `build_query_plan` keeps `をした` and discards
        // `期限` / `確認`; part of speech does exactly the opposite, and that
        // inversion is the whole reason this lane exists.
        let projected = project("期限の確認をした議事録");
        let words: Vec<&str> = projected.split(' ').collect();
        for content in ["期限", "確認"] {
            assert!(
                words.contains(&content),
                "content word {content} must survive: {projected}"
            );
        }
        for function in ["の", "を", "た", "をした"] {
            assert!(
                !words.contains(&function),
                "function word {function} must be dropped: {projected}"
            );
        }
    }

    #[test]
    fn a_query_and_a_document_segment_the_same_way() {
        // IPADIC has no entry for 議事録, so it comes apart into 議事 + 録 — on
        // BOTH sides. The lane never needs a segmentation to be *right*, only
        // for the index and the query to agree, so that agreement is what is
        // under test here rather than any particular split. A segmentation this
        // lane gets wrong costs recall in one lane; a segmentation the two sides
        // disagree about costs everything.
        let document = project("本日の議事録を確認した");
        let query = project("議事録");
        assert_eq!(query, "議事 録", "the split is recorded, not endorsed");
        for word in query.split(' ') {
            assert!(
                document.split(' ').any(|indexed| indexed == word),
                "query word {word} is absent from {document}"
            );
        }
    }

    #[test]
    fn a_compound_run_is_split_into_words() {
        let projected = project("認証仕様書を確認する");
        assert!(
            projected.split(' ').count() >= 2,
            "a compound run must not stay one token: {projected}"
        );
        assert!(projected.contains("認証"), "{projected}");
    }

    #[test]
    fn ascii_words_survive() {
        // Measured: this projects to `Ln 1 , Col 1 Spaces : 2 UTF - 8 LF
        // JavaScript`. IPADIC does not tag ASCII `,` / `:` as 記号, so part of
        // speech leaves them standing — harmless, because `unicode61` drops a
        // bare punctuation token at tokenization, and `UTF-8` is the trigram
        // lane's job anyway.
        let projected = project("Ln 1, Col 1 Spaces: 2 UTF-8 LF JavaScript");
        for word in ["Col", "Spaces", "JavaScript"] {
            assert!(
                projected.split(' ').any(|indexed| indexed == word),
                "{word} must survive: {projected}"
            );
        }
    }

    #[test]
    fn empty_text_projects_to_nothing() {
        assert_eq!(project(""), "");
    }

    #[test]
    fn the_projection_is_a_pure_function_of_its_input() {
        // The index stores this column and the query path recomputes it; if the
        // two ever disagreed the lane would silently retrieve nothing.
        let text = "期限の確認をした議事録";
        assert_eq!(project(text), project(text));
    }
}
