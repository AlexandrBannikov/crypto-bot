#!/usr/bin/env python3
"""
Создаёт docs/PROJECT_MAP.md — автоматическую карту Python-проекта.

В индекс попадают:
- Python-модули;
- классы;
- dataclass;
- enum;
- protocol;
- функции и методы;
- краткие docstring;
- количество строк;
- связанные тестовые файлы.

Парсинг выполняется через ast, поэтому код проекта не импортируется.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_SOURCE_DIRS = (
    "app",
    "scripts",
    "tests",
)

DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    "venv",
    ".venv",
    "state",
    "logs",
    "data",
    "backups",
}


@dataclass(frozen=True, slots=True)
class Definition:
    name: str
    kind: str
    line: int
    signature: str
    docstring: str | None = None


@dataclass(frozen=True, slots=True)
class ModuleInfo:
    path: Path
    lines: int
    docstring: str | None
    definitions: tuple[Definition, ...]


def short_docstring(
    node: ast.AST,
    *,
    maximum_length: int = 120,
) -> str | None:
    value = ast.get_docstring(node, clean=True)

    if not value:
        return None

    first_paragraph = value.split("\n\n", 1)[0]
    normalized = " ".join(first_paragraph.split())

    if len(normalized) <= maximum_length:
        return normalized

    return normalized[: maximum_length - 1].rstrip() + "…"


def expression_text(node: ast.AST | None) -> str:
    if node is None:
        return ""

    try:
        return ast.unparse(node)
    except Exception:
        return "..."


def function_signature(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> str:
    parts: list[str] = []

    positional = (
        list(node.args.posonlyargs)
        + list(node.args.args)
    )

    default_offset = (
        len(positional)
        - len(node.args.defaults)
    )

    for index, argument in enumerate(positional):
        text = argument.arg

        if argument.annotation is not None:
            text += ": " + expression_text(
                argument.annotation
            )

        if index >= default_offset:
            default = node.args.defaults[
                index - default_offset
            ]
            text += " = " + expression_text(default)

        parts.append(text)

    if node.args.vararg is not None:
        vararg = "*" + node.args.vararg.arg

        if node.args.vararg.annotation is not None:
            vararg += ": " + expression_text(
                node.args.vararg.annotation
            )

        parts.append(vararg)
    elif node.args.kwonlyargs:
        parts.append("*")

    for argument, default in zip(
        node.args.kwonlyargs,
        node.args.kw_defaults,
    ):
        text = argument.arg

        if argument.annotation is not None:
            text += ": " + expression_text(
                argument.annotation
            )

        if default is not None:
            text += " = " + expression_text(default)

        parts.append(text)

    if node.args.kwarg is not None:
        kwarg = "**" + node.args.kwarg.arg

        if node.args.kwarg.annotation is not None:
            kwarg += ": " + expression_text(
                node.args.kwarg.annotation
            )

        parts.append(kwarg)

    signature = f"{node.name}({', '.join(parts)})"

    if node.returns is not None:
        signature += " -> " + expression_text(
            node.returns
        )

    return signature


def class_kind(node: ast.ClassDef) -> str:
    decorators = {
        expression_text(decorator)
        for decorator in node.decorator_list
    }

    bases = {
        expression_text(base).split(".")[-1]
        for base in node.bases
    }

    if any(
        decorator == "dataclass"
        or decorator.startswith("dataclass(")
        for decorator in decorators
    ):
        return "dataclass"

    if "Protocol" in bases:
        return "protocol"

    if bases.intersection(
        {"Enum", "IntEnum", "StrEnum"}
    ):
        return "enum"

    return "class"


def collect_class_definitions(
    node: ast.ClassDef,
) -> list[Definition]:
    definitions = [
        Definition(
            name=node.name,
            kind=class_kind(node),
            line=node.lineno,
            signature=node.name,
            docstring=short_docstring(node),
        )
    ]

    for child in node.body:
        if isinstance(
            child,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            kind = (
                "async method"
                if isinstance(
                    child,
                    ast.AsyncFunctionDef,
                )
                else "method"
            )

            definitions.append(
                Definition(
                    name=f"{node.name}.{child.name}",
                    kind=kind,
                    line=child.lineno,
                    signature=function_signature(child),
                    docstring=short_docstring(child),
                )
            )

    return definitions


def parse_module(
    project_root: Path,
    path: Path,
) -> ModuleInfo:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))

    definitions: list[Definition] = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            definitions.extend(
                collect_class_definitions(node)
            )

        elif isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            kind = (
                "async function"
                if isinstance(
                    node,
                    ast.AsyncFunctionDef,
                )
                else "function"
            )

            definitions.append(
                Definition(
                    name=node.name,
                    kind=kind,
                    line=node.lineno,
                    signature=function_signature(node),
                    docstring=short_docstring(node),
                )
            )

    relative_path = path.relative_to(project_root)

    return ModuleInfo(
        path=relative_path,
        lines=len(source.splitlines()),
        docstring=short_docstring(tree),
        definitions=tuple(definitions),
    )


def iter_python_files(
    project_root: Path,
    source_dirs: Iterable[str],
) -> Iterable[Path]:
    for source_dir in source_dirs:
        root = project_root / source_dir

        if not root.exists():
            continue

        for path in sorted(root.rglob("*.py")):
            if any(
                part in DEFAULT_EXCLUDED_DIRS
                for part in path.parts
            ):
                continue

            yield path


def related_test_paths(
    module: ModuleInfo,
    modules: tuple[ModuleInfo, ...],
) -> tuple[Path, ...]:
    if not module.path.parts:
        return ()

    if module.path.parts[0] == "tests":
        return ()

    stem = module.path.stem
    expected_name = f"test_{stem}.py"

    return tuple(
        candidate.path
        for candidate in modules
        if (
            candidate.path.parts
            and candidate.path.parts[0] == "tests"
            and candidate.path.name == expected_name
        )
    )


def render_index(
    modules: tuple[ModuleInfo, ...],
) -> str:
    generated_at = datetime.now(
        timezone.utc
    ).strftime("%Y-%m-%d %H:%M UTC")

    total_lines = sum(
        module.lines for module in modules
    )
    total_definitions = sum(
        len(module.definitions)
        for module in modules
    )
    total_tests = sum(
        1
        for module in modules
        if (
            module.path.parts
            and module.path.parts[0] == "tests"
        )
    )

    lines = [
        "# Карта проекта crypto-bot",
        "",
        "> Файл создан автоматически командой "
        "`python scripts/build_project_index.py`.",
        "> Не редактировать вручную.",
        "",
        f"Обновлено: **{generated_at}**",
        "",
        "## Сводка",
        "",
        f"- Python-файлов: **{len(modules)}**",
        f"- Определений: **{total_definitions}**",
        f"- Строк Python-кода: **{total_lines}**",
        f"- Тестовых модулей: **{total_tests}**",
        "",
        "## Быстрый каталог",
        "",
    ]

    for module in modules:
        lines.append(
            f"- [`{module.path}`](../{module.path})"
            f" — {module.lines} строк, "
            f"{len(module.definitions)} определений"
        )

    grouped: dict[str, list[ModuleInfo]] = {}

    for module in modules:
        top_level = (
            module.path.parts[0]
            if module.path.parts
            else "root"
        )
        grouped.setdefault(
            top_level,
            [],
        ).append(module)

    for group_name, group_modules in grouped.items():
        lines.extend(
            [
                "",
                f"## `{group_name}/`",
                "",
            ]
        )

        for module in group_modules:
            lines.extend(
                [
                    f"### [`{module.path}`](../{module.path})",
                    "",
                    f"Строк: **{module.lines}**",
                ]
            )

            if module.docstring:
                lines.append(
                    f"\n{module.docstring}"
                )

            tests = related_test_paths(
                module,
                modules,
            )

            if tests:
                test_links = ", ".join(
                    f"[`{path}`](../{path})"
                    for path in tests
                )
                lines.append(
                    f"\nСвязанные тесты: {test_links}"
                )

            if not module.definitions:
                lines.extend(
                    [
                        "",
                        "_Публичных классов и функций "
                        "не найдено._",
                    ]
                )
                continue

            lines.extend(
                [
                    "",
                    "| Тип | Определение | Строка | Описание |",
                    "|---|---|---:|---|",
                ]
            )

            for definition in module.definitions:
                signature = (
                    definition.signature
                    .replace("|", r"\|")
                )
                description = (
                    definition.docstring or ""
                ).replace("|", r"\|")

                lines.append(
                    f"| {definition.kind} "
                    f"| `{signature}` "
                    f"| {definition.line} "
                    f"| {description} |"
                )

    lines.extend(
        [
            "",
            "## Правила использования",
            "",
            "Перед добавлением нового класса или модуля:",
            "",
            "1. Найти похожую функциональность "
            "в этой карте.",
            "2. Выполнить поиск по репозиторию.",
            "3. Расширять существующий модуль, "
            "если он уже решает ту же задачу.",
            "4. После изменений обновить карту.",
            "",
        ]
    )

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Создать автоматическую карту "
            "Python-проекта"
        )
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Проверить актуальность карты "
            "без перезаписи"
        ),
    )
    parser.add_argument(
        "--output",
        default="docs/PROJECT_MAP.md",
        help="Путь к итоговому Markdown-файлу",
    )

    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    output_path = project_root / args.output

    modules = tuple(
        parse_module(project_root, path)
        for path in iter_python_files(
            project_root,
            DEFAULT_SOURCE_DIRS,
        )
    )

    content = render_index(modules)

    if args.check:
        if not output_path.exists():
            raise SystemExit(
                f"{output_path.relative_to(project_root)} "
                "не существует"
            )

        current_content = output_path.read_text(
            encoding="utf-8"
        )

        # Дата генерации меняется при каждом запуске.
        # При проверке сравниваем содержимое без строки даты.
        def without_generated_at(value: str) -> list[str]:
            return [
                line
                for line in value.splitlines()
                if not line.startswith("Обновлено:")
            ]

        if without_generated_at(
            current_content
        ) != without_generated_at(content):
            raise SystemExit(
                "Карта проекта устарела. Выполните: "
                "python scripts/build_project_index.py"
            )

        print("Карта проекта актуальна")
        return

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    output_path.write_text(
        content,
        encoding="utf-8",
    )

    print(
        "Карта проекта создана: "
        f"{output_path.relative_to(project_root)}"
    )
    print(f"Python-файлов: {len(modules)}")
    print(
        "Определений: "
        f"{sum(len(item.definitions) for item in modules)}"
    )


if __name__ == "__main__":
    main()
