//! The captures in `fixtures/layout-parsing/` are what the service really sent
//! (see that directory's README for provenance), replayed through the parser.
//!
//! They exist because the mock was wrong about PaddleOCR-VL three times running
//! — the response envelope, the figure markup, the way a page ends — and CI
//! stayed green through all three, because the mock and the code agreed with
//! each other while the service disagreed with both. A hand-written body can
//! only ever encode what someone already believed. These cannot.
//!
//! The first thing they proved is the reason `pair_images_with_boxes` is gone:
//! on 2026-08-03 all three of these pages were refused, each by a different
//! count check, none of them for the raw HTML that was the expected and decided
//! refusal. The infographic page has no table at all and was still refused.

use kio_adapter::local_ocr_markdownize::parse_layout_parsing;

const INFOGRAPHIC: &str = include_str!("fixtures/layout-parsing/infographic-two-charts.json");
const INVOICE: &str = include_str!("fixtures/layout-parsing/invoice-table.json");
const SLIDE: &str = include_str!("fixtures/layout-parsing/slide-single-figure.json");

fn parse(raw: &str) -> Vec<kio_adapter::local_ocr_markdownize::LayoutParsedPage> {
    let body: serde_json::Value = serde_json::from_str(raw).expect("capture is valid JSON");
    parse_layout_parsing(&body).expect("a real response must parse")
}

/// Every image the Markdown cites gets the box its own file name carries.
///
/// The counts here are the ones that used to refuse these pages: 19 references
/// against 20 entries in `markdown.images` (a `footer_image` crop the text never
/// cites), and 19 references against figure blocks that never matched them
/// either. Reading the box off the name makes all of that irrelevant.
#[test]
fn the_infographic_page_yields_one_bbox_per_cited_image() {
    let pages = parse(INFOGRAPHIC);
    assert_eq!(pages.len(), 1);
    let images = &pages[0].images;
    assert_eq!(images.len(), 19, "19 of the 20 crops are cited in the text");
    assert!(
        images.iter().all(|image| image.bbox.is_some()),
        "every cited image carries a box"
    );
    // The two charts, by the boxes their own names encode:
    // `img_in_chart_box_60_1175_504_1367.jpg` and `…_551_1190_947_1370.jpg`.
    let boxes: Vec<_> = images.iter().filter_map(|image| image.bbox).collect();
    assert!(boxes.contains(&[60, 1175, 504, 1367]), "{boxes:?}");
    assert!(boxes.contains(&[551, 1190, 947, 1370]), "{boxes:?}");
}

/// A page whose only figure sits beside an inline `<table>`.
///
/// `table` was in the figure-label list, so this page counted 2 boxes against 1
/// cited image and was refused. A table is rendered inline, not as a crop, so it
/// never had an image to pair with.
#[test]
fn the_invoice_page_is_not_confused_by_its_table() {
    let pages = parse(INVOICE);
    let images = &pages[0].images;
    assert_eq!(images.len(), 1);
    assert!(images[0].bbox.is_some());
    // The table stays in the Markdown as raw HTML. Parsing does not judge that
    // — the v1 acceptance check does, and refuses the page (07 §5, S3-F).
    assert!(
        pages[0].markdown.contains("<table"),
        "{}",
        pages[0].markdown
    );
}

/// Crops nested inside other blocks are cited like any other image.
///
/// 10 of this page's 13 crops are icons inside table cells, with no block of
/// their own anywhere in `parsing_res_list`. Any scheme that pairs against that
/// list cannot describe them; their names can.
#[test]
fn the_slide_pages_nested_crops_still_get_their_boxes() {
    let pages = parse(SLIDE);
    let images = &pages[0].images;
    assert_eq!(images.len(), 11, "11 of the 13 crops are cited");
    assert!(images.iter().all(|image| image.bbox.is_some()));
    // An icon from inside the left-hand table: it is cited, and its box is the
    // icon's own, not the table's.
    let boxes: Vec<_> = images.iter().filter_map(|image| image.bbox).collect();
    assert!(boxes.contains(&[76, 433, 134, 489]), "{boxes:?}");
}

/// The service does not end a page the way Normalized Markdown v1 requires, and
/// these three show it disagreeing with itself: two end with one LF, one with
/// none. (A page ending in a table has been seen with two.) Parsing leaves the
/// text as sent; `unit_from_hint` is what normalizes it.
#[test]
fn the_captures_disagree_about_how_a_page_ends() {
    let endings: Vec<usize> = [INFOGRAPHIC, INVOICE, SLIDE]
        .iter()
        .map(|raw| {
            let text = parse(raw)[0].markdown.clone();
            text.len() - text.trim_end_matches('\n').len()
        })
        .collect();
    assert_eq!(endings, vec![1, 0, 1], "measured 2026-08-03");
}
