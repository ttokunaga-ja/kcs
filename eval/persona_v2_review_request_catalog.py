"""Bounded, non-authorizing review requests for persona-PC v2.

The catalog freezes *what* seven independent reviews must inspect.  It is not a
review receipt: it deliberately contains no reviewer identity, decision,
approval, waiver, solver/G0 capability, or write/history authority.  Positive
receipts must be supplied by a later trust boundary and remain unbound here.

Only immutable canonical ``bytes`` are cached.  Public builders always decode a
fresh object so caller mutation cannot poison the process-wide baseline.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import hmac
import json
import unicodedata

try:
    from . import persona_v2_chunk_accounting as chunk_accounting
    from . import persona_v2_contract as envelope
    from . import persona_v2_overlay_contract as overlay_contract
    from . import persona_v2_overlay_reservation_layout as reservation
    from . import persona_v2_payload_equivalence_rule_catalog as payload
    from . import persona_v2_realism_profile as realism
    from . import persona_v2_route_affinity as route
    from . import persona_v2_semantic_projection_complete_inventory_validator as complete_validator
    from . import persona_v2_semantic_projection_corpus_content as corpus_projection
    from . import persona_v2_semantic_projection_global_content as global_projection
    from . import persona_v2_semantic_projection_relations_parameters as relation_projection
    from . import persona_v2_source_matched_lifecycle_inventory as lifecycle_projection
    from . import persona_v2_topology as topology
    from . import persona_v2_variant_catalog as variant
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_chunk_accounting as chunk_accounting
    import persona_v2_contract as envelope
    import persona_v2_overlay_contract as overlay_contract
    import persona_v2_overlay_reservation_layout as reservation
    import persona_v2_payload_equivalence_rule_catalog as payload
    import persona_v2_realism_profile as realism
    import persona_v2_route_affinity as route
    import persona_v2_semantic_projection_complete_inventory_validator as complete_validator
    import persona_v2_semantic_projection_corpus_content as corpus_projection
    import persona_v2_semantic_projection_global_content as global_projection
    import persona_v2_semantic_projection_relations_parameters as relation_projection
    import persona_v2_source_matched_lifecycle_inventory as lifecycle_projection
    import persona_v2_topology as topology
    import persona_v2_variant_catalog as variant


ARTIFACT_SCHEMA = "kio.persona.pc-review-request-catalog/v1"
ARTIFACT_KIND = "persona-pc-v2-non-authorizing-review-request-catalog"
ARTIFACT_SCHEMA_VERSION = 1

MAX_CATALOG_BYTES = 256 * 1024
MAX_STRING_BYTES = 4 * 1024
MAX_CANONICAL_DEPTH = 8
MAX_CANONICAL_NODES = 4_096
MAX_INTEGER_MAGNITUDE = 2**63 - 1
MAX_LIST_ITEMS = 64
MAX_DICT_FIELDS = 32

REVIEW_CLASS_ORDER = (
    "topology-activity",
    "realism-profile",
    "variant-profile",
    "route-human",
    "overlay-reservation",
    "chunk-accounting",
    "semantic-projection-inventory",
)

AUTHORITY_FIELDS = (
    "authorizes_approval",
    "authorizes_g0_freeze",
    "authorizes_history_or_kio",
    "authorizes_positive_review_receipt",
    "authorizes_render_or_write",
    "authorizes_reviewer_identity",
    "authorizes_solver",
    "authorizes_waiver",
)

SUBJECT_PIN_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "body_framing",
        "canonical_bytes",
        "coordinates",
        "sha256",
        "subject_id",
        "subject_role",
    }
)
PROJECTION_PIN_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "body_framing",
        "canonical_bytes",
        "coordinates",
        "projection_ordinal",
        "receipt_id",
        "sha256",
    }
)
PROJECTION_BINDING_FIELDS = frozenset(
    {
        "aggregate",
        "binding_id",
        "mapping_relation",
        "ordered_projection_pins",
        "pin_representation",
        "projection_class_id",
        "projection_count",
    }
)
REQUEST_FIELDS = frozenset(
    {
        "positive_receipt_bound",
        "projection_bindings",
        "request_id",
        "request_ordinal",
        "request_status",
        "required_reviewer_kind",
        "review_class_id",
        "review_contract",
        "subject_pins",
    }
)

# Frozen current subject pins.  Live builders are reauthenticated against this
# table before a catalog can be built.
SUBJECT_PIN_SPECS = {
    "topology": (
        "persona-pc-v2-topology",
        "kio.persona.pc-topology/v2",
        2,
        134_195,
        "02e0e68d37378a1123743673aad826757d17480de77a5a7313f09932c5759c4a",
    ),
    "realism-profile": (
        "persona-pc-v2-realism-profile",
        "kio.persona.pc-realism-profile/v2",
        2,
        36_811,
        "990139d3a544ad57ea77752a6a2de8d4345897e961ca85bd506bd1ee041b3fdb",
    ),
    "variant-catalog": (
        "persona-pc-v2-variant-catalog",
        "kio.persona.pc-variant-catalog/v2",
        2,
        211_733,
        "807dd3cdd8df613ac21e6ba64877fb5abb40c72ed4949abaa0d440a449e7f9e9",
    ),
    "route-affinity": (
        "persona-pc-v2-route-affinity-matrix",
        "kio.persona.pc-route-affinity/v2",
        2,
        70_626,
        "7536b815ed5f614db2c31d49138385c7be76c71d45d7fc30f3380b3a9ae3b957",
    ),
    "overlay-contract": (
        "persona-pc-v2-overlay-contract",
        "kio.persona.pc-overlay-contract/v2",
        2,
        71_179,
        "e9154297f6dd5cf30ccbcc819d725cb08c533ec84a7b2df359937ddfb6517c23",
    ),
    "overlay-reservation-suite": (
        "persona-pc-v2-overlay-reservation-suite",
        "kio.persona.pc-overlay-reservation-suite/v2",
        2,
        21_680,
        "0423ed61ea7b39dd5229e2ad6f972fc12055717ad401ee9b74911dd5696f15a4",
    ),
    "chunk-accounting": (
        "persona-pc-v2-chunk-accounting",
        "kio.persona.pc-chunk-accounting/v1",
        1,
        19_801,
        "66a9bd0b5ab8c5f61cd4bdc66b45532810d65b056fcaf8955fff7f366248ab52",
    ),
    "complete-semantic-projection-inventory": (
        "persona-pc-v2-complete-semantic-projection-derivation-inventory",
        "kio.persona.pc-semantic-projection-derivation-inventory/v2",
        2,
        697_466,
        "820c976a930c3f2ed0a54e44c08b01cad8a0879513f1b06012e353fb9bd3fd91",
    ),
}

# Frozen all-persona pins, ordered exactly as the complete inventory receipts.
# Keeping these as tuples (rather than generated catalog state) makes current
# projection drift fail closed.
RELATION_PROJECTION_PINS = (
    ("p01", "pilot", 44_642, "01b6fda1b8fea5b67a6d24adbbdc5b7f0b38435c0ed8b411adac33b9db8a4910"),
    ("p01", "full-residual", 437_242, "4d2dc9adfc0aa7322f6edbb04973c8334db14705a642b217cb3b73e7ba8a7a69"),
    ("p02", "pilot", 57_289, "3f49586eccf40f1a4bd21f8d451728cd3ed4ac43602c448d4ffa664e72f02d96"),
    ("p02", "full-residual", 561_044, "f51fc854324691988f02552b3f6b4967e69b41ce5f0584995e1766734e25c544"),
    ("p03", "pilot", 34_733, "8d2b1e45eec0dd11750da2baceaa5368744b1b66f8e9f23b2625853f5b962c51"),
    ("p03", "full-residual", 340_805, "dc6c72b61525413070d1536e9ccf402c91e0fd8b6529552f1636ed5ac3619a65"),
    ("p04", "pilot", 36_864, "1316f5243dc5e14a514cf5d5508334761ce52627c9f9a5dbb05599e15ac6b1d9"),
    ("p04", "full-residual", 360_535, "566457e8685a7e3c0379e72af0417ea3d763d392586bba126501ef11579f5142"),
    ("p05", "pilot", 45_640, "8534d94bdebf27bda6d6e432d4f9e306e6d22102d10842cae282e709e6c21c2f"),
    ("p05", "full-residual", 446_959, "2b4189bd26f245955128d32f2fd4a5ea013f312a40db4383a8a5f13c34a56cce"),
    ("p06", "pilot", 24_690, "144504afa1599b81e16d299dbe8a024535706b2403d66033ba8004d759e8b72d"),
    ("p06", "full-residual", 241_974, "56836eee807a9238d97306f526f985f61df060fb55d7dba687cfddbd4c129ac0"),
    ("p07", "pilot", 29_401, "66761f5002f2a86dc4e2e9cd8015f7523918aa1d80b867fcc9e15643448fb73f"),
    ("p07", "full-residual", 287_856, "f67e61dd6249b055071a904469ee3d8deb41d792ba8524dffa58e1ec49dc4f85"),
    ("p08", "pilot", 38_650, "01b696ee7dfc354416cfc356f8bb79a3885c2b37b7cccbb50df1fb740d5257eb"),
    ("p08", "full-residual", 379_124, "2bbe6b6794f4f6459ef23889ccaa467fe4b0dee4f8bde6be9eeb8da2268897fa"),
    ("p09", "pilot", 38_399, "f6022b6aa16bc103bf430f02823aa00ee1463e98ca7e942bdf003c1bf6f17108"),
    ("p09", "full-residual", 376_950, "c9fceff2e2c2e6f48aa9af31f8966811711f1004d036b338e3eab3b954fc98ba"),
    ("p10", "pilot", 53_618, "8541ef7f6a7a5e3e54918d794725e318daa87284c3a92efd00c33078b9471067"),
    ("p10", "full-residual", 525_330, "32535b4e3000f09d4d3c724d5ba809889f5b427898e141c853bba0c703d964a1"),
    ("p11", "pilot", 45_296, "d5e825594ab12317a62340ba495ec27e2d2d6033f7ff2a2b5d53b2831bb200ee"),
    ("p11", "full-residual", 444_422, "0889bef98fb7054c64959cc5a9b03db21b4dccc4229e5cd11cca2625ede30c3b"),
    ("p12", "pilot", 67_132, "05874be1cdbdb9d873b665f2227790f9fbeba5931c9268e3879e6ab9f9838f4d"),
    ("p12", "full-residual", 658_944, "1b2faa5cf4edfa6b57e993f08a634ec89806bedbfd7b2f71101951ca91c2f2fc"),
    ("p13", "pilot", 29_647, "0b391770d0ffade0a1407b9af1ce20e3636e266e288186a7722657c02fc17a02"),
    ("p13", "full-residual", 290_647, "4b2aa300e76c45d137c5c711913a4b0c00aef710ebe1dfc135f3557fbabf12d6"),
    ("p14", "pilot", 63_367, "d99ed25de6d81e44081144e2de657d409b95c265243cb73163bc635349e38a2f"),
    ("p14", "full-residual", 620_867, "9804e1ee9f16afe32e75b7254678c16078147aa392b60819fa275dea0ac003d4"),
    ("p15", "pilot", 30_706, "813e976e4dd3ef3bf8369a73cfc50b705f0914d5210d42aea5b2004e26d6fcef"),
    ("p15", "full-residual", 301_150, "89a0e655465d825f4c74a7937cacb9925f02f0a1082ff87fe6847f0f0b8535a5"),
    ("p16", "pilot", 24_726, "36e1b3bd79c5ca22fae9492fe3d1a94201f6688cbef2e0fa718545a85dbda24f"),
    ("p16", "full-residual", 242_298, "58074d2fcac1acdaeceaccf69db746856f42d99e48978d815cdfe185bd1d05ab"),
    ("p17", "pilot", 36_180, "5ac9942a3d06edc457359951a5a6562684539204923fa1ce717cf77ba352e014"),
    ("p17", "full-residual", 354_116, "bdd7580e19402a07f47da09d0de45c1a8a5c51b438171f8ff25d0290819b2168"),
    ("p18", "pilot", 44_642, "12d661b479e29681090577361461e3ee841a41c6e8340bf5bf8214089ae7bedb"),
    ("p18", "full-residual", 437_242, "955d004ef7860882c83cd0ceb95d6821156ce6cdb8b7cfa2f5f461c1502dc625"),
    ("p19", "pilot", 41_291, "fd037b4435fc4d5c906089c50607618f9a1d3036202f1e9360a0e5dbe6da84be"),
    ("p19", "full-residual", 405_163, "7f4ed2e9c5bbb06af2e35eac9636772ed903eaab9234b3c1d2aa9e286cfb6e3c"),
    ("p20", "pilot", 45_206, "60629c529f2d6785c5573d5d3aa544cb208874e35e1a2653460bb3925f1fa08a"),
    ("p20", "full-residual", 443_622, "67d03842fdc7e0b7aca77677d2a373a480f1964f3ea63f7e539d9f86207a6c88"),
)
LIFECYCLE_PROJECTION_PINS = (
    ("p01", 253_386, "3ab896112e5732b38e0b53a2d13ef20cccdb47d134d3ba0d038677bcea00cc05"),
    ("p02", 250_488, "67d7d781d570d6927aa84db882a294e7b7a87330feea354da1062f7e7394926e"),
    ("p03", 250_852, "84945b282b6b1913fc28a383bffaf5af66577dc295a81d39a7a49bd48deec207"),
    ("p04", 256_800, "330064e042bb811b1af9625757506c7ddc3beab180f5dc1970c823cde0b60cbc"),
    ("p05", 253_865, "6ccc3b6c6656ba63e9b68d62cdd61b8bf2fad576d590df81416622a5486f4061"),
    ("p06", 254_432, "d148748295a6a41aa3798f5bfa883f4a740f373c8caf42b282b85b6ab422bf42"),
    ("p07", 251_576, "a99f6a0a5f28254809ad69a351fb91fba95719d8210809ee38431758eaf0ff5a"),
    ("p08", 254_488, "be1b6be7ea3dc05638160aed921f64bee1309953ec01aafcf75f3e8ee37a2485"),
    ("p09", 254_631, "efc24aad5d9797a628dca269aaac9c05bc72d037a6b3cccca34cef6e54c9932f"),
    ("p10", 254_715, "b3c9db08f1104f3f8b0e0183b75664b3c44ec09757c45ba464d9a75a2146b43e"),
    ("p11", 251_491, "238dc10825129749b28f490f347142d56f7845fbd3a0c87790d3f17d0c5e5008"),
    ("p12", 250_645, "799620662d66416a8aa2a81cd64658d5b7be74a962659474ae9fcad1bd29086f"),
    ("p13", 252_072, "bfba095f2813566f285cd254942a8ab505efc541093ebdefb1b53351f8925c91"),
    ("p14", 254_387, "23cd11fa455d47b61fc38810f1a72bc155609e034eee2e142c9b73b110d33500"),
    ("p15", 251_229, "6d25e9c390592eda7b3727c7d3bb117d820acd013d5fd14d2f8cf98ccfeaa79e"),
    ("p16", 251_966, "1049e9251a5702f3d40f91f2b8b9fa9af156b9260ec8a302c32037c747b18923"),
    ("p17", 251_994, "07b236e15984f5e71eb583e6f491d75d1b759970275f45c871e278bfe1ae941c"),
    ("p18", 251_573, "3589f1457a7f231e904f734884684e1495a7c3e4be30707dff23eceeafa7414e"),
    ("p19", 255_022, "b23f60b52eea5871ee0f236ba5b93b10c26caecd3c47afc9a9e63e3ee6f6a06d"),
    ("p20", 251_675, "6d0bf32c17d5d2bc9a846a8a2aed88cb4a1a6949cc31fb6a04666f08f1ea7292"),
)

SINGLETON_PROJECTION_SPECS = {
    "topology-path-load": (
        "persona-pc-v2-topology-path-load-content-projection",
        "kio.persona.pc-topology-path-load-content-projection/v1",
        "canonical-json",
        133_187,
        "36c27d36ba074b884090a094541b33e34f719c2ed6c817309d26c9d9e2395db6",
        "projection-derivation-topology-path-load",
    ),
    "realism-locale-security": (
        "persona-pc-v2-realism-locale-security-content-projection",
        "kio.persona.pc-realism-locale-security-content-projection/v1",
        "canonical-json",
        32_762,
        "6aec6942e00305334d90e0094c1a1903af2f6dd941ccc8e2e08d6f91980086ed",
        "projection-derivation-realism-locale-security",
    ),
    "recipe-content-filename-policy": (
        "persona-pc-v2-recipe-content-filename-policy-content-projection",
        "kio.persona.pc-recipe-content-filename-policy-content-projection/v1",
        "canonical-json",
        250_388,
        "c7570d0f0436e5321929f84e13e59a130fba2f9976764493d04e1ad9aaf7e4ba",
        "projection-derivation-recipe-content-filename-policy",
    ),
    "route-scores": (
        "persona-pc-v2-route-scores-content-projection",
        "kio.persona.pc-route-scores-content-projection/v1",
        "canonical-json",
        88_085,
        "a555ef18181f525ca713e5f3655969dbd8d8b0ba3a205a5ae700f9ba2234ff03",
        "projection-derivation-route-scores",
    ),
    "payload-equivalence-rules": (
        "persona-pc-v2-payload-equivalence-rules-projection",
        "kio.persona.pc-payload-equivalence-rules-projection/v1",
        "canonical-json",
        4_288,
        "a23ca9032d9779d9ebdde1d490354f70e5f1c0a09db9e8e3eaea26098e477649",
        "payload-equivalence-rules-global",
    ),
}

RUBRIC_SPECS = {
    "topology-activity": (
        "persona-v2-topology-activity-review-rubric-v1",
        "independent-qualified-reviewer",
        (
            "topology-scope-paths-and-loads-exact",
            "activity-units-are-semantically-coherent",
            "active-leaf-and-ambient-lanes-remain-separated",
            "nesting-and-path-boundaries-are-covered",
            "unresolved-topology-blockers-are-recorded",
        ),
    ),
    "realism-profile": (
        "persona-v2-realism-profile-review-rubric-v1",
        "independent-qualified-reviewer",
        (
            "all-twenty-personas-are-distinct",
            "locale-language-and-security-axes-are-plausible",
            "per-persona-format-mix-is-coherent",
            "cross-persona-leakage-is-absent",
            "unresolved-realism-blockers-are-recorded",
        ),
    ),
    "variant-profile": (
        "persona-v2-variant-profile-review-rubric-v1",
        "independent-qualified-reviewer",
        (
            "all-seventy-one-variants-have-distinct-purpose",
            "ordinary-and-tail-variants-are-feasible",
            "family-and-extension-ratios-remain-integer-exact",
            "recipe-projection-preserves-variant-content-policy",
            "unresolved-variant-blockers-are-recorded",
        ),
    ),
    "route-human": (
        "persona-v2-route-human-review-rubric-v1",
        "independent-human",
        (
            "all-active-route-rows-are-human-inspected",
            "maximum-score-scopes-match-persona-use-cases",
            "zero-score-semantics-are-not-treated-as-prohibition",
            "route-bias-does-not-encode-solved-placement",
            "unresolved-route-blockers-are-recorded",
        ),
    ),
    "overlay-reservation": (
        "persona-v2-overlay-reservation-review-rubric-v1",
        "independent-qualified-reviewer",
        (
            "overlay-contract-relations-are-complete",
            "reservation-origin-counts-and-order-are-exact",
            "concrete-relation-projections-preserve-reservations",
            "payload-equivalence-rules-preserve-overlay-semantics",
            "unresolved-overlay-blockers-are-recorded",
        ),
    ),
    "chunk-accounting": (
        "persona-v2-chunk-accounting-review-rubric-v1",
        "independent-qualified-reviewer",
        (
            "four-chunk-metrics-remain-distinct",
            "current-and-history-counting-boundaries-are-exact",
            "move-delete-restore-purge-semantics-are-covered",
            "lifecycle-projections-are-only-transitive-evidence",
            "unresolved-chunk-accounting-blockers-are-recorded",
        ),
    ),
    "semantic-projection-inventory": (
        "persona-v2-semantic-projection-inventory-review-rubric-v1",
        "independent-qualified-reviewer",
        (
            "all-twelve-projection-classes-are-covered",
            "all-two-hundred-fifty-three-receipts-are-ordered",
            "projection-pins-bind-content-only-bodies",
            "query-review-and-authority-data-are-excluded",
            "unresolved-semantic-projection-blockers-are-recorded",
        ),
    ),
}

# Frozen after focused tests, an independent security audit, and isolated
# PYTHONHASHSEED=0/1 build+validation measurements agreed exactly.
EXPECTED_CATALOG_BYTES = 42_931
EXPECTED_CATALOG_SHA256 = (
    "1b444a6d1617907160fce3945e0c5608fdeeefb50c87565263f23b6c0d1cb098"
)


class PersonaV2ReviewRequestCatalogError(ValueError):
    """Raised when the non-authorizing request catalog is invalid."""


def _fail(message):
    raise PersonaV2ReviewRequestCatalogError(message)


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _preflight(value):
    nodes = 0

    def visit(item, depth):
        nonlocal nodes
        nodes += 1
        if nodes > MAX_CANONICAL_NODES or depth > MAX_CANONICAL_DEPTH:
            _fail("review request catalog exceeds its structural cap")
        if type(item) is dict:
            if len(item) > MAX_DICT_FIELDS:
                _fail("review request object exceeds its field cap")
            for key, child in item.items():
                if type(key) is not str:
                    _fail("review request keys must be exact strings")
                visit(key, depth + 1)
                visit(child, depth + 1)
        elif type(item) is list:
            if len(item) > MAX_LIST_ITEMS:
                _fail("review request list exceeds its item cap")
            for child in item:
                visit(child, depth + 1)
        elif type(item) is str:
            if (
                len(item) > MAX_STRING_BYTES
                or len(item.encode("utf-8")) > MAX_STRING_BYTES
                or unicodedata.normalize("NFC", item) != item
            ):
                _fail("review request string exceeds its canonical cap")
        elif type(item) is bool:
            return
        elif type(item) is int:
            if abs(item) > MAX_INTEGER_MAGNITUDE:
                _fail("review request integer exceeds its canonical cap")
        else:
            _fail("review request catalog contains a forbidden scalar type")

    visit(value, 0)


def canonical_json_bytes(value):
    _preflight(value)
    try:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        _fail(f"review request catalog is not canonical JSON: {error}")
    if len(raw) > MAX_CATALOG_BYTES:
        _fail("review request catalog exceeds its byte cap")
    return raw


def _pin(subject_id, spec, *, role):
    kind, schema, version, size, digest = spec
    return {
        "artifact_kind": kind,
        "artifact_schema": schema,
        "artifact_schema_version": version,
        "body_framing": "canonical-json",
        "canonical_bytes": size,
        "coordinates": {},
        "sha256": digest,
        "subject_id": subject_id,
        "subject_role": role,
    }


def _require_live_subject(subject_id, builder, validator_fn, canonicalizer):
    expected = SUBJECT_PIN_SPECS[subject_id]
    value = builder()
    try:
        valid = validator_fn(value)
    except Exception as error:  # fixed outer error avoids leaking callback data
        raise PersonaV2ReviewRequestCatalogError(
            f"current subject validation failed for {subject_id}"
        ) from None
    if valid is not True:
        _fail(f"current subject validator was not exact True for {subject_id}")
    raw = canonicalizer(value)
    actual = (
        value.get("artifact_kind"),
        value.get("artifact_schema"),
        value.get("artifact_schema_version"),
        len(raw),
        _sha256(raw),
    )
    if actual != expected:
        _fail(f"current subject pin drifted for {subject_id}")
    return _pin(subject_id, expected, role="exact-current-review-subject")


def _subject_pins():
    pins = {
        "topology": _require_live_subject(
            "topology", topology.build_topology_contract,
            topology.validate_topology_contract, topology.canonical_json_bytes
        ),
        "realism-profile": _require_live_subject(
            "realism-profile", realism.build_realism_profile,
            realism.validate_realism_profile, realism.canonical_json_bytes
        ),
        "variant-catalog": _require_live_subject(
            "variant-catalog", variant.build_variant_catalog,
            variant.validate_variant_catalog, variant.canonical_json_bytes
        ),
        "route-affinity": _require_live_subject(
            "route-affinity", route.build_route_affinity,
            route.validate_route_affinity, route.canonical_json_bytes
        ),
        "overlay-contract": _require_live_subject(
            "overlay-contract", overlay_contract.build_overlay_contract,
            overlay_contract.validate_overlay_contract,
            overlay_contract.canonical_json_bytes
        ),
        "overlay-reservation-suite": _require_live_subject(
            "overlay-reservation-suite", reservation.build_overlay_reservation_suite,
            reservation.validate_overlay_reservation_suite,
            reservation.canonical_json_bytes
        ),
        "chunk-accounting": _require_live_subject(
            "chunk-accounting", chunk_accounting.build_chunk_accounting_contract,
            chunk_accounting.validate_chunk_accounting_contract,
            chunk_accounting.canonical_json_bytes
        ),
    }
    complete = SUBJECT_PIN_SPECS["complete-semantic-projection-inventory"]
    independent_complete = (
        complete_validator.SUITE_KIND,
        complete_validator.SUITE_SCHEMA,
        complete_validator.ARTIFACT_SCHEMA_VERSION,
        complete_validator.EXPECTED_SUITE_CANONICAL_BYTES,
        complete_validator.EXPECTED_SUITE_SHA256,
    )
    if independent_complete != complete:
        _fail("complete semantic projection inventory pin drifted")
    pins["complete-semantic-projection-inventory"] = _pin(
        "complete-semantic-projection-inventory",
        complete,
        role="exact-current-review-subject",
    )
    return pins


def _literal_subject_pins():
    """Return detached frozen pins without consulting mutable live providers."""

    return {
        subject_id: _pin(
            subject_id, spec, role="exact-current-review-subject"
        )
        for subject_id, spec in SUBJECT_PIN_SPECS.items()
    }


def _projection_pin(
    *, kind, schema, framing, size, digest, receipt_id, ordinal, coordinates
):
    return {
        "artifact_kind": kind,
        "artifact_schema": schema,
        "artifact_schema_version": 1,
        "body_framing": framing,
        "canonical_bytes": size,
        "coordinates": copy.deepcopy(coordinates),
        "projection_ordinal": ordinal,
        "receipt_id": receipt_id,
        "sha256": digest,
    }


def _require_projection_raw(class_id, coordinates):
    if class_id == "topology-path-load":
        value = global_projection.build_topology_path_load_content_projection()
        valid = global_projection.validate_topology_path_load_content_projection(value)
        raw = global_projection.canonical_json_bytes(value)
    elif class_id == "realism-locale-security":
        value = global_projection.build_realism_locale_security_content_projection()
        valid = global_projection.validate_realism_locale_security_content_projection(value)
        raw = global_projection.canonical_json_bytes(value)
    elif class_id == "route-scores":
        value = global_projection.build_route_scores_content_projection()
        valid = global_projection.validate_route_scores_content_projection(value)
        raw = global_projection.canonical_json_bytes(value)
    elif class_id == "recipe-content-filename-policy":
        value = (
            corpus_projection.build_recipe_content_filename_policy_content_projection()
        )
        valid = (
            corpus_projection.validate_recipe_content_filename_policy_content_projection(
                value
            )
        )
        raw = corpus_projection.canonical_json_bytes(value)
    elif class_id == "payload-equivalence-rules":
        value = payload.build_payload_equivalence_rules_projection()
        valid = payload.validate_payload_equivalence_rules_projection(value)
        raw = payload.canonical_json_bytes(value)
    elif class_id == "concrete-overlay-relations":
        raw = relation_projection.concrete_overlay_relations_projection_body_bytes(
            coordinates["persona_id"], coordinates["origin"]
        )
        valid = relation_projection.validate_projection_body(class_id, coordinates, raw)
    elif class_id == "query-independent-lifecycle-fact-rendition-rules":
        persona_id = coordinates["persona_id"]
        value = lifecycle_projection.build_source_matched_lifecycle_content_projection(
            persona_id
        )
        valid = lifecycle_projection.validate_source_matched_lifecycle_content_projection(
            persona_id, value
        )
        raw = lifecycle_projection.canonical_json_bytes(value)
    else:  # pragma: no cover - literal registry controls all calls
        _fail("unknown review projection class")
    if valid is not True or type(raw) is not bytes:
        _fail(f"current projection validation failed for {class_id}")
    return raw


def _singleton_projection_pin(class_id, ordinal=1, *, authenticate=True):
    kind, schema, framing, size, digest, receipt_id = SINGLETON_PROJECTION_SPECS[
        class_id
    ]
    coordinates = {"scope": "suite"} if class_id == "recipe-content-filename-policy" else {}
    if authenticate and class_id in {
        "topology-path-load",
        "realism-locale-security",
        "route-scores",
    }:
        if {
            row[0]: (row[1], row[2])
            for row in global_projection.EXPECTED_PROJECTION_PINS
        }.get(class_id) != (
            size,
            digest,
        ):
            _fail(f"current projection pin drifted for {class_id}")
    elif authenticate and class_id == "recipe-content-filename-policy":
        if (
            corpus_projection.RECIPE_KIND != kind
            or corpus_projection.RECIPE_SCHEMA != schema
        ):
            _fail("current recipe projection contract drifted")
    elif authenticate and class_id == "payload-equivalence-rules":
        if (
            payload.PROJECTION_KIND != kind
            or payload.PROJECTION_SCHEMA != schema
        ):
            _fail("current payload projection contract drifted")
    return _projection_pin(
        kind=kind,
        schema=schema,
        framing=framing,
        size=size,
        digest=digest,
        receipt_id=receipt_id,
        ordinal=ordinal,
        coordinates=coordinates,
    )


def _relation_projection_pins(*, authenticate=True):
    if len(RELATION_PROJECTION_PINS) != 40:
        _fail("frozen relation projection pin table is incomplete")
    if authenticate and (
        relation_projection.RELATION_KIND
        != "persona-pc-v2-concrete-overlay-relations-origin-projection"
        or relation_projection.RELATION_SCHEMA
        != "kio.persona.pc-concrete-overlay-relations-origin-projection/v1"
        or relation_projection.EXPECTED_RELATION_BODY_COUNT != 40
        or sum(row[2] for row in RELATION_PROJECTION_PINS) != 8_988_409
    ):
        _fail("current concrete-overlay relation projection contract drifted")
    result = []
    for ordinal, (persona_id, origin, size, digest) in enumerate(
        RELATION_PROJECTION_PINS, start=1
    ):
        coordinates = {"origin": origin, "persona_id": persona_id}
        result.append(
            _projection_pin(
                kind=relation_projection.RELATION_KIND,
                schema=relation_projection.RELATION_SCHEMA,
                framing="canonical-jsonl-lf",
                size=size,
                digest=digest,
                receipt_id=(
                    "projection-derivation-concrete-overlay-relations-"
                    f"{persona_id}-{origin}"
                ),
                ordinal=ordinal,
                coordinates=coordinates,
            )
        )
    return result


def _lifecycle_projection_pins(*, authenticate=True):
    if len(LIFECYCLE_PROJECTION_PINS) != 20:
        _fail("frozen lifecycle projection pin table is incomplete")
    if authenticate and (
        lifecycle_projection.PROJECTION_KIND
        != "persona-pc-v2-source-matched-lifecycle-content-projection"
        or lifecycle_projection.PROJECTION_SCHEMA
        != "kio.persona.pc-source-matched-lifecycle-content-projection/v1"
        or sum(row[1] for row in LIFECYCLE_PROJECTION_PINS) != 5_057_286
    ):
        _fail("current lifecycle projection contract drifted")
    result = []
    for ordinal, (persona_id, size, digest) in enumerate(
        LIFECYCLE_PROJECTION_PINS, start=1
    ):
        coordinates = {"persona_id": persona_id}
        result.append(
            _projection_pin(
                kind=lifecycle_projection.PROJECTION_KIND,
                schema=lifecycle_projection.PROJECTION_SCHEMA,
                framing="canonical-json",
                size=size,
                digest=digest,
                receipt_id=f"projection-derivation-lifecycle-rules-{persona_id}",
                ordinal=ordinal,
                coordinates=coordinates,
            )
        )
    return result


def _pin_digest(pins):
    rows = [
        {
            "canonical_bytes": pin["canonical_bytes"],
            "receipt_id": pin["receipt_id"],
            "sha256": pin["sha256"],
        }
        for pin in pins
    ]
    return _sha256(canonical_json_bytes(rows))


def _projection_binding(binding_id, class_id, relation, pins):
    return {
        "aggregate": {
            "cumulative_canonical_bytes": sum(
                pin["canonical_bytes"] for pin in pins
            ),
            "ordered_projection_pins_sha256": _pin_digest(pins),
        },
        "binding_id": binding_id,
        "mapping_relation": relation,
        "ordered_projection_pins": copy.deepcopy(pins),
        "pin_representation": "explicit-ordered-pins",
        "projection_class_id": class_id,
        "projection_count": len(pins),
    }


def _inventory_projection_binding(*, authenticate=True):
    if authenticate and (
        complete_validator.EXPECTED_CUMULATIVE_EXTERNAL_BODY_BYTES_FROZEN
        != 155_741_381
        or complete_validator.EXPECTED_ORDERED_PROJECTION_PINS_SHA256
        != "d9ffe202e88bff01c3238e0b4749e4c9cd1e8a759b420d2e12dcf27d8b25b7c8"
    ):
        _fail("complete inventory ordered projection pin aggregate drifted")
    return {
        "aggregate": {
            "cumulative_canonical_bytes": 155_741_381,
            "ordered_projection_pins_sha256": (
                "d9ffe202e88bff01c3238e0b4749e4c9cd1e8a759b420d2e12dcf27d8b25b7c8"
            ),
        },
        "binding_id": "complete-inventory-all-253-ordered-pins",
        "mapping_relation": "inventory-ordered-pin-digest",
        "ordered_projection_pins": [],
        "pin_representation": "complete-inventory-ordered-pin-digest",
        "projection_class_id": "all-twelve-complete-inventory-classes",
        "projection_count": 253,
    }


def _request(ordinal, class_id, subjects, bindings):
    rubric_id, reviewer_kind, checks = RUBRIC_SPECS[class_id]
    return {
        "positive_receipt_bound": False,
        "projection_bindings": copy.deepcopy(bindings),
        "request_id": f"persona-v2-review-request-{class_id}",
        "request_ordinal": ordinal,
        "request_status": "awaiting-independent-positive-receipt",
        "required_reviewer_kind": reviewer_kind,
        "review_class_id": class_id,
        "review_contract": {
            "approval_bound": False,
            "ordered_check_ids": list(checks),
            "review_decision_bound": False,
            "reviewer_identity_bound": False,
            "rubric_id": rubric_id,
            "rubric_version": 1,
            "waiver_bound": False,
        },
        "subject_pins": copy.deepcopy(subjects),
    }


def _build_catalog_value():
    subjects = _literal_subject_pins()
    topology_pin = _singleton_projection_pin(
        "topology-path-load", authenticate=False
    )
    realism_pin = _singleton_projection_pin(
        "realism-locale-security", authenticate=False
    )
    recipe_pin = _singleton_projection_pin(
        "recipe-content-filename-policy", authenticate=False
    )
    route_pin = _singleton_projection_pin("route-scores", authenticate=False)
    relation_pins = _relation_projection_pins(authenticate=False)
    payload_pin = _singleton_projection_pin(
        "payload-equivalence-rules", authenticate=False
    )
    lifecycle_pins = _lifecycle_projection_pins(authenticate=False)
    requests = [
        _request(1, "topology-activity", [subjects["topology"]], [
            _projection_binding("topology-path-load-direct-owner", "topology-path-load", "direct-owner-chain", [topology_pin])
        ]),
        _request(2, "realism-profile", [subjects["realism-profile"]], [
            _projection_binding("realism-locale-security-direct-owner", "realism-locale-security", "direct-owner-chain", [realism_pin])
        ]),
        _request(3, "variant-profile", [subjects["variant-catalog"]], [
            _projection_binding("recipe-policy-variant-direct-owner", "recipe-content-filename-policy", "direct-owner-chain", [recipe_pin])
        ]),
        _request(4, "route-human", [subjects["route-affinity"]], [
            _projection_binding("route-scores-direct-owner", "route-scores", "direct-owner-chain", [route_pin])
        ]),
        _request(5, "overlay-reservation", [subjects["overlay-contract"], subjects["overlay-reservation-suite"]], [
            _projection_binding("concrete-relations-reservation-chain", "concrete-overlay-relations", "transitive-consumer-chain", relation_pins),
            _projection_binding("payload-rules-overlay-direct-owner", "payload-equivalence-rules", "direct-owner-chain", [payload_pin]),
        ]),
        _request(6, "chunk-accounting", [subjects["chunk-accounting"]], [
            _projection_binding("lifecycle-rules-chunk-accounting-transitive", "query-independent-lifecycle-fact-rendition-rules", "transitive-consumer-chain", lifecycle_pins)
        ]),
        _request(7, "semantic-projection-inventory", [subjects["complete-semantic-projection-inventory"]], [
            _inventory_projection_binding(authenticate=False)
        ]),
    ]
    value = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {field: False for field in AUTHORITY_FIELDS},
        "canonical_limits": {
            "external_projection_bodies_embedded": False,
            "max_canonical_bytes": MAX_CATALOG_BYTES,
            "max_explicit_projection_pin_count": 65,
            "max_projection_binding_count": 8,
            "max_review_request_count": 7,
            "max_string_bytes": MAX_STRING_BYTES,
            "max_subject_pin_count": 8,
        },
        "completion_claims": {
            "all_seven_review_requests_bound_to_current_pins": True,
            "positive_receipt_bound": False,
            "reviewer_identity_bound": False,
        },
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "orders": {"review_classes": list(REVIEW_CLASS_ORDER)},
        "review_requests": requests,
        "summary": {
            "authority_grant_count": 0,
            "explicit_projection_pin_count": 65,
            "positive_receipt_count": 0,
            "projection_binding_count": 8,
            "review_request_count": 7,
            "route_human_request_count": 1,
            "subject_pin_count": 8,
        },
    }
    raw = canonical_json_bytes(value)
    if EXPECTED_CATALOG_BYTES is not None and len(raw) != EXPECTED_CATALOG_BYTES:
        _fail("review request catalog canonical byte length drifted")
    if EXPECTED_CATALOG_SHA256 is not None and _sha256(raw) != EXPECTED_CATALOG_SHA256:
        _fail("review request catalog SHA-256 drifted")
    return value


@functools.lru_cache(maxsize=1)
def _canonical_catalog_raw():
    return canonical_json_bytes(_build_catalog_value())


def _authenticate_current_dependencies():
    """Reauthenticate current subjects/contracts; cache no mutable trust state."""

    _subject_pins()
    for class_id in (
        "topology-path-load",
        "realism-locale-security",
        "recipe-content-filename-policy",
        "route-scores",
        "payload-equivalence-rules",
    ):
        _singleton_projection_pin(class_id, authenticate=True)
    _relation_projection_pins(authenticate=True)
    _lifecycle_projection_pins(authenticate=True)
    _inventory_projection_binding(authenticate=True)
    return True


def build_review_request_catalog():
    """Return a detached request catalog; never a positive review receipt."""

    _authenticate_current_dependencies()
    return json.loads(_canonical_catalog_raw().decode("utf-8"))


def review_request_catalog_bytes():
    """Return the immutable, bounded canonical catalog bytes."""

    _authenticate_current_dependencies()
    return bytes(_canonical_catalog_raw())


def validate_review_request_catalog(value):
    """Validate through the producer-independent sibling validator."""

    try:
        from . import persona_v2_review_request_catalog_validator as independent
    except ImportError:  # pragma: no cover
        import persona_v2_review_request_catalog_validator as independent
    try:
        result = independent.validate_review_request_catalog(value)
    except independent.PersonaV2ReviewRequestCatalogValidationError as error:
        raise PersonaV2ReviewRequestCatalogError(str(error)) from None
    if result is not True:
        _fail("independent review request validator did not return exact True")
    return True


def review_request_catalog_sha256(value=None):
    if value is None:
        raw = review_request_catalog_bytes()
    else:
        opening = canonical_json_bytes(value)
        validate_review_request_catalog(value)
        closing = canonical_json_bytes(value)
        if not hmac.compare_digest(opening, closing):
            _fail("review request catalog changed during hashing")
        raw = opening
    return _sha256(raw)


__all__ = [
    "ARTIFACT_KIND",
    "ARTIFACT_SCHEMA",
    "ARTIFACT_SCHEMA_VERSION",
    "EXPECTED_CATALOG_BYTES",
    "EXPECTED_CATALOG_SHA256",
    "MAX_CATALOG_BYTES",
    "PersonaV2ReviewRequestCatalogError",
    "REVIEW_CLASS_ORDER",
    "build_review_request_catalog",
    "canonical_json_bytes",
    "review_request_catalog_bytes",
    "review_request_catalog_sha256",
    "validate_review_request_catalog",
]
