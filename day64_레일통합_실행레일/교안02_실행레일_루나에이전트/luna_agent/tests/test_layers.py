"""층 구조 테스트: 아래 층(core -> tools -> guards -> graph -> main, evaluate, ui)이 위 층을 import 하지 않는다."""
import ast
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"

# 층 번호: 숫자가 작을수록 아래 층
LAYERS = {"core": 0, "tools": 1, "guards": 2, "graph": 3, "main": 4, "evaluate": 4, "ui": 4}


def layer_of(module_name: str) -> int:
    """app.x.y 모듈 이름의 층 번호."""
    return LAYERS[module_name.split(".")[1]]


def imported_app_modules(path: Path) -> list:
    """파일이 import 하는 app.* 모듈 이름 목록."""
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
    """모든 app 모듈이 자기 층 이하만 import 한다."""
    checked = 0
    for path in APP_DIR.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        module = "app." + ".".join(path.relative_to(APP_DIR).with_suffix("").parts)
        for imported in imported_app_modules(path):
            assert layer_of(imported) <= layer_of(module), f"{module} 이 위 층 {imported} 를 import 한다"
        checked += 1
    assert checked >= 20


def test_every_module_has_main_check():
    """모든 모듈이 uv run -m 으로 돌려 볼 수 있는 if __name__ == "__main__" 블록을 가진다."""
    for path in APP_DIR.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        assert 'if __name__ == "__main__":' in path.read_text(encoding="utf-8"), path
