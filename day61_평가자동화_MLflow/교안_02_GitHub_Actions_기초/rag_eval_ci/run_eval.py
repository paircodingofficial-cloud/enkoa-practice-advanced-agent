"""골든셋으로 app.py 를 평가해 reports/ 에 결과를 남깁니다.

사용: uv run python run_eval.py --split smoke   (변경 요청마다, 대표 사례만)
      uv run python run_eval.py --split full    (야간·수동, 전체 사례)
합격 여부는 여기서 정하지 않고 tests/ 의 pytest 가 reports/results.json 을 읽어 판정합니다.
"""
import argparse
import json
import os
from pathlib import Path

import mlflow
import pandas as pd

# DeepEval 이 사용 기록을 외부로 보내지 않게 합니다. deepeval 을 불러오기 전에 정해야 합니다.
os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"
from deepeval.metrics import GEval
from deepeval.models import OpenAIModel
from deepeval.test_case import LLMTestCase, SingleTurnParams
from mlflow.entities import Feedback
from mlflow.genai.scorers import scorer

import app

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "reports"
# 판사 모델: 생성 모델과 다른 모델로 채점합니다. 판사를 바꾸면 기준선도 새로 만듭니다.
# gpt-5.6-luna 는 temperature 를 지정할 수 없는 모델이라 지정하지 않습니다.
JUDGE_MODEL = os.getenv("OPENAI_EVAL_MODEL", "gpt-5.6-luna")
judge_llm = OpenAIModel(model=JUDGE_MODEL)
# 회귀 게이트가 통과·실패를 판정할 때 쓰는 채점 함수 이름 목록입니다. @scorer 함수 이름과 같아야 합니다.
JUDGED_SCORERS = ["correctness", "citation_valid"]


def read_jsonl(path):
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


source_texts = {}
for doc in read_jsonl(ROOT / "data" / "docs.jsonl"):
    source_texts[doc["doc_id"]] = doc["text"]


def normalize(text):
    for mark in ["･", "∙", "・", "•"]:
        text = text.replace(mark, "·")
    return " ".join(text.split())


def check_citation(citation, source_texts, searched_ids):
    """인용 하나가 이번 답변의 실제 근거인지 차례로 검사해, 처음 걸린 문제 또는 "확인"을 돌려줍니다.

    citation: 답변 부분에 붙은 인용 하나입니다. {"evidence_id": 근거 ID, "quote": 인용 구절}
    source_texts: 근거 ID -> 문서 원문 사전입니다.
    searched_ids: 이번 질문에서 검색해 온 문서의 근거 ID 목록입니다.
    반환값: 아래 순서로 검사해 처음 걸린 문제를 돌려줍니다. 모두 통과하면 "확인"입니다.
        "없는 근거 ID": 문서에 없는 근거 ID 를 인용함
        "검색하지 않은 문서": 있는 문서지만 이번 질문에서 검색하지 않음
        "원문에 없는 문구": 표기를 맞춘(normalize) 뒤에도 인용 구절이 원문에 없음
    """
    cited_id = citation["evidence_id"]
    if cited_id not in source_texts:
        return "없는 근거 ID"
    if cited_id not in searched_ids:
        return "검색하지 않은 문서"
    if normalize(citation["quote"]) not in normalize(source_texts[cited_id]):
        return "원문에 없는 문구"
    return "확인"


@scorer
def citation_valid(outputs):
    problems = []
    for segment in outputs["segments"]:
        for citation in segment["citations"]:
            status = check_citation(citation, source_texts, outputs["searched_ids"])
            if status != "확인":
                problems.append(f"{status}: {citation['evidence_id']}")

    if len(problems) == 0:
        return Feedback(value=True, rationale="붙은 인용이 모두 근거 ID·문구 대조를 통과함")
    return Feedback(value=False, rationale="; ".join(problems))


# 정답 판정의 판단 단계입니다. 정답 답변(expected_output)과 비교합니다.
CORRECTNESS_STEPS = [
    "expected_output 에 적힌 사실이 actual_output 에 모두 들어 있는지 본다.",
    "숫자, 기간, 대상, 조건이 하나라도 다르거나 빠지면 틀린 것으로 본다.",
    "expected_output 이 자료에서 확인할 수 없다는 안내이면, actual_output 도 확인할 수 없다고 답해야 맞다.",
    "판정 이유(reason)는 한국어로 쓴다.",
]


@scorer
def correctness(inputs, outputs, expectations):
    # DeepEval G-Eval 을 MLflow 채점 함수로 감쌉니다. 정답 답변은 골든셋의 expected_output 입니다.
    # 평가는 여러 질문을 동시에 채점하므로, 지표를 부를 때마다 새로 만들어 점수가 섞이지 않게 합니다.
    metric = GEval(
        name="정답 판정",
        evaluation_steps=CORRECTNESS_STEPS,
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.EXPECTED_OUTPUT],
        model=judge_llm,
        threshold=0.7,
        async_mode=False,  # 지표 안에서 비동기로 호출하지 않습니다(동시 채점 중 이벤트 루프 오류를 막습니다).
    )

    # 여러 질문을 동시에 채점하므로 진행 표시를 끕니다(켜 두면 표시가 서로 겹칩니다).
    metric.measure(LLMTestCase(input=inputs["question"], actual_output=outputs["answer"], expected_output=expectations["expected_output"]), _show_indicator=False)
    return Feedback(value=metric.success, rationale=metric.reason)


def to_records(cases):
    """골든 사례를 evaluate 가 읽는 inputs·expectations 형식으로 바꿉니다."""
    records = []
    for case in cases:
        expectations = {"case_id": case["case_id"], "expected_output": case["expected_output"]}
        records.append({"inputs": {"question": case["input"]}, "expectations": expectations})
    return records


def pass_rates(cases, case_ids):
    """case_ids 사례 가운데 채점 함수마다 통과한 비율을 계산합니다. 전체를 셀 때는 list(cases), 빠른 점검(smoke) 사례만 셀 때는 그 ID 목록을 넘깁니다."""
    rates = {}
    for name in JUDGED_SCORERS:
        passed = 0
        for case_id in case_ids:
            if cases[case_id][name] is True:
                passed += 1
        rates[name] = round(passed / len(case_ids), 4)
    return rates


def make_report(result, split):
    """평가 결과를 case_id 별 통과 여부와 지표로 정리합니다. pytest 는 이 dict 만 읽습니다."""
    cases = {}
    errors = 0
    for _, row in result.result_df.iterrows():
        case = {}
        for name in JUDGED_SCORERS:
            value = row[f"{name}/value"]
            # 채점 중 오류가 난 행은 값이 비어 있습니다. 통과로 세지 않고 오류로 셉니다.
            if pd.isna(value):
                errors += 1
                case[name] = None
            else:
                # 채점 함수는 True/False 로 판정을 남깁니다. numpy 의 참거짓도 bool 로 맞춥니다.
                case[name] = bool(value == True)
        cases[row["case_id/value"]] = case
    return {"split": split, "run_id": result.run_id, "errors": errors,
            "metrics": pass_rates(cases, list(cases)), "cases": cases}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["smoke", "full"], default="smoke")
    args = parser.parse_args()

    cases = []
    for case in read_jsonl(ROOT / "data" / "golden.jsonl"):
        # smoke 는 유형별 대표 사례만 골라 변경 요청마다 빠르고 싸게 돌립니다.
        if args.split == "full" or case["smoke"]:
            cases.append(case)

    REPORTS.mkdir(exist_ok=True)
    mlflow.set_tracking_uri(f"sqlite:///{REPORTS / 'mlflow.db'}")
    # 자동 추적을 끕니다. 켜 두면 평가가 실행 기록을 못 찾고 멈추는 일이 있습니다. 기록은 @mlflow.trace 로 남깁니다.
    mlflow.langchain.autolog(disable=True)
    mlflow.openai.autolog(disable=True)
    mlflow.set_experiment("library-rag-ci")
    with mlflow.start_run(run_name=f"ci-{args.split}"):
        mlflow.log_param("split", args.split)
        mlflow.log_param("top_k", app.TOP_K)
        mlflow.log_param("prompt_version", app.PROMPT_VERSION)
        mlflow.log_param("app_model", app.MODEL_NAME)
        mlflow.log_param("judge_model", JUDGE_MODEL)
        result = mlflow.genai.evaluate(data=to_records(cases), predict_fn=app.answer_with_citations,
                                       scorers=[correctness, citation_valid])
        report = make_report(result, args.split)
        mlflow.log_metric("errors", report["errors"])

    (REPORTS / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # CI 화면의 요약에 붙일 표입니다. 판정은 통과·실패·오류로 적고, 실패한 사례는 질문을 함께 적습니다.
    labels = {True: "통과", False: "실패", None: "오류"}
    lines = [f"## RAG 평가 결과 ({args.split}, {len(cases)}건, 채점 오류 {report['errors']}건)", "",
             "| 사례 | 정답 판정 | 인용 검증 |", "|---|---|---|"]
    failed = []
    for case in cases:
        judged = report["cases"][case["case_id"]]
        lines.append(f"| {case['case_id']} | {labels[judged['correctness']]} | {labels[judged['citation_valid']]} |")
        if judged["correctness"] is not True or judged["citation_valid"] is not True:
            failed.append(f"- {case['case_id']}: {case['input']}")
    lines.append("")
    for name, value in report["metrics"].items():
        lines.append(f"- {name}: {value}")
    if len(failed) > 0:
        lines += ["", "### 통과하지 못한 사례", ""] + failed
    (REPORTS / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report["metrics"], ensure_ascii=False), "errors:", report["errors"])


if __name__ == "__main__":
    main()
