import json
from pathlib import Path

import pytest

from codecov_cli.services.staticanalysis import analyze_file
from codecov_cli.services.staticanalysis.types import FileAnalysisRequest

here = Path(__file__)
here_parent = here.parent


@pytest.mark.parametrize(
    "input_filename,output_filename",
    [
        ("samples/inputs/sample_001.py", "samples/outputs/sample_001.json"),
        ("samples/inputs/sample_002.py", "samples/outputs/sample_002.json"),
        ("samples/inputs/sample_003.js", "samples/outputs/sample_003.json"),
    ],
)
def test_sample_analysis(input_filename, output_filename):
    config = {}
    res = analyze_file(
        config, FileAnalysisRequest(Path(input_filename), Path(input_filename))
    )
    with open(output_filename, "r") as file:
        expected_result = json.load(file)
    json_res = json.dumps(res.asdict())
    res_dict = json.loads(json_res)
    assert sorted(res_dict["result"].keys()) == sorted(expected_result["result"].keys())
    res_dict["result"]["functions"] = sorted(
        res_dict["result"]["functions"], key=lambda x: x["start_line"]
    )
    expected_result["result"]["functions"] = sorted(
        expected_result["result"]["functions"], key=lambda x: x["start_line"]
    )
    assert res_dict["result"]["functions"] == expected_result["result"]["functions"]
    assert res_dict["result"].get("statements") == expected_result["result"].get(
        "statements"
    )
    assert res_dict["result"] == expected_result["result"]
    assert res_dict == expected_result
