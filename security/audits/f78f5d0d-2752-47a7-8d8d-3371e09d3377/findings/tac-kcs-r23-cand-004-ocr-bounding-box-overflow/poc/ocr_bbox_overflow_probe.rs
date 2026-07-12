use std::panic;

#[derive(Clone, Copy)]
struct BBoxObject {
    x: i64,
    y: i64,
    w: i64,
    h: i64,
}

fn parse_bbox_like_kcs_object(input: BBoxObject) -> [i64; 4] {
    let x1 = input.x;
    let y1 = input.y;
    let x2 = x1 + input.w;
    let y2 = y1 + input.h;
    [x1, y1, x2, y2]
}

fn inverted(bbox: [i64; 4]) -> bool {
    bbox[2] < bbox[0] || bbox[3] < bbox[1]
}

fn main() {
    panic::set_hook(Box::new(|_| {}));

    let normal = parse_bbox_like_kcs_object(BBoxObject {
        x: 10,
        y: 5,
        w: 20,
        h: 7,
    });
    println!("normal_bbox={normal:?} inverted={}", inverted(normal));
    println!("checked_add_control={:?}", i64::MAX.checked_add(1));

    let overflow = panic::catch_unwind(|| {
        parse_bbox_like_kcs_object(BBoxObject {
            x: i64::MAX,
            y: 0,
            w: 1,
            h: 1,
        })
    });

    match overflow {
        Ok(bbox) => println!("overflow_bbox={bbox:?} inverted={}", inverted(bbox)),
        Err(_) => println!("overflow_result=panic"),
    }
}
