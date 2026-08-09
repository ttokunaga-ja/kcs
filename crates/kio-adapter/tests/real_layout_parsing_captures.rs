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
    // Until 2026-08-06 this asserted the opposite -- that the table stayed raw
    // HTML and the v1 check refused the whole page (07 §5, S3-F). It is now the
    // GFM notation 07 §5 asks for, with the row's own text intact and its
    // header row left empty because nothing in the response says there is one.
    let markdown = &pages[0].markdown;
    assert!(!markdown.contains("<table"), "{markdown}");
    assert!(markdown.contains("| 項目 | 数量 | OCR画像 |"), "{markdown}");
    assert!(
        markdown.contains("| | | |\n| --- | --- | --- |"),
        "{markdown}"
    );
}

/// Both capture pages that hold a table now hold a table Kio can index.
///
/// The refusal cost two of the three real documents everything -- not a degraded
/// reading, no reading at all. This is the assertion that says so directly, over
/// the responses the service really sent rather than over a mock.
#[test]
fn no_capture_still_carries_raw_table_markup() {
    for (name, raw) in [
        ("infographic", INFOGRAPHIC),
        ("infographic-as-pdf", INFOGRAPHIC_AS_PDF),
        ("invoice", INVOICE),
        ("slide", SLIDE),
    ] {
        for page in parse(raw) {
            for tag in ["<table", "</table", "<tr", "<td"] {
                assert!(
                    !page.markdown.contains(tag),
                    "{name} still carries {tag}: {}",
                    page.markdown
                );
            }
        }
    }
    // The slide's two tables are where the conversion has to hold: one opens on
    // a data row, the other on a header, and eight figures sit inside cells.
    let slide = parse(SLIDE).remove(0).markdown;
    assert!(
        slide.contains("| ![](imgs/img_in_image_box_76_433_134_489.jpg) | High text density |"),
        "{slide}"
    );
    // Two tables, and the second is the four-column one. A converter that
    // dropped or merged a column would still satisfy everything above.
    assert_eq!(
        slide.matches("\n| --- | --- | --- |\n").count(),
        1,
        "{slide}"
    );
    assert_eq!(
        slide.matches("\n| --- | --- | --- | --- |\n").count(),
        1,
        "{slide}"
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
/// # The lower bound is still unsupported [2026-08-09]
///
/// Round 5 went looking for evidence beneath the floor and came back with none.
/// That is worth stating rather than leaving as an absence: four of the five
/// captures it took cite no image at all, so no ratio exists on them, and they
/// are not in `captures` below. Every figure in the table above sits far above
/// 0.25 and every piece of decoration far below, so the floor is held up from
/// one side only -- nothing here shows what a real figure just under it would
/// look like, and nothing here would notice if one existed.
///
/// The gap is known and cheap to live with: `[search]
/// related_images_min_area_ratio` is one line and needs no reindex. It is not
/// closed by widening this test.
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
        let largest = boxes.iter().map(area).max().unwrap_or_else(|| {
            panic!(
                "{name} cites no images, and this test only describes pages that have at \
                 least one figure -- the ratio's denominator is the page's largest crop, \
                 which a page without figures does not have.\n\n\
                 Four of the captures in this directory are like that (the code editor, \
                 the terminal, the whiteboard, and the sealed circular, whose one crop the \
                 Markdown never cites). They are deliberately not in `captures` above. Do \
                 not add them and do not give the empty case a default: the floor's lower \
                 bound really is unsupported by evidence, and making this test swallow such \
                 a page would hide that instead of fixing it. See README.md."
            )
        });
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

/// V7 (W3): how close a real page comes to a chunk boundary that cuts an image
/// reference in half.
///
/// A chunk is a byte span of a unit (03 §8.1), so `[chunking].max_chars` can sever
/// a `kio://` reference -- and a severed one is dropped rather than guessed at,
/// which costs the Agent that image in `related_images[]` and costs it its
/// embedding, silently. `kio-index`'s
/// `v7_a_blank_line_free_run_lets_a_split_cut_an_image_reference` pins WHEN that
/// can happen: only inside a blank-line-free run longer than `max_chars`, because
/// rule 5 prefers the last blank line in the window and hard-cuts only when there
/// is none. So the frequency question is this one measurement, and these captures
/// are where it can be taken.
///
/// Measured rather than eyeballed, because the reference the chunker sees is not
/// the one the service sent: `imgs/img_in_….jpg` becomes a 123-character URI by
/// the time the body is normalized (07 §5.2). A full URI is added per reference
/// WITHOUT subtracting the short name it replaces, so every run below is
/// over-stated and the reported margin is a floor, not an estimate.
const SHIPPED_MAX_CHARS: usize = 6000;
const KIO_IMAGE_URI_CHARS: usize = 123;

#[test]
fn no_real_page_holds_a_blank_line_free_run_that_a_chunk_boundary_could_cut() {
    let mut worst = 0usize;
    let mut worst_page = "";
    for (name, raw) in [
        ("infographic", INFOGRAPHIC),
        ("infographic-as-pdf", INFOGRAPHIC_AS_PDF),
        ("invoice", INVOICE),
        ("slide", SLIDE),
    ] {
        for page in parse(raw) {
            // Splitting on `\n\n` alone under-counts the blank lines the chunker
            // recognizes (it tolerates whitespace between the two newlines), which
            // makes these runs longer than the real ones -- again the safe side.
            for run in page.markdown.split("\n\n") {
                let references = run.matches("![](").count();
                // Only a run that holds a reference can sever one.
                if references == 0 {
                    continue;
                }
                let projected = run.chars().count() + references * KIO_IMAGE_URI_CHARS;
                if projected > worst {
                    worst = projected;
                    worst_page = name;
                }
            }
        }
    }
    // A measurement that stopped finding anything to measure would pass both
    // assertions below while telling nobody that it had stopped.
    assert!(
        worst > 0,
        "no run in any capture holds an image reference -- this stopped measuring"
    );
    assert!(
        worst < SHIPPED_MAX_CHARS,
        "{worst_page} holds a {worst}-character run of references with no blank line \
         in it, at or over max_chars {SHIPPED_MAX_CHARS} -- a boundary can now land \
         inside one of its URIs, and the image it names drops out of search silently"
    );
    // The margin, not just the verdict. The shape that closes it is a table: the
    // slide's icon table is one blank-line-free run holding several references,
    // and a table a few times its size is an ordinary document, not a contrived
    // one. If this margin ever falls under 2x, the fail-empty rule stops being a
    // thing that never fires and W3 needs a louder answer than dropping.
    //
    // Converting tables to GFM MOVED this, in the direction nobody predicted:
    // 2189 -> 995, because the notation it replaces carried a `style` attribute
    // on every cell. A table crossing 6000 now has to be a genuinely big table
    // rather than a modest one wrapped in markup.
    assert!(
        worst * 2 < SHIPPED_MAX_CHARS,
        "measured 2026-08-06 at 995 characters on the slide (6.0x under 6000); \
         now {worst} on {worst_page}"
    );
}
