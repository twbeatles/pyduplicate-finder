import pytest

from cli import _parse_args


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0", 0.0),
        ("1", 1.0),
        ("0.9", 0.9),
    ],
)
def test_parse_args_accepts_similarity_threshold_boundary_values(raw, expected):
    args = _parse_args(["D:/scan-target", "--similarity-threshold", raw])
    assert float(args.similarity_threshold) == expected


@pytest.mark.parametrize("raw", ["-0.1", "1.5"])
def test_parse_args_rejects_similarity_threshold_out_of_range(raw):
    with pytest.raises(SystemExit) as ex:
        _parse_args(["D:/scan-target", "--similarity-threshold", raw])
    assert int(ex.value.code or 0) == 2
