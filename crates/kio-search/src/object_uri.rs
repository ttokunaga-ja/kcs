//! Object reference URIs and the image references embedded in normalized
//! Markdown (08-evidence-pointer-spec.md §2.3, 05-runtime.md §1.7).
//!
//! `kio://<scope_id>/object/<type>/<hash>` names a content-addressed object and
//! nothing more. It is **not** an Evidence Pointer: it carries no commit, tree,
//! or path, so it supports neither time-travel nor `kio evidence verify`. That
//! asymmetry is the reason a search hit on an image still anchors its
//! `evidence_pointer` to the referencing chunk and exposes the image only as
//! `payload_uri` / `related_images[]` (05-runtime.md §1.7).

use serde::{Deserialize, Serialize};

use crate::evidence::validate_full_hash;
use crate::{Result, SearchError};

/// The literal second path segment that distinguishes an object reference from
/// an Evidence Pointer URI (whose second segment is always a `sha256:` commit).
pub const OBJECT_SEGMENT: &str = "object";
pub const IMAGE_OBJECT_TYPE: &str = "image";

const OBJECT_URI_REQUIREMENT: &str =
    "object URI must be kio://<scope_id>/object/<type>/<hash> with a full sha256 hash";

/// A `kio://<scope_id>/object/<type>/<hash>` reference whose grammar has been
/// checked. Borrowed so callers cannot swap in unvalidated input afterwards
/// (same discipline as [`crate::evidence::ValidatedHash`]).
///
/// The type is **not** restricted here — 08 §2.3 keeps the grammar generic and
/// leaves the accepted-type policy to each consumer (MVP issues and accepts
/// `image` only; `kio open` enforces that at its own boundary).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ObjectUri<'a> {
    scope_id: &'a str,
    object_type: &'a str,
    hash: &'a str,
}

impl<'a> ObjectUri<'a> {
    pub fn scope_id(self) -> &'a str {
        self.scope_id
    }

    pub fn object_type(self) -> &'a str {
        self.object_type
    }

    /// The `sha256:`-prefixed object hash, exactly as written in the URI.
    pub fn hash(self) -> &'a str {
        self.hash
    }

    pub fn is_image(self) -> bool {
        self.object_type == IMAGE_OBJECT_TYPE
    }
}

/// Parses an object reference URI.
///
/// The input is treated as opaque (08 §2.3): the `scope_id` is returned with its
/// case preserved and is never normalized, so a fork copy carrying the original
/// scope's id round-trips unchanged and stays resolvable by hash.
pub fn parse_object_uri(uri: &str) -> Result<ObjectUri<'_>> {
    let rest = uri
        .strip_prefix("kio://")
        .ok_or_else(|| SearchError::Evidence(OBJECT_URI_REQUIREMENT.to_owned()))?;
    // Object URIs carry no query string; `?` would smuggle bytes past the
    // grammar check and into whatever resolves the hash.
    if rest.contains('?') {
        return Err(SearchError::Evidence(OBJECT_URI_REQUIREMENT.to_owned()));
    }
    let parts = rest.split('/').collect::<Vec<_>>();
    let [scope_id, OBJECT_SEGMENT, object_type, hash] = parts[..] else {
        return Err(SearchError::Evidence(OBJECT_URI_REQUIREMENT.to_owned()));
    };
    if scope_id.is_empty() || object_type.is_empty() {
        return Err(SearchError::Evidence(OBJECT_URI_REQUIREMENT.to_owned()));
    }
    validate_full_hash(hash)
        .map_err(|_| SearchError::Evidence(OBJECT_URI_REQUIREMENT.to_owned()))?;
    Ok(ObjectUri {
        scope_id,
        object_type,
        hash,
    })
}

/// One image referenced by a chunk body, as emitted in `related_images[]`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RelatedImage {
    pub image_uri: String,
    pub order: usize,
}

/// Extracts the image object URIs a chunk body references, in order of first
/// appearance (05-runtime.md §1.7).
///
/// This is the exact inverse of the Markdown image-target substitution that
/// writes these URIs in the first place (`replace_image_placeholders` /
/// `next_markdown_image_target` in `kio-adapter`'s OCR path, 07 §5.2), so the
/// two scan with the same discipline: `![` → the first following `](` → the
/// first following `)`.
///
/// Deterministic, allocation-light, and inference-free — no index is consulted
/// and no existence check is performed. `related_images[]` enumerates
/// references, not live objects: a purged image can still be named by a chunk
/// body, and `kio open` is what terminates that case (05-runtime.md §1.7).
///
/// Anything that does not parse is dropped rather than guessed at (fail-empty).
/// A chunk is a byte span of a normalized unit (03 §8.1), so a `[chunking]`
/// boundary can cut a reference in half; returning a URI built from a truncated
/// hash would be worse than returning nothing.
///
/// # Why this is stricter than `collect_unit_image_references`
///
/// `kio-cli`'s `verify_objects::collect_unit_image_references` answers a
/// different question over the same bytes — *which image objects must stay
/// alive?* — and so scans for a bare `kio://` token anywhere in a unit, cutting
/// it at the first whitespace or `)]>"'`. Over-including is the safe direction
/// there: an extra hit only keeps a reachable object from being reported as an
/// orphan.
///
/// Here the safe direction is the opposite one. `related_images[]` is a promise
/// that the Agent has something worth opening, so a URI merely *mentioned* in
/// prose or quoted inside a fenced code block must not appear — it would hand
/// the Agent a `kio open` that fails. (Kio indexes its own `docs/`, where the
/// specification text quotes example image URIs verbatim, so this is a live
/// case and not a hypothetical one.) Requiring the full `![…](…)` image form
/// keeps the extractor pinned to what the OCR path actually emits.
#[must_use]
pub fn extract_related_images(text: &str) -> Vec<RelatedImage> {
    let mut images: Vec<RelatedImage> = Vec::new();
    let mut cursor = 0usize;
    while let Some((target_start, target_end)) = next_markdown_image_target(text, cursor) {
        cursor = target_end;
        let target = &text[target_start..target_end];
        let Ok(object) = parse_object_uri(target) else {
            continue;
        };
        if !object.is_image() {
            continue;
        }
        // Same image twice in one chunk is one reference: a duplicate tells the
        // Agent nothing new and only costs it a second `kio open`.
        if images.iter().any(|image| image.image_uri == target) {
            continue;
        }
        images.push(RelatedImage {
            image_uri: target.to_owned(),
            order: images.len(),
        });
    }
    images
}

/// Byte range of the target (the `(...)` payload) of the next Markdown image
/// at or after `cursor`. Every delimiter is ASCII, so the returned offsets are
/// always UTF-8 character boundaries.
fn next_markdown_image_target(text: &str, cursor: usize) -> Option<(usize, usize)> {
    let image_start = text[cursor..].find("![")? + cursor;
    let label_end = text[image_start + 2..].find("](")? + image_start + 2;
    let target_start = label_end + 2;
    let relative_end = text[target_start..].find(')')?;
    Some((target_start, target_start + relative_end))
}

#[cfg(test)]
mod tests {
    use super::*;

    const HASH_A: &str = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    const HASH_B: &str = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

    fn image_uri(hash: &str) -> String {
        format!("kio://scope_01J8ZQ/object/image/{hash}")
    }

    #[test]
    fn parses_a_well_formed_image_object_uri() {
        let uri = image_uri(HASH_A);
        let parsed = parse_object_uri(&uri).unwrap();
        assert_eq!(parsed.scope_id(), "scope_01J8ZQ");
        assert_eq!(parsed.object_type(), "image");
        assert_eq!(parsed.hash(), HASH_A);
        assert!(parsed.is_image());
    }

    #[test]
    fn preserves_scope_id_case_and_does_not_normalize() {
        // 08 §2.3: the URI is opaque and the authority position keeps its case;
        // registry lookup is case-sensitive (ULIDs are uppercase).
        let uri = format!("kio://Scope_01J8ZQaB/object/image/{HASH_A}");
        assert_eq!(parse_object_uri(&uri).unwrap().scope_id(), "Scope_01J8ZQaB");
    }

    #[test]
    fn rejects_evidence_pointer_uris_and_malformed_shapes() {
        // An Evidence Pointer has five segments and no `object` literal.
        assert!(
            parse_object_uri(&format!("kio://scope/{HASH_A}/{HASH_A}/{HASH_A}/{HASH_A}")).is_err()
        );
        assert!(parse_object_uri("https://example.com/object/image/x").is_err());
        assert!(parse_object_uri(&format!("kio://scope/objekt/image/{HASH_A}")).is_err());
        assert!(parse_object_uri(&format!("kio:///object/image/{HASH_A}")).is_err());
        assert!(parse_object_uri(&format!("kio://scope/object//{HASH_A}")).is_err());
        assert!(parse_object_uri(&format!("kio://scope/object/image/{HASH_A}/extra")).is_err());
        assert!(parse_object_uri(&format!("kio://scope/object/image/{HASH_A}?sv=1")).is_err());
    }

    #[test]
    fn rejects_hashes_outside_the_object_hash_grammar() {
        assert!(parse_object_uri("kio://scope/object/image/sha256:abc").is_err());
        assert!(parse_object_uri(&format!(
            "kio://scope/object/image/{}",
            HASH_A.trim_start_matches("sha256:")
        ))
        .is_err());
        // Uppercase hex is not the canonical digest form.
        assert!(parse_object_uri(&format!(
            "kio://scope/object/image/{}",
            HASH_A.to_uppercase()
        ))
        .is_err());
    }

    #[test]
    fn extracts_references_in_order_of_appearance() {
        let text = format!(
            "見出し\n\n![fig-1]({})\n\n本文が続く。\n\n![fig-2]({})\n",
            image_uri(HASH_A),
            image_uri(HASH_B)
        );
        let images = extract_related_images(&text);
        assert_eq!(
            images,
            vec![
                RelatedImage {
                    image_uri: image_uri(HASH_A),
                    order: 0
                },
                RelatedImage {
                    image_uri: image_uri(HASH_B),
                    order: 1
                },
            ]
        );
    }

    #[test]
    fn collapses_a_repeated_image_to_its_first_appearance() {
        let text = format!(
            "![logo]({a})\n\n中身\n\n![logo]({a})\n\n![other]({b})",
            a = image_uri(HASH_A),
            b = image_uri(HASH_B)
        );
        let images = extract_related_images(&text);
        assert_eq!(images.len(), 2);
        assert_eq!(images[0].image_uri, image_uri(HASH_A));
        assert_eq!(images[0].order, 0);
        assert_eq!(images[1].image_uri, image_uri(HASH_B));
        // `order` indexes the collapsed list, so it stays gap-free.
        assert_eq!(images[1].order, 1);
    }

    #[test]
    fn w3_drops_references_cut_by_a_chunk_boundary() {
        // `[chunking].max_chars` can split a unit mid-reference (03 §8.1). Each
        // truncation below must yield nothing rather than a guessed hash.
        let full = format!("前段\n\n![fig-1]({})", image_uri(HASH_A));
        for cut in [
            full.len() - 1,  // missing the closing paren
            full.len() - 20, // truncated hash
            full.len() - 40,
        ] {
            assert!(
                extract_related_images(&full[..cut]).is_empty(),
                "truncation at {cut} must not yield a reference"
            );
        }
        // A chunk that *starts* mid-reference has no `![` to anchor on.
        let tail = format!("{})\n\n後続の本文", HASH_A);
        assert!(extract_related_images(&tail).is_empty());
    }

    #[test]
    fn a_broken_reference_does_not_hide_a_later_valid_one() {
        let text = format!(
            "![bad](kio://scope/object/image/sha256:short)\n\n![good]({})",
            image_uri(HASH_B)
        );
        let images = extract_related_images(&text);
        assert_eq!(images.len(), 1);
        assert_eq!(images[0].image_uri, image_uri(HASH_B));
        assert_eq!(images[0].order, 0);
    }

    #[test]
    fn ignores_non_image_targets() {
        let text = format!(
            "![rel](./figures/a.png)\n\n[link]({})\n\n![doc](kio://scope/object/blob/{})\n",
            image_uri(HASH_A),
            HASH_B.trim_start_matches("sha256:")
        );
        // The plain link is not an image reference, the relative path is not a
        // kio URI, and `blob` is not the image type.
        assert!(extract_related_images(&text).is_empty());
    }

    #[test]
    fn ignores_uris_merely_mentioned_in_prose_or_code() {
        // Deliberately looser than `verify_objects::collect_unit_image_references`
        // (see the fn docs): that scanner answers "must this object stay alive?"
        // and counts a bare token, while `related_images[]` promises the Agent
        // something it can actually open. Kio indexes its own `docs/`, whose
        // specification text quotes example image URIs verbatim.
        let quoted = format!(
            "画像参照は `{}` の形を取る。\n\n```json\n{{ \"image_uri\": \"{}\" }}\n```\n",
            image_uri(HASH_A),
            image_uri(HASH_B)
        );
        assert!(extract_related_images(&quoted).is_empty());
    }

    #[test]
    fn handles_multibyte_bodies_without_panicking() {
        let text = format!(
            "日本語の段落です。図を参照。\n\n![図 1（全体像）]({})\n\n続きの日本語。",
            image_uri(HASH_A)
        );
        let images = extract_related_images(&text);
        assert_eq!(images.len(), 1);
        assert_eq!(images[0].image_uri, image_uri(HASH_A));
    }

    #[test]
    fn empty_and_image_free_bodies_yield_nothing() {
        assert!(extract_related_images("").is_empty());
        assert!(extract_related_images("見出しだけの本文\n\n段落。").is_empty());
    }
}
