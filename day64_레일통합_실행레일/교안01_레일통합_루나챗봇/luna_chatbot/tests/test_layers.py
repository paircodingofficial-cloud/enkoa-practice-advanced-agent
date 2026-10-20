"""레이어드 아키텍처: 아래 층이 위 층을 import 하지 않는지 확인한다(core -> tools -> guards -> graph -> 실행, 화면)."""
import ast
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"

# 층 번호가 작을수록 아래 층이다. 같은 층이나 아래 층만 import 할 수 있다
LAYERS = {"core": 0, "tools": 1, "guards": 2, "graph": 3, "main": 4, "evaluate": 4, "ui": 4}


def layer_of(module_name: str) -> int:
    """app.x.y 모양 모듈 이름의 층 번호를 돌려준다."""
    return LAYERS[module_name.split(".")[1]]


def imported_app_modules(path: Path) -> list:
    """파일 하나가 import 하는 app. 모듈 이름 목록을 돌려준다."""
    names = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app."):
            names.append(node.module)
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("app."):
                    names.append(alias.name)
    return names


def test_lower_layers_do_not_import_upper_layers():
    checked = 0
    violations = []
    for path in APP_DIR.rglob("*.py"):
        relative = path.relative_to(APP_DIR.parent).with_suffix("")
        module_name = ".".join(relative.parts)
        if module_name.endswith("__init__") or module_name == "app":
            continue
        checked += 1
        for imported in imported_app_modules(path):
            if layer_of(imported) > layer_of(module_name):
                violations.append(f"{module_name} -> {imported}")
    # 검사한 파일이 0 개면 통과가 거짓이므로 개수도 확인한다
    assert checked >= 20
    assert violations == []
