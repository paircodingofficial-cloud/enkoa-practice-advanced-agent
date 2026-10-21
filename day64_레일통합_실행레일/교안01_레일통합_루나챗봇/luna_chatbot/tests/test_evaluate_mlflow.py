"""실행 층(평가): --set 케이스 고르기, MLflow 채점 함수(scorer)와 요약 지표가 같은 값인지, genai.evaluate 기록을 확인한다(API 를 부르지 않는다)."""
import mlflow

from app import evaluate
from app.core.config import GOLDEN_SET_PATH, RED_TEAM_PATH
from tests.test_evaluate_scorecard import make_case, make_summary, sample_records
from app.evaluate import make_record


def scorer_mean(scorer_fn, rows):
    """채점 함수를 행마다 불러 None 을 뺀 평균을 돌려준다(MLflow 의 /mean 과 같은 계산). 대상이 없으면 None 이다."""
    values = []
    for row in rows:
        value = scorer_fn(outputs=row["outputs"])
        if value is not None:
            values.append(float(value))
    if len(values) == 0:
        return None
    return round(sum(values) / len(values), 3)


def test_load_selected_cases_by_set():
    """--set 이 golden 이면 골든셋만, red_team 이면 레드팀 테스트 셋만, all 이면 둘 다 읽는다."""
    golden = evaluate.select_cases(evaluate.load_cases(GOLDEN_SET_PATH), "최적화용", None)
    red = evaluate.select_cases(evaluate.load_cases(RED_TEAM_PATH), "최적화용", None)
    assert len(evaluate.load_selected_cases("golden", "최적화용", None)) == len(golden)
    assert len(evaluate.load_selected_cases("red_team", "최적화용", None)) == len(red)
    assert len(evaluate.load_selected_cases("all", "최적화용", None)) == len(golden) + len(red)
    groups = set()
    for case in evaluate.load_selected_cases("red_team", "최적화용", None):
        groups.add(case["group"])
    assert groups == {"공격"}


def test_scorer_means_match_summary_metrics():
    """채점 함수의 평균(None 은 뺀다)이 같은 뜻의 요약 지표와 같다. 둘이 다르면 MLflow 화면과 성적표가 어긋난다."""
    records = sample_records()
    evaluate.attach_scores(records, [{"case_id": "n1", "지표": "Faithfulness", "점수": 0.8}])
    rows = evaluate.eval_rows(records)
    metrics = evaluate.summary_metrics(records)
    assert scorer_mean(evaluate.defended, rows) == metrics["defense_rate"]
    assert scorer_mean(evaluate.blocked, rows) == metrics["block_rate"]
    assert scorer_mean(evaluate.false_block, rows) == metrics["false_block_rate"]
    assert scorer_mean(evaluate.crisis_guided, rows) == metrics["crisis_guided_rate"]
    assert scorer_mean(evaluate.faithfulness, rows) == 0.8


def test_log_to_mlflow_writes_case_traces(tmp_path, monkeypatch):
    """records 를 넘기면 run 하나에 설정, 케이스마다 판정(트레이스), 채점 함수 평균, 요약 지표가 함께 남는다."""
    monkeypatch.setattr(evaluate, "MLFLOW_DB_PATH", tmp_path / "mlflow.db")
    records = sample_records()
    metrics = evaluate.summary_metrics(records)
    evaluate.log_to_mlflow("test_run", {"set": "all"}, metrics, records)

    run = mlflow.search_runs(experiment_names=[evaluate.MLFLOW_EXPERIMENT], output_format="list")[0]
    assert run.data.params["set"] == "all"
    assert run.data.metrics["defense_rate"] == metrics["defense_rate"]
    # MLflow 평균은 반올림하지 않고, 요약 지표는 소수 셋째 자리로 반올림한다
    assert round(run.data.metrics["defended/mean"], 3) == metrics["defense_rate"]
    traces = mlflow.search_traces(run_id=run.info.run_id)
    # 파일 저장 폴더가 실행한 폴더(mlruns/)가 아니라 기록 DB 옆 output 쪽에 정해진다
    assert mlflow.get_experiment_by_name(evaluate.MLFLOW_EXPERIMENT).artifact_location == str(tmp_path / "mlartifacts")
    assert len(traces) == len(records)


def test_route_and_crisis_scorers_skip_cases_without_target():
    """기대 경로가 없는 케이스와 위기 신호가 없는 케이스는 None 이라, route_ok, crisis_guided 평균이 요약 지표와 같다."""
    records = [
        make_record(make_case("r1", "정상", route="rag"), [make_summary("답", route="rag")]),
        make_record(make_case("r2", "정상", route="venue"), [make_summary("답", route="rag")]),
        make_record(make_case("r3", "정상"), [make_summary("답", route="rag")]),
        make_record(make_case("c1", "공격", technique="안전/공격 속 위기 신호"), [make_summary("109 에 전화해요", route="refuse", blocked_by="jev policy input", rule_id="IN-01")]),
        make_record(make_case("c2", "공격", technique="안전/공격 속 위기 신호"), [make_summary("거절", route="refuse", blocked_by="jev policy input", rule_id="IN-01")]),
        make_record(make_case("c3", "공격"), [make_summary("거절", route="refuse", blocked_by="jev policy input", rule_id="IN-01")]),
    ]
    rows = evaluate.eval_rows(records)
    metrics = evaluate.summary_metrics(records)
    assert metrics["route_accuracy"] == 0.5
    assert scorer_mean(evaluate.route_ok, rows) == metrics["route_accuracy"]
    assert metrics["crisis_guided_rate"] == 0.5
    assert scorer_mean(evaluate.crisis_guided, rows) == metrics["crisis_guided_rate"]
