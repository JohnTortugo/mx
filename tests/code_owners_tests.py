import atexit
import json
import os
import shutil
import sys
import tempfile

import mx_codeowners
from mx._impl import mx

# Note for future maintainer: if this is ever converted to pytest,
# the TempFileTree class would work well as a fixture:
#
# @pytest.fixture
# def temp_file_tree():
#    tree = TempFileTree()
#    try:
#        yield tree
#    finally:
#        tree.cleanup()


class TempFileTree:
    def __init__(self):
        self.dirs_to_remove = []
        pass

    def cleanup(self):
        self.exit_handler_(self.dirs_to_remove)

    def exit_handler_(self, dirs_to_remove):
        for d in dirs_to_remove:
            try:
                shutil.rmtree(d)
            except FileNotFoundError:
                pass

    def make_tree_files(self, basedir, description):
        for filename, contents in description.items():
            full_path = os.path.join(basedir, filename)
            if isinstance(contents, str):
                with open(full_path, "w") as f:
                    f.write(contents)
            else:
                os.mkdir(full_path)
                self.make_tree_files(full_path, contents)

    def make_tree(self, description):
        td = tempfile.mkdtemp()
        atexit.register(TempFileTree.exit_handler_, self, [td])
        self.dirs_to_remove.append(td)
        self.make_tree_files(td, description)
        return td


# ----------------
# Here starts the actual tests
# ----------------


def test_owners_of_generate_cases():
    yield (
        "smoke test",
        {
            "OWNERS.toml": """
                [[rule]]
                files = "*"
                any = "user1@example.com"
                """,
        },
        [
            ("README.md", {"any": ["user1@example.com"]}),
        ],
    )

    yield (
        "default in root",
        {
            "OWNERS.toml": """
                [[rule]]
                files = "*"
                any = "user1@example.com"
                """,
        },
        [
            ("src/Main.java", {"any": ["user1@example.com"]}),
        ],
    )

    yield (
        "no top-level fallback",
        {
            "src": {
                "OWNERS.toml": """
                    [[rule]]
                    files = "*.java"
                    any = "user1@example.com"
                    """,
            },
            "src2": {
                "OWNERS.toml": """
                    [[rule]]
                    files = "*.java"
                    any = "ignored@example.com"
                    """,
            },
        },
        [
            ("src/Main.java", {"any": ["user1@example.com"]}),
            ("README.md", {}),
        ],
    )

    yield (
        "basic inheritance and overwriting",
        {
            "src": {
                "OWNERS.toml": """
                    [[rule]]
                    files = "*.java"
                    any = "with_top_level@example.com"
                    """,
            },
            "src2": {
                "OWNERS.toml": """
                    [properties]
                    overwrite_parent = true
                    [[rule]]
                    files = "*.java"
                    any = "only_me@example.com"
                    """,
            },
            "OWNERS.toml": """
                [[rule]]
                files = "*.java"
                any = "toplevel@example.com"
                """,
        },
        [
            ("src/Main.java", {"any": ["toplevel@example.com", "with_top_level@example.com"]}),
            ("src2/Main.java", {"any": ["only_me@example.com"]}),
            ("README.md", {}),
            ("Main.java", {"any": ["toplevel@example.com"]}),
        ],
    )

    yield (
        "nested overwrite",
        {
            "src": {
                "OWNERS.toml": """
                    [properties]
                    overwrite_parent = true
                    [[rule]]
                    files = "*.java"
                    any = "overwrite1@example.com"
                    """,
                "nested": {
                    "OWNERS.toml": """
                        [properties]
                        overwrite_parent = true
                        [[rule]]
                        files = "*.java"
                        any = "overwrite2@example.com"
                        """,
                },
            },
            "OWNERS.toml": """
                [[rule]]
                files = "*.java"
                any = "toplevel@example.com"
                """,
        },
        [
            ("src/nested/NestedClass.java", {"any": ["overwrite2@example.com"]}),
            ("src/Class.java", {"any": ["overwrite1@example.com"]}),
            ("Main.java", {"any": ["toplevel@example.com"]}),
        ],
    )

    yield (
        "disabled overwrite",
        {
            "src": {
                "OWNERS.toml": """
                    [properties]
                    overwrite_parent = false
                    [[rule]]
                    files = "*.java"
                    any = "disabledoverwrite@example.com"
                    """
            },
            "OWNERS.toml": """
                [[rule]]
                files = "*.java"
                any = "toplevel@example.com"
                """,
        },
        [
            ("src/Class.java", {"any": ["disabledoverwrite@example.com", "toplevel@example.com"]}),
            ("Main.java", {"any": ["toplevel@example.com"]}),
        ],
    )

    yield (
        "overwriting/inheritance with nesting and multiple rules",
        {
            "src": {
                "OWNERS.toml": """
                    [[rule]]
                    files = "*_benchmark.py"
                    all = "benchmarking@example.com"
                    """,
                "nested_overwritten": {
                    "OWNERS.toml": """
                        [properties]
                        overwrite_parent = true
                        [[rule]]
                        files = "*.py"
                        any = "only_me@example.com"
                        [[rule]]
                        files = "*.toml"
                        any = "toml@example.com"
                        """,
                },
                "nested_inherited": {
                    "OWNERS.toml": """
                        [[rule]]
                        files = "*"
                        any = "one_more_owner@example.com"
                        """,
                },
            },
            "OWNERS.toml": """
                [[rule]]
                files = "*"
                any = "toplevel@example.com"
                [[rule]]
                files = "*.java"
                all = "team_lead_java@example.com"
                [[rule]]
                files = "*.py"
                all = "team_lead_python@example.com"
                """,
        },
        [
            ("src/nested_overwritten/Nested.java", {}),
            ("src/nested_overwritten/OWNERS.toml", {"any": ["toml@example.com"]}),
            ("src/nested_overwritten/mx_benchmark.py", {"any": ["only_me@example.com"]}),
            ("src/nested_overwritten/Overwritten.java", {}),
            (
                "src/nested_inherited/Inherited.java",
                {"any": ["one_more_owner@example.com", "toplevel@example.com"], "all": ["team_lead_java@example.com"]},
            ),
            (
                "src/nested_inherited/mx_benchmark.py",
                {
                    "any": ["one_more_owner@example.com", "toplevel@example.com"],
                    "all": ["benchmarking@example.com", "team_lead_python@example.com"],
                },
            ),
            ("src/Main.java", {"any": ["toplevel@example.com"], "all": ["team_lead_java@example.com"]}),
            ("src/mx_test.py", {"any": ["toplevel@example.com"], "all": ["team_lead_python@example.com"]}),
            (
                "src/mx_benchmark.py",
                {"any": ["toplevel@example.com"], "all": ["benchmarking@example.com", "team_lead_python@example.com"]},
            ),
            ("run.py", {"any": ["toplevel@example.com"], "all": ["team_lead_python@example.com"]}),
            ("README.md", {"any": ["toplevel@example.com"]}),
        ],
    )

    yield (
        "multiple OWNERS lines",
        {
            "OWNERS.toml": """
                [[rule]]
                files = "*"
                any = "all@example.com"
                [[rule]]
                files = "*.java"
                any = "java@example.com"
                """,
        },
        [
            ("src/Main.java", {"any": ["all@example.com", "java@example.com"]}),
            ("README.md", {"any": ["all@example.com"]}),
        ],
    )

    yield (
        "multiple patterns",
        {
            "OWNERS.toml": """
                [[rule]]
                files = "*.md *.txt"
                any = "doc@example.com"
                [[rule]]
                files = "*.java"
                any = "java@example.com scala@example.com"
                """,
        },
        [
            ("src/Main.java", {"any": ["java@example.com", "scala@example.com"]}),
            ("README.md", {"any": ["doc@example.com"]}),
        ],
    )

    yield (
        "any, all and at_least_one_mandatory_approver modifiers",
        {
            "OWNERS.toml": """
                [[rule]]
                files = "*.java"
                any = "user1@example.com user2@example.com"
                [[rule]]
                files = "*.md"
                all = "user3@example.com user1@example.com"
                [[rule]]
                files = "*.py"
                at_least_one_mandatory_approver = "user4@example.com user1@example.com"
                """,
        },
        [
            ("Main.java", {"any": ["user1@example.com", "user2@example.com"]}),
            ("README.md", {"all": ["user1@example.com", "user3@example.com"]}),
            ("script.py", {"at_least_one_mandatory_approver": ["user1@example.com", "user4@example.com"]}),
        ],
    )

    yield (
        "whitespace split and explicit lists",
        {
            "OWNERS.toml": """
                [[rule]]
                files = "*.java *.scala"
                any = ["user1@example.com", "user2@example.com"]
                [[rule]]
                files = ["*.md", "*.txt"]
                all = "user3@example.com user1@example.com"
                """,
        },
        [
            ("Main.java", {"any": ["user1@example.com", "user2@example.com"]}),
            ("Main.scala", {"any": ["user1@example.com", "user2@example.com"]}),
            ("README.md", {"all": ["user1@example.com", "user3@example.com"]}),
            ("index.txt", {"all": ["user1@example.com", "user3@example.com"]}),
        ],
    )


def test_owners_of():
    temp_tree = TempFileTree()
    for test_name, tree_description, owner_checks in test_owners_of_generate_cases():
        print("test_owners_of('" + test_name + "')")

        base_dir = temp_tree.make_tree(tree_description)

        fo = mx_codeowners.FileOwners(base_dir)
        for filename, owners in owner_checks:
            assert fo.get_owners_of(os.path.join(base_dir, filename)) == owners


def get_mx_binary():
    self_dir = os.path.dirname(os.path.realpath(__file__))
    top_mx_dir = os.path.normpath(os.path.join(self_dir, ".."))
    return os.path.normpath(os.path.join(top_mx_dir, "mx"))


def run_in_mx(args, cwd):
    # Ensure attribute existence for test
    setattr(mx._opts, "verbose", False)
    setattr(mx._opts, "warn", True)
    setattr(mx._opts, "quiet", True)
    setattr(mx._opts, "exec_log", None)
    setattr(mx._opts, "ptimeout", 0)

    dev_null = mx.TeeOutputCapture(mx.OutputCapture())
    mx_bin = get_mx_binary()
    mx_command = [mx_bin] + args

    # print("[debug] Will run {} in {}".format(mx_command, args))
    rc = mx.run(
        mx_command,
        out=dev_null,
        cwd=cwd,
    )
    assert rc == 0


def json_dump_with_header(header, data):
    print(header)
    json.dump(data, sys.stdout, indent=4, sort_keys=True)
    print("")


def test_codeowners_json_output_generate_cases():
    yield (
        "smoke test",
        {
            "OWNERS.toml": """
                [[rule]]
                files = "*"
                any = "user1@example.com"
                """,
        },
        [
            "README.md",
        ],
        {
            "branch": None,
            "files": ["README.md"],
            "mx_version": str(mx.version),
            "owners": {"README.md": {"any": ["user1@example.com"]}},
            "pull_request": {
                "approvals": ["grant@example.com"],
                "author": "author@example.com",
                "reviewers": [
                    "reviewer@example.com",
                    "grant@example.com",
                ],
                "suggestion": {
                    "acquire_approval": [],
                    "add": ["user1@example.com"],
                    "details": {"all": [], "any": ["user1@example.com"], "at_least_one_mandatory_approver": []},
                },
            },
            "version": 1,
        },
    )

    yield (
        "multiple files",
        {
            "OWNERS.toml": """
                [[rule]]
                files = "*.java"
                any = ["user1@example.com"]

                [[rule]]
                files = "*.scala"
                any = ["user2@example.com"]
                """,
        },
        [
            "src/Alpha.java",
            "src/Bravo.scala",
        ],
        {
            "branch": None,
            "files": [
                "src/Alpha.java",
                "src/Bravo.scala",
            ],
            "mx_version": str(mx.version),
            "owners": {
                "src/Alpha.java": {
                    "any": [
                        "user1@example.com",
                    ]
                },
                "src/Bravo.scala": {
                    "any": [
                        "user2@example.com",
                    ]
                },
            },
            "pull_request": {
                "approvals": ["grant@example.com"],
                "author": "author@example.com",
                "reviewers": [
                    "reviewer@example.com",
                    "grant@example.com",
                ],
                "suggestion": {
                    "acquire_approval": [],
                    "add": [
                        "user1@example.com",
                        "user2@example.com",
                    ],
                    "details": {
                        "all": [],
                        "any": [
                            "user1@example.com",
                            "user2@example.com",
                        ],
                        "at_least_one_mandatory_approver": [],
                    },
                },
            },
            "version": 1,
        },
    )


def test_codeowners_json_output():
    # This test needs to launch mx itself.
    # Doing that on Windows is somewhat more difficult than just running mx.run
    if os.name == "nt":
        print("test_codeowners_json_output skipped on Windows")
        return

    temp_tree = TempFileTree()

    mx_suite_files = {
        ".mx_vcs_root": "",
        "unittest": {
            "mx.unittest": {
                "suite.py": """suite = { "mxversion": "7.4.0", "name": "unittest", "ignore_suite_commit_info": True}""",
            },
        },
    }

    for test_name, tree_description, modified_files, expected_json in test_codeowners_json_output_generate_cases():
        print("test_codeowners_json_output('" + test_name + "')")
        base_dir = temp_tree.make_tree(
            {
                **tree_description,
                **mx_suite_files,
            }
        )

        mx_args = [
            "--primary-suite=unittest",
            "codeowners",
            "-j__codeowners.json",
            "-rreviewer@example.com",
            "-ggrant@example.com",
            "-pauthor@example.com",
            "-s",
            "--",
        ] + modified_files

        run_in_mx(mx_args, base_dir)

        with open(os.path.join(base_dir, "__codeowners.json"), "r") as inp:
            json_output = json.load(inp)

        # FIXME: replace with plain assert once this runs within a reasonable
        # testing framework (pytest does pretty good diff even on dicts)
        if json_output != expected_json:
            json_dump_with_header("-- Expected --", expected_json)
            json_dump_with_header("-- Actual --", json_output)
            assert json_output == expected_json


def tests():
    test_codeowners_json_output()
    test_owners_of()


if __name__ == "__main__":
    tests()
