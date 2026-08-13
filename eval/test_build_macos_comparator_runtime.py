import hashlib
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "eval" / "build_macos_comparator_runtime.sh"
README = ROOT / "eval" / "README.md"


class ComparatorRuntimeBuilderContractTests(unittest.TestCase):
    def test_builder_uses_zsh_canonicalization_not_nonportable_realpath(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("/usr/bin/realpath", source)
        self.assertIn("readonly ADMIN_SCRIPT=${0:A}", source)
        self.assertIn('[[ "$0" == "$ADMIN_SCRIPT"', source)

    def test_verify_preflight_precedes_any_smoke_workspace_or_tool_execution(self):
        source = SCRIPT.read_text(encoding="utf-8")
        verify = source.split("if [[ $mode == verify ]]; then", 1)[1].split(
            "\nfi\n[[ ${EUID} -eq 0 ]]", 1
        )[0]
        preflight = verify.index("runtime is not built and mounted")
        read_only = verify.index("MNT_RDONLY is not set")
        workspace = verify.index('/bin/mkdir -m 0700 -- "$VERIFY_ROOT"')
        first_tool = verify.index('"$RUNTIME_ROOT/bin/rga-preproc"')
        self.assertLess(preflight, workspace)
        self.assertLess(read_only, workspace)
        self.assertLess(workspace, first_tool)

    def test_readme_pins_current_script_and_chains_verify_after_build(self):
        source = SCRIPT.read_bytes()
        readme = README.read_text(encoding="utf-8")
        match = re.search(r"Expected for this revision: ([0-9a-f]{64})", readme)
        self.assertIsNotNone(match)
        self.assertEqual(hashlib.sha256(source).hexdigest(), match.group(1))
        self.assertIn("' build-runtime \"$admin_dir\" &&", readme)


if __name__ == "__main__":
    unittest.main()
