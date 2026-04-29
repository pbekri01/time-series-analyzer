import pandas as pd

from tsproj.core.ts_core.pipeline import analyze_many


def test_analyze_many_smoke():
    df1 = pd.DataFrame({
        "Entity": ["A"] * 8,
        "Year": [2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007],
        "Value1": [1, 2, 3, 4, 5, 6, 7, 8],
    })

    df2 = pd.DataFrame({
        "Entity": ["A"] * 8,
        "Year": [2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007],
        "Value2": [2, 4, 6, 8, 10, 12, 14, 16],
    })

    dfs = {
        "series_1": df1,
        "series_2": df2,
    }

    result = analyze_many(
        dfs,
        max_lag=2,
        period=1,
        min_points=5,
        normalization="zscore",
    )

    assert "meta" in result
    assert "entities" in result
    assert "A" in result["entities"]

    entity = result["entities"]["A"]
    assert "pairwise_analysis" in entity
    assert len(entity["pairwise_analysis"]) == 1

    pair = entity["pairwise_analysis"][0]
    assert pair["series_A"] == "series_1"
    assert pair["series_B"] == "series_2"