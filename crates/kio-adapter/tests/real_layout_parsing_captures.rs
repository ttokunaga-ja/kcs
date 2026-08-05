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
/// The same infographic wrapped in a PDF. Wired in only here: it is the one
/// capture that shows a ratio surviving a resolution change, which is the
/// property the floor below depends on.
const INFOGRAPHIC_AS_PDF: &str =
    include_str!("fixtures/layout-parsing/infographic-two-charts-as-pdf.json");

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

/// The floor `related_images[]` is filtered at must fall between these pages'
/// decoration and these pages' figures.
///
/// `kio-cli` ships 0.25 as the smallest share of a page's largest figure that
/// earns an Agent a `kio open`, and the justification for that number is these
/// captures and nothing else -- four pages, which is thin. Thin is survivable
/// while it is checkable: if a capture is ever added whose real figure falls
/// under the floor, or whose decoration rises above it, this fails and says so
/// instead of the default quietly starting to hide something.
///
/// The constant is repeated rather than imported because `kio-cli` depends on
/// this crate and not the other way round. Changing one without the other is
/// exactly what this test exists to catch.
const SHIPPED_MIN_AREA_RATIO: f64 = 0.25;

/// Which crops are the real figures, by the boxes their names carry.
///
/// Named explicitly because no field in the response answers this. `block_label`
/// looked like it did on the infographic, where every non-chart happened to be
/// an icon -- but the invoice's only figure is spelled `image`, and it is bigger
/// than either of the infographic's charts.
const FIGURES: &[(&str, &[[i64; 4]])] = &[
    (
        "infographic",
        &[[60, 1175, 504, 1367], [551, 1190, 947, 1370]],
    ),
    (
        "infographic-as-pdf",
        &[[57, 1126, 485, 1313], [529, 1143, 911, 1316]],
    ),
    ("invoice", &[[386, 0, 1032, 189]]),
    ("slide", &[[814, 626, 1634, 904]]),
];

#[test]
fn the_captures_separate_figures_from_decoration_around_the_shipped_floor() {
    let captures = [INFOGRAPHIC, INFOGRAPHIC_AS_PDF, INVOICE, SLIDE];
    let mut smallest_figure = f64::MAX;
    let mut largest_decoration = 0.0_f64;
    for ((name, figures), raw) in FIGURES.iter().zip(captures) {
        let boxes: Vec<[i64; 4]> = parse(raw)[0]
            .images
            .iter()
            .filter_map(|image| image.bbox)
            .collect();
        let area = |bbox: &[i64; 4]| (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]);
        // The same denominator the filter uses: the largest figure on the page,
        // not the page itself. A share of the page would move with the render
        // resolution, and `infographic-as-pdf` is that exact case -- the same
        // picture resampled to 96%, where every absolute area shifts and this
        // ratio does not.
        let largest = boxes.iter().map(area).max().expect("a page with crops");
        for bbox in &boxes {
            let ratio = area(bbox) as f64 / largest as f64;
            if figures.contains(bbox) {
                smallest_figure = smallest_figure.min(ratio);
            } else {
                largest_decoration = largest_decoration.max(ratio);
            }
        }
        for figure in *figures {
            assert!(boxes.contains(figure), "{name} lost {figure:?}");
        }
    }
    assert!(
        largest_decoration < SHIPPED_MIN_AREA_RATIO,
        "decoration reaches {largest_decoration:.4} of its page's largest figure, \
         at or above the {SHIPPED_MIN_AREA_RATIO} floor -- the floor would keep it"
    );
    assert!(
        smallest_figure > SHIPPED_MIN_AREA_RATIO,
        "a real figure is only {smallest_figure:.4} of its page's largest, \
         at or below the {SHIPPED_MIN_AREA_RATIO} floor -- the floor would hide it"
    );
    // Sitting between the two groups is not enough; it has to sit between them
    // with room, or the next page of a kind nobody has captured lands on it.
    assert!(
        smallest_figure / largest_decoration > 4.0,
        "measured 2026-08-05 at 0.8257 vs 0.1070 (7.7x); now {smallest_figure:.4} \
         vs {largest_decoration:.4}"
    );
}
