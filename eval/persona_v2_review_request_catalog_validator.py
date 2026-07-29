"""Producer-independent validation for persona-PC v2 review requests.

The sibling request producer is deliberately not imported.  This module owns
literal copies of every subject pin, explicit projection pin, review rubric,
and request mapping needed to reconstruct the exact catalog.  The only cached
derived value is immutable canonical ``bytes``; live subject artifacts and
projection contracts are authenticated afresh by every successful public call.
"""

from __future__ import annotations

import functools
import hashlib
import hmac
import json
import unicodedata

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_chunk_accounting as chunk_accounting
    from . import persona_v2_contract as envelope
    from . import persona_v2_overlay_contract as overlay_contract
    from . import persona_v2_overlay_reservation_layout as reservation
    from . import persona_v2_realism_profile as realism
    from . import persona_v2_route_affinity as route
    from . import persona_v2_topology as topology
    from . import persona_v2_variant_catalog as variant
    from . import persona_v2_payload_equivalence_rule_catalog_validator as payload_validator
    from . import persona_v2_semantic_projection_complete_inventory_validator as complete_validator
    from . import persona_v2_semantic_projection_corpus_content_validator as corpus_validator
    from . import persona_v2_semantic_projection_global_content_validator as global_validator
    from . import persona_v2_semantic_projection_relations_parameters_validator as relation_validator
    from . import persona_v2_source_matched_lifecycle_inventory_validator as lifecycle_validator
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_chunk_accounting as chunk_accounting
    import persona_v2_contract as envelope
    import persona_v2_overlay_contract as overlay_contract
    import persona_v2_overlay_reservation_layout as reservation
    import persona_v2_realism_profile as realism
    import persona_v2_route_affinity as route
    import persona_v2_topology as topology
    import persona_v2_variant_catalog as variant
    import persona_v2_payload_equivalence_rule_catalog_validator as payload_validator
    import persona_v2_semantic_projection_complete_inventory_validator as complete_validator
    import persona_v2_semantic_projection_corpus_content_validator as corpus_validator
    import persona_v2_semantic_projection_global_content_validator as global_validator
    import persona_v2_semantic_projection_relations_parameters_validator as relation_validator
    import persona_v2_source_matched_lifecycle_inventory_validator as lifecycle_validator


ARTIFACT_SCHEMA = "kio.persona.pc-review-request-catalog/v1"
ARTIFACT_KIND = "persona-pc-v2-non-authorizing-review-request-catalog"
ARTIFACT_SCHEMA_VERSION = 1
FIXTURE_ID = "kio-persona-pc-v2"
FIXTURE_SCHEMA_VERSION = 2

MAX_CATALOG_BYTES = 256 * 1024
MAX_STRING_BYTES = 4 * 1024
MAX_CANONICAL_DEPTH = 8
MAX_CANONICAL_NODES = 4_096
MAX_INTEGER_MAGNITUDE = 2**63 - 1
MAX_LIST_ITEMS = 64
MAX_DICT_FIELDS = 32

# Frozen after focused tests, an independent security audit, and isolated
# PYTHONHASHSEED=0/1 build+validation measurements agreed exactly.
EXPECTED_CATALOG_BYTES = 42_931
EXPECTED_CATALOG_SHA256 = (
    "33011fa5b41a0f99d61fd93b8ce5fc949b7d19eab4276cac688bb1ceb6eccb26"
)

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
TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind", "artifact_schema", "artifact_schema_version",
        "authority", "canonical_limits", "completion_claims", "fixture_id",
        "fixture_schema_version", "g0_contract_frozen", "orders",
        "review_requests", "summary",
    }
)
REQUEST_FIELDS = frozenset(
    {
        "positive_receipt_bound", "projection_bindings", "request_id",
        "request_ordinal", "request_status", "required_reviewer_kind",
        "review_class_id", "review_contract", "subject_pins",
    }
)
REVIEW_CONTRACT_FIELDS = frozenset(
    {
        "approval_bound", "ordered_check_ids", "review_decision_bound",
        "reviewer_identity_bound", "rubric_id", "rubric_version",
        "waiver_bound",
    }
)
SUBJECT_PIN_FIELDS = frozenset(
    {
        "artifact_kind", "artifact_schema", "artifact_schema_version",
        "body_framing", "canonical_bytes", "coordinates", "sha256",
        "subject_id", "subject_role",
    }
)
PROJECTION_PIN_FIELDS = frozenset(
    {
        "artifact_kind", "artifact_schema", "artifact_schema_version",
        "body_framing", "canonical_bytes", "coordinates",
        "projection_ordinal", "receipt_id", "sha256",
    }
)
PROJECTION_BINDING_FIELDS = frozenset(
    {
        "aggregate", "binding_id", "mapping_relation",
        "ordered_projection_pins", "pin_representation",
        "projection_class_id", "projection_count",
    }
)
AGGREGATE_FIELDS = frozenset(
    {"cumulative_canonical_bytes", "ordered_projection_pins_sha256"}
)

SUBJECT_PIN_SPECS = {
    "topology": (
        "persona-pc-v2-topology", "kio.persona.pc-topology/v2", 2, 134_195,
        "02e0e68d37378a1123743673aad826757d17480de77a5a7313f09932c5759c4a",
    ),
    "realism-profile": (
        "persona-pc-v2-realism-profile", "kio.persona.pc-realism-profile/v2", 2,
        36_811, "990139d3a544ad57ea77752a6a2de8d4345897e961ca85bd506bd1ee041b3fdb",
    ),
    "variant-catalog": (
        "persona-pc-v2-variant-catalog", "kio.persona.pc-variant-catalog/v2", 2,
        211_733, "807dd3cdd8df613ac21e6ba64877fb5abb40c72ed4949abaa0d440a449e7f9e9",
    ),
    "route-affinity": (
        "persona-pc-v2-route-affinity-matrix", "kio.persona.pc-route-affinity/v2", 2,
        70_626, "7536b815ed5f614db2c31d49138385c7be76c71d45d7fc30f3380b3a9ae3b957",
    ),
    "overlay-contract": (
        "persona-pc-v2-overlay-contract", "kio.persona.pc-overlay-contract/v2", 2,
        71_179, "e9154297f6dd5cf30ccbcc819d725cb08c533ec84a7b2df359937ddfb6517c23",
    ),
    "overlay-reservation-suite": (
        "persona-pc-v2-overlay-reservation-suite",
        "kio.persona.pc-overlay-reservation-suite/v2", 2, 21_680,
        "0423ed61ea7b39dd5229e2ad6f972fc12055717ad401ee9b74911dd5696f15a4",
    ),
    "chunk-accounting": (
        "persona-pc-v2-chunk-accounting", "kio.persona.pc-chunk-accounting/v1", 1,
        19_801, "66a9bd0b5ab8c5f61cd4bdc66b45532810d65b056fcaf8955fff7f366248ab52",
    ),
    "complete-semantic-projection-inventory": (
        "persona-pc-v2-complete-semantic-projection-derivation-inventory",
        "kio.persona.pc-semantic-projection-derivation-inventory/v2", 2, 697_466,
        "820c976a930c3f2ed0a54e44c08b01cad8a0879513f1b06012e353fb9bd3fd91",
    ),
}

SINGLETON_PROJECTION_SPECS = {
    "topology-path-load": (
        "persona-pc-v2-topology-path-load-content-projection",
        "kio.persona.pc-topology-path-load-content-projection/v1",
        "canonical-json", 133_187,
        "36c27d36ba074b884090a094541b33e34f719c2ed6c817309d26c9d9e2395db6",
        "projection-derivation-topology-path-load", {},
    ),
    "realism-locale-security": (
        "persona-pc-v2-realism-locale-security-content-projection",
        "kio.persona.pc-realism-locale-security-content-projection/v1",
        "canonical-json", 32_762,
        "6aec6942e00305334d90e0094c1a1903af2f6dd941ccc8e2e08d6f91980086ed",
        "projection-derivation-realism-locale-security", {},
    ),
    "recipe-content-filename-policy": (
        "persona-pc-v2-recipe-content-filename-policy-content-projection",
        "kio.persona.pc-recipe-content-filename-policy-content-projection/v1",
        "canonical-json", 250_388,
        "c7570d0f0436e5321929f84e13e59a130fba2f9976764493d04e1ad9aaf7e4ba",
        "projection-derivation-recipe-content-filename-policy", {"scope": "suite"},
    ),
    "route-scores": (
        "persona-pc-v2-route-scores-content-projection",
        "kio.persona.pc-route-scores-content-projection/v1",
        "canonical-json", 88_085,
        "a555ef18181f525ca713e5f3655969dbd8d8b0ba3a205a5ae700f9ba2234ff03",
        "projection-derivation-route-scores", {},
    ),
    "payload-equivalence-rules": (
        "persona-pc-v2-payload-equivalence-rules-projection",
        "kio.persona.pc-payload-equivalence-rules-projection/v1",
        "canonical-json", 4_288,
        "a23ca9032d9779d9ebdde1d490354f70e5f1c0a09db9e8e3eaea26098e477649",
        "payload-equivalence-rules-global", {},
    ),
}

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

# Independent literal closure of the accepted complete inventory.  Each row is
# [receipt_id, projection_class_id, coordinates, canonical_bytes, sha256] in
# exact derivation-receipt order.  It is intentionally not imported from the
# complete-inventory or namespace producers.
COMPLETE_ORDERED_RECEIPT_ROWS_JSON = r'''[["projection-derivation-topology-path-load","topology-path-load",{},133187,"36c27d36ba074b884090a094541b33e34f719c2ed6c817309d26c9d9e2395db6"],["projection-derivation-realism-locale-security","realism-locale-security",{},32762,"6aec6942e00305334d90e0094c1a1903af2f6dd941ccc8e2e08d6f91980086ed"],["projection-derivation-route-scores","route-scores",{},88085,"a555ef18181f525ca713e5f3655969dbd8d8b0ba3a205a5ae700f9ba2234ff03"],["projection-derivation-primary-use-case-corpus-half","primary-use-case-corpus-half",{"scope":"suite"},6790,"5a106cb58f91b9e47195c728bf229c2d7d4b15da1c067480178ecc8a514050bd"],["projection-derivation-recipe-content-filename-policy","recipe-content-filename-policy",{"scope":"suite"},250388,"c7570d0f0436e5321929f84e13e59a130fba2f9976764493d04e1ad9aaf7e4ba"],["projection-derivation-fact-graph-p01","fact-graph",{"persona_id":"p01"},22997,"11890827739a1fb21ef77655df3d89bc6f12b13f94e6204d6cca9c979e20ebb1"],["projection-derivation-fact-graph-p02","fact-graph",{"persona_id":"p02"},22944,"15f9d67a362085242da120b1c5bd0d339ebfaabc912fc46e4cc4e649bc84b87c"],["projection-derivation-fact-graph-p03","fact-graph",{"persona_id":"p03"},23070,"19657da3b76598e4d3cd2fb5568d156c8b29f01c1f5973fee583f933cea2deb7"],["projection-derivation-fact-graph-p04","fact-graph",{"persona_id":"p04"},23165,"3283399ee1492c91d4ccac8622929f44691dfd997bf311a1d29d4c15eb8d1b8e"],["projection-derivation-fact-graph-p05","fact-graph",{"persona_id":"p05"},23132,"5c234f3aa5410b0167fa7711835c1e2434314a35b90a8465346d52c7dd27fd3c"],["projection-derivation-fact-graph-p06","fact-graph",{"persona_id":"p06"},23115,"b56421520368c2ba8a093441900b9c12907e85a81e3a781fafe509f819f86812"],["projection-derivation-fact-graph-p07","fact-graph",{"persona_id":"p07"},23252,"3469b7396b71f5a22055298890f0aa0c69b11a32d3240db7219874f1f8de8469"],["projection-derivation-fact-graph-p08","fact-graph",{"persona_id":"p08"},23102,"01e71a3bbdc317e099aa13f6b357f19054e7c217e133e2e2b877246299bef183"],["projection-derivation-fact-graph-p09","fact-graph",{"persona_id":"p09"},23142,"4688db1d2441d57d5eaae553c0ed40e277481a2d1a82ccee564f77af762b0e50"],["projection-derivation-fact-graph-p10","fact-graph",{"persona_id":"p10"},23092,"a2f936b0dd0abed5c1a9634518b22115bd03e77e0778c9cd382f6464e7dfa3eb"],["projection-derivation-fact-graph-p11","fact-graph",{"persona_id":"p11"},23022,"0bfb9745b0230c330502ccf6e1ce0de14203aebf2b712d5ae5fea7b98eff2ba6"],["projection-derivation-fact-graph-p12","fact-graph",{"persona_id":"p12"},23109,"f48de2395bb77e0ee83c48f2d831862ced4e2b38bc268e2325e39af13017bee0"],["projection-derivation-fact-graph-p13","fact-graph",{"persona_id":"p13"},23073,"928e10abed40189e6312c997cea2e99d5d1989a882f7fc8de6f70580e3888722"],["projection-derivation-fact-graph-p14","fact-graph",{"persona_id":"p14"},23019,"f47e1becb42fbcdd99d04f3e726610e87b55afe90b7e89e0da74261b330ae73e"],["projection-derivation-fact-graph-p15","fact-graph",{"persona_id":"p15"},23126,"4b4a1f613e879da5a2aeef5aafe7ed40aaa458b7e43e84a45f5ceb24ae26d161"],["projection-derivation-fact-graph-p16","fact-graph",{"persona_id":"p16"},23169,"71800547371c872309ce17329cc41a4d1627562ecd13f266e5ec926dd76e0de2"],["projection-derivation-fact-graph-p17","fact-graph",{"persona_id":"p17"},23066,"1c3239ac44a1670fbaa21b52fe562b48d2d200c2fbd16d4e079551abc53133e0"],["projection-derivation-fact-graph-p18","fact-graph",{"persona_id":"p18"},23066,"5179d39d6c72ecf5a7bdf07ee94071501d014a19459303f4cece9f660df4e5dc"],["projection-derivation-fact-graph-p19","fact-graph",{"persona_id":"p19"},23022,"b70ceeeee03af60afdf89e458a8884a777f7ddd15f02b7448c24688781e89a55"],["projection-derivation-fact-graph-p20","fact-graph",{"persona_id":"p20"},23133,"e225136c7db6b896d602e324ded9dfca385c389d37d31881df4b51349ad8f0f7"],["projection-derivation-base-content-context-p01-pilot-001","base-source-content-context",{"origin":"pilot","persona_id":"p01","source_shard_id":"p01-source-intent-pilot-shard-0001","source_shard_ordinal":1},666227,"ea5f24d8779feb4b153848c4cad1ef93d63d384bf9d82990ff7fd864e80105df"],["projection-derivation-base-content-context-p01-full-residual-001","base-source-content-context",{"origin":"full-residual","persona_id":"p01","source_shard_id":"p01-source-intent-full-residual-shard-0001","source_shard_ordinal":1},2451447,"19d9d74c3f81043c5bf14dd21af6fa14abc391fdecca380674683f65ef4f168b"],["projection-derivation-base-content-context-p01-full-residual-002","base-source-content-context",{"origin":"full-residual","persona_id":"p01","source_shard_id":"p01-source-intent-full-residual-shard-0002","source_shard_ordinal":2},2453809,"bef877f1bcd5fa268d3991ffdd39d25c5540d7c10c4fede20aa85ddefb501213"],["projection-derivation-base-content-context-p01-full-residual-003","base-source-content-context",{"origin":"full-residual","persona_id":"p01","source_shard_id":"p01-source-intent-full-residual-shard-0003","source_shard_ordinal":3},1566924,"9d2bd148d4e13e9d70c027e84d1b626430b6ac804b6fb999418da91c03703238"],["projection-derivation-base-content-context-p02-pilot-001","base-source-content-context",{"origin":"pilot","persona_id":"p02","source_shard_id":"p02-source-intent-pilot-shard-0001","source_shard_ordinal":1},832732,"9b2014aaef520b3b8618c099ebf032cd96447d9feec8f6086072bf3023365b4c"],["projection-derivation-base-content-context-p02-full-residual-001","base-source-content-context",{"origin":"full-residual","persona_id":"p02","source_shard_id":"p02-source-intent-full-residual-shard-0001","source_shard_ordinal":1},2452935,"675b3ef773b73dff3e3b091dcd30f419c88337995fb0558d3e948778053ac195"],["projection-derivation-base-content-context-p02-full-residual-002","base-source-content-context",{"origin":"full-residual","persona_id":"p02","source_shard_id":"p02-source-intent-full-residual-shard-0002","source_shard_ordinal":2},2450826,"4e41e1ca3576d602c54b55ad4f4f5ad57c773989f8d617a4e03731ee524c1221"],["projection-derivation-base-content-context-p02-full-residual-003","base-source-content-context",{"origin":"full-residual","persona_id":"p02","source_shard_id":"p02-source-intent-full-residual-shard-0003","source_shard_ordinal":3},2459665,"35dce038ccc1c0fcb2811f8ccf2b28e97e02eb55beee4f5fc2c7096a6134cba1"],["projection-derivation-base-content-context-p02-full-residual-004","base-source-content-context",{"origin":"full-residual","persona_id":"p02","source_shard_id":"p02-source-intent-full-residual-shard-0004","source_shard_ordinal":4},726132,"e17629b279b0dff6b0f5cd79d043372bd8091523268a701597975a000d367ab1"],["projection-derivation-base-content-context-p03-pilot-001","base-source-content-context",{"origin":"pilot","persona_id":"p03","source_shard_id":"p03-source-intent-pilot-shard-0001","source_shard_ordinal":1},555991,"b0c9213fce2de4271770f74995d44e873d1713254c86e4b91aaf4dd535f294d6"],["projection-derivation-base-content-context-p03-full-residual-001","base-source-content-context",{"origin":"full-residual","persona_id":"p03","source_shard_id":"p03-source-intent-full-residual-shard-0001","source_shard_ordinal":1},2454857,"cbab36c6b379e25e747489409b42e19fac6dfed6b1a9f2b533d4fd9a8cdbf8b5"],["projection-derivation-base-content-context-p03-full-residual-002","base-source-content-context",{"origin":"full-residual","persona_id":"p03","source_shard_id":"p03-source-intent-full-residual-shard-0002","source_shard_ordinal":2},2462600,"7ccdd57bfe2a43cdde6836c6add43c2aa566314b8fc98c13ec5e8c05538dd947"],["projection-derivation-base-content-context-p03-full-residual-003","base-source-content-context",{"origin":"full-residual","persona_id":"p03","source_shard_id":"p03-source-intent-full-residual-shard-0003","source_shard_ordinal":3},483402,"2be21c7106067d5d48becf9ca667ba4ee9821afc071fc952c57d432803a88f73"],["projection-derivation-base-content-context-p04-pilot-001","base-source-content-context",{"origin":"pilot","persona_id":"p04","source_shard_id":"p04-source-intent-pilot-shard-0001","source_shard_ordinal":1},555167,"efab427db1ac042ebe0417e91f40270aecdea5f37dcb95120a8d80436d4b809b"],["projection-derivation-base-content-context-p04-full-residual-001","base-source-content-context",{"origin":"full-residual","persona_id":"p04","source_shard_id":"p04-source-intent-full-residual-shard-0001","source_shard_ordinal":1},2451461,"c592d72e27b95adf64c6835a180e425a02d881704d777b3706496e708da775f0"],["projection-derivation-base-content-context-p04-full-residual-002","base-source-content-context",{"origin":"full-residual","persona_id":"p04","source_shard_id":"p04-source-intent-full-residual-shard-0002","source_shard_ordinal":2},2459746,"bac49967b65215a675ba649e9540c23da6a78501a25a3da6bc7e89db456d256a"],["projection-derivation-base-content-context-p04-full-residual-003","base-source-content-context",{"origin":"full-residual","persona_id":"p04","source_shard_id":"p04-source-intent-full-residual-shard-0003","source_shard_ordinal":3},482241,"c8da27713db4d1ec466a7a4b219610496b56f3adb703e94fa1b4fa46127df8d3"],["projection-derivation-base-content-context-p05-pilot-001","base-source-content-context",{"origin":"pilot","persona_id":"p05","source_shard_id":"p05-source-intent-pilot-shard-0001","source_shard_ordinal":1},666936,"9a236c5927691dcb9002263507b6e52d93f5936a48fd10401f5c320d3dc91dec"],["projection-derivation-base-content-context-p05-full-residual-001","base-source-content-context",{"origin":"full-residual","persona_id":"p05","source_shard_id":"p05-source-intent-full-residual-shard-0001","source_shard_ordinal":1},2457103,"e71b935df9bc726061b12f2e4c5909d1d0ec16f675b6b93169c8dc26940a86cb"],["projection-derivation-base-content-context-p05-full-residual-002","base-source-content-context",{"origin":"full-residual","persona_id":"p05","source_shard_id":"p05-source-intent-full-residual-shard-0002","source_shard_ordinal":2},2460289,"1979f026c734efe8675759bf732f6f066072fef7641a9a4b499de17ba4c2818f"],["projection-derivation-base-content-context-p05-full-residual-003","base-source-content-context",{"origin":"full-residual","persona_id":"p05","source_shard_id":"p05-source-intent-full-residual-shard-0003","source_shard_ordinal":3},1561189,"115e6be7322c54cc15a888384eb3355e5cc6ef6d8abcb6c8ad9524f5026af658"],["projection-derivation-base-content-context-p06-pilot-001","base-source-content-context",{"origin":"pilot","persona_id":"p06","source_shard_id":"p06-source-intent-pilot-shard-0001","source_shard_ordinal":1},444998,"020022ea61343d34eabc582641bc4e9bc8900e8756cac74e8f6bb081717fdaf2"],["projection-derivation-base-content-context-p06-full-residual-001","base-source-content-context",{"origin":"full-residual","persona_id":"p06","source_shard_id":"p06-source-intent-full-residual-shard-0001","source_shard_ordinal":1},2463067,"147b8aaefba0cc590957c6608f53e103913228689b5575b683b6eea68edf4178"],["projection-derivation-base-content-context-p06-full-residual-002","base-source-content-context",{"origin":"full-residual","persona_id":"p06","source_shard_id":"p06-source-intent-full-residual-shard-0002","source_shard_ordinal":2},1859718,"15104cccc1b0608c117ffeacb7ed340fbb900f447ba0843a8a6704aa6177a5cc"],["projection-derivation-base-content-context-p07-pilot-001","base-source-content-context",{"origin":"pilot","persona_id":"p07","source_shard_id":"p07-source-intent-pilot-shard-0001","source_shard_ordinal":1},390177,"3cd04f9ae8e1bf8f4307b4c6bd913f2e05571ba1458f74919fbcea9bc98adc91"],["projection-derivation-base-content-context-p07-full-residual-001","base-source-content-context",{"origin":"full-residual","persona_id":"p07","source_shard_id":"p07-source-intent-full-residual-shard-0001","source_shard_ordinal":1},2470426,"81da3c4714ad1c7aa309b383379a20b2c1b800ff69e4eea7bd37db9ad7f077d9"],["projection-derivation-base-content-context-p07-full-residual-002","base-source-content-context",{"origin":"full-residual","persona_id":"p07","source_shard_id":"p07-source-intent-full-residual-shard-0002","source_shard_ordinal":2},1319299,"d947661f71197c65d12e96d3298976eac8e179dbb17c6f66bf5ab37889464218"],["projection-derivation-base-content-context-p08-pilot-001","base-source-content-context",{"origin":"pilot","persona_id":"p08","source_shard_id":"p08-source-intent-pilot-shard-0001","source_shard_ordinal":1},445732,"fe26a98866924e896e3996aed0168754806c676bf465e6bb4f6a07f2da19cdd4"],["projection-derivation-base-content-context-p08-full-residual-001","base-source-content-context",{"origin":"full-residual","persona_id":"p08","source_shard_id":"p08-source-intent-full-residual-shard-0001","source_shard_ordinal":1},2475179,"48032fe9af73295c7c58f8f9517eea4410876d26ed4db88a82016a5b675bdb99"],["projection-derivation-base-content-context-p08-full-residual-002","base-source-content-context",{"origin":"full-residual","persona_id":"p08","source_shard_id":"p08-source-intent-full-residual-shard-0002","source_shard_ordinal":2},1854128,"98abeb7e1f6111ca93091568dbe9b3256905c2a5632207de0ca7eb6c8384ca5d"],["projection-derivation-base-content-context-p09-pilot-001","base-source-content-context",{"origin":"pilot","persona_id":"p09","source_shard_id":"p09-source-intent-pilot-shard-0001","source_shard_ordinal":1},501000,"f3d1dcabd5de7c13007a6783fef11916bce56a3145127cdfcae89a21ea08d8e4"],["projection-derivation-base-content-context-p09-full-residual-001","base-source-content-context",{"origin":"full-residual","persona_id":"p09","source_shard_id":"p09-source-intent-full-residual-shard-0001","source_shard_ordinal":1},2474735,"5cf60632101d72fa4b3328b91097b53e702d6b11d26f9811a060554b2a9bc5d7"],["projection-derivation-base-content-context-p09-full-residual-002","base-source-content-context",{"origin":"full-residual","persona_id":"p09","source_shard_id":"p09-source-intent-full-residual-shard-0002","source_shard_ordinal":2},2391602,"12963d8807b70aa343f5a8533db85c1f0b5e8aad0c8193c41f1cd2392bb237b3"],["projection-derivation-base-content-context-p10-pilot-001","base-source-content-context",{"origin":"pilot","persona_id":"p10","source_shard_id":"p10-source-intent-pilot-shard-0001","source_shard_ordinal":1},613050,"e76327714a424b2c12efd8d63978421f559c90b369ef7c5a4c95c223dc290317"],["projection-derivation-base-content-context-p10-full-residual-001","base-source-content-context",{"origin":"full-residual","persona_id":"p10","source_shard_id":"p10-source-intent-full-residual-shard-0001","source_shard_ordinal":1},2484590,"d885a23dcc8e5b0ac57022b8e1edee7f4adc4686d028519546ca7d0bdca15760"],["projection-derivation-base-content-context-p10-full-residual-002","base-source-content-context",{"origin":"full-residual","persona_id":"p10","source_shard_id":"p10-source-intent-full-residual-shard-0002","source_shard_ordinal":2},2448216,"0f4e5d9cc0a960b237b54597b6ff85042b6eb8abe4939d85f402fd34dfabbb09"],["projection-derivation-base-content-context-p10-full-residual-003","base-source-content-context",{"origin":"full-residual","persona_id":"p10","source_shard_id":"p10-source-intent-full-residual-shard-0003","source_shard_ordinal":3},1021201,"8778e84eb31adcab537d4d97a8a4f77163941f94acd882a8e34e9b0073681a61"],["projection-derivation-base-content-context-p11-pilot-001","base-source-content-context",{"origin":"pilot","persona_id":"p11","source_shard_id":"p11-source-intent-pilot-shard-0001","source_shard_ordinal":1},557091,"3f44b1aa6b8b77fdfd8afb930dbfded2f8ade6549da9b117c7d4547e2ae9a859"],["projection-derivation-base-content-context-p11-full-residual-001","base-source-content-context",{"origin":"full-residual","persona_id":"p11","source_shard_id":"p11-source-intent-full-residual-shard-0001","source_shard_ordinal":1},2467040,"02c33fdf661c70ef9c943edfc579c5e96db33049887bd41fa28d3ce47cb0a71f"],["projection-derivation-base-content-context-p11-full-residual-002","base-source-content-context",{"origin":"full-residual","persona_id":"p11","source_shard_id":"p11-source-intent-full-residual-shard-0002","source_shard_ordinal":2},2460923,"930b18affcd09e65a98957f74b0332de721468b88127ab1e54354e12d539e550"],["projection-derivation-base-content-context-p11-full-residual-003","base-source-content-context",{"origin":"full-residual","persona_id":"p11","source_shard_id":"p11-source-intent-full-residual-shard-0003","source_shard_ordinal":3},482801,"b64cbd85afec76cbfc474091362f9f91be897651a2f478e2f931d7f3ed641d08"],["projection-derivation-base-content-context-p12-pilot-001","base-source-content-context",{"origin":"pilot","persona_id":"p12","source_shard_id":"p12-source-intent-pilot-shard-0001","source_shard_ordinal":1},889541,"9b2dd78b950ea2a2ddfc13a5c5b245aa2c733f061e746c3349205dc0427fceaa"],["projection-derivation-base-content-context-p12-full-residual-001","base-source-content-context",{"origin":"full-residual","persona_id":"p12","source_shard_id":"p12-source-intent-full-residual-shard-0001","source_shard_ordinal":1},2457024,"9a74ff97f4936efc9202954cf25a4ea03bd252b0a3403b8ea234b792c38c7174"],["projection-derivation-base-content-context-p12-full-residual-002","base-source-content-context",{"origin":"full-residual","persona_id":"p12","source_shard_id":"p12-source-intent-full-residual-shard-0002","source_shard_ordinal":2},2457933,"df41d8d00cd614bbf1750916e8964c7d3bf28a831ee7f697a70ee2d4c74b7234"],["projection-derivation-base-content-context-p12-full-residual-003","base-source-content-context",{"origin":"full-residual","persona_id":"p12","source_shard_id":"p12-source-intent-full-residual-shard-0003","source_shard_ordinal":3},2463632,"80a2fe90b728fccff4fe30572667809702ca657d553cb57ed59c1cc5707c0cdf"],["projection-derivation-base-content-context-p12-full-residual-004","base-source-content-context",{"origin":"full-residual","persona_id":"p12","source_shard_id":"p12-source-intent-full-residual-shard-0004","source_shard_ordinal":4},1261813,"017d023232c95a3a90eb47a1a207af00e955d54008a693e959d93a89ca08c401"],["projection-derivation-base-content-context-p13-pilot-001","base-source-content-context",{"origin":"pilot","persona_id":"p13","source_shard_id":"p13-source-intent-pilot-shard-0001","source_shard_ordinal":1},390376,"4069617ba4991e585a28b01b2bddf8264ae1802d687bb707f7dcbde26d1ae745"],["projection-derivation-base-content-context-p13-full-residual-001","base-source-content-context",{"origin":"full-residual","persona_id":"p13","source_shard_id":"p13-source-intent-full-residual-shard-0001","source_shard_ordinal":1},2474392,"251ac5d62257504ff40e26df2194d550c98907b3de1fd33316fa0eee45fbe7b5"],["projection-derivation-base-content-context-p13-full-residual-002","base-source-content-context",{"origin":"full-residual","persona_id":"p13","source_shard_id":"p13-source-intent-full-residual-shard-0002","source_shard_ordinal":2},1317179,"f7a2910f4b34832df80c63e1ab731ab34c540ddfce74937c491ed5fe5e599d85"],["projection-derivation-base-content-context-p14-pilot-001","base-source-content-context",{"origin":"pilot","persona_id":"p14","source_shard_id":"p14-source-intent-pilot-shard-0001","source_shard_ordinal":1},724474,"94aa7850fd265a834616f590982bcc99da8ed3b3d325bd8c16b66f85ae9da6be"],["projection-derivation-base-content-context-p14-full-residual-001","base-source-content-context",{"origin":"full-residual","persona_id":"p14","source_shard_id":"p14-source-intent-full-residual-shard-0001","source_shard_ordinal":1},2478004,"d13c7b0b69d59dd32ae7bab5e45e89779f470427eb2902342f4d6ee6328aea05"],["projection-derivation-base-content-context-p14-full-residual-002","base-source-content-context",{"origin":"full-residual","persona_id":"p14","source_shard_id":"p14-source-intent-full-residual-shard-0002","source_shard_ordinal":2},2460534,"c18daa840d51dbf40c02b5272ad2e96dec6212cfb5160ec6ed7b1c91197d0dc9"],["projection-derivation-base-content-context-p14-full-residual-003","base-source-content-context",{"origin":"full-residual","persona_id":"p14","source_shard_id":"p14-source-intent-full-residual-shard-0003","source_shard_ordinal":3},2097433,"98dccb5937aa121d4314104a66823e93e86b7dd0f81cd57d14125a9c6212f675"],["projection-derivation-base-content-context-p15-pilot-001","base-source-content-context",{"origin":"pilot","persona_id":"p15","source_shard_id":"p15-source-intent-pilot-shard-0001","source_shard_ordinal":1},445358,"9136b26a1f86c9a490576aa5727144232d200f913139149fb2db18b423c40d27"],["projection-derivation-base-content-context-p15-full-residual-001","base-source-content-context",{"origin":"full-residual","persona_id":"p15","source_shard_id":"p15-source-intent-full-residual-shard-0001","source_shard_ordinal":1},2469389,"b5e5b1a43602d0cded4a968c6505a834fd07c5c0c9e22a2fe51e52f54bfb1046"],["projection-derivation-base-content-context-p15-full-residual-002","base-source-content-context",{"origin":"full-residual","persona_id":"p15","source_shard_id":"p15-source-intent-full-residual-shard-0002","source_shard_ordinal":2},1856600,"32f6ca214467227025f1e83de41b72eeea76fe4844848ece024e3fd9477925d8"],["projection-derivation-base-content-context-p16-pilot-001","base-source-content-context",{"origin":"pilot","persona_id":"p16","source_shard_id":"p16-source-intent-pilot-shard-0001","source_shard_ordinal":1},445165,"dfb2ffadb6614c97c1882f4d7fe6fb4302980c44340cd37235cd34396e73abce"],["projection-derivation-base-content-context-p16-full-residual-001","base-source-content-context",{"origin":"full-residual","persona_id":"p16","source_shard_id":"p16-source-intent-full-residual-shard-0001","source_shard_ordinal":1},2467313,"915296e151217b857d3c116f6e85a9d663631a8c2e714e92276ab755192b6d8a"],["projection-derivation-base-content-context-p16-full-residual-002","base-source-content-context",{"origin":"full-residual","persona_id":"p16","source_shard_id":"p16-source-intent-full-residual-shard-0002","source_shard_ordinal":2},1856913,"615148946e072de9fb9a00e7f7ab3830a8e4872d800f6c774f875d6a21820b5c"],["projection-derivation-base-content-context-p17-pilot-001","base-source-content-context",{"origin":"pilot","persona_id":"p17","source_shard_id":"p17-source-intent-pilot-shard-0001","source_shard_ordinal":1},445869,"50f8723e14f8c7854384c534ce2e07fb30ca58b0450fac58efd54df30d0578f1"],["projection-derivation-base-content-context-p17-full-residual-001","base-source-content-context",{"origin":"full-residual","persona_id":"p17","source_shard_id":"p17-source-intent-full-residual-shard-0001","source_shard_ordinal":1},2476126,"c4b4bbe09a8a0ba6216b2fb3ec3196c1d804ec150ca723ebe7aecef189afd11f"],["projection-derivation-base-content-context-p17-full-residual-002","base-source-content-context",{"origin":"full-residual","persona_id":"p17","source_shard_id":"p17-source-intent-full-residual-shard-0002","source_shard_ordinal":2},1854412,"95e115f3e968b468504a5fc099da1abaf6ab7010fa992348d68f9cf3a75940d7"],["projection-derivation-base-content-context-p18-pilot-001","base-source-content-context",{"origin":"pilot","persona_id":"p18","source_shard_id":"p18-source-intent-pilot-shard-0001","source_shard_ordinal":1},667511,"9afe910797ec47c63c3f83cfefbab3f4049711e9740f49a216d6237ed3a7c24e"],["projection-derivation-base-content-context-p18-full-residual-001","base-source-content-context",{"origin":"full-residual","persona_id":"p18","source_shard_id":"p18-source-intent-full-residual-shard-0001","source_shard_ordinal":1},2457748,"0dd91395ae42e503a8ccb0714ec6dcc4be5cc9e1d656fabd79162a1a8f24f271"],["projection-derivation-base-content-context-p18-full-residual-002","base-source-content-context",{"origin":"full-residual","persona_id":"p18","source_shard_id":"p18-source-intent-full-residual-shard-0002","source_shard_ordinal":2},2467084,"2968d218bbea97fde1aff68fde47f2ce88640636178a5e312ce56ab5d11bad06"],["projection-derivation-base-content-context-p18-full-residual-003","base-source-content-context",{"origin":"full-residual","persona_id":"p18","source_shard_id":"p18-source-intent-full-residual-shard-0003","source_shard_ordinal":3},1558898,"9717db87bc099723b566dd4923daad467a713957c34bd59b408ccc591277d750"],["projection-derivation-base-content-context-p19-pilot-001","base-source-content-context",{"origin":"pilot","persona_id":"p19","source_shard_id":"p19-source-intent-pilot-shard-0001","source_shard_ordinal":1},501828,"cec1e05785dc14b8b134b60de431ce546effc7e1d9e77f152ffb2653c6472919"],["projection-derivation-base-content-context-p19-full-residual-001","base-source-content-context",{"origin":"full-residual","persona_id":"p19","source_shard_id":"p19-source-intent-full-residual-shard-0001","source_shard_ordinal":1},2481579,"a45ae0264ae5689abc70a621193295992929bc8a759469dc24dd6cd0f9f7053e"],["projection-derivation-base-content-context-p19-full-residual-002","base-source-content-context",{"origin":"full-residual","persona_id":"p19","source_shard_id":"p19-source-intent-full-residual-shard-0002","source_shard_ordinal":2},2392161,"e9abf2d81962074d57256ceaf3d302bb22c97c32a0c1cb461eaed68992f41894"],["projection-derivation-base-content-context-p20-pilot-001","base-source-content-context",{"origin":"pilot","persona_id":"p20","source_shard_id":"p20-source-intent-pilot-shard-0001","source_shard_ordinal":1},557106,"5c9c9c7863b9d949fde6f95d804734ae27b8ea8b387d67bbeb8c101c73a5273c"],["projection-derivation-base-content-context-p20-full-residual-001","base-source-content-context",{"origin":"full-residual","persona_id":"p20","source_shard_id":"p20-source-intent-full-residual-shard-0001","source_shard_ordinal":1},2465009,"88aad8f1702178349ad529dc6311bbf22e486e796efcd952b6c45d04639754ec"],["projection-derivation-base-content-context-p20-full-residual-002","base-source-content-context",{"origin":"full-residual","persona_id":"p20","source_shard_id":"p20-source-intent-full-residual-shard-0002","source_shard_ordinal":2},2462841,"595926af0e50bba08f49e673207381bcfe0fb6cb6a800b4956700ae55407f92e"],["projection-derivation-base-content-context-p20-full-residual-003","base-source-content-context",{"origin":"full-residual","persona_id":"p20","source_shard_id":"p20-source-intent-full-residual-shard-0003","source_shard_ordinal":3},483044,"da4b133912a02152ac6f334b09d16b285dec556d223ddf5c8dcada0e17962250"],["projection-derivation-effective-membership-p01","effective-source-membership",{"persona_id":"p01"},103439,"d620a63b9762cf6119d795845c5b1533207ced29ae97fbb6ab3765a966d07f5e"],["projection-derivation-effective-membership-p02","effective-source-membership",{"persona_id":"p02"},103793,"5d5939f3e69e86802b753ecb43168e33dcb797418d1a73762538293301c496de"],["projection-derivation-effective-membership-p03","effective-source-membership",{"persona_id":"p03"},103447,"c1588bd6c2d6413e996eaf5cd985246b3acc15ddbf7b8f37da7519f717a182dd"],["projection-derivation-effective-membership-p04","effective-source-membership",{"persona_id":"p04"},103483,"3b719f5d727b814f0c64cc481a8b7fcf8cf4a693b66408db0c06daa8960c3d92"],["projection-derivation-effective-membership-p05","effective-source-membership",{"persona_id":"p05"},103494,"298246eb8eb172a18565e31daf7e6b551fcdc03c37b7d7cb8107e9973e8ec036"],["projection-derivation-effective-membership-p06","effective-source-membership",{"persona_id":"p06"},103084,"e8e8265192239b5e4bfd84a7c806e792f5267628051b9acea68060b1c903fc48"],["projection-derivation-effective-membership-p07","effective-source-membership",{"persona_id":"p07"},103141,"06290c65e5ada4d02b42b37adaa82158b1ef7822f91a7b1a424836ac7116a492"],["projection-derivation-effective-membership-p08","effective-source-membership",{"persona_id":"p08"},103100,"60e16ea9e8a0f6960211727de49f55d30dd5e3e0ce339ea8ef74cf580cabd224"],["projection-derivation-effective-membership-p09","effective-source-membership",{"persona_id":"p09"},103100,"5a94978734465c98a2852b90864ef0b850c0ee03a03fc1f4db5981ab233d7aa6"],["projection-derivation-effective-membership-p10","effective-source-membership",{"persona_id":"p10"},103452,"2077bcddae13536c7d87017bd265b3756383d82d6404b0af2c616f4b0538939b"],["projection-derivation-effective-membership-p11","effective-source-membership",{"persona_id":"p11"},103445,"af9b3401ecfb7e12cbe4ba689ad7e2289bbc2078d73d1eb23fc757496eff4f44"],["projection-derivation-effective-membership-p12","effective-source-membership",{"persona_id":"p12"},103840,"9ef924f289a50e1d78e4a0a42e5719077f4a754f93a525f6b44115c270eb51f7"],["projection-derivation-effective-membership-p13","effective-source-membership",{"persona_id":"p13"},103081,"07058f4379e66b3d4203340a5d243eebdc4a2645b3418c524c1915ed3b224be1"],["projection-derivation-effective-membership-p14","effective-source-membership",{"persona_id":"p14"},103437,"ffc4023e1a10d94f1ac93b2491596d0a53f772bfaa2ce4340de72e2d08ab57dc"],["projection-derivation-effective-membership-p15","effective-source-membership",{"persona_id":"p15"},103106,"b3e9fa174c6033bded58fb8c821d750a48d6b571d6b30755bddfe054b4f3c83c"],["projection-derivation-effective-membership-p16","effective-source-membership",{"persona_id":"p16"},103121,"43851b9c556ddce007a36feda355bec683138a53cb475c889afdedbcfb82b7d9"],["projection-derivation-effective-membership-p17","effective-source-membership",{"persona_id":"p17"},103084,"390d1e87330d31658e72866544fdcb49705d1d0162e49a1663932c75ce82be27"],["projection-derivation-effective-membership-p18","effective-source-membership",{"persona_id":"p18"},103430,"2cf145bcbf13c9e1ec72da74cce5ac654fab1d7a0a9fb77ac101a4675d024b5e"],["projection-derivation-effective-membership-p19","effective-source-membership",{"persona_id":"p19"},103055,"ffdae6826bcf841d3a862e9dcb374ed768118a5790b5b596c9f38ad05582aa12"],["projection-derivation-effective-membership-p20","effective-source-membership",{"persona_id":"p20"},103467,"04992d4efa12caa78a86aeb3d9dac1403aedf23b415092255322c0d18e097f8e"],["projection-derivation-concrete-overlay-relations-p01-pilot","concrete-overlay-relations",{"origin":"pilot","persona_id":"p01"},44642,"01b6fda1b8fea5b67a6d24adbbdc5b7f0b38435c0ed8b411adac33b9db8a4910"],["projection-derivation-concrete-overlay-relations-p01-full-residual","concrete-overlay-relations",{"origin":"full-residual","persona_id":"p01"},437242,"4d2dc9adfc0aa7322f6edbb04973c8334db14705a642b217cb3b73e7ba8a7a69"],["projection-derivation-concrete-overlay-relations-p02-pilot","concrete-overlay-relations",{"origin":"pilot","persona_id":"p02"},57289,"3f49586eccf40f1a4bd21f8d451728cd3ed4ac43602c448d4ffa664e72f02d96"],["projection-derivation-concrete-overlay-relations-p02-full-residual","concrete-overlay-relations",{"origin":"full-residual","persona_id":"p02"},561044,"f51fc854324691988f02552b3f6b4967e69b41ce5f0584995e1766734e25c544"],["projection-derivation-concrete-overlay-relations-p03-pilot","concrete-overlay-relations",{"origin":"pilot","persona_id":"p03"},34733,"8d2b1e45eec0dd11750da2baceaa5368744b1b66f8e9f23b2625853f5b962c51"],["projection-derivation-concrete-overlay-relations-p03-full-residual","concrete-overlay-relations",{"origin":"full-residual","persona_id":"p03"},340805,"dc6c72b61525413070d1536e9ccf402c91e0fd8b6529552f1636ed5ac3619a65"],["projection-derivation-concrete-overlay-relations-p04-pilot","concrete-overlay-relations",{"origin":"pilot","persona_id":"p04"},36864,"1316f5243dc5e14a514cf5d5508334761ce52627c9f9a5dbb05599e15ac6b1d9"],["projection-derivation-concrete-overlay-relations-p04-full-residual","concrete-overlay-relations",{"origin":"full-residual","persona_id":"p04"},360535,"566457e8685a7e3c0379e72af0417ea3d763d392586bba126501ef11579f5142"],["projection-derivation-concrete-overlay-relations-p05-pilot","concrete-overlay-relations",{"origin":"pilot","persona_id":"p05"},45640,"8534d94bdebf27bda6d6e432d4f9e306e6d22102d10842cae282e709e6c21c2f"],["projection-derivation-concrete-overlay-relations-p05-full-residual","concrete-overlay-relations",{"origin":"full-residual","persona_id":"p05"},446959,"2b4189bd26f245955128d32f2fd4a5ea013f312a40db4383a8a5f13c34a56cce"],["projection-derivation-concrete-overlay-relations-p06-pilot","concrete-overlay-relations",{"origin":"pilot","persona_id":"p06"},24690,"144504afa1599b81e16d299dbe8a024535706b2403d66033ba8004d759e8b72d"],["projection-derivation-concrete-overlay-relations-p06-full-residual","concrete-overlay-relations",{"origin":"full-residual","persona_id":"p06"},241974,"56836eee807a9238d97306f526f985f61df060fb55d7dba687cfddbd4c129ac0"],["projection-derivation-concrete-overlay-relations-p07-pilot","concrete-overlay-relations",{"origin":"pilot","persona_id":"p07"},29401,"66761f5002f2a86dc4e2e9cd8015f7523918aa1d80b867fcc9e15643448fb73f"],["projection-derivation-concrete-overlay-relations-p07-full-residual","concrete-overlay-relations",{"origin":"full-residual","persona_id":"p07"},287856,"f67e61dd6249b055071a904469ee3d8deb41d792ba8524dffa58e1ec49dc4f85"],["projection-derivation-concrete-overlay-relations-p08-pilot","concrete-overlay-relations",{"origin":"pilot","persona_id":"p08"},38650,"01b696ee7dfc354416cfc356f8bb79a3885c2b37b7cccbb50df1fb740d5257eb"],["projection-derivation-concrete-overlay-relations-p08-full-residual","concrete-overlay-relations",{"origin":"full-residual","persona_id":"p08"},379124,"2bbe6b6794f4f6459ef23889ccaa467fe4b0dee4f8bde6be9eeb8da2268897fa"],["projection-derivation-concrete-overlay-relations-p09-pilot","concrete-overlay-relations",{"origin":"pilot","persona_id":"p09"},38399,"f6022b6aa16bc103bf430f02823aa00ee1463e98ca7e942bdf003c1bf6f17108"],["projection-derivation-concrete-overlay-relations-p09-full-residual","concrete-overlay-relations",{"origin":"full-residual","persona_id":"p09"},376950,"c9fceff2e2c2e6f48aa9af31f8966811711f1004d036b338e3eab3b954fc98ba"],["projection-derivation-concrete-overlay-relations-p10-pilot","concrete-overlay-relations",{"origin":"pilot","persona_id":"p10"},53618,"8541ef7f6a7a5e3e54918d794725e318daa87284c3a92efd00c33078b9471067"],["projection-derivation-concrete-overlay-relations-p10-full-residual","concrete-overlay-relations",{"origin":"full-residual","persona_id":"p10"},525330,"32535b4e3000f09d4d3c724d5ba809889f5b427898e141c853bba0c703d964a1"],["projection-derivation-concrete-overlay-relations-p11-pilot","concrete-overlay-relations",{"origin":"pilot","persona_id":"p11"},45296,"d5e825594ab12317a62340ba495ec27e2d2d6033f7ff2a2b5d53b2831bb200ee"],["projection-derivation-concrete-overlay-relations-p11-full-residual","concrete-overlay-relations",{"origin":"full-residual","persona_id":"p11"},444422,"0889bef98fb7054c64959cc5a9b03db21b4dccc4229e5cd11cca2625ede30c3b"],["projection-derivation-concrete-overlay-relations-p12-pilot","concrete-overlay-relations",{"origin":"pilot","persona_id":"p12"},67132,"05874be1cdbdb9d873b665f2227790f9fbeba5931c9268e3879e6ab9f9838f4d"],["projection-derivation-concrete-overlay-relations-p12-full-residual","concrete-overlay-relations",{"origin":"full-residual","persona_id":"p12"},658944,"1b2faa5cf4edfa6b57e993f08a634ec89806bedbfd7b2f71101951ca91c2f2fc"],["projection-derivation-concrete-overlay-relations-p13-pilot","concrete-overlay-relations",{"origin":"pilot","persona_id":"p13"},29647,"0b391770d0ffade0a1407b9af1ce20e3636e266e288186a7722657c02fc17a02"],["projection-derivation-concrete-overlay-relations-p13-full-residual","concrete-overlay-relations",{"origin":"full-residual","persona_id":"p13"},290647,"4b2aa300e76c45d137c5c711913a4b0c00aef710ebe1dfc135f3557fbabf12d6"],["projection-derivation-concrete-overlay-relations-p14-pilot","concrete-overlay-relations",{"origin":"pilot","persona_id":"p14"},63367,"d99ed25de6d81e44081144e2de657d409b95c265243cb73163bc635349e38a2f"],["projection-derivation-concrete-overlay-relations-p14-full-residual","concrete-overlay-relations",{"origin":"full-residual","persona_id":"p14"},620867,"9804e1ee9f16afe32e75b7254678c16078147aa392b60819fa275dea0ac003d4"],["projection-derivation-concrete-overlay-relations-p15-pilot","concrete-overlay-relations",{"origin":"pilot","persona_id":"p15"},30706,"813e976e4dd3ef3bf8369a73cfc50b705f0914d5210d42aea5b2004e26d6fcef"],["projection-derivation-concrete-overlay-relations-p15-full-residual","concrete-overlay-relations",{"origin":"full-residual","persona_id":"p15"},301150,"89a0e655465d825f4c74a7937cacb9925f02f0a1082ff87fe6847f0f0b8535a5"],["projection-derivation-concrete-overlay-relations-p16-pilot","concrete-overlay-relations",{"origin":"pilot","persona_id":"p16"},24726,"36e1b3bd79c5ca22fae9492fe3d1a94201f6688cbef2e0fa718545a85dbda24f"],["projection-derivation-concrete-overlay-relations-p16-full-residual","concrete-overlay-relations",{"origin":"full-residual","persona_id":"p16"},242298,"58074d2fcac1acdaeceaccf69db746856f42d99e48978d815cdfe185bd1d05ab"],["projection-derivation-concrete-overlay-relations-p17-pilot","concrete-overlay-relations",{"origin":"pilot","persona_id":"p17"},36180,"5ac9942a3d06edc457359951a5a6562684539204923fa1ce717cf77ba352e014"],["projection-derivation-concrete-overlay-relations-p17-full-residual","concrete-overlay-relations",{"origin":"full-residual","persona_id":"p17"},354116,"bdd7580e19402a07f47da09d0de45c1a8a5c51b438171f8ff25d0290819b2168"],["projection-derivation-concrete-overlay-relations-p18-pilot","concrete-overlay-relations",{"origin":"pilot","persona_id":"p18"},44642,"12d661b479e29681090577361461e3ee841a41c6e8340bf5bf8214089ae7bedb"],["projection-derivation-concrete-overlay-relations-p18-full-residual","concrete-overlay-relations",{"origin":"full-residual","persona_id":"p18"},437242,"955d004ef7860882c83cd0ceb95d6821156ce6cdb8b7cfa2f5f461c1502dc625"],["projection-derivation-concrete-overlay-relations-p19-pilot","concrete-overlay-relations",{"origin":"pilot","persona_id":"p19"},41291,"fd037b4435fc4d5c906089c50607618f9a1d3036202f1e9360a0e5dbe6da84be"],["projection-derivation-concrete-overlay-relations-p19-full-residual","concrete-overlay-relations",{"origin":"full-residual","persona_id":"p19"},405163,"7f4ed2e9c5bbb06af2e35eac9636772ed903eaab9234b3c1d2aa9e286cfb6e3c"],["projection-derivation-concrete-overlay-relations-p20-pilot","concrete-overlay-relations",{"origin":"pilot","persona_id":"p20"},45206,"60629c529f2d6785c5573d5d3aa544cb208874e35e1a2653460bb3925f1fa08a"],["projection-derivation-concrete-overlay-relations-p20-full-residual","concrete-overlay-relations",{"origin":"full-residual","persona_id":"p20"},443622,"67d03842fdc7e0b7aca77677d2a373a480f1964f3ea63f7e539d9f86207a6c88"],["projection-derivation-source-instance-parameters-cell-catalog","source-instance-parameters",{"parameter_catalog_id":"global-source-parameter-cells-v1"},103149,"f215f54910fad0945f8975d5ab544f71b095fdd5b81b66c1aca8e94bc703594b"],["projection-derivation-source-instance-parameters-p01-pilot-001","source-instance-parameters",{"origin":"pilot","persona_id":"p01","source_shard_id":"p01-source-intent-pilot-shard-0001","source_shard_ordinal":1},92570,"a70de71e5d004443e6ba60c7128e0f406cf21759ca6de5357a97a6a3f00c9b86"],["projection-derivation-source-instance-parameters-p01-full-residual-001","source-instance-parameters",{"origin":"full-residual","persona_id":"p01","source_shard_id":"p01-source-intent-full-residual-shard-0001","source_shard_ordinal":1},349037,"d3bbafb2da5ceb03c7636604cd012ceaebdc233b627d85949b8af7caf1ea98a5"],["projection-derivation-source-instance-parameters-p01-full-residual-002","source-instance-parameters",{"origin":"full-residual","persona_id":"p01","source_shard_id":"p01-source-intent-full-residual-shard-0002","source_shard_ordinal":2},349618,"21714a67ca8119f90d8fd249835e60989df05962b8d5ccccd14ad8830c48a9ad"],["projection-derivation-source-instance-parameters-p01-full-residual-003","source-instance-parameters",{"origin":"full-residual","persona_id":"p01","source_shard_id":"p01-source-intent-full-residual-shard-0003","source_shard_ordinal":3},231919,"054ba2ad372b2c1bfd6f6a9c5747d362734a2201f0be021d6adb773f1ab8dca4"],["projection-derivation-source-instance-parameters-p02-pilot-001","source-instance-parameters",{"origin":"pilot","persona_id":"p02","source_shard_id":"p02-source-intent-pilot-shard-0001","source_shard_ordinal":1},115530,"4b094d0c9c420cba50b0c66b13f1be941cbcd3b67bae2144df2d17f38604176a"],["projection-derivation-source-instance-parameters-p02-full-residual-001","source-instance-parameters",{"origin":"full-residual","persona_id":"p02","source_shard_id":"p02-source-intent-full-residual-shard-0001","source_shard_ordinal":1},349766,"4ef4d8ad49a7846500e9065d4dc0f614dcb04a69bbe0e8fb882a184335e89722"],["projection-derivation-source-instance-parameters-p02-full-residual-002","source-instance-parameters",{"origin":"full-residual","persona_id":"p02","source_shard_id":"p02-source-intent-full-residual-shard-0002","source_shard_ordinal":2},348551,"a7a9a49d278cd7fc9ec2c78a9490cfd7804b372673c5e52b58e574f9584a5223"],["projection-derivation-source-instance-parameters-p02-full-residual-003","source-instance-parameters",{"origin":"full-residual","persona_id":"p02","source_shard_id":"p02-source-intent-full-residual-shard-0003","source_shard_ordinal":3},355887,"b8df79cf193c7b1d9a68eb25ec8645fd751e40c3bfa0cf4b25f58ebc3fe3309b"],["projection-derivation-source-instance-parameters-p02-full-residual-004","source-instance-parameters",{"origin":"full-residual","persona_id":"p02","source_shard_id":"p02-source-intent-full-residual-shard-0004","source_shard_ordinal":4},107236,"4f8c1128c920c9293f684a22f3c0b0bec0a01efc30f239351626c579eb236c1f"],["projection-derivation-source-instance-parameters-p03-pilot-001","source-instance-parameters",{"origin":"pilot","persona_id":"p03","source_shard_id":"p03-source-intent-pilot-shard-0001","source_shard_ordinal":1},78031,"34016ecc579af38453ff4641a9843a2374ec41cb192c950e3f4cc31a4bc21b92"],["projection-derivation-source-instance-parameters-p03-full-residual-001","source-instance-parameters",{"origin":"full-residual","persona_id":"p03","source_shard_id":"p03-source-intent-full-residual-shard-0001","source_shard_ordinal":1},350519,"08e6de055a7d22136e09d27aa7851ea41561423e410ee94317f91eff2ee34969"],["projection-derivation-source-instance-parameters-p03-full-residual-002","source-instance-parameters",{"origin":"full-residual","persona_id":"p03","source_shard_id":"p03-source-intent-full-residual-shard-0002","source_shard_ordinal":2},362190,"8acbc10078162e149b6769f57c682282962aa8363a80cd4f41a9b9176d40dc4f"],["projection-derivation-source-instance-parameters-p03-full-residual-003","source-instance-parameters",{"origin":"full-residual","persona_id":"p03","source_shard_id":"p03-source-intent-full-residual-shard-0003","source_shard_ordinal":3},70815,"c848d5cb036d0d9eb2446fb370689bcf32caf5e0617ee7d57b474e0eb2d9403c"],["projection-derivation-source-instance-parameters-p04-pilot-001","source-instance-parameters",{"origin":"pilot","persona_id":"p04","source_shard_id":"p04-source-intent-pilot-shard-0001","source_shard_ordinal":1},77345,"8e30def3b9f6a4282510d6ab7d09865acae86ab785b32808c83b05d3d2941352"],["projection-derivation-source-instance-parameters-p04-full-residual-001","source-instance-parameters",{"origin":"full-residual","persona_id":"p04","source_shard_id":"p04-source-intent-full-residual-shard-0001","source_shard_ordinal":1},349259,"e6b735b8f8ea611dbe7ec5fdcef326bfa10eba9bde91901e847577ebc2493631"],["projection-derivation-source-instance-parameters-p04-full-residual-002","source-instance-parameters",{"origin":"full-residual","persona_id":"p04","source_shard_id":"p04-source-intent-full-residual-shard-0002","source_shard_ordinal":2},358468,"e8968d05102c1ef070b7e4b4873a84d75b087b722d27bd8c4059bfff2b236f54"],["projection-derivation-source-instance-parameters-p04-full-residual-003","source-instance-parameters",{"origin":"full-residual","persona_id":"p04","source_shard_id":"p04-source-intent-full-residual-shard-0003","source_shard_ordinal":3},69620,"40dc236de5e5acd96e5991c6dea9347172c01aefd1227e487a2824a2da3b5b78"],["projection-derivation-source-instance-parameters-p05-pilot-001","source-instance-parameters",{"origin":"pilot","persona_id":"p05","source_shard_id":"p05-source-intent-pilot-shard-0001","source_shard_ordinal":1},93222,"f536f1ec2a3bb9a5a1ea7c0acd97c97440954116717eddf5d1415a46d5b43974"],["projection-derivation-source-instance-parameters-p05-full-residual-001","source-instance-parameters",{"origin":"full-residual","persona_id":"p05","source_shard_id":"p05-source-intent-full-residual-shard-0001","source_shard_ordinal":1},350248,"762d225f773a9baac75400ba54648437565eea027ac3ebe9fb21e9c7679eaa34"],["projection-derivation-source-instance-parameters-p05-full-residual-002","source-instance-parameters",{"origin":"full-residual","persona_id":"p05","source_shard_id":"p05-source-intent-full-residual-shard-0002","source_shard_ordinal":2},356307,"106f773d53f8424099b39d226986de709340ffba805a27983c26cdc1b1199f82"],["projection-derivation-source-instance-parameters-p05-full-residual-003","source-instance-parameters",{"origin":"full-residual","persona_id":"p05","source_shard_id":"p05-source-intent-full-residual-shard-0003","source_shard_ordinal":3},229716,"19506eeeb874c7a316094c5713fb6ebeb8f44acfdb2666994c12015d68667f08"],["projection-derivation-source-instance-parameters-p06-pilot-001","source-instance-parameters",{"origin":"pilot","persona_id":"p06","source_shard_id":"p06-source-intent-pilot-shard-0001","source_shard_ordinal":1},62922,"4f1dd39e7acc0bcb43f36341d71e88379313e4c6e2b1a16d261be5ee2af21535"],["projection-derivation-source-instance-parameters-p06-full-residual-001","source-instance-parameters",{"origin":"full-residual","persona_id":"p06","source_shard_id":"p06-source-intent-full-residual-shard-0001","source_shard_ordinal":1},356898,"b21e97595c895b634ff303a80b269a2fd7d0c33cdfc7d1d57f2c3a9f665d9e65"],["projection-derivation-source-instance-parameters-p06-full-residual-002","source-instance-parameters",{"origin":"full-residual","persona_id":"p06","source_shard_id":"p06-source-intent-full-residual-shard-0002","source_shard_ordinal":2},274393,"ff923725bb7cbf7aa3abf846ad0dda598c60eb923150ffff58750694fabeb862"],["projection-derivation-source-instance-parameters-p07-pilot-001","source-instance-parameters",{"origin":"pilot","persona_id":"p07","source_shard_id":"p07-source-intent-pilot-shard-0001","source_shard_ordinal":1},55492,"d82c8ce2f6e9827c447aa642315b12f8ab97c8b4bbaffc0854c667bf7e6574a9"],["projection-derivation-source-instance-parameters-p07-full-residual-001","source-instance-parameters",{"origin":"full-residual","persona_id":"p07","source_shard_id":"p07-source-intent-full-residual-shard-0001","source_shard_ordinal":1},362161,"1bda7c4734cb35b7acb24e3b223495234745664d07607b71bd73c6b132161b98"],["projection-derivation-source-instance-parameters-p07-full-residual-002","source-instance-parameters",{"origin":"full-residual","persona_id":"p07","source_shard_id":"p07-source-intent-full-residual-shard-0002","source_shard_ordinal":2},193999,"25e8f5f0cf7f01abe5ee629d5f14de29165de0dc7c6cf3bef617c6dfe4e91c95"],["projection-derivation-source-instance-parameters-p08-pilot-001","source-instance-parameters",{"origin":"pilot","persona_id":"p08","source_shard_id":"p08-source-intent-pilot-shard-0001","source_shard_ordinal":1},62579,"00b1c89293b44ce561b7adb975a25f11931baad35249999f9d349dc4644aa0df"],["projection-derivation-source-instance-parameters-p08-full-residual-001","source-instance-parameters",{"origin":"full-residual","persona_id":"p08","source_shard_id":"p08-source-intent-full-residual-shard-0001","source_shard_ordinal":1},359041,"be5f60e267717db28572078e92c3f42d3b4bdbfd5a5695dd950b53145ebf915b"],["projection-derivation-source-instance-parameters-p08-full-residual-002","source-instance-parameters",{"origin":"full-residual","persona_id":"p08","source_shard_id":"p08-source-intent-full-residual-shard-0002","source_shard_ordinal":2},269058,"f4ae369feb919f126cd3929d0e251976837c1c88eae24e8d67d7a428f02d565c"],["projection-derivation-source-instance-parameters-p09-pilot-001","source-instance-parameters",{"origin":"pilot","persona_id":"p09","source_shard_id":"p09-source-intent-pilot-shard-0001","source_shard_ordinal":1},70126,"c50ba5695f68118a2ce702ca0d6e40d12fa1121f9f791df486603504c30af8c8"],["projection-derivation-source-instance-parameters-p09-full-residual-001","source-instance-parameters",{"origin":"full-residual","persona_id":"p09","source_shard_id":"p09-source-intent-full-residual-shard-0001","source_shard_ordinal":1},356896,"1feea46016fa9058f8360f9b50fa53076f2969157f09e550975a863d051d53b6"],["projection-derivation-source-instance-parameters-p09-full-residual-002","source-instance-parameters",{"origin":"full-residual","persona_id":"p09","source_shard_id":"p09-source-intent-full-residual-shard-0002","source_shard_ordinal":2},347302,"ddc2022be00659959c71e271b8deb9b6a1559429d9d745b39b6e5e06123d618f"],["projection-derivation-source-instance-parameters-p10-pilot-001","source-instance-parameters",{"origin":"pilot","persona_id":"p10","source_shard_id":"p10-source-intent-pilot-shard-0001","source_shard_ordinal":1},86376,"8ebdf7bb4e28d14990f805fc6a8644df052eb461e23ff7d0320c8ebae59ba634"],["projection-derivation-source-instance-parameters-p10-full-residual-001","source-instance-parameters",{"origin":"full-residual","persona_id":"p10","source_shard_id":"p10-source-intent-full-residual-shard-0001","source_shard_ordinal":1},361095,"c7067f1fb0041918e83fde1591e758df64b0d2b84e14dc5fbaeb3a069f98cf95"],["projection-derivation-source-instance-parameters-p10-full-residual-002","source-instance-parameters",{"origin":"full-residual","persona_id":"p10","source_shard_id":"p10-source-intent-full-residual-shard-0002","source_shard_ordinal":2},356051,"96558ed261998a934b8a1ff7476d1a2147a9448d80684dfa585245b59063158a"],["projection-derivation-source-instance-parameters-p10-full-residual-003","source-instance-parameters",{"origin":"full-residual","persona_id":"p10","source_shard_id":"p10-source-intent-full-residual-shard-0003","source_shard_ordinal":3},149330,"1d2ab544661dd3a675bcd28607bdb79a12a26c4bc9ab1adca3be6353e358d5c0"],["projection-derivation-source-instance-parameters-p11-pilot-001","source-instance-parameters",{"origin":"pilot","persona_id":"p11","source_shard_id":"p11-source-intent-pilot-shard-0001","source_shard_ordinal":1},79301,"f9a2628cbf477c27b7a1de5798305920da90cd579a0e2e1418c3d0efb004ce9f"],["projection-derivation-source-instance-parameters-p11-full-residual-001","source-instance-parameters",{"origin":"full-residual","persona_id":"p11","source_shard_id":"p11-source-intent-full-residual-shard-0001","source_shard_ordinal":1},364292,"9edf42c508293d75a5d94d097deb01c6426a6bffa741cb4c6fac7e3388191cb7"],["projection-derivation-source-instance-parameters-p11-full-residual-002","source-instance-parameters",{"origin":"full-residual","persona_id":"p11","source_shard_id":"p11-source-intent-full-residual-shard-0002","source_shard_ordinal":2},360199,"e21e113945f42748ce40b432998f10c1b468972baf06548b418090ff66436e98"],["projection-derivation-source-instance-parameters-p11-full-residual-003","source-instance-parameters",{"origin":"full-residual","persona_id":"p11","source_shard_id":"p11-source-intent-full-residual-shard-0003","source_shard_ordinal":3},70252,"70241ee53b78c7968dc58df95672b7ad844ff96d6bc4afc1d0dcc58879e8598c"],["projection-derivation-source-instance-parameters-p12-pilot-001","source-instance-parameters",{"origin":"pilot","persona_id":"p12","source_shard_id":"p12-source-intent-pilot-shard-0001","source_shard_ordinal":1},124093,"0efe363a22b874cdd5ef81b1ebb9f54238c3b66616e7dd8e574e9dd83185d8e1"],["projection-derivation-source-instance-parameters-p12-full-residual-001","source-instance-parameters",{"origin":"full-residual","persona_id":"p12","source_shard_id":"p12-source-intent-full-residual-shard-0001","source_shard_ordinal":1},350225,"fc802098a110e5b7f2788883ddbf2bf25947c962c1f6bb6d594c2e73f17d0ebf"],["projection-derivation-source-instance-parameters-p12-full-residual-002","source-instance-parameters",{"origin":"full-residual","persona_id":"p12","source_shard_id":"p12-source-intent-full-residual-shard-0002","source_shard_ordinal":2},350903,"42afc3bb682ba933700cd0d5cbb4c0312d72f29186a804d5e4000e244445be8a"],["projection-derivation-source-instance-parameters-p12-full-residual-003","source-instance-parameters",{"origin":"full-residual","persona_id":"p12","source_shard_id":"p12-source-intent-full-residual-shard-0003","source_shard_ordinal":3},362301,"5b5159e08d66eda61cf6e8a1399089311ce13b29685382f1feb933250a27fd02"],["projection-derivation-source-instance-parameters-p12-full-residual-004","source-instance-parameters",{"origin":"full-residual","persona_id":"p12","source_shard_id":"p12-source-intent-full-residual-shard-0004","source_shard_ordinal":4},183193,"dbdb4cf75657debe31a995fefc87e1391abdcd915a01a61f5ae4455ea179c27f"],["projection-derivation-source-instance-parameters-p13-pilot-001","source-instance-parameters",{"origin":"pilot","persona_id":"p13","source_shard_id":"p13-source-intent-pilot-shard-0001","source_shard_ordinal":1},55840,"ee621611c8d483ba92012f8d5aec782469dfc9b2efda90d26949c6ea363c7ecd"],["projection-derivation-source-instance-parameters-p13-full-residual-001","source-instance-parameters",{"origin":"full-residual","persona_id":"p13","source_shard_id":"p13-source-intent-full-residual-shard-0001","source_shard_ordinal":1},367471,"1fd811c9e48bf7156e40ac9d76eaf3a02d14c866b96eecc05c4369349ce151a6"],["projection-derivation-source-instance-parameters-p13-full-residual-002","source-instance-parameters",{"origin":"full-residual","persona_id":"p13","source_shard_id":"p13-source-intent-full-residual-shard-0002","source_shard_ordinal":2},191953,"4bb0516f3bd6702d905b16fc3cac340d869b9ba23e6800a2e69240fdb8ed0fe4"],["projection-derivation-source-instance-parameters-p14-pilot-001","source-instance-parameters",{"origin":"pilot","persona_id":"p14","source_shard_id":"p14-source-intent-pilot-shard-0001","source_shard_ordinal":1},101920,"e031a1d3f0e3eac1a0fb4a521b896fc2011c93255f1172852f59d81664ac1766"],["projection-derivation-source-instance-parameters-p14-full-residual-001","source-instance-parameters",{"origin":"full-residual","persona_id":"p14","source_shard_id":"p14-source-intent-full-residual-shard-0001","source_shard_ordinal":1},354854,"ab916b9562fd1458e5b15d7fa5d3ae10148cf40c1048a02a441b5fd41dd60721"],["projection-derivation-source-instance-parameters-p14-full-residual-002","source-instance-parameters",{"origin":"full-residual","persona_id":"p14","source_shard_id":"p14-source-intent-full-residual-shard-0002","source_shard_ordinal":2},361122,"fda8c3f8bdd819fe65dbab156ef590be7c1eaae2ea964790b3b3b03f32347f3c"],["projection-derivation-source-instance-parameters-p14-full-residual-003","source-instance-parameters",{"origin":"full-residual","persona_id":"p14","source_shard_id":"p14-source-intent-full-residual-shard-0003","source_shard_ordinal":3},306713,"742c2afa7b361f64b03f170d23fb3456e8d15d9e18ce21a735ad3da9e87bbe34"],["projection-derivation-source-instance-parameters-p15-pilot-001","source-instance-parameters",{"origin":"pilot","persona_id":"p15","source_shard_id":"p15-source-intent-pilot-shard-0001","source_shard_ordinal":1},63201,"f273d3b486a32c7d3c14913deb3b3c417cd8cf2b8334216d5982940e44861b46"],["projection-derivation-source-instance-parameters-p15-full-residual-001","source-instance-parameters",{"origin":"full-residual","persona_id":"p15","source_shard_id":"p15-source-intent-full-residual-shard-0001","source_shard_ordinal":1},362963,"4aac4c6fcee907bf3d4612417aa8925bf83b92552420bee960cca9e40000767b"],["projection-derivation-source-instance-parameters-p15-full-residual-002","source-instance-parameters",{"origin":"full-residual","persona_id":"p15","source_shard_id":"p15-source-intent-full-residual-shard-0002","source_shard_ordinal":2},270771,"f99d40265e71d84b0c6b370f5b52dd631e87c5c328c75bfc76a863b68bfcd954"],["projection-derivation-source-instance-parameters-p16-pilot-001","source-instance-parameters",{"origin":"pilot","persona_id":"p16","source_shard_id":"p16-source-intent-pilot-shard-0001","source_shard_ordinal":1},63098,"751d20aff514a31741c320537ad0f9783eb83426616bb499bcb27c7025a20a58"],["projection-derivation-source-instance-parameters-p16-full-residual-001","source-instance-parameters",{"origin":"full-residual","persona_id":"p16","source_shard_id":"p16-source-intent-full-residual-shard-0001","source_shard_ordinal":1},360865,"76c6bc96efa125ff301905e6832624c745307b9dbf5d11ebd69e96a8cfaab9ef"],["projection-derivation-source-instance-parameters-p16-full-residual-002","source-instance-parameters",{"origin":"full-residual","persona_id":"p16","source_shard_id":"p16-source-intent-full-residual-shard-0002","source_shard_ordinal":2},271891,"e80b1e5107de10a7bd2d93bbef3f0f238af2a8f80c1fd540b0f1cc0174e9b345"],["projection-derivation-source-instance-parameters-p17-pilot-001","source-instance-parameters",{"origin":"pilot","persona_id":"p17","source_shard_id":"p17-source-intent-pilot-shard-0001","source_shard_ordinal":1},63163,"9d4274393baa0cf210ab9c1cdb91e29511cce3345780115935caf5192c331475"],["projection-derivation-source-instance-parameters-p17-full-residual-001","source-instance-parameters",{"origin":"full-residual","persona_id":"p17","source_shard_id":"p17-source-intent-full-residual-shard-0001","source_shard_ordinal":1},363747,"462dd60c92633b0988ea639224533adf3f1c1835d3c389dd44d8a27663677ee3"],["projection-derivation-source-instance-parameters-p17-full-residual-002","source-instance-parameters",{"origin":"full-residual","persona_id":"p17","source_shard_id":"p17-source-intent-full-residual-shard-0002","source_shard_ordinal":2},269609,"c439336db9e91fa00b90996f348ec517354bfcad79b72819fff55d66b91c3455"],["projection-derivation-source-instance-parameters-p18-pilot-001","source-instance-parameters",{"origin":"pilot","persona_id":"p18","source_shard_id":"p18-source-intent-pilot-shard-0001","source_shard_ordinal":1},93898,"4719ae3a321a91d91eec1a4008d2d73b81f69d405d410cebd6f9ca0b632e4e10"],["projection-derivation-source-instance-parameters-p18-full-residual-001","source-instance-parameters",{"origin":"full-residual","persona_id":"p18","source_shard_id":"p18-source-intent-full-residual-shard-0001","source_shard_ordinal":1},350604,"628baddd41db6322494a620ca1701880e3eb7686e078f663a0d459708d04a5d3"],["projection-derivation-source-instance-parameters-p18-full-residual-002","source-instance-parameters",{"origin":"full-residual","persona_id":"p18","source_shard_id":"p18-source-intent-full-residual-shard-0002","source_shard_ordinal":2},364560,"1a903e2eb69de79d2e47c48bd03a76b6d29ed4c9ce8f51ef440aeafe09e94785"],["projection-derivation-source-instance-parameters-p18-full-residual-003","source-instance-parameters",{"origin":"full-residual","persona_id":"p18","source_shard_id":"p18-source-intent-full-residual-shard-0003","source_shard_ordinal":3},227331,"c48799a991e6e9ffa9792e54da80ae22a5c9804af9d9749e83190e33ef9b4b2a"],["projection-derivation-source-instance-parameters-p19-pilot-001","source-instance-parameters",{"origin":"pilot","persona_id":"p19","source_shard_id":"p19-source-intent-pilot-shard-0001","source_shard_ordinal":1},70787,"bb107eeaaca62e9e6a4e823d5b1347dcb4c5559122af12d259310ae145c74e82"],["projection-derivation-source-instance-parameters-p19-full-residual-001","source-instance-parameters",{"origin":"full-residual","persona_id":"p19","source_shard_id":"p19-source-intent-full-residual-shard-0001","source_shard_ordinal":1},362138,"759aba46a43919bd70219a2a36f5b799059fe96a5c5b0004a25f4fd77cfdeeb7"],["projection-derivation-source-instance-parameters-p19-full-residual-002","source-instance-parameters",{"origin":"full-residual","persona_id":"p19","source_shard_id":"p19-source-intent-full-residual-shard-0002","source_shard_ordinal":2},347904,"7bbb92918db9b19fd2db5a71d75d258cfcff12433010fe98b1776d095a20fdb3"],["projection-derivation-source-instance-parameters-p20-pilot-001","source-instance-parameters",{"origin":"pilot","persona_id":"p20","source_shard_id":"p20-source-intent-pilot-shard-0001","source_shard_ordinal":1},78593,"cdfea902ff60963b6d5000f9c6567539ea57df766883683bbc3b3746524f9321"],["projection-derivation-source-instance-parameters-p20-full-residual-001","source-instance-parameters",{"origin":"full-residual","persona_id":"p20","source_shard_id":"p20-source-intent-full-residual-shard-0001","source_shard_ordinal":1},355258,"f4b2d5a6ee0c744c50ae620e2ced9af0d768fb96f8006cb3266d1b418a3e7f2f"],["projection-derivation-source-instance-parameters-p20-full-residual-002","source-instance-parameters",{"origin":"full-residual","persona_id":"p20","source_shard_id":"p20-source-intent-full-residual-shard-0002","source_shard_ordinal":2},362541,"93673bbfb4469305dbdaf2fe969b5a625d8554ae86d5e6c4e37d378a7e3c3682"],["projection-derivation-source-instance-parameters-p20-full-residual-003","source-instance-parameters",{"origin":"full-residual","persona_id":"p20","source_shard_id":"p20-source-intent-full-residual-shard-0003","source_shard_ordinal":3},70553,"750e192ae07b770dd9b12970144e229c1ed871fb026e0331b29ff7258cc6b186"],["projection-derivation-lifecycle-rules-p01","query-independent-lifecycle-fact-rendition-rules",{"persona_id":"p01"},253386,"3ab896112e5732b38e0b53a2d13ef20cccdb47d134d3ba0d038677bcea00cc05"],["projection-derivation-lifecycle-rules-p02","query-independent-lifecycle-fact-rendition-rules",{"persona_id":"p02"},250488,"67d7d781d570d6927aa84db882a294e7b7a87330feea354da1062f7e7394926e"],["projection-derivation-lifecycle-rules-p03","query-independent-lifecycle-fact-rendition-rules",{"persona_id":"p03"},250852,"84945b282b6b1913fc28a383bffaf5af66577dc295a81d39a7a49bd48deec207"],["projection-derivation-lifecycle-rules-p04","query-independent-lifecycle-fact-rendition-rules",{"persona_id":"p04"},256800,"330064e042bb811b1af9625757506c7ddc3beab180f5dc1970c823cde0b60cbc"],["projection-derivation-lifecycle-rules-p05","query-independent-lifecycle-fact-rendition-rules",{"persona_id":"p05"},253865,"6ccc3b6c6656ba63e9b68d62cdd61b8bf2fad576d590df81416622a5486f4061"],["projection-derivation-lifecycle-rules-p06","query-independent-lifecycle-fact-rendition-rules",{"persona_id":"p06"},254432,"d148748295a6a41aa3798f5bfa883f4a740f373c8caf42b282b85b6ab422bf42"],["projection-derivation-lifecycle-rules-p07","query-independent-lifecycle-fact-rendition-rules",{"persona_id":"p07"},251576,"a99f6a0a5f28254809ad69a351fb91fba95719d8210809ee38431758eaf0ff5a"],["projection-derivation-lifecycle-rules-p08","query-independent-lifecycle-fact-rendition-rules",{"persona_id":"p08"},254488,"be1b6be7ea3dc05638160aed921f64bee1309953ec01aafcf75f3e8ee37a2485"],["projection-derivation-lifecycle-rules-p09","query-independent-lifecycle-fact-rendition-rules",{"persona_id":"p09"},254631,"efc24aad5d9797a628dca269aaac9c05bc72d037a6b3cccca34cef6e54c9932f"],["projection-derivation-lifecycle-rules-p10","query-independent-lifecycle-fact-rendition-rules",{"persona_id":"p10"},254715,"b3c9db08f1104f3f8b0e0183b75664b3c44ec09757c45ba464d9a75a2146b43e"],["projection-derivation-lifecycle-rules-p11","query-independent-lifecycle-fact-rendition-rules",{"persona_id":"p11"},251491,"238dc10825129749b28f490f347142d56f7845fbd3a0c87790d3f17d0c5e5008"],["projection-derivation-lifecycle-rules-p12","query-independent-lifecycle-fact-rendition-rules",{"persona_id":"p12"},250645,"799620662d66416a8aa2a81cd64658d5b7be74a962659474ae9fcad1bd29086f"],["projection-derivation-lifecycle-rules-p13","query-independent-lifecycle-fact-rendition-rules",{"persona_id":"p13"},252072,"bfba095f2813566f285cd254942a8ab505efc541093ebdefb1b53351f8925c91"],["projection-derivation-lifecycle-rules-p14","query-independent-lifecycle-fact-rendition-rules",{"persona_id":"p14"},254387,"23cd11fa455d47b61fc38810f1a72bc155609e034eee2e142c9b73b110d33500"],["projection-derivation-lifecycle-rules-p15","query-independent-lifecycle-fact-rendition-rules",{"persona_id":"p15"},251229,"6d25e9c390592eda7b3727c7d3bb117d820acd013d5fd14d2f8cf98ccfeaa79e"],["projection-derivation-lifecycle-rules-p16","query-independent-lifecycle-fact-rendition-rules",{"persona_id":"p16"},251966,"1049e9251a5702f3d40f91f2b8b9fa9af156b9260ec8a302c32037c747b18923"],["projection-derivation-lifecycle-rules-p17","query-independent-lifecycle-fact-rendition-rules",{"persona_id":"p17"},251994,"07b236e15984f5e71eb583e6f491d75d1b759970275f45c871e278bfe1ae941c"],["projection-derivation-lifecycle-rules-p18","query-independent-lifecycle-fact-rendition-rules",{"persona_id":"p18"},251573,"3589f1457a7f231e904f734884684e1495a7c3e4be30707dff23eceeafa7414e"],["projection-derivation-lifecycle-rules-p19","query-independent-lifecycle-fact-rendition-rules",{"persona_id":"p19"},255022,"b23f60b52eea5871ee0f236ba5b93b10c26caecd3c47afc9a9e63e3ee6f6a06d"],["projection-derivation-lifecycle-rules-p20","query-independent-lifecycle-fact-rendition-rules",{"persona_id":"p20"},251675,"6d0bf32c17d5d2bc9a846a8a2aed88cb4a1a6949cc31fb6a04666f08f1ea7292"],["payload-equivalence-rules-global","payload-equivalence-rules",{},4288,"a23ca9032d9779d9ebdde1d490354f70e5f1c0a09db9e8e3eaea26098e477649"]]'''

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


class PersonaV2ReviewRequestCatalogValidationError(ValueError):
    """Raised for any request-catalog or authenticated dependency mismatch."""


def _fail(message):
    raise PersonaV2ReviewRequestCatalogValidationError(message)


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
            if len(item) > MAX_STRING_BYTES:
                _fail("review request string exceeds its canonical cap")
            try:
                encoded = item.encode("utf-8")
            except UnicodeError:
                _fail("review request string is not strict UTF-8")
            if len(encoded) > MAX_STRING_BYTES or unicodedata.normalize("NFC", item) != item:
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
    """Return bounded canonical JSON bytes after strict domain preflight."""

    _preflight(value)
    try:
        raw = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        _fail(f"review request catalog is not canonical JSON: {error}")
    if len(raw) > MAX_CATALOG_BYTES:
        _fail("review request catalog exceeds its byte cap")
    return raw


def _is_sha256(value):
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


LOCAL_COMPLETE_ORDERED_PIN_DIGEST = (
    "f524ddcccdd89a216b87d2ad8f98076c8eacabbc258e7b68d514162764a3a97c"
)
LOCAL_COMPLETE_CLASS_COUNTS = (
    ("topology-path-load", 1),
    ("realism-locale-security", 1),
    ("route-scores", 1),
    ("primary-use-case-corpus-half", 1),
    ("recipe-content-filename-policy", 1),
    ("fact-graph", 20),
    ("base-source-content-context", 73),
    ("effective-source-membership", 20),
    ("concrete-overlay-relations", 40),
    ("source-instance-parameters", 74),
    ("query-independent-lifecycle-fact-rendition-rules", 20),
    ("payload-equivalence-rules", 1),
)
LOCAL_RELEVANT_CLASS_IDENTITIES = {
    "topology-path-load": (
        "persona-pc-v2-topology-path-load-content-projection",
        "kio.persona.pc-topology-path-load-content-projection/v1",
        1,
        "canonical-json",
    ),
    "realism-locale-security": (
        "persona-pc-v2-realism-locale-security-content-projection",
        "kio.persona.pc-realism-locale-security-content-projection/v1",
        1,
        "canonical-json",
    ),
    "recipe-content-filename-policy": (
        "persona-pc-v2-recipe-content-filename-policy-content-projection",
        "kio.persona.pc-recipe-content-filename-policy-content-projection/v1",
        1,
        "canonical-json",
    ),
    "route-scores": (
        "persona-pc-v2-route-scores-content-projection",
        "kio.persona.pc-route-scores-content-projection/v1",
        1,
        "canonical-json",
    ),
    "concrete-overlay-relations": (
        "persona-pc-v2-concrete-overlay-relations-origin-projection",
        "kio.persona.pc-concrete-overlay-relations-origin-projection/v1",
        1,
        "canonical-jsonl-lf",
    ),
    "query-independent-lifecycle-fact-rendition-rules": (
        "persona-pc-v2-source-matched-lifecycle-content-projection",
        "kio.persona.pc-source-matched-lifecycle-content-projection/v1",
        1,
        "canonical-json",
    ),
    "payload-equivalence-rules": (
        "persona-pc-v2-payload-equivalence-rules-projection",
        "kio.persona.pc-payload-equivalence-rules-projection/v1",
        1,
        "canonical-json",
    ),
}


def _strict_complete_registry_rows():
    """Parse and authenticate the independent exact-253 literal registry."""

    def reject_duplicate_object_keys(pairs):
        keys = [key for key, _value in pairs]
        if len(keys) != len(set(keys)):
            _fail("complete receipt registry contains a duplicate coordinate key")
        return dict(pairs)

    try:
        materialized = json.loads(
            COMPLETE_ORDERED_RECEIPT_ROWS_JSON,
            object_pairs_hook=reject_duplicate_object_keys,
        )
    except PersonaV2ReviewRequestCatalogValidationError:
        raise
    except (TypeError, ValueError, UnicodeError):
        _fail("complete receipt registry literal is not strict JSON")
    if type(materialized) is not list or len(materialized) != 253:
        _fail("complete receipt registry must contain exactly 253 rows")

    rows = []
    for item in materialized:
        if type(item) is not list or len(item) != 5:
            _fail("complete receipt registry row schema drifted")
        receipt_id, class_id, coordinates, size, digest = item
        if (
            type(receipt_id) is not str
            or not receipt_id
            or len(receipt_id.encode("utf-8")) > MAX_STRING_BYTES
            or unicodedata.normalize("NFC", receipt_id) != receipt_id
            or type(class_id) is not str
            or class_id not in dict(LOCAL_COMPLETE_CLASS_COUNTS)
            or type(coordinates) is not dict
            or len(coordinates) > 4
            or type(size) is not int
            or type(size) is bool
            or not 0 < size <= 4 * 2**20
            or not _is_sha256(digest)
        ):
            _fail("complete receipt registry scalar domain drifted")
        coordinate_items = []
        for key, value in coordinates.items():
            if (
                type(key) is not str
                or not key
                or len(key.encode("utf-8")) > MAX_STRING_BYTES
                or unicodedata.normalize("NFC", key) != key
            ):
                _fail("complete receipt registry coordinate key drifted")
            if type(value) is str:
                if (
                    not value
                    or len(value.encode("utf-8")) > MAX_STRING_BYTES
                    or unicodedata.normalize("NFC", value) != value
                ):
                    _fail("complete receipt registry coordinate value drifted")
            elif (
                type(value) is not int
                or type(value) is bool
                or not 0 < value <= MAX_INTEGER_MAGNITUDE
            ):
                _fail("complete receipt registry coordinate value drifted")
            coordinate_items.append((key, value))
        rows.append(
            (
                receipt_id,
                class_id,
                tuple(sorted(coordinate_items)),
                size,
                digest,
            )
        )
    rows = tuple(rows)

    # Cardinality is checked before any set/digest work above this point.
    if len({row[0] for row in rows}) != 253:
        _fail("complete receipt registry IDs are not unique")
    if len({(row[3], row[4]) for row in rows}) != 253:
        _fail("complete receipt registry body identities are not unique")
    expected_class_order = tuple(
        class_id
        for class_id, count in LOCAL_COMPLETE_CLASS_COUNTS
        for _index in range(count)
    )
    if tuple(row[1] for row in rows) != expected_class_order:
        _fail("complete receipt registry class order/count drifted")
    if sum(row[3] for row in rows) != 155_741_381:
        _fail("complete receipt registry cumulative bytes drifted")

    # Dedicated exact-253 canonicalizer: do not relax the public 64-item cap.
    ordered_pin_rows = [
        {
            "canonical_bytes": row[3],
            "receipt_id": row[0],
            "sha256": row[4],
        }
        for row in rows
    ]
    raw = json.dumps(
        ordered_pin_rows,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    digest = _sha256(raw)
    if not hmac.compare_digest(digest, LOCAL_COMPLETE_ORDERED_PIN_DIGEST):
        _fail("complete receipt registry ordered digest drifted")
    if not hmac.compare_digest(
        digest, complete_validator.EXPECTED_ORDERED_PROJECTION_PINS_SHA256
    ):
        _fail("complete receipt registry differs from the independent inventory pin")
    return rows


def _authenticate_relevant_projection_membership():
    """Prove every explicit request pin is an exact complete-inventory member."""

    registry = _strict_complete_registry_rows()
    by_id = {row[0]: row for row in registry}
    relevant_by_class = {}
    relevant_count = 0
    expected = _expected_catalog_value()
    for request in expected["review_requests"]:
        for binding in request["projection_bindings"]:
            pins = binding["ordered_projection_pins"]
            if not pins:
                continue
            class_id = binding["projection_class_id"]
            identity = LOCAL_RELEVANT_CLASS_IDENTITIES.get(class_id)
            if identity is None:
                _fail("review projection uses an unregistered relevant class")
            class_rows = []
            for ordinal, pin in enumerate(pins, start=1):
                if (
                    pin["projection_ordinal"] != ordinal
                    or (
                        pin["artifact_kind"],
                        pin["artifact_schema"],
                        pin["artifact_schema_version"],
                        pin["body_framing"],
                    )
                    != identity
                ):
                    _fail("relevant projection identity/order drifted")
                row = (
                    pin["receipt_id"],
                    class_id,
                    tuple(sorted(pin["coordinates"].items())),
                    pin["canonical_bytes"],
                    pin["sha256"],
                )
                if by_id.get(pin["receipt_id"]) != row:
                    _fail("relevant projection is not an exact complete-inventory member")
                class_rows.append(row)
                relevant_count += 1
            if class_id in relevant_by_class:
                _fail("relevant projection class is split across request bindings")
            relevant_by_class[class_id] = tuple(class_rows)
    if relevant_count != 65 or set(relevant_by_class) != set(
        LOCAL_RELEVANT_CLASS_IDENTITIES
    ):
        _fail("relevant complete-inventory membership count drifted")
    for class_id, rows in relevant_by_class.items():
        registry_class_rows = tuple(row for row in registry if row[1] == class_id)
        if rows != registry_class_rows:
            _fail("relevant projection class does not bind its exact ordered receipt set")
    return True


def _live_subject_sources():
    return (
        (
            "topology",
            topology.build_topology_contract,
            topology.validate_topology_contract,
            topology.canonical_json_bytes,
        ),
        (
            "realism-profile",
            realism.build_realism_profile,
            realism.validate_realism_profile,
            realism.canonical_json_bytes,
        ),
        (
            "variant-catalog",
            variant.build_variant_catalog,
            variant.validate_variant_catalog,
            variant.canonical_json_bytes,
        ),
        (
            "route-affinity",
            route.build_route_affinity,
            route.validate_route_affinity,
            route.canonical_json_bytes,
        ),
        (
            "overlay-contract",
            overlay_contract.build_overlay_contract,
            overlay_contract.validate_overlay_contract,
            overlay_contract.canonical_json_bytes,
        ),
        (
            "overlay-reservation-suite",
            reservation.build_overlay_reservation_suite,
            reservation.validate_overlay_reservation_suite,
            reservation.canonical_json_bytes,
        ),
        (
            "chunk-accounting",
            chunk_accounting.build_chunk_accounting_contract,
            chunk_accounting.validate_chunk_accounting_contract,
            chunk_accounting.canonical_json_bytes,
        ),
    )


def _authenticate_live_subjects():
    """Authenticate seven live bodies plus the independent complete pin."""

    if (
        envelope.FIXTURE_ID != FIXTURE_ID
        or envelope.FIXTURE_SCHEMA_VERSION != FIXTURE_SCHEMA_VERSION
    ):
        _fail("persona fixture identity drifted")
    authenticated = []
    for subject_id, builder, validator_fn, canonicalizer in _live_subject_sources():
        expected = SUBJECT_PIN_SPECS[subject_id]
        try:
            value = builder()
            if type(value) is not dict or validator_fn(value) is not True:
                _fail(f"current subject validation failed for {subject_id}")
            raw = canonicalizer(value)
        except PersonaV2ReviewRequestCatalogValidationError:
            raise
        except Exception:
            _fail(f"current subject validation failed for {subject_id}")
        if type(raw) is not bytes:
            _fail(f"current subject canonicalizer failed for {subject_id}")
        actual = (
            value.get("artifact_kind"),
            value.get("artifact_schema"),
            value.get("artifact_schema_version"),
            len(raw),
            _sha256(raw),
        )
        if actual != expected:
            _fail(f"current subject pin drifted for {subject_id}")
        authenticated.append((subject_id, bytes(raw)))

    complete = SUBJECT_PIN_SPECS["complete-semantic-projection-inventory"]
    if (
        complete_validator.SUITE_KIND,
        complete_validator.SUITE_SCHEMA,
        complete_validator.ARTIFACT_SCHEMA_VERSION,
        complete_validator.EXPECTED_SUITE_CANONICAL_BYTES,
        complete_validator.EXPECTED_SUITE_SHA256,
    ) != complete:
        _fail("complete semantic projection inventory subject pin drifted")
    if (
        complete_validator.EXPECTED_CUMULATIVE_EXTERNAL_BODY_BYTES_FROZEN
        != 155_741_381
        or complete_validator.EXPECTED_ORDERED_PROJECTION_PINS_SHA256
        != "f524ddcccdd89a216b87d2ad8f98076c8eacabbc258e7b68d514162764a3a97c"
    ):
        _fail("complete semantic projection inventory ordered pin digest drifted")
    return tuple(authenticated)


def _authenticate_projection_contracts():
    """Bind all 65 literals to independent class contracts and all-253 pin."""

    global_specs = (
        (
            "topology-path-load",
            global_validator.TOPOLOGY_PROJECTION_KIND,
            global_validator.TOPOLOGY_PROJECTION_SCHEMA,
        ),
        (
            "realism-locale-security",
            global_validator.REALISM_PROJECTION_KIND,
            global_validator.REALISM_PROJECTION_SCHEMA,
        ),
        (
            "route-scores",
            global_validator.ROUTE_PROJECTION_KIND,
            global_validator.ROUTE_PROJECTION_SCHEMA,
        ),
    )
    literal_global_pins = tuple(
        (class_id, SINGLETON_PROJECTION_SPECS[class_id][3],
         SINGLETON_PROJECTION_SPECS[class_id][4])
        for class_id, _kind, _schema in global_specs
    )
    if tuple(global_validator.EXPECTED_PROJECTION_PINS) != literal_global_pins:
        _fail("global projection pin contract drifted")
    for class_id, kind, schema in global_specs:
        literal = SINGLETON_PROJECTION_SPECS[class_id]
        if (kind, schema) != literal[:2]:
            _fail(f"global projection identity drifted for {class_id}")

    recipe = SINGLETON_PROJECTION_SPECS["recipe-content-filename-policy"]
    if (corpus_validator.RECIPE_KIND, corpus_validator.RECIPE_SCHEMA) != recipe[:2]:
        _fail("recipe projection identity drifted")
    payload = SINGLETON_PROJECTION_SPECS["payload-equivalence-rules"]
    if (
        payload_validator.PROJECTION_KIND,
        payload_validator.PROJECTION_SCHEMA,
        payload_validator.EXPECTED_PROJECTION_BYTES,
        payload_validator.EXPECTED_PROJECTION_SHA256,
    ) != (payload[0], payload[1], payload[3], payload[4]):
        _fail("payload-equivalence projection pin contract drifted")
    if (
        relation_validator.RELATION_KIND
        != "persona-pc-v2-concrete-overlay-relations-origin-projection"
        or relation_validator.RELATION_SCHEMA
        != "kio.persona.pc-concrete-overlay-relations-origin-projection/v1"
        or relation_validator.EXPECTED_RELATION_BODY_COUNT != 40
    ):
        _fail("relation projection class contract drifted")
    if (
        lifecycle_validator.PROJECTION_KIND
        != "persona-pc-v2-source-matched-lifecycle-content-projection"
        or lifecycle_validator.PROJECTION_SCHEMA
        != "kio.persona.pc-source-matched-lifecycle-content-projection/v1"
    ):
        _fail("lifecycle projection class contract drifted")

    if len(RELATION_PROJECTION_PINS) != 40:
        _fail("relation projection literal count drifted")
    expected_relation_coordinates = tuple(
        (f"p{ordinal:02d}", origin)
        for ordinal in range(1, 21)
        for origin in ("pilot", "full-residual")
    )
    if tuple((row[0], row[1]) for row in RELATION_PROJECTION_PINS) != expected_relation_coordinates:
        _fail("relation projection literal order drifted")
    if sum(row[2] for row in RELATION_PROJECTION_PINS) != 8_988_409:
        _fail("relation projection literal byte total drifted")
    if len(LIFECYCLE_PROJECTION_PINS) != 20:
        _fail("lifecycle projection literal count drifted")
    if tuple(row[0] for row in LIFECYCLE_PROJECTION_PINS) != tuple(
        f"p{ordinal:02d}" for ordinal in range(1, 21)
    ):
        _fail("lifecycle projection literal order drifted")
    if sum(row[1] for row in LIFECYCLE_PROJECTION_PINS) != 5_057_286:
        _fail("lifecycle projection literal byte total drifted")
    all_sizes_and_digests = [
        (spec[3], spec[4]) for spec in SINGLETON_PROJECTION_SPECS.values()
    ] + [
        (row[2], row[3]) for row in RELATION_PROJECTION_PINS
    ] + [
        (row[1], row[2]) for row in LIFECYCLE_PROJECTION_PINS
    ]
    if len(all_sizes_and_digests) != 65 or any(
        type(size) is not int or size <= 0 or not _is_sha256(digest)
        for size, digest in all_sizes_and_digests
    ):
        _fail("explicit projection literal domain drifted")
    _authenticate_relevant_projection_membership()
    return True


def _subject_pin(subject_id):
    kind, schema, version, size, digest = SUBJECT_PIN_SPECS[subject_id]
    return {
        "artifact_kind": kind,
        "artifact_schema": schema,
        "artifact_schema_version": version,
        "body_framing": "canonical-json",
        "canonical_bytes": size,
        "coordinates": {},
        "sha256": digest,
        "subject_id": subject_id,
        "subject_role": "exact-current-review-subject",
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
        "coordinates": dict(coordinates),
        "projection_ordinal": ordinal,
        "receipt_id": receipt_id,
        "sha256": digest,
    }


def _singleton_projection_pin(class_id):
    kind, schema, framing, size, digest, receipt_id, coordinates = (
        SINGLETON_PROJECTION_SPECS[class_id]
    )
    return _projection_pin(
        kind=kind,
        schema=schema,
        framing=framing,
        size=size,
        digest=digest,
        receipt_id=receipt_id,
        ordinal=1,
        coordinates=coordinates,
    )


def _relation_projection_pins():
    return [
        _projection_pin(
            kind="persona-pc-v2-concrete-overlay-relations-origin-projection",
            schema="kio.persona.pc-concrete-overlay-relations-origin-projection/v1",
            framing="canonical-jsonl-lf",
            size=size,
            digest=digest,
            receipt_id=(
                "projection-derivation-concrete-overlay-relations-"
                f"{persona_id}-{origin}"
            ),
            ordinal=ordinal,
            coordinates={"origin": origin, "persona_id": persona_id},
        )
        for ordinal, (persona_id, origin, size, digest) in enumerate(
            RELATION_PROJECTION_PINS, start=1
        )
    ]


def _lifecycle_projection_pins():
    return [
        _projection_pin(
            kind="persona-pc-v2-source-matched-lifecycle-content-projection",
            schema="kio.persona.pc-source-matched-lifecycle-content-projection/v1",
            framing="canonical-json",
            size=size,
            digest=digest,
            receipt_id=f"projection-derivation-lifecycle-rules-{persona_id}",
            ordinal=ordinal,
            coordinates={"persona_id": persona_id},
        )
        for ordinal, (persona_id, size, digest) in enumerate(
            LIFECYCLE_PROJECTION_PINS, start=1
        )
    ]


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
        "ordered_projection_pins": pins,
        "pin_representation": "explicit-ordered-pins",
        "projection_class_id": class_id,
        "projection_count": len(pins),
    }


def _inventory_projection_binding():
    return {
        "aggregate": {
            "cumulative_canonical_bytes": 155_741_381,
            "ordered_projection_pins_sha256": (
                "f524ddcccdd89a216b87d2ad8f98076c8eacabbc258e7b68d514162764a3a97c"
            ),
        },
        "binding_id": "complete-inventory-all-253-ordered-pins",
        "mapping_relation": "inventory-ordered-pin-digest",
        "ordered_projection_pins": [],
        "pin_representation": "complete-inventory-ordered-pin-digest",
        "projection_class_id": "all-twelve-complete-inventory-classes",
        "projection_count": 253,
    }


def _request(ordinal, class_id, subject_ids, bindings):
    rubric_id, reviewer_kind, checks = RUBRIC_SPECS[class_id]
    return {
        "positive_receipt_bound": False,
        "projection_bindings": bindings,
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
        "subject_pins": [_subject_pin(subject_id) for subject_id in subject_ids],
    }


def _expected_catalog_value():
    topology_pin = _singleton_projection_pin("topology-path-load")
    realism_pin = _singleton_projection_pin("realism-locale-security")
    recipe_pin = _singleton_projection_pin("recipe-content-filename-policy")
    route_pin = _singleton_projection_pin("route-scores")
    relation_pins = _relation_projection_pins()
    payload_pin = _singleton_projection_pin("payload-equivalence-rules")
    lifecycle_pins = _lifecycle_projection_pins()
    requests = [
        _request(
            1,
            "topology-activity",
            ("topology",),
            [
                _projection_binding(
                    "topology-path-load-direct-owner",
                    "topology-path-load",
                    "direct-owner-chain",
                    [topology_pin],
                )
            ],
        ),
        _request(
            2,
            "realism-profile",
            ("realism-profile",),
            [
                _projection_binding(
                    "realism-locale-security-direct-owner",
                    "realism-locale-security",
                    "direct-owner-chain",
                    [realism_pin],
                )
            ],
        ),
        _request(
            3,
            "variant-profile",
            ("variant-catalog",),
            [
                _projection_binding(
                    "recipe-policy-variant-direct-owner",
                    "recipe-content-filename-policy",
                    "direct-owner-chain",
                    [recipe_pin],
                )
            ],
        ),
        _request(
            4,
            "route-human",
            ("route-affinity",),
            [
                _projection_binding(
                    "route-scores-direct-owner",
                    "route-scores",
                    "direct-owner-chain",
                    [route_pin],
                )
            ],
        ),
        _request(
            5,
            "overlay-reservation",
            ("overlay-contract", "overlay-reservation-suite"),
            [
                _projection_binding(
                    "concrete-relations-reservation-chain",
                    "concrete-overlay-relations",
                    "transitive-consumer-chain",
                    relation_pins,
                ),
                _projection_binding(
                    "payload-rules-overlay-direct-owner",
                    "payload-equivalence-rules",
                    "direct-owner-chain",
                    [payload_pin],
                ),
            ],
        ),
        _request(
            6,
            "chunk-accounting",
            ("chunk-accounting",),
            [
                _projection_binding(
                    "lifecycle-rules-chunk-accounting-transitive",
                    "query-independent-lifecycle-fact-rendition-rules",
                    "transitive-consumer-chain",
                    lifecycle_pins,
                )
            ],
        ),
        _request(
            7,
            "semantic-projection-inventory",
            ("complete-semantic-projection-inventory",),
            [_inventory_projection_binding()],
        ),
    ]
    return {
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
        "fixture_id": FIXTURE_ID,
        "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
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


@functools.lru_cache(maxsize=1)
def _expected_catalog_raw():
    """Cache only the immutable independent canonical expectation."""

    raw = canonical_json_bytes(_expected_catalog_value())
    if EXPECTED_CATALOG_BYTES is not None and len(raw) != EXPECTED_CATALOG_BYTES:
        _fail("independent review request reconstruction differs from its golden")
    if EXPECTED_CATALOG_SHA256 is not None and not hmac.compare_digest(
        _sha256(raw), EXPECTED_CATALOG_SHA256
    ):
        _fail("independent review request reconstruction differs from its golden")
    return bytes(raw)


def _validate_structural_contract(value):
    if type(value) is not dict or set(value) != TOP_LEVEL_FIELDS:
        _fail("review request catalog top-level schema drifted")
    authority = value["authority"]
    if type(authority) is not dict or tuple(authority) != AUTHORITY_FIELDS or any(
        type(flag) is not bool or flag is not False for flag in authority.values()
    ):
        _fail("review request catalog authority must be exact and all false")
    if value["g0_contract_frozen"] is not False:
        _fail("review request catalog cannot freeze G0")
    completion = value["completion_claims"]
    if (
        type(completion) is not dict
        or completion.get("positive_receipt_bound") is not False
        or completion.get("reviewer_identity_bound") is not False
    ):
        _fail("review request catalog cannot bind a receipt or reviewer")
    requests = value["review_requests"]
    if type(requests) is not list or len(requests) != 7:
        _fail("review request count drifted")
    if tuple(row.get("review_class_id") for row in requests) != REVIEW_CLASS_ORDER:
        _fail("review request class order drifted")

    subject_count = binding_count = explicit_pin_count = 0
    route_human_count = 0
    for ordinal, request in enumerate(requests, start=1):
        if type(request) is not dict or set(request) != REQUEST_FIELDS:
            _fail("review request field schema drifted")
        class_id = REVIEW_CLASS_ORDER[ordinal - 1]
        if (
            request["request_ordinal"] != ordinal
            or request["request_id"] != f"persona-v2-review-request-{class_id}"
            or request["request_status"]
            != "awaiting-independent-positive-receipt"
            or request["positive_receipt_bound"] is not False
        ):
            _fail("review request identity or non-authorizing status drifted")
        rubric_id, reviewer_kind, checks = RUBRIC_SPECS[class_id]
        if request["required_reviewer_kind"] != reviewer_kind:
            _fail("required reviewer kind drifted")
        if class_id == "route-human":
            if reviewer_kind != "independent-human":
                _fail("route review must require an independent human")
            route_human_count += 1
        contract = request["review_contract"]
        if type(contract) is not dict or set(contract) != REVIEW_CONTRACT_FIELDS:
            _fail("review rubric field schema drifted")
        if (
            contract["rubric_id"] != rubric_id
            or contract["rubric_version"] != 1
            or contract["ordered_check_ids"] != list(checks)
            or contract["approval_bound"] is not False
            or contract["review_decision_bound"] is not False
            or contract["reviewer_identity_bound"] is not False
            or contract["waiver_bound"] is not False
        ):
            _fail("review rubric contract drifted")

        subjects = request["subject_pins"]
        bindings = request["projection_bindings"]
        if type(subjects) is not list or type(bindings) is not list:
            _fail("review subject or projection binding is not an exact list")
        subject_count += len(subjects)
        binding_count += len(bindings)
        for subject in subjects:
            if type(subject) is not dict or set(subject) != SUBJECT_PIN_FIELDS:
                _fail("review subject pin schema drifted")
            if subject["subject_role"] != "exact-current-review-subject":
                _fail("review subject role drifted")
        for binding in bindings:
            if type(binding) is not dict or set(binding) != PROJECTION_BINDING_FIELDS:
                _fail("review projection binding schema drifted")
            aggregate = binding["aggregate"]
            pins = binding["ordered_projection_pins"]
            if type(aggregate) is not dict or set(aggregate) != AGGREGATE_FIELDS:
                _fail("review projection aggregate schema drifted")
            if type(pins) is not list or len(pins) > MAX_LIST_ITEMS:
                _fail("review explicit projection pin list drifted")
            explicit_pin_count += len(pins)
            for pin_ordinal, pin in enumerate(pins, start=1):
                if type(pin) is not dict or set(pin) != PROJECTION_PIN_FIELDS:
                    _fail("review projection pin schema drifted")
                if pin["projection_ordinal"] != pin_ordinal:
                    _fail("review projection pin order drifted")

    if (
        subject_count != 8
        or binding_count != 8
        or explicit_pin_count != 65
        or route_human_count != 1
        or value["summary"]
        != {
            "authority_grant_count": 0,
            "explicit_projection_pin_count": 65,
            "positive_receipt_count": 0,
            "projection_binding_count": 8,
            "review_request_count": 7,
            "route_human_request_count": 1,
            "subject_pin_count": 8,
        }
    ):
        _fail("review request catalog exact counts drifted")
    return True


def _validated_catalog_raw(value):
    raw = canonical_json_bytes(value)
    if EXPECTED_CATALOG_BYTES is not None and len(raw) != EXPECTED_CATALOG_BYTES:
        _fail("review request catalog differs from its frozen canonical pin")
    if EXPECTED_CATALOG_SHA256 is not None and not hmac.compare_digest(
        _sha256(raw), EXPECTED_CATALOG_SHA256
    ):
        _fail("review request catalog differs from its frozen canonical pin")
    expected_raw = _expected_catalog_raw()
    if not hmac.compare_digest(raw, expected_raw):
        _fail("review request catalog differs from independent reconstruction")
    snapshot = json.loads(raw.decode("utf-8"))
    _validate_structural_contract(snapshot)
    # Keep live trust outside the immutable expected-byte cache.  Otherwise an
    # upstream drift after the first validation would be accepted as current.
    _authenticate_live_subjects()
    _authenticate_projection_contracts()
    closing = canonical_json_bytes(value)
    if not hmac.compare_digest(raw, closing):
        _fail("caller-owned review request catalog mutated during validation")
    return raw


def validate_review_request_catalog(value):
    """Validate an exact detached catalog against independent reconstruction."""

    _validated_catalog_raw(value)
    return True


def review_request_catalog_bytes(value):
    """Validate and return immutable canonical request-catalog bytes."""

    return bytes(_validated_catalog_raw(value))


def review_request_catalog_sha256(value):
    """Validate and return the exact request-catalog SHA-256 digest."""

    return _sha256(review_request_catalog_bytes(value))


__all__ = [
    "ARTIFACT_KIND",
    "ARTIFACT_SCHEMA",
    "ARTIFACT_SCHEMA_VERSION",
    "EXPECTED_CATALOG_BYTES",
    "EXPECTED_CATALOG_SHA256",
    "MAX_CATALOG_BYTES",
    "MAX_STRING_BYTES",
    "PersonaV2ReviewRequestCatalogValidationError",
    "REVIEW_CLASS_ORDER",
    "canonical_json_bytes",
    "review_request_catalog_bytes",
    "review_request_catalog_sha256",
    "validate_review_request_catalog",
]
